"""Requête USN, filtrage, reprise sur USN, détection rotation et dimensionnement (EF-04, D3).

Interroge le journal USN du volume NTFS via DeviceIoControl / FSCTL_QUERY_USN_JOURNAL
et FSCTL_READ_USN_JOURNAL.
Gère :
- La persistance du dernier USN traité et la reprise exacte
- La détection de rotation de journal (Journal ID modifié ou USN antérieur au FirstUsn)
- Le dimensionnement initial (FSCTL_CREATE_USN_JOURNAL, défaut 256 Mo)
- Le dimensionnement dynamique et l'alerte proactive d'utilisation (seuil 80%)
- L'abstraction du sous-système IOCTL pour testabilité complète hors Windows.
"""

from __future__ import annotations

import datetime
import logging
import os
import struct
import sys
from abc import ABC, abstractmethod
from typing import Iterator, Optional

from systemorion.models import (
    OrionConfig,
    UsnError,
    UsnJournalData,
    UsnReason,
    UsnRecord,
)
from systemorion.state import StateDB

logger = logging.getLogger("systemorion.journal_usn")

# Constantes IOCTL Windows (winioctl.h)
FSCTL_QUERY_USN_JOURNAL = 0x000900F4
FSCTL_READ_USN_JOURNAL = 0x000900BB
FSCTL_CREATE_USN_JOURNAL = 0x000900E7

# Différence d'époque entre FILETIME (1601-01-01) et Unix (1970-01-01) en microsecondes
FILETIME_EPOCH_DIFF_US = 11644473600000000


def filetime_to_datetime(filetime: int) -> datetime.datetime:
    """Convertit un timestamp Windows FILETIME (intervalles de 100ns) en datetime UTC."""
    try:
        us = (filetime // 10) - FILETIME_EPOCH_DIFF_US
        return datetime.datetime.fromtimestamp(us / 1_000_000, tz=datetime.timezone.utc)
    except (ValueError, OSError, OverflowError):
        return datetime.datetime.now(datetime.timezone.utc)


class UsnIoctlBackend(ABC):
    """Interface d'abstraction pour les appels DeviceIoControl sur les volumes NTFS."""

    @abstractmethod
    def open_volume(self, volume_path: str) -> Any:
        """Ouvre un handle sur le volume (ex: \\\\.\\C:)."""
        ...

    @abstractmethod
    def close_volume(self, handle: Any) -> None:
        """Ferme le handle du volume."""
        ...

    @abstractmethod
    def query_journal(self, handle: Any) -> UsnJournalData:
        """Exécute FSCTL_QUERY_USN_JOURNAL."""
        ...

    @abstractmethod
    def read_journal(
        self,
        handle: Any,
        journal_id: int,
        start_usn: int,
        reason_mask: int,
        buffer_size: int = 65536,
    ) -> bytes:
        """Exécute FSCTL_READ_USN_JOURNAL et retourne le tampon d'octets brut."""
        ...

    @abstractmethod
    def create_or_resize_journal(
        self,
        handle: Any,
        max_size_bytes: int,
        allocation_delta_bytes: int,
    ) -> None:
        """Exécute FSCTL_CREATE_USN_JOURNAL pour allouer ou redimensionner le journal."""
        ...


class Win32UsnIoctlBackend(UsnIoctlBackend):
    """Implémentation concrète Windows utilisant pywin32 (win32file)."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise PlatformError("Win32UsnIoctlBackend n'est supporté que sous Windows.")
        import win32file  # type: ignore

        self._win32 = win32file

    def open_volume(self, volume_path: str) -> Any:
        vol = volume_path.rstrip("\\")
        if not vol.startswith(r"\\.\\"):
            vol = rf"\\.\{vol}"
        try:
            handle = self._win32.CreateFile(
                vol,
                self._win32.GENERIC_READ | self._win32.GENERIC_WRITE,
                self._win32.FILE_SHARE_READ | self._win32.FILE_SHARE_WRITE,
                None,
                self._win32.OPEN_EXISTING,
                0,
                0,
            )
            return handle
        except Exception as e:
            raise UsnError(f"Impossible d'ouvrir le volume {volume_path}: {e}") from e

    def close_volume(self, handle: Any) -> None:
        try:
            self._win32.CloseHandle(handle)
        except Exception:
            pass

    def query_journal(self, handle: Any) -> UsnJournalData:
        try:
            # USN_JOURNAL_DATA_V0 attendu : 56 octets minimum
            # Q (UsnJournalID), q (FirstUsn), q (NextUsn), q (LowestValidUsn),
            # q (MaxUsn), Q (MaximumSize), Q (AllocationDelta)
            out_buf = self._win32.DeviceIoControl(
                handle,
                FSCTL_QUERY_USN_JOURNAL,
                None,
                56,
                None,
            )
            journal_id, first_usn, next_usn, _, _, max_size, alloc_delta = struct.unpack(
                "<QqqqqQQ", out_buf[:56]
            )
            return UsnJournalData(
                journal_id=journal_id,
                first_usn=first_usn,
                next_usn=next_usn,
                max_size=max_size,
                allocation_delta=alloc_delta,
            )
        except Exception as e:
            raise UsnError(f"Échec FSCTL_QUERY_USN_JOURNAL: {e}") from e

    def read_journal(
        self,
        handle: Any,
        journal_id: int,
        start_usn: int,
        reason_mask: int,
        buffer_size: int = 65536,
    ) -> bytes:
        try:
            # READ_USN_JOURNAL_DATA_V0 : 40 octets
            # StartUsn (q), ReasonMask (I), ReturnOnlyOnClose (I), Timeout (Q), BytesToWaitFor (Q), UsnJournalID (Q)
            in_buf = struct.pack(
                "<qIIQQQ",
                start_usn,
                reason_mask,
                0,  # ReturnOnlyOnClose = 0
                0,  # Timeout = 0
                0,  # BytesToWaitFor = 0
                journal_id,
            )
            out_buf = self._win32.DeviceIoControl(
                handle,
                FSCTL_READ_USN_JOURNAL,
                in_buf,
                buffer_size,
                None,
            )
            return bytes(out_buf)
        except Exception as e:
            raise UsnError(f"Échec FSCTL_READ_USN_JOURNAL: {e}") from e

    def create_or_resize_journal(
        self,
        handle: Any,
        max_size_bytes: int,
        allocation_delta_bytes: int,
    ) -> None:
        try:
            # CREATE_USN_JOURNAL_DATA : 16 octets
            # MaximumSize (Q), AllocationDelta (Q)
            in_buf = struct.pack("<QQ", max_size_bytes, allocation_delta_bytes)
            self._win32.DeviceIoControl(
                handle,
                FSCTL_CREATE_USN_JOURNAL,
                in_buf,
                0,
                None,
            )
        except Exception as e:
            raise UsnError(f"Échec FSCTL_CREATE_USN_JOURNAL: {e}") from e


class MockUsnIoctlBackend(UsnIoctlBackend):
    """Backend de simulation pour les tests unitaires et plateformes de dev."""

    def __init__(self, initial_journal: Optional[UsnJournalData] = None) -> None:
        self.journal_data = initial_journal or UsnJournalData(
            journal_id=123456789,
            first_usn=1000,
            next_usn=50000,
            max_size=256 * 1024 * 1024,
            allocation_delta=32 * 1024 * 1024,
        )
        self.records_to_return: list[bytes] = []
        self.created_sizes: list[tuple[int, int]] = []

    def open_volume(self, volume_path: str) -> Any:
        return "mock_handle"

    def close_volume(self, handle: Any) -> None:
        pass

    def query_journal(self, handle: Any) -> UsnJournalData:
        return self.journal_data

    def read_journal(
        self,
        handle: Any,
        journal_id: int,
        start_usn: int,
        reason_mask: int,
        buffer_size: int = 65536,
    ) -> bytes:
        if self.records_to_return:
            return self.records_to_return.pop(0)
        # Par défaut, retourner un buffer avec seulement le NextUsn (8 octets)
        return struct.pack("<q", start_usn)

    def create_or_resize_journal(
        self,
        handle: Any,
        max_size_bytes: int,
        allocation_delta_bytes: int,
    ) -> None:
        self.created_sizes.append((max_size_bytes, allocation_delta_bytes))
        self.journal_data = UsnJournalData(
            journal_id=self.journal_data.journal_id,
            first_usn=self.journal_data.first_usn,
            next_usn=self.journal_data.next_usn,
            max_size=max_size_bytes,
            allocation_delta=allocation_delta_bytes,
        )


class UsnJournalReader:
    """Gestionnaire de détection et lecture du journal USN (EF-04, D3)."""

    def __init__(
        self,
        volume: str,
        state_db: StateDB,
        config: OrionConfig,
        backend: Optional[UsnIoctlBackend] = None,
    ) -> None:
        self.volume = volume.upper().rstrip("\\")
        if not self.volume.endswith(":"):
            self.volume += ":"
        self.state_db = state_db
        self.config = config

        if backend is not None:
            self.backend = backend
        elif sys.platform == "win32":
            self.backend = Win32UsnIoctlBackend()
        else:
            self.backend = MockUsnIoctlBackend()

    def ensure_journal_sizing(self) -> None:
        """CDC EF-04 : Dimensionnement initial du journal USN (défaut 256 Mo)."""
        target_size_bytes = self.config.usn_journal_size_mb * 1024 * 1024
        alloc_delta_bytes = max(target_size_bytes // 8, 16 * 1024 * 1024)

        handle = self.backend.open_volume(self.volume)
        try:
            current = self.backend.query_journal(handle)
            if current.max_size < target_size_bytes:
                logger.info(
                    "Dimensionnement journal USN sur %s: %d Mo -> %d Mo",
                    self.volume,
                    current.max_size // (1024 * 1024),
                    self.config.usn_journal_size_mb,
                )
                self.backend.create_or_resize_journal(handle, target_size_bytes, alloc_delta_bytes)
        finally:
            self.backend.close_volume(handle)

    def check_rotation_and_capacity(self) -> tuple[bool, str, float]:
        """Vérifie la rotation du journal et le taux d'utilisation de la capacité.

        Retourne un tuple :
        (rotation_detectee: bool, raison_rotation: str, utilisation_pct: float)
        """
        handle = self.backend.open_volume(self.volume)
        try:
            current = self.backend.query_journal(handle)
        finally:
            self.backend.close_volume(handle)

        # Calcul du taux d'utilisation approximatif
        used_bytes = max(current.next_usn - current.first_usn, 0)
        utilization_pct = min(100.0, (used_bytes / max(current.max_size, 1)) * 100.0)

        # Récupération de l'état persisté
        progress = self.state_db.get_usn_progress(self.volume)
        if progress is None:
            # Premier démarrage sur ce volume : initialisation de l'état
            self.state_db.set_usn_progress(self.volume, current.next_usn, current.journal_id)
            return (False, "", utilization_pct)

        # Règle 1 de rotation : L'identifiant du journal a changé (EF-04)
        if progress.journal_id != current.journal_id:
            msg = (
                f"Identifiant de journal modifié (précédent: {progress.journal_id}, "
                f"actuel: {current.journal_id})"
            )
            return (True, msg, utilization_pct)

        # Règle 2 de rotation : Le dernier USN traité a été tronqué (EF-04)
        if progress.last_usn < current.first_usn:
            msg = (
                f"Dépassement de capacité journal (dernier USN traité: {progress.last_usn}, "
                f"premier USN valide: {current.first_usn})"
            )
            return (True, msg, utilization_pct)

        return (False, "", utilization_pct)

    def read_pending_records(
        self,
        reason_mask: int = UsnReason.BACKUP_RELEVANT,
    ) -> Iterator[UsnRecord]:
        """Lit les nouveaux enregistrements USN depuis le dernier USN persisté.

        Met à jour la progression dans la base d'état après chaque lot d'enregistrements.
        """
        handle = self.backend.open_volume(self.volume)
        try:
            current = self.backend.query_journal(handle)
            progress = self.state_db.get_usn_progress(self.volume)

            start_usn = progress.last_usn if progress else current.next_usn
            journal_id = current.journal_id

            # Lecture séquentielle par tampons
            while True:
                buf = self.backend.read_journal(
                    handle=handle,
                    journal_id=journal_id,
                    start_usn=start_usn,
                    reason_mask=reason_mask,
                )

                if len(buf) < 8:
                    break

                # Les 8 premiers octets contiennent le NextUsn à interroger
                (next_usn_in_stream,) = struct.unpack("<q", buf[:8])

                # Si aucun enregistrement n'a été retourné au-delà de NextUsn
                if len(buf) == 8 or next_usn_in_stream == start_usn:
                    break

                offset = 8
                records_batch: list[UsnRecord] = []

                while offset + 60 <= len(buf):
                    # En-tête USN_RECORD_V2 (60 octets)
                    (
                        rec_len,
                        major_ver,
                        minor_ver,
                        file_ref,
                        parent_ref,
                        usn,
                        timestamp_raw,
                        reason,
                        _,
                        _,
                        _,
                        name_len,
                        name_offset,
                    ) = struct.unpack("<IHHQQqqIIIIHH", buf[offset : offset + 60])

                    if rec_len == 0 or major_ver != 2:
                        break

                    # Extraction du nom de fichier (UTF-16LE)
                    name_start = offset + name_offset
                    name_end = name_start + name_len
                    if name_end <= len(buf):
                        filename = buf[name_start:name_end].decode("utf-16-le", errors="replace")
                    else:
                        filename = ""

                    dt = filetime_to_datetime(timestamp_raw)
                    rec = UsnRecord(
                        usn=usn,
                        filename=filename,
                        file_reference_number=file_ref,
                        parent_file_reference_number=parent_ref,
                        reason=reason,
                        timestamp=dt,
                    )
                    records_batch.append(rec)
                    yield rec

                    offset += rec_len

                # Mise à jour de la progression
                start_usn = next_usn_in_stream
                self.state_db.set_usn_progress(self.volume, start_usn, journal_id)
                if records_batch:
                    self.state_db.record_usn_metrics(self.volume, len(records_batch))

        finally:
            self.backend.close_volume(handle)


def pack_mock_usn_record_v2(
    usn: int,
    filename: str,
    file_ref: int = 1000,
    parent_ref: int = 500,
    reason: int = UsnReason.DATA_OVERWRITE | UsnReason.CLOSE,
) -> bytes:
    """Utilitaire de test : génère un tampon binaire USN_RECORD_V2 valide."""
    name_bytes = filename.encode("utf-16-le")
    name_len = len(name_bytes)
    name_offset = 60
    rec_len = (name_offset + name_len + 7) & ~7  # Alignement 8 octets
    padding = b"\x00" * (rec_len - (name_offset + name_len))

    # FILETIME actuel
    now_ft = int((datetime.datetime.now(datetime.timezone.utc).timestamp() * 1_000_000 + FILETIME_EPOCH_DIFF_US) * 10)

    header = struct.pack(
        "<IHHQQqqIIIIHH",
        rec_len,
        2,  # MajorVersion = 2
        0,  # MinorVersion = 0
        file_ref,
        parent_ref,
        usn,
        now_ft,
        reason,
        0,  # SourceInfo
        0,  # SecurityId
        0,  # FileAttributes
        name_len,
        name_offset,
    )
    return header + name_bytes + padding
