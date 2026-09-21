"""Tests unitaires pour l'interface en ligne de commande (CLI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from systemorion.cli import main


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--help"])
    assert code == 0
    captured = capsys.readouterr()
    assert "systemorion" in captured.out
    assert "status" in captured.out


def test_cli_status(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["status"])
    assert code == 0
    captured = capsys.readouterr()
    assert "System Orion — État du système" in captured.out
    assert "Configuration active" in captured.out


def test_cli_test_ad(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["test-ad", "--mock-home", r"\\SRV-AD01\home$\Utilisateur"])
    assert code == 0
    captured = capsys.readouterr()
    assert "homeDirectory résolu" in captured.out


def test_cli_list_versions(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(["list-versions", str(tmp_path / "doc.txt")])
    assert code == 0
    captured = capsys.readouterr()
    assert "Versions archivées pour" in captured.out


def test_cli_restore_success_and_failure(tmp_path: Path) -> None:
    # Cas fichier inexistant
    code_err = main(["restore", str(tmp_path / "non_existent.txt")])
    assert code_err == 1

    # Cas fichier existant
    backup_file = tmp_path / "doc__20260908_1430.txt"
    backup_file.write_text("Hello backup")
    dest_dir = tmp_path / "restored"
    dest_dir.mkdir()

    code_ok = main(["restore", str(backup_file), "--destination", str(dest_dir)])
    assert code_ok == 0
    assert (dest_dir / "doc.txt").exists()
    assert (dest_dir / "doc.txt").read_text() == "Hello backup"
