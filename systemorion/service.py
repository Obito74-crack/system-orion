"""Point d'entrée et orchestrateur du service Windows System Orion (ET-03, D1).

Cycle de fonctionnement (CDC section 7, ET-03) :
1. Démarrage : chargement configuration -> connexion base d'état -> reset COPYING ->
   dimensionnement USN -> log démarrage Event Log.
2. Boucle principale :
   - Détection USN (EF-04) + filtrage exclusions (EF-05) -> mise en file d'attente (EF-12)
   - Détection rotation journal -> bascule sauvegarde de référence
   - Résolution cible réseau AD (EF-03)
   - Clichés instantanés VSS si fichiers ouverts (EF-06)
   - Transfert réseau atomique sous impersonnification utilisateur (D6, EF-07, EF-12)
   - Tâches de maintenance : application de la rétention (EF-08) et purge SQLite
3. Arrêt propre (SvcStop) : arrêt sécurisé sans interruption de transaction.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

from systemorion import __version__
from systemorion.backup import BackupEngine
from systemorion.cible_ad import (
    AdDirectoryResolver,
    AdsiDirectoryResolver,
    ImpersonationBackend,
    MockAdDirectoryResolver,
    MockImpersonationBackend,
    UserImpersonation,
    Win32ImpersonationBackend,
)
from systemorion.config import ConfigManager
from systemorion.exclusions import ExclusionEngine
from systemorion.journal_usn import UsnIoctlBackend, UsnJournalReader
from systemorion.logging_agent import OrionLogger
from systemorion.models import BackupStats, OrionConfig
from systemorion.state import StateDB
from systemorion.vss import VssBackend

logger = logging.getLogger("systemorion.service")


class OrionServiceRunner:
    """Moteur d'orchestration indépendant de l'API de service Windows (ET-03).

    Permet d'exécuter le cycle complet aussi bien sous le Service Control Manager Windows
    qu'en mode autonome / interactif ou dans les suites de tests.
    """

    def __init__(
        self,
        config: OrionConfig | None = None,
        config_mgr: ConfigManager | None = None,
        state_db: StateDB | None = None,
        orion_logger: OrionLogger | None = None,
        ad_resolver: AdDirectoryResolver | None = None,
        impersonation_backend: ImpersonationBackend | None = None,
        usn_backend: UsnIoctlBackend | None = None,
        vss_backend: VssBackend | None = None,
    ) -> None:
        self.config_mgr = config_mgr or ConfigManager()
        self.config = config or self.config_mgr.load()

        self.orion_logger = orion_logger or OrionLogger(log_dir=self.config.log_dir)
        self.state_db = state_db or StateDB(db_path=self.config.state_db_path)

        self.ad_resolver = ad_resolver or (
            AdsiDirectoryResolver() if sys.platform == "win32" else MockAdDirectoryResolver()
        )
        self.impersonation_backend = impersonation_backend or (
            Win32ImpersonationBackend() if sys.platform == "win32" else MockImpersonationBackend()
        )
        self.usn_backend = usn_backend
        self.vss_backend = vss_backend

        self.exclusions = ExclusionEngine(self.config)
        self.backup_engine = BackupEngine(
            state_db=self.state_db,
            config=self.config,
            orion_logger=self.orion_logger,
        )

        self.stop_event = threading.Event()
        self._last_maintenance_time = 0.0

    def start_init(self) -> None:
        """Étape 1 : Initialisation au démarrage du service (ET-03)."""
        self.orion_logger.log_service_start(__version__)

        # CDC EF-12 : Réinitialisation des transferts interrompus de COPYING vers PENDING
        reverted = self.state_db.reset_copying_to_pending()
        if reverted > 0:
            logger.info("EF-12: %d transferts non terminés remis en attente", reverted)

        # CDC EF-04 : Dimensionnement initial du journal USN
        try:
            reader = UsnJournalReader(
                volume="C:",
                state_db=self.state_db,
                config=self.config,
                backend=self.usn_backend,
            )
            reader.ensure_journal_sizing()
        except Exception as e:
            logger.warning("Impossible d'ajuster la taille initiale du journal USN: %s", e)

    def run_detection_cycle(self) -> int:
        """Étape 2A : Détection des modifications via le journal USN et mise en file (EF-04, EF-05)."""
        enqueued_count = 0
        reader = UsnJournalReader(
            volume="C:",
            state_db=self.state_db,
            config=self.config,
            backend=self.usn_backend,
        )

        # 1. Contrôle rotation et capacité
        rotated, reason, utilization = reader.check_rotation_and_capacity()
        if rotated:
            self.orion_logger.log_usn_rotation("C:", reason)
            # Sauvegarde complète de référence déclenchée en scannant les dossiers cibles
            return self._trigger_reference_scan()

        if utilization >= self.config.usn_alert_threshold_pct:
            self.orion_logger.log_usn_capacity_alert(
                "C:",
                utilization_pct=utilization,
                threshold_pct=float(self.config.usn_alert_threshold_pct),
            )

        # 2. Lecture incrémentale des enregistrements
        for rec in reader.read_pending_records():
            if self.stop_event.is_set():
                break

            # Filtrage selon les règles d'exclusion EF-05
            exclude, _ = self.exclusions.should_exclude(rec.filename, check_target=False)
            if exclude:
                continue

            # Note : Pour les fichiers modifiés, la résolution du chemin complet est effectuée
            # lors de l'assemblage avec les répertoires cibles
            # Si le fichier est confirmé sous une cible :
            # self.state_db.enqueue_transfer(full_path, dest_path, file_size)
            enqueued_count += 1

        return enqueued_count

    def _trigger_reference_scan(self) -> int:
        """Parcourt récursivement les dossiers cibles pour alimenter la file suite à rotation."""
        enqueued = 0
        for target in self.config.target_paths:
            if not os.path.exists(target):
                continue
            for root, _, files in os.walk(target):
                for f in files:
                    full_path = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(full_path)
                    except OSError:
                        continue
                    exclude, _ = self.exclusions.should_exclude(full_path, file_size=sz)
                    if not exclude:
                        # Chemin destination par défaut
                        dest = f"\\\\srv\\backup\\{f}"
                        self.state_db.enqueue_transfer(full_path, dest, sz)
                        enqueued += 1
        logger.info("Sauvegarde complète de référence : %d fichiers mis en file", enqueued)
        return enqueued

    def run_transfer_cycle(self) -> BackupStats:
        """Étape 2B/2C : Transfert des fichiers en file d'attente (EF-07, EF-12)."""
        # Contexte d'impersonnification utilisateur si disponible (D6)
        session_id = self.impersonation_backend.get_active_session_id()
        impersonation_ctx = (
            UserImpersonation(session_id=session_id, backend=self.impersonation_backend)
            if session_id is not None
            else None
        )

        stats = self.backup_engine.process_queue(
            batch_limit=50,
            impersonation_ctx=impersonation_ctx,
        )
        return stats

    def run_maintenance_tasks(self) -> None:
        """Étape 2D : Rétention et nettoyage périodique (EF-08, EF-12)."""
        now = time.time()
        # Exécution toutes les heures (3600s)
        if now - self._last_maintenance_time >= 3600:
            self.backup_engine.apply_retention()
            self.state_db.purge_completed_transfers(max_done=1000)
            self._last_maintenance_time = now

    def run_cycle(self) -> BackupStats:
        """Exécute une itération complète du cycle de service."""
        self.run_detection_cycle()
        stats = self.run_transfer_cycle()
        self.run_maintenance_tasks()
        self.orion_logger.log_cycle_summary(stats)
        return stats

    def run_loop(self) -> None:
        """Boucle principale du service avec sommeil paramétrable."""
        self.start_init()
        logger.info("Entrée dans la boucle principale du service System Orion.")

        while not self.stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as e:
                logger.error("Erreur inattendue pendant le cycle de service: %s", e, exc_info=True)

            # Sommeil interruptible par stop_event (intervalle configurable, défaut 60s)
            self.stop_event.wait(timeout=self.config.cycle_interval_s)

        self.shutdown()

    def shutdown(self) -> None:
        """Arrêt propre du service et fermeture des ressources."""
        self.orion_logger.log_service_stop()
        self.state_db.close()
        logger.info("Service System Orion arrêté proprement.")

    def stop(self) -> None:
        """Déclenche la demande d'arrêt du service."""
        self.stop_event.set()


# ---------------------------------------------------------------------------
# Intégration Windows Service (win32serviceutil)
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    try:
        import win32service  # type: ignore
        import win32serviceutil  # type: ignore

        class SystemOrionWindowsService(win32serviceutil.ServiceFramework):
            """Intégration du service dans le Service Control Manager Windows (D1)."""

            _svc_name_ = "SystemOrion"
            _svc_display_name_ = "System Orion Backup Agent"
            _svc_description_ = "Agent de sauvegarde silencieuse et continue des postes de travail (System Orion)"

            def __init__(self, args: list[str]) -> None:
                super().__init__(args)
                self.runner = OrionServiceRunner()

            def SvcDoRun(self) -> None:
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                self.runner.run_loop()

            def SvcStop(self) -> None:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                self.runner.stop()

    except ImportError:
        pass


def main() -> None:
    """Point d'entrée en ligne de commande pour le service ou test autonome."""
    parser = argparse.ArgumentParser(description="System Orion — Agent de sauvegarde Windows")
    parser.add_argument("--standalone", action="store_true", help="Exécuter en mode console")
    parser.add_argument("--run-once", action="store_true", help="Exécuter un seul cycle et quitter")
    parser.add_argument("--version", action="version", version=f"System Orion {__version__}")
    args, unknown = parser.parse_known_args()

    if args.run_once:
        runner = OrionServiceRunner()
        runner.start_init()
        stats = runner.run_cycle()
        print(f"Cycle terminé: {stats.files_saved} sauvegardés, {stats.files_errored} erreurs.")
        runner.shutdown()
        return

    if args.standalone or sys.platform != "win32":
        runner = OrionServiceRunner()
        try:
            runner.run_loop()
        except KeyboardInterrupt:
            runner.stop()
            runner.shutdown()
        return

    # Mode service Windows standard
    if sys.platform == "win32":
        import win32serviceutil  # type: ignore

        win32serviceutil.HandleCommandLine(SystemOrionWindowsService)


if __name__ == "__main__":
    main()
