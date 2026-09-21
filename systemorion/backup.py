"""Moteur de transfert, file de copie, versioning et résilience réseau (EF-07, EF-08, EF-12).

Gère :
- Le découplage total entre la détection locale et le transfert réseau (EF-12).
- Le transfert atomique sur partage SMB : copie vers <nom>.part puis renommage atomique.
- La préservation des métadonnées (horodatage de modification).
- Le versioning horodaté : <nom>__YYYYMMDD_HHMM.<ext> (EF-08).
- Les règles de rétention : quotas de versions et purge des anciennes versions (EF-08).
- La limitation de bande passante progressive et la gestion des coupures réseau (EF-12).
- Le respect de la règle « aucune suppression côté sauvegarde lors d'une suppression source » (EF-07).
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import sys
import time
from contextlib import AbstractContextManager as ContextManager
from contextlib import nullcontext
from pathlib import Path, PureWindowsPath

from systemorion.logging_agent import OrionLogger
from systemorion.models import (
    BackupStats,
    NetworkError,
    OrionConfig,
    TransferRecord,
    TransferState,
)
from systemorion.state import StateDB

logger = logging.getLogger("systemorion.backup")


def generate_version_tag(dt: datetime.datetime | None = None) -> str:
    """Génère le tag de versioning au format standard CDC EF-08 : __YYYYMMDD_HHMM."""
    target_dt = dt or datetime.datetime.now(datetime.UTC)
    return target_dt.strftime("__%Y%m%d_%H%M")


def build_versioned_destination(dest_path: str, version_tag: str) -> str:
    """Insère le tag de version avant l'extension du fichier (EF-08).

    Ex: \\\\srv\\rapport.docx + __20260908_1430 -> \\\\srv\\rapport__20260908_1430.docx
    """
    if dest_path.startswith("/") and sys.platform != "win32":
        path_obj = Path(dest_path)
        return str(path_obj.parent / f"{path_obj.stem}{version_tag}{path_obj.suffix}")

    path_obj = PureWindowsPath(dest_path)
    stem = path_obj.stem
    suffix = path_obj.suffix
    parent = path_obj.parent

    versioned_name = f"{stem}{version_tag}{suffix}"
    return str(parent / versioned_name)


class NetworkBackoffTracker:
    """Gère le backoff exponentiel en cas d'indisponibilité du réseau SMB (EF-12)."""

    def __init__(self, initial_delay_s: float = 10.0, max_delay_s: float = 300.0) -> None:
        self.initial_delay_s = initial_delay_s
        self.max_delay_s = max_delay_s
        self.current_delay_s = initial_delay_s
        self.consecutive_failures = 0
        self.next_retry_time = 0.0

    def record_failure(self) -> float:
        """Consigne un échec réseau et calcule le prochain délai d'attente."""
        self.consecutive_failures += 1
        # Progression : 10s, 20s, 40s, 80s, ... plafonné à max_delay_s
        delay = min(self.initial_delay_s * (2 ** (self.consecutive_failures - 1)), self.max_delay_s)
        self.current_delay_s = delay
        self.next_retry_time = time.time() + delay
        return delay

    def record_success(self) -> None:
        """Réinitialise les compteurs suite à un transfert réussi."""
        self.consecutive_failures = 0
        self.current_delay_s = self.initial_delay_s
        self.next_retry_time = 0.0

    def is_retry_allowed(self) -> bool:
        """Indique si le délai de repli est écoulé pour autoriser une nouvelle tentative."""
        return time.time() >= self.next_retry_time


class BackupEngine:
    """Moteur central d'exécution des sauvegardes (EF-07, EF-08, EF-12)."""

    def __init__(
        self,
        state_db: StateDB,
        config: OrionConfig,
        orion_logger: OrionLogger | None = None,
        copy_chunk_size: int = 64 * 1024,  # 64 Ko
    ) -> None:
        self.state_db = state_db
        self.config = config
        self.orion_logger = orion_logger
        self.copy_chunk_size = copy_chunk_size
        self.backoff = NetworkBackoffTracker(
            initial_delay_s=float(config.backoff_initial_s),
            max_delay_s=float(config.backoff_max_s),
        )

    def enqueue_file(self, source_path: str, dest_path: str, file_size: int) -> int:
        """Ajoute un fichier à la file d'attente persistante SQLite (EF-12)."""
        return self.state_db.enqueue_transfer(source_path, dest_path, file_size)

    def copy_file_atomic(
        self,
        source_path: str,
        dest_path: str,
        bandwidth_limit_kbps: int | None = None,
    ) -> int:
        r"""Effectue la copie atomique d'un fichier vers le partage SMB (EF-12).

        Mécanisme :
        1. Création des répertoires cibles si inexistants.
        2. Écriture dans <dest_path>.part
        3. Préservation des timestamps de modification (EF-07).
        4. Renommage atomique .part -> dest_path.
        5. Throttling optionnel si bandwidth_limit_kbps est configuré.
        """
        dest_part = f"{dest_path}.part"
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except OSError as e:
                raise NetworkError(f"Impossible de créer le dossier cible '{dest_dir}': {e}") from e

        bytes_copied = 0
        throttle = bandwidth_limit_kbps is not None and bandwidth_limit_kbps > 0
        bytes_per_sec = (bandwidth_limit_kbps * 1024) if throttle else 0

        try:
            with open(source_path, "rb") as fsrc, open(dest_part, "wb") as fdst:
                while True:
                    start_chunk = time.time()
                    chunk = fsrc.read(self.copy_chunk_size)
                    if not chunk:
                        break
                    fdst.write(chunk)
                    bytes_copied += len(chunk)

                    # Throttling de bande passante si demandé (EF-12)
                    if throttle and bytes_per_sec > 0:
                        elapsed = time.time() - start_chunk
                        expected_time = len(chunk) / bytes_per_sec
                        if expected_time > elapsed:
                            time.sleep(expected_time - elapsed)

            # Préservation des attributs et timestamps (EF-07)
            try:
                shutil.copystat(source_path, dest_part)
            except OSError:
                pass

            # Renommage atomique sur SMB (EF-12)
            # Sous Windows / SMB, os.replace est atomique
            os.replace(dest_part, dest_path)
            return bytes_copied

        except (OSError, PermissionError) as e:
            # Nettoyage du fichier partiel en cas d'interruption
            try:
                if os.path.exists(dest_part):
                    os.remove(dest_part)
            except OSError:
                pass
            raise NetworkError(f"Erreur transfert réseau '{dest_path}': {e}") from e

    def process_transfer_item(
        self,
        item: TransferRecord,
        source_override: str | None = None,
    ) -> tuple[bool, int, str | None]:
        """Traite un fichier individuel de la file d'attente.

        Gère le versioning (EF-08), la mise à jour de l'état SQLite,
        et l'enregistrement dans l'historique des sauvegardes.
        """
        source = source_override or item.source_path
        if not os.path.exists(source):
            # CDC EF-05 : Si le fichier a disparu entre détection et copie, marquer DONE et consigner
            logger.info("Fichier source disparu avant transfert : %s", item.source_path)
            self.state_db.set_transfer_state(item.id, TransferState.DONE)
            return (True, 0, None)

        # 1. Passage en état COPYING (EF-12)
        self.state_db.set_transfer_state(item.id, TransferState.COPYING)

        # 2. Construction du chemin versionné (EF-08)
        version_tag = generate_version_tag()
        versioned_dest = build_versioned_destination(item.dest_path, version_tag)

        try:
            # 3. Transfert atomique avec throttling
            copied_bytes = self.copy_file_atomic(
                source_path=source,
                dest_path=versioned_dest,
                bandwidth_limit_kbps=self.config.bandwidth_limit_kbps,
            )

            # 4. Enregistrement dans l'historique des sauvegardes (EF-08)
            self.state_db.record_backup(
                source_path=item.source_path,
                dest_path=versioned_dest,
                file_size=copied_bytes,
                version_tag=version_tag,
            )

            # 5. Passage en état DONE (EF-12)
            self.state_db.set_transfer_state(item.id, TransferState.DONE)
            self.backoff.record_success()
            return (True, copied_bytes, None)

        except Exception as e:
            err_msg = str(e)
            logger.warning("Échec transfert pour '%s': %s", item.source_path, err_msg)
            # En cas d'erreur réseau, on remet en PENDING avec incrément d'erreur
            self.state_db.set_transfer_state(item.id, TransferState.PENDING, error=err_msg)
            self.backoff.record_failure()
            if self.orion_logger:
                self.orion_logger.log_network_error(item.dest_path, err_msg)
            return (False, 0, err_msg)

    def process_queue(
        self,
        batch_limit: int = 50,
        impersonation_ctx: ContextManager | None = None,
    ) -> BackupStats:
        """Dépile et transfère les fichiers en attente (EF-12).

        Prend en compte le backoff réseau : si un incident réseau est survenu récemment,
        le dépilage est suspendu jusqu'au terme du délai calculé.
        """
        start_time = time.time()
        stats = BackupStats()

        if not self.backoff.is_retry_allowed():
            logger.debug(
                "Backoff réseau actif, attente de %.1fs avant nouvelle tentative",
                self.backoff.next_retry_time - time.time(),
            )
            return stats

        pending_items = self.state_db.get_pending_transfers(limit=batch_limit)
        if not pending_items:
            return stats

        ctx = impersonation_ctx if impersonation_ctx is not None else nullcontext()

        with ctx:
            for item in pending_items:
                success, bytes_transferred, _ = self.process_transfer_item(item)
                if success:
                    stats.files_saved += 1
                    stats.bytes_transferred += bytes_transferred
                else:
                    stats.files_errored += 1
                    # En cas d'échec réseau, on interrompt le lot courant pour éviter de mitrailler le serveur
                    break

        stats.cycle_duration_s = time.time() - start_time
        return stats

    def apply_retention(self) -> int:
        """Applique les politiques de rétention configurées (CDC EF-08).

        Supprime les versions excédentaires sur le partage distant et purge
        leurs entrées correspondantes dans la base d'état.
        """
        max_versions = self.config.retention_max_versions
        if max_versions <= 0:
            return 0

        total_pruned = 0
        # Récupération des chemins sources distincts ayant des sauvegardes
        conn = self.state_db._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT source_path FROM backup_history;")
        sources = [row[0] for row in cur.fetchall()]

        for src in sources:
            prunable = self.state_db.get_prunable_versions(src, max_versions=max_versions)
            for record in prunable:
                # 1. Suppression du fichier distant archivé
                try:
                    if os.path.exists(record.dest_path):
                        os.remove(record.dest_path)
                except OSError as e:
                    logger.debug("Impossible d'effacer l'ancienne version '%s': %s", record.dest_path, e)

                # 2. Suppression de l'entrée dans l'historique SQLite
                self.state_db.delete_history_record(record.id)
                total_pruned += 1

        if total_pruned > 0:
            logger.info("Rétention EF-08 appliquée : %d anciennes versions purgées", total_pruned)
        return total_pruned
