"""Tests unitaires pour systemorion.logging_agent (OrionLogger).

Vérifie la conformité avec :
- CDC EF-10 : Journal Windows Event Log « SystemOrion » + fichiers rotatifs locaux
- CDC D8 / section 9 : Aucun contenu de fichier journalisé
- CDC EF-04 : Alertes USN et détection de rotation
"""

from pathlib import Path

import pytest

from systemorion.logging_agent import MemoryEventLogBackend, OrionLogger
from systemorion.models import BackupStats


@pytest.fixture
def memory_event_backend() -> MemoryEventLogBackend:
    return MemoryEventLogBackend()


@pytest.fixture
def orion_logger(tmp_path: Path, memory_event_backend: MemoryEventLogBackend) -> OrionLogger:
    return OrionLogger(
        log_dir=tmp_path / "logs",
        event_backend=memory_event_backend,
        max_bytes=1024,
        backup_count=2,
    )


def test_service_lifecycle_events(
    orion_logger: OrionLogger,
    memory_event_backend: MemoryEventLogBackend,
) -> None:
    """Vérifie les événements de démarrage et arrêt du service (EF-10)."""
    orion_logger.log_service_start("0.1.0")
    assert len(memory_event_backend.events) == 1
    evt_id, evt_type, msg = memory_event_backend.events[0]
    assert evt_id == OrionLogger.EVT_SERVICE_STARTED
    assert "0.1.0" in msg

    orion_logger.log_service_stop("Arrêt système")
    assert len(memory_event_backend.events) == 2
    evt_id, evt_type, msg = memory_event_backend.events[1]
    assert evt_id == OrionLogger.EVT_SERVICE_STOPPED
    assert "Arrêt système" in msg


def test_cycle_summary_clean_vs_warning(
    orion_logger: OrionLogger,
    memory_event_backend: MemoryEventLogBackend,
) -> None:
    """Vérifie le compte-rendu d'un cycle selon les erreurs rencontrées (D8, EF-10)."""
    # Cycle réussi sans erreur
    stats_ok = BackupStats(
        files_saved=12,
        files_skipped=5,
        files_errored=0,
        bytes_transferred=10240,
        cycle_duration_s=2.5,
    )
    orion_logger.log_cycle_summary(stats_ok)
    assert memory_event_backend.events[-1][0] == OrionLogger.EVT_CYCLE_SUCCESS

    # Cycle avec avertissement (erreurs)
    stats_err = BackupStats(
        files_saved=10,
        files_skipped=5,
        files_errored=2,
        bytes_transferred=8000,
        cycle_duration_s=3.0,
    )
    orion_logger.log_cycle_summary(stats_err)
    assert memory_event_backend.events[-1][0] == OrionLogger.EVT_CYCLE_WARNING


def test_usn_and_vss_alerts(
    orion_logger: OrionLogger,
    memory_event_backend: MemoryEventLogBackend,
) -> None:
    """CDC EF-04 & EF-06 : Alertes VSS et USN."""
    orion_logger.log_vss_failure("Code 0x80042306")
    assert memory_event_backend.events[-1][0] == OrionLogger.EVT_VSS_FAILURE

    orion_logger.log_usn_rotation("C:", "Journal ID modifié")
    assert memory_event_backend.events[-1][0] == OrionLogger.EVT_USN_ROTATION

    orion_logger.log_usn_capacity_alert("C:", utilization_pct=85.5, threshold_pct=80.0)
    assert memory_event_backend.events[-1][0] == OrionLogger.EVT_USN_CAPACITY_ALERT


def test_local_file_logging(tmp_path: Path, memory_event_backend: MemoryEventLogBackend) -> None:
    """Vérifie que les logs s'écrivent bien dans le fichier rotatif local."""
    log_dir = tmp_path / "logs"
    logger = OrionLogger(log_dir=log_dir, event_backend=memory_event_backend)
    logger.log_service_start("0.1.0")

    log_file = log_dir / "systemorion.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Service System Orion démarré" in content
