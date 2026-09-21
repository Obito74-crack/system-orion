"""Tests unitaires pour systemorion.service (OrionServiceRunner).

Vérifie la conformité avec :
- CDC ET-03 : Cycle de fonctionnement complet (démarrage -> détection -> transfert -> maintenance -> arrêt)
- CDC D1 : Service autonome silencieux
- CDC EF-12 : Reprise et robustesse
"""

from pathlib import Path

import pytest

from systemorion.cible_ad import MockAdDirectoryResolver, MockImpersonationBackend
from systemorion.config import ConfigManager, DictRegistryBackend
from systemorion.journal_usn import MockUsnIoctlBackend
from systemorion.logging_agent import MemoryEventLogBackend, OrionLogger
from systemorion.models import OrionConfig, TransferState
from systemorion.service import OrionServiceRunner
from systemorion.state import StateDB
from systemorion.vss import MockVssBackend


@pytest.fixture
def test_environment(tmp_path: Path):
    """Prépare un environnement isolé avec tous les backends mockés."""
    cfg = OrionConfig()
    cfg.state_db_path = str(tmp_path / "service_test.db")
    cfg.log_dir = str(tmp_path / "logs")
    cfg.target_paths = [str(tmp_path / "Documents")]

    reg_backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=reg_backend)

    event_backend = MemoryEventLogBackend()
    orion_logger = OrionLogger(log_dir=cfg.log_dir, event_backend=event_backend)
    state_db = StateDB(cfg.state_db_path)

    ad_resolver = MockAdDirectoryResolver(
        user_directories={"testuser": r"\\srv\home\testuser"}
    )
    impersonation_backend = MockImpersonationBackend(active_session=1)
    usn_backend = MockUsnIoctlBackend()
    vss_backend = MockVssBackend()

    runner = OrionServiceRunner(
        config=cfg,
        config_mgr=cfg_mgr,
        state_db=state_db,
        orion_logger=orion_logger,
        ad_resolver=ad_resolver,
        impersonation_backend=impersonation_backend,
        usn_backend=usn_backend,
        vss_backend=vss_backend,
    )

    yield runner, state_db, event_backend, tmp_path
    runner.shutdown()


def test_service_start_init(test_environment) -> None:
    """CDC ET-03 : Initialisation au démarrage et réinitialisation des transferts orphelins."""
    runner, state_db, event_backend, _ = test_environment

    # Simuler un transfert interrompu en état COPYING
    tid = state_db.enqueue_transfer(r"C:\interrompu.txt", r"\\srv\interrompu.txt", 500)
    state_db.set_transfer_state(tid, TransferState.COPYING)

    runner.start_init()

    # Le transfert doit avoir été remis en PENDING (EF-12)
    pending = state_db.get_pending_transfers()
    assert len(pending) == 1
    assert pending[0].state == TransferState.PENDING

    # L'événement de démarrage doit avoir été consigné
    assert any(evt[0] == OrionLogger.EVT_SERVICE_STARTED for evt in event_backend.events)


def test_service_full_cycle_execution(test_environment) -> None:
    """CDC ET-03 : Exécution d'un cycle complet (détection -> transfert -> maintenance)."""
    runner, state_db, event_backend, tmp_path = test_environment

    # Préparation d'un fichier source et ajout en file
    doc_dir = tmp_path / "Documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    src_file = doc_dir / "rapport.txt"
    src_file.write_text("Données de test", encoding="utf-8")

    dst_file = str(tmp_path / "share" / "rapport.txt")
    state_db.enqueue_transfer(str(src_file), dst_file, 100)

    runner.start_init()
    stats = runner.run_cycle()

    # Le fichier doit avoir été sauvegardé avec succès
    assert stats.files_saved == 1
    assert stats.files_errored == 0

    # Vérification que le transfert est DONE
    counts = state_db.get_queue_counts()
    assert counts[TransferState.DONE.value] == 1


def test_service_graceful_shutdown(test_environment) -> None:
    """Vérifie l'arrêt propre et la libération des ressources."""
    runner, _, event_backend, _ = test_environment

    runner.stop()
    assert runner.stop_event.is_set()

    runner.shutdown()
    assert any(evt[0] == OrionLogger.EVT_SERVICE_STOPPED for evt in event_backend.events)
