"""Résolution Active Directory et impersonnification utilisateur (EF-03, D5, D6).

Gère :
- La découverte de l'espace cible AD de l'utilisateur connecté (attribut homeDirectory via ADSI/WinNT).
- La construction du chemin UNC standard : <homeDirectory>\\SystemOrion\\<NomPoste>\\<Relatif>.
- L'isolation de session (Session 0) : interdiction des lettres de lecteurs, utilisation stricte d'UNC.
- L'emprunt d'identité (D6) : context manager UserImpersonation basé sur
  WTSQueryUserToken + ImpersonateLoggedOnUser et RevertToSelf garanti.
- Abstraction injectable pour testabilité complète hors environnement Active Directory.
"""

from __future__ import annotations

import logging
import platform
import sys
from abc import ABC, abstractmethod
from pathlib import PureWindowsPath
from typing import Any

from systemorion.models import AdResolutionError, ImpersonationError

logger = logging.getLogger("systemorion.cible_ad")


class AdDirectoryResolver(ABC):
    """Interface pour interroger Active Directory sur les attributs utilisateur."""

    @abstractmethod
    def get_user_home_directory(self, domain: str, username: str) -> str | None:
        """Retourne le chemin UNC homeDirectory de l'utilisateur ou None si non renseigné."""
        ...


class AdsiDirectoryResolver(AdDirectoryResolver):
    """Implémentation concrète utilisant ADSI via win32com sous Windows (ET-01)."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise AdResolutionError("AdsiDirectoryResolver n'est supporté que sous Windows.")
        import win32com.client  # type: ignore

        self._client = win32com.client

    def get_user_home_directory(self, domain: str, username: str) -> str | None:
        try:
            # Recherche via le fournisseur WinNT ou LDAP
            ads_path = f"WinNT://{domain}/{username},user"
            user_obj = self._client.GetObject(ads_path)
            home_dir = getattr(user_obj, "HomeDirectory", None)
            if home_dir and str(home_dir).strip():
                return str(home_dir).strip()
            return None
        except Exception as e:
            logger.warning("Échec résolution ADSI pour %s\\%s: %s", domain, username, e)
            return None


class MockAdDirectoryResolver(AdDirectoryResolver):
    """Backend de simulation Active Directory pour les tests."""

    def __init__(self, user_directories: dict[str, str] | None = None) -> None:
        self.user_directories = user_directories or {}

    def get_user_home_directory(self, domain: str, username: str) -> str | None:
        key = f"{domain}\\{username}".lower()
        return self.user_directories.get(key) or self.user_directories.get(username.lower())


class ImpersonationBackend(ABC):
    """Interface d'emprunt d'identité utilisateur (D6)."""

    @abstractmethod
    def impersonate_user(self, session_id: int) -> Any:
        """Obtient le jeton utilisateur et applique l'impersonnification."""
        ...

    @abstractmethod
    def revert_to_self(self, token_handle: Any) -> None:
        """Rétablit les privilèges du compte SYSTEM."""
        ...

    @abstractmethod
    def get_active_session_id(self) -> int | None:
        """Retourne l'ID de la session interactive courante (console ou RDP)."""
        ...


class Win32ImpersonationBackend(ImpersonationBackend):
    """Backend natif Windows utilisant WTSQueryUserToken et ImpersonateLoggedOnUser."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ImpersonationError("Win32ImpersonationBackend n'est supporté que sous Windows.")
        import win32security  # type: ignore
        import win32ts  # type: ignore

        self._win32sec = win32security
        self._win32ts = win32ts

    def get_active_session_id(self) -> int | None:
        try:
            # Récupère l'ID de la session console active
            session_id = self._win32ts.WTSGetActiveConsoleSessionId()
            if session_id == 0xFFFFFFFF:
                return None
            return session_id
        except Exception:
            return None

    def impersonate_user(self, session_id: int) -> Any:
        try:
            # Requiert le privilège SeTcbPrivilege détenu par le compte SYSTEM (D1)
            token = self._win32ts.WTSQueryUserToken(session_id)
            self._win32sec.ImpersonateLoggedOnUser(token)
            return token
        except Exception as e:
            raise ImpersonationError(
                f"Impossible d'emprunter l'identité de la session {session_id}: {e}"
            ) from e

    def revert_to_self(self, token_handle: Any) -> None:
        try:
            self._win32sec.RevertToSelf()
        finally:
            if token_handle:
                try:
                    token_handle.Close()
                except Exception:
                    pass


class MockImpersonationBackend(ImpersonationBackend):
    """Backend de simulation pour les tests."""

    def __init__(self, active_session: int | None = 1) -> None:
        self.active_session = active_session
        self.is_impersonating = False
        self.impersonated_sessions: list[int] = []

    def get_active_session_id(self) -> int | None:
        return self.active_session

    def impersonate_user(self, session_id: int) -> Any:
        self.is_impersonating = True
        self.impersonated_sessions.append(session_id)
        return "mock_token"

    def revert_to_self(self, token_handle: Any) -> None:
        self.is_impersonating = False


class UserImpersonation:
    """Gestionnaire de contexte pour l'emprunt d'identité utilisateur (CDC D6).

    Garantit le retour aux privilèges SYSTEM (RevertToSelf) quoi qu'il arrive.
    """

    def __init__(
        self,
        session_id: int | None = None,
        backend: ImpersonationBackend | None = None,
    ) -> None:
        if backend is not None:
            self.backend = backend
        elif sys.platform == "win32":
            self.backend = Win32ImpersonationBackend()
        else:
            self.backend = MockImpersonationBackend()

        self.session_id = session_id or self.backend.get_active_session_id()
        self._token: Any = None

    def __enter__(self) -> UserImpersonation:
        if self.session_id is None:
            raise ImpersonationError("Aucune session utilisateur active détectée sur le poste.")
        self._token = self.backend.impersonate_user(self.session_id)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if self._token is not None:
                self.backend.revert_to_self(self._token)
        finally:
            self._token = None


def resolve_backup_destination(
    source_file_path: str,
    base_target_path: str,
    user_home_dir: str,
    computer_name: str | None = None,
    subfolder_name: str = "SystemOrion",
) -> str:
    r"""Construit le chemin UNC absolu de destination pour un fichier source (CDC EF-03).

    Règle EF-03 : <homeDirectory>\SystemOrion\<NomPoste>\<CheminRelatif>
    Interdiction absolue des lettres de lecteurs (Session 0, section 8).
    """
    if not user_home_dir or not user_home_dir.startswith(r"\\"):
        raise AdResolutionError(
            f"Chemin cible invalide '{user_home_dir}'. Un chemin UNC (\\\\serveur\\partage) est obligatoire."
        )

    host_name = computer_name or platform.node()

    # Calcul du chemin relatif par rapport à la racine cible source
    src_pure = PureWindowsPath(source_file_path)
    base_pure = PureWindowsPath(base_target_path)

    try:
        rel_path = src_pure.relative_to(base_pure)
    except ValueError:
        # Si non relatif directement, conserver le nom du dossier parent et du fichier
        rel_path = PureWindowsPath(src_pure.name)

    # Assemblage UNC standardisé
    dest_path = PureWindowsPath(user_home_dir) / subfolder_name / host_name / rel_path
    return str(dest_path)
