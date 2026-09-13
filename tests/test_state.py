"""Tests unitaires pour systemorion.state (StateDB).

Vérifie la conformité avec :
- CDC ET-01 : SQLite WAL + synchronous=FULL
- CDC EF-12 : Machine à états, files d'attente persistantes, reset COPYING -> PENDING
- CDC EF-08 : Historique et règles de rétention
- CDC EF-04 : Suivi de progression USN et métriques
"""

import threading
from pathlib import Path

import pytest
from systemorion.models import TransferState
from systemorion.state import StateDB


@pytest.fixture
def state_db(tmp_path: Path) -> StateDB:
    """Fixture fournissant une base SQLite temporaire sur disque."""
    db_file = tmp_path / "test_state.db"
    db = StateDB(db_path=db_file)
    yield db
    db.close()


def test_db_initialization_and_pragmas(state_db: StateDB) -> None:
    """Vérifie que la base est initialisée avec les bons PRAGMA selon ET-01."""
    conn = state_db._get_connection()
    cur = conn.cursor()

    # Vérification mode journal
    cur.execute("PRAGMA journal_mode;")
    mode = cur.fetchone()[0].upper()
    assert mode == "WAL"

    # Vérification synchronous
    cur.execute("PRAGMA synchronous;")
    sync = cur.fetchone()[0]
    # 2 = FULL
    assert sync == 2

    # Vérification foreign keys
    cur.execute("PRAGMA foreign_keys;")
    fk = cur.fetchone()[0]
    assert fk == 1


def test_usn_progress_lifecycle(state_db: StateDB) -> None:
    """Vérifie le cycle de vie de la progression USN (EF-04)."""
    # Aucun état initial
    assert state_db.get_usn_progress("C:") is None

    # Sauvegarde initiale
    state_db.set_usn_progress("C:", last_usn=1000, journal_id=9999)
    progress = state_db.get_usn_progress("c:")  # Test insensible à la casse
    assert progress is not None
    assert progress.volume == "C:"
    assert progress.last_usn == 1000
    assert progress.journal_id == 9999

    # Mise à jour (ON CONFLICT DO UPDATE)
    state_db.set_usn_progress("C:", last_usn=2500, journal_id=9999)
    updated = state_db.get_usn_progress("C:")
    assert updated is not None
    assert updated.last_usn == 2500
    assert updated.journal_id == 9999


def test_transfer_queue_state_machine(state_db: StateDB) -> None:
    """Vérifie les transitions de la machine à états des transferts (EF-12)."""
    # 1. Enqueue
    tid = state_db.enqueue_transfer(
        source_path=r"C:\Users\Alice\Documents\report.docx",
        dest_path=r"\\srv\backups\Alice\report.docx",
        file_size=1024,
    )
    assert tid > 0

    pending = state_db.get_pending_transfers()
    assert len(pending) == 1
    assert pending[0].id == tid
    assert pending[0].state == TransferState.PENDING
    assert pending[0].attempt_count == 0

    # 2. PENDING -> COPYING
    state_db.set_transfer_state(tid, TransferState.COPYING)
    assert len(state_db.get_pending_transfers()) == 0

    # 3. COPYING -> DONE
    state_db.set_transfer_state(tid, TransferState.DONE)
    counts = state_db.get_queue_counts()
    assert counts[TransferState.DONE.value] == 1
    assert counts[TransferState.PENDING.value] == 0


def test_reset_copying_to_pending_on_restart(state_db: StateDB) -> None:
    """CDC EF-12 : Au redémarrage, tout fichier en COPYING doit repasser en PENDING."""
    t1 = state_db.enqueue_transfer(r"C:\f1.txt", r"\\srv\f1.txt", 100)
    t2 = state_db.enqueue_transfer(r"C:\f2.txt", r"\\srv\f2.txt", 200)

    # Passage en cours de copie
    state_db.set_transfer_state(t1, TransferState.COPYING)
    state_db.set_transfer_state(t2, TransferState.COPYING)

    assert len(state_db.get_pending_transfers()) == 0

    # Simuler le redémarrage du service
    reverted = state_db.reset_copying_to_pending()
    assert reverted == 2

    # Vérifier qu'ils sont à nouveau éligibles
    pending = state_db.get_pending_transfers()
    assert len(pending) == 2
    assert all(t.state == TransferState.PENDING for t in pending)
    assert all(t.last_error == "Interrompu par arrêt du service" for t in pending)


def test_backup_history_and_retention(state_db: StateDB) -> None:
    """CDC EF-08 : Historique et calcul des versions à élaguer."""
    src = r"C:\data\project.zip"

    # Enregistrer 5 versions successives
    ids = []
    for i in range(5):
        tag = f"__2026090{i}_1200"
        hid = state_db.record_backup(
            source_path=src,
            dest_path=f"\\\\srv\\project{tag}.zip",
            file_size=5000 + i,
            version_tag=tag,
        )
        ids.append(hid)

    versions = state_db.get_backup_versions(src)
    assert len(versions) == 5

    # Règle de rétention : conserver les 3 dernières versions
    prunable = state_db.get_prunable_versions(src, max_versions=3)
    assert len(prunable) == 2  # Les 2 plus anciennes doivent être supprimées

    # Supprimer une ancienne version
    state_db.delete_history_record(prunable[0].id)
    assert len(state_db.get_backup_versions(src)) == 4


def test_usn_metrics_and_summary(state_db: StateDB) -> None:
    """CDC EF-04 : Enregistrement et calcul des métriques d'activité USN."""
    state_db.record_usn_metrics("C:", records_count=150)
    state_db.record_usn_metrics("C:", records_count=250)

    total, rate = state_db.get_usn_activity_summary("C:", window_hours=72)
    assert total == 400
    assert rate == 400 / 72


def test_thread_safety(tmp_path: Path) -> None:
    """Vérifie la robustesse en environnement multithread."""
    db = StateDB(db_path=tmp_path / "concurrent.db")
    errors = []

    def worker(worker_id: int) -> None:
        try:
            for i in range(25):
                src = f"C:\\Users\\User{worker_id}\\file_{i}.dat"
                dst = f"\\\\srv\\share\\file_{worker_id}_{i}.dat"
                tid = db.enqueue_transfer(src, dst, 1024)
                db.set_transfer_state(tid, TransferState.COPYING)
                db.set_transfer_state(tid, TransferState.DONE)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db.close()
    assert len(errors) == 0
