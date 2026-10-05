"""Abstraction des backends de stockage de sauvegarde (SMB / Drive).

Deux backends sont fournis :
- ``SmbStorageBackend``   : partage réseau SMB (production Windows, D5).
- ``DriveStorageBackend`` : dossier local synchronisé (Google Drive, OneDrive,
                             Nextcloud...) utilisé pour tester sur Linux/macOS.

L'interface unique permet au moteur de sauvegarde de rester indépendant du
protocole de stockage sous-jacent.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path, PureWindowsPath

logger = logging.getLogger("systemorion.storage")


class StorageBackend(ABC):
    """Interface commune aux backends de stockage."""

    name: str = "abstract"

    @abstractmethod
    def resolve_destination(self, source_path: str, base_target: str, subfolder: str) -> str:
        """Retourne le chemin de destination final pour un fichier source."""
        ...

    @abstractmethod
    def ensure_directory(self, path: str) -> None:
        """Crée le répertoire cible si nécessaire."""
        ...

    @abstractmethod
    def remove_file(self, path: str) -> None:
        """Supprime un fichier (rétention)."""
        ...

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Vérifie l'existence d'un fichier."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Vérifie que le backend est disponible (chemin cible joignable)."""
        ...

    @property
    @abstractmethod
    def root_hint(self) -> str:
        """Retourne une représentation lisible du chemin racine."""
        ...


class SmbStorageBackend(StorageBackend):
    """Backend SMB pour la production Windows (CDC D5, EF-03).

    Les chemins sont au format UNC absolu (``\\\\serveur\\partage\\...``).
    Les opérations de création/suppression de fichiers sont déléguées aux
    fonctions natives du système (``os.makedirs``, ``os.remove``).
    """

    name = "smb"

    def __init__(self, unc_root: str) -> None:
        if not unc_root.startswith(r"\\"):
            raise ValueError(f"Le chemin SMB doit être UNC (commencer par \\\\): {unc_root}")
        self._root = unc_root

    @property
    def root_hint(self) -> str:
        return self._root

    def resolve_destination(self, source_path: str, base_target: str, subfolder: str) -> str:
        src = PureWindowsPath(source_path)
        base = PureWindowsPath(base_target)
        try:
            rel = src.relative_to(base)
        except ValueError:
            rel = PureWindowsPath(src.name)
        return str(PureWindowsPath(self._root) / subfolder / rel)

    def ensure_directory(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def remove_file(self, path: str) -> None:
        os.remove(path)

    def file_exists(self, path: str) -> bool:
        return os.path.isfile(path)

    def is_available(self) -> bool:
        return os.path.isdir(self._root)


class DriveStorageBackend(StorageBackend):
    """Backend Drive (dossier synchronisé local) pour tests Linux/macOS.

    Simule un partage réseau via un dossier local (ex. ``~/GoogleDrive/`` ou
    ``~/Nextcloud/``). Les chemins sont natifs de la plateforme hôte.
    """

    name = "drive"

    def __init__(self, local_root: str | Path) -> None:
        self._root = Path(local_root).expanduser().resolve()

    @property
    def root_hint(self) -> str:
        return str(self._root)

    def resolve_destination(self, source_path: str, base_target: str, subfolder: str) -> str:
        src = Path(source_path)
        base = Path(base_target)
        try:
            rel = src.relative_to(base)
        except ValueError:
            rel = Path(src.name)
        return str(self._root / subfolder / rel)

    def ensure_directory(self, path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    def remove_file(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)

    def file_exists(self, path: str) -> bool:
        return Path(path).is_file()

    def is_available(self) -> bool:
        return self._root.is_dir()


def create_backend(
    storage_type: str,
    unc_override: str | None = None,
    drive_path: str | None = None,
) -> StorageBackend:
    """Fabrique le backend de stockage approprié selon la configuration.

    Priorité :
    1. ``drive`` explicite (tests Linux/macOS)
    2. ``smb`` avec ``unc_override`` si fourni
    3. ``smb`` avec chemin par défaut (Windows production)
    """
    if storage_type == "drive":
        if not drive_path:
            raise ValueError("DriveStorageBackend nécessite un drive_path non vide")
        return DriveStorageBackend(drive_path)

    if storage_type == "smb":
        if unc_override:
            return SmbStorageBackend(unc_override)
        # Chemin par défaut Windows production (EF-03)
        return SmbStorageBackend(r"\\serveur\partage$")

    raise ValueError(f"Type de stockage inconnu: {storage_type!r} (attendu 'smb' ou 'drive')")
