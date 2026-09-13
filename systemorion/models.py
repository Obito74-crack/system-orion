"""Types partagés, dataclasses et exceptions pour System Orion.

Ce module centralise toutes les structures de données échangées entre modules
afin d'éviter les imports circulaires. Aucune logique métier ici — uniquement
des définitions de types.

Cf. CDC ET-02 (structure du code) — module ajouté pour la cohésion architecturale.
Décision d'architecture DA-01.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TransferState(enum.Enum):
    """Machine à états d'un transfert de fichier (EF-12).

    Cycle de vie : PENDING → COPYING → DONE
    En cas d'échec non récupérable : PENDING → COPYING → FAILED
    Au redémarrage du service : tout COPYING repasse en PENDING.
    """

    PENDING = "PENDING"
    COPYING = "COPYING"
    DONE = "DONE"
    FAILED = "FAILED"


class UsnReason(enum.IntFlag):
    """Raisons de modification USN pertinentes pour System Orion (EF-04).

    Sous-ensemble des USN_REASON_* définis dans winioctl.h.
    Seules les raisons qui impliquent un contenu modifié sont retenues.
    """

    DATA_OVERWRITE = 0x00000001
    DATA_EXTEND = 0x00000002
    DATA_TRUNCATION = 0x00000004
    NAMED_DATA_OVERWRITE = 0x00000010
    NAMED_DATA_EXTEND = 0x00000020
    NAMED_DATA_TRUNCATION = 0x00000040
    FILE_CREATE = 0x00000100
    FILE_DELETE = 0x00000200
    RENAME_NEW_NAME = 0x00002000
    CLOSE = 0x80000000

    # Masque combiné pour les raisons déclenchant une sauvegarde
    BACKUP_RELEVANT = (
        DATA_OVERWRITE
        | DATA_EXTEND
        | DATA_TRUNCATION
        | NAMED_DATA_OVERWRITE
        | NAMED_DATA_EXTEND
        | NAMED_DATA_TRUNCATION
        | FILE_CREATE
        | RENAME_NEW_NAME
    )


# ---------------------------------------------------------------------------
# Dataclasses — Persistance (state.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsnProgress:
    """Progression de lecture du journal USN pour un volume donné."""

    volume: str
    last_usn: int
    journal_id: int
    updated_at: datetime


@dataclass(slots=True)
class TransferRecord:
    """Enregistrement d'un transfert dans la file d'attente SQLite."""

    id: int
    source_path: str
    dest_path: str
    file_size: int
    state: TransferState
    enqueued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempt_count: int = 0
    last_error: Optional[str] = None


@dataclass(frozen=True, slots=True)
class BackupRecord:
    """Entrée dans l'historique des sauvegardes réussies."""

    id: int
    source_path: str
    dest_path: str
    file_size: int
    backed_up_at: datetime
    version_tag: str  # ex: "__20260908_1430" (EF-08)


# ---------------------------------------------------------------------------
# Dataclasses — Détection USN (journal_usn.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UsnJournalData:
    """Métadonnées du journal USN d'un volume."""

    journal_id: int
    first_usn: int
    next_usn: int
    max_size: int
    allocation_delta: int


@dataclass(frozen=True, slots=True)
class UsnRecord:
    """Enregistrement USN individuel lu depuis le journal."""

    usn: int
    filename: str
    file_reference_number: int
    parent_file_reference_number: int
    reason: int
    timestamp: datetime
    source_path: str = ""  # Résolu après lecture


# ---------------------------------------------------------------------------
# Dataclasses — Configuration (config.py)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OrionConfig:
    """Configuration complète de System Orion (D7 — magasin unique).

    Alimentée soit par l'assistant manuel (EF-01/EF-01a), soit par GPO (EF-02).
    Lue depuis HKLM\\SOFTWARE\\SystemOrion sous Windows.
    """

    # Arborescences à sauvegarder (EF-01)
    target_paths: list[str] = field(default_factory=lambda: [
        r"~\Documents",
        r"~\Desktop",
        r"~\Pictures",
        r"~\Favorites",
    ])

    # Exclusions (EF-05)
    exclusion_patterns: list[str] = field(default_factory=lambda: [
        "*.tmp", "*.temp", "~$*", "*.lnk",
        "thumbs.db", "desktop.ini",
    ])
    exclusion_extensions: list[str] = field(default_factory=lambda: [
        ".tmp", ".temp", ".bak", ".swp", ".swo",
        ".pyc", ".pyo", ".log",
    ])
    excluded_dirs: list[str] = field(default_factory=lambda: [
        "$RECYCLE.BIN",
        "AppData",
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
    ])

    # Cible réseau (D5, EF-03)
    unc_override: Optional[str] = None  # Si différent de homeDirectory AD
    backup_subfolder: str = "SystemOrion"  # Sous-dossier dans homeDirectory

    # Rétention (EF-08)
    retention_max_versions: int = 10
    retention_max_days: int = 90

    # USN Journal (EF-04)
    usn_journal_size_mb: int = 256
    usn_alert_threshold_pct: int = 80
    usn_min_coverage_hours: int = 72

    # Résilience réseau (EF-12)
    bandwidth_limit_kbps: Optional[int] = None
    reconnect_jitter_max_s: int = 900  # 0-15 min par défaut
    backoff_initial_s: int = 10
    backoff_max_s: int = 300  # 5 min

    # Planification
    cycle_interval_s: int = 60  # Intervalle entre les cycles de lecture USN

    # GPO (D7, EF-01a)
    managed_by_gpo: bool = False

    # Chemins système
    log_dir: str = r"C:\ProgramData\SystemOrion\logs"
    state_db_path: str = r"C:\ProgramData\SystemOrion\state.db"


# ---------------------------------------------------------------------------
# Dataclasses — Statistiques
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BackupStats:
    """Statistiques d'un cycle de sauvegarde (EF-10)."""

    files_saved: int = 0
    files_skipped: int = 0
    files_errored: int = 0
    bytes_transferred: int = 0
    cycle_duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Exceptions hiérarchiques (DA-03)
# ---------------------------------------------------------------------------


class OrionError(Exception):
    """Exception de base pour System Orion."""

    def __init__(self, message: str, error_code: int = 0) -> None:
        super().__init__(message)
        self.error_code = error_code


class ConfigError(OrionError):
    """Erreur de lecture/écriture de la configuration."""


class StateError(OrionError):
    """Erreur de la base d'état SQLite."""


class UsnError(OrionError):
    """Erreur de lecture/manipulation du journal USN."""


class VssError(OrionError):
    """Erreur de création/suppression de cliché VSS."""


class AdResolutionError(OrionError):
    """Erreur de résolution Active Directory."""


class BackupError(OrionError):
    """Erreur lors du transfert de fichiers."""


class NetworkError(BackupError):
    """Erreur réseau (partage SMB indisponible)."""


class ImpersonationError(OrionError):
    """Erreur d'emprunt d'identité utilisateur."""
