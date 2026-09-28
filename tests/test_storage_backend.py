"""Tests pour le module storage_backend (SMB / Drive).

Vérifie :
- La création des backends selon le type configuré
- La résolution des chemins de destination
- Les opérations fichiers (ensure_directory, remove_file, file_exists)
- La fabrique create_backend() avec ses erreurs
"""

import os
from pathlib import Path

import pytest

from systemorion.storage_backend import (
    DriveStorageBackend,
    SmbStorageBackend,
    create_backend,
)


class TestSmbStorageBackend:
    """Tests du backend SMB (production Windows)."""

    def test_create_with_valid_unc(self) -> None:
        backend = SmbStorageBackend(r"\\serveur\partage$")
        assert backend.name == "smb"
        assert backend.root_hint == r"\\serveur\partage$"

    def test_create_with_invalid_path_raises(self) -> None:
        with pytest.raises(ValueError, match="UNC"):
            SmbStorageBackend("/chemin/invalide")

    def test_resolve_destination(self) -> None:
        backend = SmbStorageBackend(r"\\serveur\partage$")
        dest = backend.resolve_destination(
            r"C:\Users\alice\Documents\rapport.docx",
            r"C:\Users\alice\Documents",
            "SystemOrion",
        )
        assert dest == r"\\serveur\partage$\SystemOrion\rapport.docx"

    def test_resolve_destination_outside_base(self) -> None:
        backend = SmbStorageBackend(r"\\serveur\partage$")
        dest = backend.resolve_destination(
            r"D:\autre\fichier.txt",
            r"C:\Users\alice",
            "SystemOrion",
        )
        assert dest == r"\\serveur\partage$\SystemOrion\fichier.txt"

    def test_is_available_false_when_missing(self) -> None:
        backend = SmbStorageBackend(r"\\nonexistent\partage")
        assert backend.is_available() is False


class TestDriveStorageBackend:
    """Tests du backend Drive (dossier synchronisé local)."""

    def test_create_with_path(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(str(tmp_path))
        assert backend.name == "drive"
        assert backend.root_hint == str(tmp_path)

    def test_create_with_tilde(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        backend = DriveStorageBackend("~/DriveTest")
        assert str(tmp_path) in backend.root_hint

    def test_resolve_destination(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        dest = backend.resolve_destination(
            str(tmp_path / "Documents" / "rapport.docx"),
            str(tmp_path / "Documents"),
            "SystemOrion",
        )
        expected = tmp_path / "SystemOrion" / "rapport.docx"
        assert dest == str(expected)

    def test_resolve_destination_outside_base(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        dest = backend.resolve_destination(
            "/autre/chemin/fichier.txt",
            str(tmp_path),
            "SystemOrion",
        )
        expected = tmp_path / "SystemOrion" / "fichier.txt"
        assert dest == str(expected)

    def test_ensure_directory(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        target = str(tmp_path / "a" / "b" / "c")
        backend.ensure_directory(target)
        assert os.path.isdir(target)

    def test_remove_file(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        f = tmp_path / "fichier.txt"
        f.write_text("contenu")
        assert f.exists()
        backend.remove_file(str(f))
        assert not f.exists()

    def test_remove_file_not_exists_no_error(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        backend.remove_file(str(tmp_path / "inexistent.txt"))  # pas d'erreur

    def test_file_exists(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        f = tmp_path / "test.txt"
        assert backend.file_exists(str(f)) is False
        f.write_text("data")
        assert backend.file_exists(str(f)) is True

    def test_is_available_true(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path)
        assert backend.is_available() is True

    def test_is_available_false(self, tmp_path: Path) -> None:
        backend = DriveStorageBackend(tmp_path / "inexistant")
        assert backend.is_available() is False


class TestCreateBackend:
    """Tests de la fabrique create_backend()."""

    def test_create_smb_with_override(self) -> None:
        backend = create_backend("smb", unc_override=r"\\srv\backup")
        assert isinstance(backend, SmbStorageBackend)
        assert backend.root_hint == r"\\srv\backup"

    def test_create_smb_default(self) -> None:
        backend = create_backend("smb")
        assert isinstance(backend, SmbStorageBackend)
        assert backend.root_hint == r"\\serveur\partage$"

    def test_create_drive(self, tmp_path: Path) -> None:
        backend = create_backend("drive", drive_path=str(tmp_path))
        assert isinstance(backend, DriveStorageBackend)
        assert backend.root_hint == str(tmp_path)

    def test_create_drive_without_path_raises(self) -> None:
        with pytest.raises(ValueError, match="drive_path"):
            create_backend("drive")

    def test_create_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="inconnu"):
            create_backend("ftp")
