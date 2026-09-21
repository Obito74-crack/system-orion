"""Tests unitaires pour systemorion.backup (BackupEngine).

Vérifie la conformité avec :
- CDC EF-07 : Copie incrémentale, préservation des métadonnées, pas d'écrasement
- CDC EF-08 : Versioning __YYYYMMDD_HHMM et application de la rétention
- CDC EF-12 : Découplage, transfert atomique (.part -> rename), backoff exponentiel
"""

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from systemorion.backup import (
    BackupEngine,
    NetworkBackoffTracker,
    build_versioned_destination,
    generate_version_tag,
)
from systemorion.models import OrionConfig, TransferState
from systemorion.state import StateDB


@pytest.fixture
def state_db(tmp_path: Path) -> StateDB:
    db = StateDB(tmp_path / "backup_test.db")
    yield db
    db.close()


@pytest.fixture
def config() -> OrionConfig:
    cfg = OrionConfig()
    cfg.retention_max_versions = 2
    cfg.backoff_initial_s = 1
    cfg.backoff_max_s = 10
    return cfg


@pytest.fixture
def engine(state_db: StateDB, config: OrionConfig) -> BackupEngine:
    return BackupEngine(state_db=state_db, config=config)


def test_version_tag_and_destination_builder() -> None:
    """CDC EF-08 : Format __YYYYMMDD_HHMM et intégration dans le chemin."""
    dt = datetime(2026, 9, 8, 14, 30, tzinfo=UTC)
    tag = generate_version_tag(dt)
    assert tag == "__20260908_1430"

    versioned = build_versioned_destination(r"\\srv\share\rapport.docx", tag)
    assert versioned.endswith(r"rapport__20260908_1430.docx")


def test_atomic_file_copy_preserves_mtime(engine: BackupEngine, tmp_path: Path) -> None:
    """CDC EF-07 & EF-12 : Copie atomique et préservation des timestamps."""
    src = tmp_path / "source.txt"
    src.write_text("Hello Orion Backup!", encoding="utf-8")

    # Définition d'un timestamp mtime spécifique
    mtime = time.time() - 3600
    os.utime(src, (mtime, mtime))

    dst = tmp_path / "dest" / "target.txt"
    bytes_copied = engine.copy_file_atomic(str(src), str(dst))

    assert bytes_copied > 0
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == "Hello Orion Backup!"
    assert abs(os.path.getmtime(dst) - mtime) < 2.0


def test_process_transfer_item_lifecycle(engine: BackupEngine, state_db: StateDB, tmp_path: Path) -> None:
    """CDC EF-12 & EF-08 : Cycle de vie d'un transfert avec archivage dans l'historique."""
    src = tmp_path / "doc.txt"
    src.write_text("Contenu important", encoding="utf-8")

    dest = tmp_path / "backup_share" / "doc.txt"

    state_db.enqueue_transfer(str(src), str(dest), file_size=100)
    item = state_db.get_pending_transfers()[0]

    success, copied, err = engine.process_transfer_item(item)
    assert success is True
    assert copied > 0
    assert err is None

    # Vérification que le transfert est DONE dans la base
    counts = state_db.get_queue_counts()
    assert counts[TransferState.DONE.value] == 1

    # Vérification qu'un enregistrement d'historique existe
    history = state_db.get_backup_versions(str(src))
    assert len(history) == 1
    assert os.path.exists(history[0].dest_path)


def test_network_backoff_tracker() -> None:
    """CDC EF-12 : Progression du backoff exponentiel."""
    tracker = NetworkBackoffTracker(initial_delay_s=2.0, max_delay_s=16.0)

    # Échec 1 -> 2s
    d1 = tracker.record_failure()
    assert d1 == 2.0
    assert tracker.is_retry_allowed() is False

    # Échec 2 -> 4s
    d2 = tracker.record_failure()
    assert d2 == 4.0

    # Échec 3 -> 8s
    d3 = tracker.record_failure()
    assert d3 == 8.0

    # Succès -> reset
    tracker.record_success()
    assert tracker.consecutive_failures == 0
    assert tracker.is_retry_allowed() is True


def test_apply_retention_purges_old_files(engine: BackupEngine, state_db: StateDB, tmp_path: Path) -> None:
    """CDC EF-08 : La rétention supprime les versions excédentaires sur disque et en base."""
    src_path = str(tmp_path / "file.dat")
    dest_dir = tmp_path / "archive"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Création de 4 versions physiques et en base (quota = 2)
    files = []
    for i in range(4):
        f = dest_dir / f"file__2026090{i}_1000.dat"
        f.write_text(f"version {i}")
        files.append(f)
        state_db.record_backup(
            source_path=src_path,
            dest_path=str(f),
            file_size=10,
            version_tag=f"__2026090{i}_1000",
        )

    assert len(state_db.get_backup_versions(src_path)) == 4

    pruned = engine.apply_retention()
    assert pruned == 2

    # Doit rester uniquement les 2 versions les plus récentes
    remaining_db = state_db.get_backup_versions(src_path)
    assert len(remaining_db) == 2

    # Les 2 plus anciennes sur disque doivent avoir été supprimées
    assert not files[0].exists()
    assert not files[1].exists()
    assert files[2].exists()
    assert files[3].exists()
