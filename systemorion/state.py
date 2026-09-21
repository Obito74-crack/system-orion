"""Persistance SQLite : USN traité, file d'attente, machine à états, historique.

Cf. CDC ET-01 : sqlite3 (stdlib), mode WAL + synchronous=FULL pour durabilité
après coupure de courant.
Cf. EF-12 : Découplage détection/transfert, machine à états PENDING/COPYING/DONE,
réinitialisation au démarrage de COPYING vers PENDING.
Cf. EF-04 : Stockage de la progression USN et métriques d'activité pour dimensionnement.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from systemorion.models import BackupRecord, StateError, TransferRecord, TransferState, UsnProgress

logger = logging.getLogger("systemorion.state")


class StateDB:
    """Gestionnaire de persistance SQLite pour System Orion.

    Garantit la durabilité et la cohérence de l'état même en cas de coupure brutale
    d'alimentation (CDC ET-01, EF-12) grâce au mode WAL et PRAGMA synchronous=FULL.
    Protégé par verrou réentrant pour garantir la sûreté en environnement multithread.
    """

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str = r"C:\ProgramData\SystemOrion\state.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._initialize_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Retourne la connexion SQLite active ou la recrée."""
        if self._conn is None:
            self._initialize_db()
        assert self._conn is not None
        return self._conn

    def _initialize_db(self) -> None:
        """Crée le répertoire parent, ouvre SQLite avec les PRAGMAs requis et initialise le schéma."""
        with self._lock:
            try:
                # Création du dossier parent si nécessaire
                if str(self.db_path) != ":memory:":
                    self.db_path.parent.mkdir(parents=True, exist_ok=True)

                self._conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    isolation_level=None,  # Autocommit control via transactions explicites
                )
                self._conn.row_factory = sqlite3.Row

                cur = self._conn.cursor()
                # CDC ET-01 : WAL mode + synchronous=FULL pour résilience aux coupures
                if str(self.db_path) != ":memory:":
                    cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=FULL;")
                cur.execute("PRAGMA busy_timeout=5000;")
                cur.execute("PRAGMA foreign_keys=ON;")

                self._create_tables()
            except sqlite3.Error as e:
                raise StateError(f"Erreur d'initialisation de la base SQLite '{self.db_path}': {e}") from e

    def _create_tables(self) -> None:
        """Crée les tables et index si inexistants."""
        assert self._conn is not None
        cur = self._conn.cursor()
        cur.execute("BEGIN IMMEDIATE;")
        try:
            # Table des métadonnées internes
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY,
                    updated_at TEXT NOT NULL
                );
            """)

            # Table de progression USN par volume (EF-04)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usn_progress (
                    volume TEXT PRIMARY KEY,
                    last_usn INTEGER NOT NULL,
                    journal_id INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # Table file d'attente des transferts avec machine à états (EF-12)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transfer_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL UNIQUE,
                    dest_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transfer_state ON transfer_queue(state);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_transfer_enqueued ON transfer_queue(enqueued_at);")

            # Table d'historique des sauvegardes pour le versioning et la rétention (EF-08)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS backup_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    dest_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    backed_up_at TEXT NOT NULL,
                    version_tag TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_history_source ON backup_history(source_path);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_history_backed_up ON backup_history(backed_up_at);")

            # Table métriques USN pour dimensionnement dynamique (EF-04)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usn_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    volume TEXT NOT NULL,
                    records_count INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_vol_time ON usn_metrics(volume, recorded_at);")

            # Initialisation version schéma
            cur.execute("SELECT version FROM schema_info WHERE version = ?;", (self.SCHEMA_VERSION,))
            if not cur.fetchone():
                now = datetime.now(UTC).isoformat()
                cur.execute(
                    "INSERT INTO schema_info (version, updated_at) VALUES (?, ?);",
                    (self.SCHEMA_VERSION, now),
                )

            cur.execute("COMMIT;")
        except Exception:
            cur.execute("ROLLBACK;")
            raise

    def close(self) -> None:
        """Ferme proprement la connexion SQLite."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    pass
                finally:
                    self._conn = None

    # -----------------------------------------------------------------------
    # USN Progress (EF-04)
    # -----------------------------------------------------------------------

    def get_usn_progress(self, volume: str) -> UsnProgress | None:
        """Récupère le dernier USN traité et l'identifiant du journal pour un volume."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT volume, last_usn, journal_id, updated_at FROM usn_progress WHERE volume = ?;",
                (volume.upper(),),
            )
            row = cur.fetchone()
            if not row:
                return None
            return UsnProgress(
                volume=row["volume"],
                last_usn=row["last_usn"],
                journal_id=row["journal_id"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def set_usn_progress(self, volume: str, last_usn: int, journal_id: int) -> None:
        """Met à jour ou insère la progression USN pour un volume."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(UTC).isoformat()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    """
                    INSERT INTO usn_progress (volume, last_usn, journal_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(volume) DO UPDATE SET
                        last_usn = excluded.last_usn,
                        journal_id = excluded.journal_id,
                        updated_at = excluded.updated_at;
                    """,
                    (volume.upper(), last_usn, journal_id, now),
                )
                cur.execute("COMMIT;")
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Impossible de sauvegarder la progression USN: {e}") from e

    # -----------------------------------------------------------------------
    # File de transfert et Machine à états (EF-12)
    # -----------------------------------------------------------------------

    def enqueue_transfer(self, source_path: str, dest_path: str, file_size: int) -> int:
        """Ajoute un fichier à la file d'attente (PENDING) ou actualise s'il était déjà en file.

        Si le fichier existe déjà en état PENDING ou FAILED, sa cible, sa taille et
        sa date sont rafraîchies et son état repasse à PENDING.
        Si l'état est COPYING, on ne l'écrase pas pour ne pas perturber le transfert courant.
        """
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(UTC).isoformat()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    "SELECT id, state FROM transfer_queue WHERE source_path = ?;",
                    (source_path,),
                )
                row = cur.fetchone()
                if row:
                    item_id = row["id"]
                    current_state = row["state"]
                    if current_state != TransferState.COPYING.value:
                        cur.execute(
                            """
                            UPDATE transfer_queue
                            SET dest_path = ?, file_size = ?, state = ?, enqueued_at = ?, last_error = NULL
                            WHERE id = ?;
                            """,
                            (dest_path, file_size, TransferState.PENDING.value, now, item_id),
                        )
                    cur.execute("COMMIT;")
                    return int(item_id)

                cur.execute(
                    """
                    INSERT INTO transfer_queue
                    (source_path, dest_path, file_size, state, enqueued_at, attempt_count)
                    VALUES (?, ?, ?, ?, ?, 0);
                    """,
                    (source_path, dest_path, file_size, TransferState.PENDING.value, now),
                )
                new_id = cur.lastrowid
                cur.execute("COMMIT;")
                assert new_id is not None
                return new_id
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Impossible d'enfiler le transfert '{source_path}': {e}") from e

    def get_pending_transfers(self, limit: int | None = None) -> list[TransferRecord]:
        """Retourne les transferts en attente ordonnés par date d'insertion."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            query = "SELECT * FROM transfer_queue WHERE state = ? ORDER BY enqueued_at ASC"
            params: list[Any] = [TransferState.PENDING.value]
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cur.execute(query, tuple(params))
            return [self._row_to_transfer_record(row) for row in cur.fetchall()]

    def set_transfer_state(
        self,
        transfer_id: int,
        state: TransferState,
        error: str | None = None,
    ) -> None:
        """Met à jour l'état d'un transfert dans la machine à états."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(UTC).isoformat()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                if state == TransferState.COPYING:
                    cur.execute(
                        """
                        UPDATE transfer_queue
                        SET state = ?, started_at = ?, attempt_count = attempt_count + 1
                        WHERE id = ?;
                        """,
                        (state.value, now, transfer_id),
                    )
                elif state == TransferState.DONE:
                    cur.execute(
                        """
                        UPDATE transfer_queue
                        SET state = ?, completed_at = ?, last_error = NULL
                        WHERE id = ?;
                        """,
                        (state.value, now, transfer_id),
                    )
                elif state == TransferState.FAILED:
                    cur.execute(
                        """
                        UPDATE transfer_queue
                        SET state = ?, completed_at = ?, last_error = ?
                        WHERE id = ?;
                        """,
                        (state.value, now, error, transfer_id),
                    )
                else:  # PENDING
                    cur.execute(
                        """
                        UPDATE transfer_queue
                        SET state = ?, last_error = ?
                        WHERE id = ?;
                        """,
                        (state.value, error, transfer_id),
                    )
                cur.execute("COMMIT;")
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur mise à jour état transfert #{transfer_id}: {e}") from e

    def reset_copying_to_pending(self) -> int:
        """CDC EF-12 : Au redémarrage, tout fichier en état COPYING repasse en PENDING.

        Garantit qu'aucun transfert interrompu par un arrêt de service ou arrêt système
        ne reste orphelin.
        """
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    """
                    UPDATE transfer_queue
                    SET state = ?, started_at = NULL, last_error = 'Interrompu par arrêt du service'
                    WHERE state = ?;
                    """,
                    (TransferState.PENDING.value, TransferState.COPYING.value),
                )
                affected = cur.rowcount
                cur.execute("COMMIT;")
                if affected > 0:
                    logger.info("EF-12: %d transferts réinitialisés de COPYING à PENDING", affected)
                return affected
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur lors du reset des transferts COPYING: {e}") from e

    def purge_completed_transfers(self, max_done: int = 1000) -> int:
        """Nettoie les transferts terminés (DONE) au-delà d'un quota pour éviter l'enflure."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    """
                    DELETE FROM transfer_queue
                    WHERE state = ? AND id NOT IN (
                        SELECT id FROM transfer_queue
                        WHERE state = ?
                        ORDER BY completed_at DESC
                        LIMIT ?
                    );
                    """,
                    (TransferState.DONE.value, TransferState.DONE.value, max_done),
                )
                deleted = cur.rowcount
                cur.execute("COMMIT;")
                return deleted
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur purge transferts DONE: {e}") from e

    def get_queue_counts(self) -> dict[str, int]:
        """Retourne le décompte des éléments par état dans la file."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT state, COUNT(*) as count FROM transfer_queue GROUP BY state;")
            counts = {s.value: 0 for s in TransferState}
            for row in cur.fetchall():
                counts[row["state"]] = row["count"]
            return counts

    # -----------------------------------------------------------------------
    # Historique et Rétention (EF-08)
    # -----------------------------------------------------------------------

    def record_backup(
        self,
        source_path: str,
        dest_path: str,
        file_size: int,
        version_tag: str,
    ) -> int:
        """Enregistre une sauvegarde réussie dans l'historique."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(UTC).isoformat()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    """
                    INSERT INTO backup_history
                    (source_path, dest_path, file_size, backed_up_at, version_tag)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (source_path, dest_path, file_size, now, version_tag),
                )
                rec_id = cur.lastrowid
                cur.execute("COMMIT;")
                assert rec_id is not None
                return rec_id
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur enregistrement historique sauvegarde: {e}") from e

    def get_backup_versions(
        self,
        source_path: str,
        limit: int | None = None,
    ) -> list[BackupRecord]:
        """Retourne la liste des versions archivées pour un fichier source donné."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            query = "SELECT * FROM backup_history WHERE source_path = ? ORDER BY backed_up_at DESC"
            params: list[Any] = [source_path]
            if limit is not None and limit > 0:
                query += " LIMIT ?"
                params.append(limit)

            cur.execute(query, tuple(params))
            return [self._row_to_backup_record(row) for row in cur.fetchall()]

    def get_prunable_versions(
        self,
        source_path: str,
        max_versions: int,
    ) -> list[BackupRecord]:
        """Retourne les versions d'un fichier qui excèdent la règle de rétention par quota (EF-08)."""
        with self._lock:
            if max_versions <= 0:
                return []
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM backup_history
                WHERE source_path = ?
                ORDER BY backed_up_at DESC
                LIMIT -1 OFFSET ?;
                """,
                (source_path, max_versions),
            )
            return [self._row_to_backup_record(row) for row in cur.fetchall()]

    def delete_history_record(self, record_id: int) -> None:
        """Supprime un enregistrement d'historique lors de la rétention."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute("DELETE FROM backup_history WHERE id = ?;", (record_id,))
                cur.execute("COMMIT;")
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur suppression historique #{record_id}: {e}") from e

    # -----------------------------------------------------------------------
    # Métriques USN pour dimensionnement dynamique (EF-04)
    # -----------------------------------------------------------------------

    def record_usn_metrics(self, volume: str, records_count: int) -> None:
        """Enregistre le nombre d'entrées USN traitées lors d'un cycle."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            now = datetime.now(UTC).isoformat()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute(
                    """
                    INSERT INTO usn_metrics (volume, records_count, recorded_at)
                    VALUES (?, ?, ?);
                    """,
                    (volume.upper(), records_count, now),
                )
                cur.execute("COMMIT;")
            except Exception as e:
                cur.execute("ROLLBACK;")
                raise StateError(f"Erreur enregistrement métriques USN: {e}") from e

    def get_usn_activity_summary(self, volume: str, window_hours: int = 72) -> tuple[int, float]:
        """Retourne (nombre total d'enregistrements, taux horaire moyen) sur la fenêtre demandée."""
        with self._lock:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT SUM(records_count) as total, COUNT(*) as samples
                FROM usn_metrics
                WHERE volume = ?
                AND datetime(recorded_at) >= datetime('now', ?);
                """,
                (volume.upper(), f"-{window_hours} hours"),
            )
            row = cur.fetchone()
            total = row["total"] if row and row["total"] is not None else 0
            rate_per_hour = total / max(window_hours, 1)
            return (total, rate_per_hour)

    # -----------------------------------------------------------------------
    # Helpers conversion
    # -----------------------------------------------------------------------

    @staticmethod
    def _row_to_transfer_record(row: sqlite3.Row) -> TransferRecord:
        return TransferRecord(
            id=row["id"],
            source_path=row["source_path"],
            dest_path=row["dest_path"],
            file_size=row["file_size"],
            state=TransferState(row["state"]),
            enqueued_at=datetime.fromisoformat(row["enqueued_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            attempt_count=row["attempt_count"],
            last_error=row["last_error"],
        )

    @staticmethod
    def _row_to_backup_record(row: sqlite3.Row) -> BackupRecord:
        return BackupRecord(
            id=row["id"],
            source_path=row["source_path"],
            dest_path=row["dest_path"],
            file_size=row["file_size"],
            backed_up_at=datetime.fromisoformat(row["backed_up_at"]),
            version_tag=row["version_tag"],
        )
