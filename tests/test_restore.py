"""Tests unitaires pour le module d'assistance à la restauration (EF-09+)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from systemorion.restore import (
    RestoreError,
    clean_version_tag_from_filename,
    extract_version_timestamp,
    find_backup_versions,
    restore_file,
)
from systemorion.state import StateDB


def test_version_tag_parsing_and_cleaning() -> None:
    filename = "synthese_financiere__20260908_1430.xlsx"
    ts = extract_version_timestamp(filename)
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 9
    assert ts.day == 8
    assert ts.hour == 14
    assert ts.minute == 30

    cleaned = clean_version_tag_from_filename(filename)
    assert cleaned == "synthese_financiere.xlsx"

    # Fichier sans tag
    assert extract_version_timestamp("document_simple.txt") is None
    assert clean_version_tag_from_filename("document_simple.txt") == "document_simple.txt"


def test_find_backup_versions_from_db_and_filesystem(tmp_path: Path) -> None:
    db_file = tmp_path / "state.db"
    state_db = StateDB(str(db_file))

    source_path = str(tmp_path / "data" / "rapport.docx")
    dest_dir = tmp_path / "backup_server"
    dest_dir.mkdir(parents=True)

    dest_v1 = str(dest_dir / "rapport__20260901_1000.docx")
    dest_v2 = str(dest_dir / "rapport__20260902_1200.docx")

    Path(dest_v1).write_text("Version 1 content")
    Path(dest_v2).write_text("Version 2 updated content")

    state_db.record_backup(
        source_path=source_path,
        dest_path=dest_v1,
        file_size=len("Version 1 content"),
        version_tag="__20260901_1000",
    )
    state_db.record_backup(
        source_path=source_path,
        dest_path=dest_v2,
        file_size=len("Version 2 updated content"),
        version_tag="__20260902_1200",
    )

    # Détection via base de données et dossier réseau
    versions = find_backup_versions(source_path, state_db=state_db, backup_search_dir=str(dest_dir))
    assert len(versions) == 2
    assert versions[0].dest_path == dest_v2
    assert versions[1].dest_path == dest_v1

    state_db.close()


def test_restore_file_normal_and_no_overwrite(tmp_path: Path) -> None:
    source_backup = tmp_path / "partage" / "devis__20260910_1500.pdf"
    source_backup.parent.mkdir(parents=True)
    source_backup.write_text("Contenu devis PDF valide")

    dest_folder = tmp_path / "restauration"
    dest_folder.mkdir(parents=True)

    # Première restauration dans un dossier cible
    res1 = restore_file(str(source_backup), str(dest_folder), overwrite=False)
    assert os.path.exists(res1.restored_path)
    assert Path(res1.restored_path).name == "devis.pdf"
    assert Path(res1.restored_path).read_text() == "Contenu devis PDF valide"
    assert res1.version_timestamp is not None
    assert res1.version_timestamp.year == 2026

    # Deuxième restauration sans écrasement -> génère devis.restored.pdf
    res2 = restore_file(str(source_backup), str(dest_folder), overwrite=False)
    assert os.path.exists(res2.restored_path)
    assert Path(res2.restored_path).name == "devis.restored.pdf"

    # Restauration avec overwrite=True vers le même fichier
    res3 = restore_file(str(source_backup), str(res1.restored_path), overwrite=True)
    assert res3.restored_path == res1.restored_path


def test_restore_file_non_existent_raises(tmp_path: Path) -> None:
    non_existent = str(tmp_path / "introuvable.docx")
    with pytest.raises(RestoreError, match="n'existe pas"):
        restore_file(non_existent, str(tmp_path))
