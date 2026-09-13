"""Tests unitaires pour systemorion.cible_ad (Active Directory et impersonnification).

Vérifie la conformité avec :
- CDC EF-03 : Découverte de la cible réseau Active Directory (homeDirectory)
- CDC D6 : Impersonnification utilisateur pour les droits SMB
- CDC Section 8 : Chemins UNC obligatoires, pas de lettre de lecteur en Session 0
"""

import pytest
from systemorion.cible_ad import (
    MockAdDirectoryResolver,
    MockImpersonationBackend,
    UserImpersonation,
    resolve_backup_destination,
)
from systemorion.models import AdResolutionError, ImpersonationError


def test_ad_resolver_directory_found() -> None:
    """Vérifie la résolution du chemin homeDirectory pour un utilisateur."""
    resolver = MockAdDirectoryResolver(
        user_directories={
            r"corp\alice": r"\\fileserver.corp.local\users$\alice",
        }
    )
    home = resolver.get_user_home_directory("corp", "alice")
    assert home == r"\\fileserver.corp.local\users$\alice"


def test_ad_resolver_directory_missing() -> None:
    """CDC EF-03 : Si l'attribut est absent, renvoyer None."""
    resolver = MockAdDirectoryResolver()
    home = resolver.get_user_home_directory("corp", "inconnu")
    assert home is None


def test_resolve_backup_destination_unc() -> None:
    """CDC EF-03 : Construction du chemin <homeDirectory>\\SystemOrion\\<NomPoste>\\..."""
    dest = resolve_backup_destination(
        source_file_path=r"C:\Users\Alice\Documents\Finance\budget.xlsx",
        base_target_path=r"C:\Users\Alice\Documents",
        user_home_dir=r"\\srv\home\alice",
        computer_name="PC-FINANCE-01",
        subfolder_name="SystemOrion",
    )
    # Vérification composition du chemin
    assert dest.startswith(r"\\srv\home\alice\SystemOrion\PC-FINANCE-01")
    assert dest.endswith(r"Finance\budget.xlsx")


def test_reject_drive_letter_in_home_directory() -> None:
    """CDC Section 8 : Rejet strict des lettres de lecteurs (isolement Session 0)."""
    with pytest.raises(AdResolutionError, match="Un chemin UNC"):
        resolve_backup_destination(
            source_file_path=r"C:\Users\Alice\doc.txt",
            base_target_path=r"C:\Users\Alice",
            user_home_dir=r"U:\alice",  # Lettre de lecteur interdite
            computer_name="PC01",
        )


def test_user_impersonation_lifecycle() -> None:
    """CDC D6 : Impersonnification utilisateur avec restauration garantie."""
    backend = MockImpersonationBackend(active_session=2)

    assert backend.is_impersonating is False

    with UserImpersonation(session_id=2, backend=backend):
        assert backend.is_impersonating is True
        assert backend.impersonated_sessions == [2]

    # RevertToSelf à la sortie
    assert backend.is_impersonating is False


def test_user_impersonation_reverts_on_error() -> None:
    """CDC D6 : Restauration des privilèges SYSTEM même en cas d'exception."""
    backend = MockImpersonationBackend(active_session=1)

    with pytest.raises(RuntimeError):
        with UserImpersonation(session_id=1, backend=backend):
            assert backend.is_impersonating is True
            raise RuntimeError("Erreur réseau pendant la copie")

    assert backend.is_impersonating is False


def test_user_impersonation_no_session_raises() -> None:
    """Si aucune session interactive n'existe, lever une ImpersonationError."""
    backend = MockImpersonationBackend(active_session=None)
    with pytest.raises(ImpersonationError, match="Aucune session"):
        with UserImpersonation(session_id=None, backend=backend):
            pass
