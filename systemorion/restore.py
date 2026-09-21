"""Module d'assistance à la restauration des versions sauvegardées (EF-09+).

Permet :
- L'énumération des versions sauvegardées d'un fichier (depuis la base locale SQLite ou par analyse du partage réseau).
- L'extraction et l'analyse des tags de version horodatés (__YYYYMMDD_HHMM).
- La restauration sécurisée et atomique vers un dossier ou fichier de destination avec préservation des métadonnées.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from systemorion.models import BackupRecord, OrionError
from systemorion.state import StateDB

logger = logging.getLogger("systemorion.restore")

VERSION_TAG_REGEX = re.compile(r"__(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})_(?P<hour>\d{2})(?P<minute>\d{2})")


class RestoreError(OrionError):
    """Exception levée en cas d'échec de restauration."""


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Résultat d'une opération de restauration."""

    source_version_path: str
    restored_path: str
    file_size: int
    restored_at: datetime
    version_timestamp: datetime | None


def extract_version_timestamp(path_or_tag: str) -> datetime | None:
    """Extrait l'horodatage d'un nom de fichier versionné ou d'un tag de version (EF-08).

    Exemples :
        - 'rapport__20260908_1430.docx' -> datetime(2026, 9, 8, 14, 30, tzinfo=UTC)
        - '__20260908_1430' -> datetime(2026, 9, 8, 14, 30, tzinfo=UTC)
    """
    match = VERSION_TAG_REGEX.search(path_or_tag)
    if not match:
        return None
    gd = match.groupdict()
    try:
        return datetime(
            year=int(gd["year"]),
            month=int(gd["month"]),
            day=int(gd["day"]),
            hour=int(gd["hour"]),
            minute=int(gd["minute"]),
            tzinfo=UTC,
        )
    except ValueError:
        return None


def clean_version_tag_from_filename(filename: str) -> str:
    """Retire le tag de versioning d'un nom de fichier pour retrouver le nom d'origine.

    Ex: 'rapport__20260908_1430.docx' -> 'rapport.docx'
    """
    return VERSION_TAG_REGEX.sub("", filename)


def find_backup_versions(
    source_path: str,
    state_db: StateDB | None = None,
    backup_search_dir: str | None = None,
) -> list[BackupRecord]:
    """Recherche toutes les versions archivées disponibles pour un fichier source.

    Interroge la base locale d'état SQLite si disponible, et complète/valide
    éventuellement avec l'arborescence réseau sur disque.
    """
    versions: list[BackupRecord] = []
    seen_dest_paths: set[str] = set()

    # 1. Interrogation de la base SQLite locale
    if state_db is not None:
        try:
            records = state_db.get_backup_versions(source_path)
            for r in records:
                if r.dest_path not in seen_dest_paths:
                    versions.append(r)
                    seen_dest_paths.add(r.dest_path)
        except Exception as e:
            logger.warning("Erreur lors de la lecture des versions dans SQLite : %s", e)

    # 2. Recherche directe sur le disque / partage réseau
    if backup_search_dir and os.path.isdir(backup_search_dir):
        source_name = Path(source_path).name

        # Pattern recherché : stem__YYYYMMDD_HHMM.ext ou nom identique
        for root, _, files in os.walk(backup_search_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                cleaned = clean_version_tag_from_filename(fname)
                if cleaned.lower() == source_name.lower() and fpath not in seen_dest_paths:
                    try:
                        fsize = os.path.getsize(fpath)
                        mtime = os.path.getmtime(fpath)
                        backed_up_at = datetime.fromtimestamp(mtime, tz=UTC)
                        ts = extract_version_timestamp(fname)
                        vtag = ts.strftime("__%Y%m%d_%H%M") if ts else ""
                        rec = BackupRecord(
                            id=0,
                            source_path=source_path,
                            dest_path=fpath,
                            file_size=fsize,
                            backed_up_at=backed_up_at,
                            version_tag=vtag,
                        )
                        versions.append(rec)
                        seen_dest_paths.add(fpath)
                    except OSError as e:
                        logger.debug("Fichier inaccessible lors du scan : %s (%s)", fpath, e)

    # Tri du plus récent au plus ancien
    versions.sort(key=lambda r: r.backed_up_at, reverse=True)
    return versions


def restore_file(
    version_dest_path: str,
    target_destination: str,
    overwrite: bool = False,
) -> RestoreResult:
    """Restaure une version sauvegardée vers une destination locale.

    Paramètres :
        version_dest_path : Chemin complet du fichier sauvegardé (ex: \\\\srv\\share\\doc__20260908_1430.docx).
        target_destination : Chemin du dossier de destination ou chemin complet du fichier restauré.
        overwrite : Si False, évite l'écrasement en générant un suffixe '.restored'.

    Retourne :
        RestoreResult avec les détails de la restauration.
    """
    if not os.path.exists(version_dest_path):
        raise RestoreError(f"Le fichier sauvegardé source n'existe pas : {version_dest_path}")

    # Résolution du nom de fichier original
    dest_p = Path(version_dest_path)
    original_filename = clean_version_tag_from_filename(dest_p.name)

    if os.path.isdir(target_destination):
        out_file_path = os.path.join(target_destination, original_filename)
    else:
        out_file_path = target_destination

    # Gestion de l'existence du fichier cible
    if os.path.exists(out_file_path) and not overwrite:
        p = Path(out_file_path)
        out_file_path = str(p.parent / f"{p.stem}.restored{p.suffix}")

    # Création du répertoire parent si nécessaire
    out_dir = os.path.dirname(out_file_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Copie atomique (.tmp puis rename)
    tmp_path = f"{out_file_path}.tmp_{os.getpid()}"
    try:
        shutil.copy2(version_dest_path, tmp_path)
        if os.path.exists(out_file_path):
            os.remove(out_file_path)
        os.rename(tmp_path, out_file_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise RestoreError(f"Échec de la copie de restauration : {e}") from e

    file_size = os.path.getsize(out_file_path)
    version_ts = extract_version_timestamp(dest_p.name)

    logger.info("Fichier restauré avec succès : '%s' -> '%s'", version_dest_path, out_file_path)

    return RestoreResult(
        source_version_path=version_dest_path,
        restored_path=out_file_path,
        file_size=file_size,
        restored_at=datetime.now(UTC),
        version_timestamp=version_ts,
    )
