"""Journalisation et supervision locale (EF-10).

Journal Windows (Event Log) dédié « SystemOrion » + fichiers rotatifs locaux.
Conformité stricte D8 / section 9 : AUCUN contenu de fichier journalisé —
uniquement les métadonnées (chemins, compteurs, horodatages, codes d'erreur).
Testable hors Windows grâce à l'abstraction du backend Event Log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from systemorion.models import BackupStats

LOGGER_NAME = "systemorion"
EVENT_SOURCE = "SystemOrion"


class EventLogBackend:
    """Interface pour l'écriture dans l'Event Log Windows."""

    def report_event(self, event_id: int, event_type: int, message: str) -> None:
        raise NotImplementedError


class Win32EventLogBackend(EventLogBackend):
    """Backend natif Windows utilisant win32evtlogutil."""

    EVENTLOG_SUCCESS = 0
    EVENTLOG_ERROR_TYPE = 1
    EVENTLOG_WARNING_TYPE = 2
    EVENTLOG_INFORMATION_TYPE = 4

    def __init__(self, source_name: str = EVENT_SOURCE) -> None:
        self.source_name = source_name
        import win32evtlogutil  # type: ignore

        self._win32evt = win32evtlogutil

    def report_event(self, event_id: int, event_type: int, message: str) -> None:
        try:
            self._win32evt.ReportEvent(
                self.source_name,
                event_id,
                eventType=event_type,
                strings=[message],
            )
        except Exception as e:
            # Ne jamais faire planter le service si l'Event Log refuse un message
            logging.getLogger(LOGGER_NAME).error("Erreur écriture Event Log: %s", e)


class MemoryEventLogBackend(EventLogBackend):
    """Backend en mémoire pour les tests et plateformes hors Windows."""

    def __init__(self) -> None:
        self.events: list[tuple[int, int, str]] = []

    def report_event(self, event_id: int, event_type: int, message: str) -> None:
        self.events.append((event_id, event_type, message))


class OrionLogger:
    """Superviseur de journalisation pour System Orion (EF-10).

    Gère simultanément :
    1. Le logger Python avec fichiers rotatifs locaux (C:\\ProgramData\\SystemOrion\\logs\\systemorion.log).
    2. L'Event Log Windows pour la supervision administrateur / SIEM.
    """

    # Identifiants d'événements Event Log standardisés (EF-10)
    EVT_SERVICE_STARTED = 1001
    EVT_SERVICE_STOPPED = 1002
    EVT_CYCLE_SUCCESS = 2001
    EVT_CYCLE_WARNING = 2002
    EVT_VSS_FAILURE = 3001
    EVT_USN_ROTATION = 3002
    EVT_USN_CAPACITY_ALERT = 3003
    EVT_DISK_SPACE_ALERT = 3004
    EVT_NETWORK_ERROR = 3005

    def __init__(
        self,
        log_dir: Path | str = r"C:\ProgramData\SystemOrion\logs",
        event_backend: EventLogBackend | None = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10 Mo par fichier
        backup_count: int = 5,
        console: bool = False,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.logger = logging.getLogger(LOGGER_NAME)
        self.logger.setLevel(logging.INFO)
        self._setup_local_handlers(max_bytes, backup_count, console)

        if event_backend is not None:
            self.event_backend = event_backend
        elif sys.platform == "win32":
            try:
                self.event_backend = Win32EventLogBackend()
            except Exception:
                self.event_backend = MemoryEventLogBackend()
        else:
            self.event_backend = MemoryEventLogBackend()

    def _setup_local_handlers(self, max_bytes: int, backup_count: int, console: bool) -> None:
        """Configure les handlers de fichiers rotatifs locaux."""
        # Éviter d'empiler des handlers si réinstancié
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / "systemorion.log"
            file_handler = RotatingFileHandler(
                str(log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except (OSError, PermissionError) as e:
            # Fallback en console si impossible d'écrire dans ProgramData
            sys.stderr.write(f"Impossible de configurer le fichier de log: {e}\n")

        if console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    # -----------------------------------------------------------------------
    # Événements métier (EF-10)
    # -----------------------------------------------------------------------

    def log_service_start(self, version: str) -> None:
        msg = f"Service System Orion démarré avec succès (version {version})."
        self.logger.info(msg)
        self.event_backend.report_event(self.EVT_SERVICE_STARTED, 4, msg)

    def log_service_stop(self, reason: str = "Demande administrateur") -> None:
        msg = f"Service System Orion arrêté. Raison: {reason}."
        self.logger.info(msg)
        self.event_backend.report_event(self.EVT_SERVICE_STOPPED, 4, msg)

    def log_cycle_summary(self, stats: BackupStats) -> None:
        """Consigne la fin d'un cycle de sauvegarde avec compteurs (D8)."""
        msg = (
            f"Cycle de sauvegarde terminé en {stats.cycle_duration_s:.1f}s: "
            f"{stats.files_saved} fichiers sauvegardés ({stats.bytes_transferred} octets), "
            f"{stats.files_skipped} ignorés, {stats.files_errored} erreurs."
        )
        if stats.files_errored > 0:
            self.logger.warning(msg)
            self.event_backend.report_event(self.EVT_CYCLE_WARNING, 2, msg)
        else:
            self.logger.info(msg)
            self.event_backend.report_event(self.EVT_CYCLE_SUCCESS, 4, msg)

    def log_vss_failure(self, error: str) -> None:
        msg = f"Échec de création du cliché instantané VSS: {error}. Repli sur copie directe avec retry."
        self.logger.warning(msg)
        self.event_backend.report_event(self.EVT_VSS_FAILURE, 2, msg)

    def log_usn_rotation(self, volume: str, reason: str) -> None:
        """CDC EF-04 : Rotation de journal détectée, déclenchement sauvegarde de référence."""
        msg = (
            f"Rotation du journal USN détectée sur {volume}: {reason}. Déclenchement sauvegarde complète de référence."
        )
        self.logger.error(msg)
        self.event_backend.report_event(self.EVT_USN_ROTATION, 1, msg)

    def log_usn_capacity_alert(self, volume: str, utilization_pct: float, threshold_pct: float) -> None:
        """CDC EF-04 : Alerte proactive avant rotation (seuil par défaut 80%)."""
        msg = f"Alerte capacité USN sur {volume}: utilisation à {utilization_pct:.1f}% (seuil: {threshold_pct:.1f}%)."
        self.logger.warning(msg)
        self.event_backend.report_event(self.EVT_USN_CAPACITY_ALERT, 2, msg)

    def log_disk_space_alert(self, target_path: str, free_mb: int) -> None:
        msg = f"Espace disque insuffisant sur la cible de sauvegarde '{target_path}': {free_mb} Mo restants."
        self.logger.error(msg)
        self.event_backend.report_event(self.EVT_DISK_SPACE_ALERT, 1, msg)

    def log_network_error(self, target_path: str, error: str) -> None:
        """CDC EF-12 : Déconnexion réseau, bascule en file d'attente persistante."""
        msg = f"Partage réseau '{target_path}' indisponible: {error}. Transferts mis en attente."
        self.logger.warning(msg)
        self.event_backend.report_event(self.EVT_NETWORK_ERROR, 2, msg)
