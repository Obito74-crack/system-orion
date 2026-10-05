"""Tests unitaires des fonctionnalités avancées (Boss de fin de jeu) :

- Déduplication par fingerprinting de contenu SHA-256 (évite la recopie inutile)
- Parallélisation multi-workers des transferts (haute performance type Robocopy /MT)
"""

from __future__ import annotations

from pathlib import Path

from systemorion.backup import BackupEngine, compute_file_hash
from systemorion.models import OrionConfig, TransferState
from systemorion.state import StateDB
from systemorion.storage_backend import DriveStorageBackend


def test_compute_file_hash(tmp_path: Path) -> None:
    """Vérifie le calcul correct du hash SHA-256 d'un fichier."""
    f = tmp_path / "sample.txt"
    f.write_text("Hello Orion System")
    h1 = compute_file_hash(str(f))
    assert isinstance(h1, str)
    assert len(h1) == 64

    # Même contenu -> même hash
    f2 = tmp_path / "sample2.txt"
    f2.write_text("Hello Orion System")
    assert compute_file_hash(str(f2)) == h1

    # Contenu différent -> hash différent
    f3 = tmp_path / "sample3.txt"
    f3.write_text("Different content")
    assert compute_file_hash(str(f3)) != h1


def test_dedup_by_hash_skips_identical_file(tmp_path: Path) -> None:
    """Un fichier déjà sauvegardé avec contenu identique n'est pas re-transféré."""
    db_file = tmp_path / "test_state.db"
    state_db = StateDB(db_path=db_file)

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source_file = source_dir / "doc.txt"
    source_file.write_text("Version initiale stable")

    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    backend = DriveStorageBackend(dest_dir)

    cfg = OrionConfig(dedup_by_hash=True)
    engine = BackupEngine(state_db=state_db, config=cfg, storage_backend=backend)

    # 1. Première sauvegarde -> transfert effectif
    dest_path = backend.resolve_destination(str(source_file), str(source_dir), "backup")
    rec_id = engine.enqueue_file(str(source_file), dest_path, source_file.stat().st_size)
    item = state_db.get_transfer_record(rec_id)
    assert item is not None

    ok, copied, err = engine.process_transfer_item(item)
    assert ok is True
    assert copied > 0

    # Vérifier l'historique et le hash enregistré
    latest = state_db.get_latest_backup(str(source_file))
    assert latest is not None
    assert latest.content_hash == compute_file_hash(str(source_file))

    # 2. Deuxième tentative avec fichier non altéré -> skip grâce au hash
    rec_id2 = engine.enqueue_file(str(source_file), dest_path, source_file.stat().st_size)
    item2 = state_db.get_transfer_record(rec_id2)
    assert item2 is not None

    ok2, copied2, err2 = engine.process_transfer_item(item2)
    assert ok2 is True
    assert copied2 == 0  # 0 octet transféré grâce à la déduplication !
    assert item2.source_path == str(source_file)
    assert state_db.get_transfer_record(rec_id2).state == TransferState.DONE

    state_db.close()


def test_multi_workers_parallel_transfer(tmp_path: Path) -> None:
    """La file d'attente s'exécute avec succès en mode multi-workers parallèle."""
    db_file = tmp_path / "test_state_workers.db"
    state_db = StateDB(db_path=db_file)

    source_dir = tmp_path / "src_batch"
    source_dir.mkdir()
    dest_dir = tmp_path / "dest_batch"
    dest_dir.mkdir()
    backend = DriveStorageBackend(dest_dir)

    # Créer 10 fichiers sources
    files = []
    for i in range(10):
        f = source_dir / f"file_{i}.txt"
        f.write_text(f"Données de test du fichier numéro {i}")
        files.append(f)

    cfg = OrionConfig(dedup_by_hash=False, max_backup_workers=4)
    engine = BackupEngine(state_db=state_db, config=cfg, storage_backend=backend)

    for f in files:
        dest = backend.resolve_destination(str(f), str(source_dir), "workers_backup")
        engine.enqueue_file(str(f), dest, f.stat().st_size)

    # Exécution avec 4 workers
    stats = engine.process_queue(batch_limit=50, max_workers=4)
    assert stats.files_saved == 10
    assert stats.files_errored == 0
    assert stats.bytes_transferred > 0

    state_db.close()
