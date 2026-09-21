"""Gestionnaire de clichés instantanés VSS (EF-06, D4).

Création et suppression de clichés instantanés du volume système via WMI
(classe Win32_ShadowCopy, contexte ClientAccessible).
Garanties :
- Context manager avec suppression assurée du cliché (__exit__ garanti)
- Verrou global d'exclusion mutuelle : un seul cliché actif à la fois (section 8)
- Mécanisme de repli avec retry espacé (3 tentatives) en cas d'échec VSS
- Abstraction injectable pour tests hors environnement Windows
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from systemorion.models import VssError

logger = logging.getLogger("systemorion.vss")

# Verrou global : un seul cliché VSS actif à la fois sur le système (section 8)
_GLOBAL_VSS_LOCK = threading.Lock()


class VssBackend(ABC):
    """Interface d'interaction avec le service VSS."""

    @abstractmethod
    def create_snapshot(self, volume_path: str) -> tuple[str, str]:
        r"""Crée un cliché instantané.

        Retourne un tuple : (snapshot_id: str, device_object_path: str)
        Ex: ('{UUID}', r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1')
        """
        ...

    @abstractmethod
    def delete_snapshot(self, snapshot_id: str) -> None:
        """Supprime le cliché instantané spécifié."""
        ...


class WmiVssBackend(VssBackend):
    """Backend natif Windows utilisant la classe WMI Win32_ShadowCopy (ET-01)."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise VssError("WmiVssBackend n'est supporté que sous Windows.")
        import win32com.client  # type: ignore

        self._wmi_locator = win32com.client.Dispatch("WbemScripting.SWbemLocator")
        self._wmi = self._wmi_locator.ConnectServer(".", "root\\cimv2")

    def create_snapshot(self, volume_path: str) -> tuple[str, str]:
        vol = volume_path.rstrip("\\")
        if not vol.endswith("\\"):
            vol += "\\"

        try:
            shadow_class = self._wmi.Get("Win32_ShadowCopy")
            in_params = shadow_class.Methods_("Create").InParameters.SpawnInstance_()
            in_params.Volume = vol
            in_params.Context = "ClientAccessible"

            out_params = shadow_class.ExecMethod_("Create", in_params)
            ret_val = out_params.ReturnValue

            if ret_val != 0:
                raise VssError(f"Échec création cliché VSS sur {vol}, code retour WMI: {ret_val}")

            shadow_id = out_params.ShadowID
            # Récupération du DeviceObject du cliché créé
            instances = self._wmi.ExecQuery(f"SELECT DeviceObject FROM Win32_ShadowCopy WHERE ID = '{shadow_id}'")
            device_object = ""
            for item in instances:
                device_object = item.DeviceObject
                break

            if not device_object:
                raise VssError(f"Cliché VSS {shadow_id} introuvable après création")

            return (shadow_id, device_object)
        except Exception as e:
            raise VssError(f"Erreur WMI VSS sur {vol}: {e}") from e

    def delete_snapshot(self, snapshot_id: str) -> None:
        try:
            instances = self._wmi.ExecQuery(f"SELECT * FROM Win32_ShadowCopy WHERE ID = '{snapshot_id}'")
            for item in instances:
                item.Delete_()
                logger.debug("Cliché VSS %s supprimé avec succès", snapshot_id)
                return
        except Exception as e:
            logger.warning("Erreur lors de la suppression du cliché VSS %s: %s", snapshot_id, e)


class MockVssBackend(VssBackend):
    """Backend de simulation VSS pour les tests unitaires et environnements hors Windows."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.created_snapshots: dict[str, str] = {}
        self.deleted_snapshots: list[str] = []
        self._counter = 1

    def create_snapshot(self, volume_path: str) -> tuple[str, str]:
        if self.should_fail:
            raise VssError("Simulation d'échec VSS (ex: quota d'espace disque dépassé)")
        snap_id = f"{{MOCK-VSS-UUID-{self._counter}}}"
        device_path = rf"\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy{self._counter}"
        self.created_snapshots[snap_id] = device_path
        self._counter += 1
        return (snap_id, device_path)

    def delete_snapshot(self, snapshot_id: str) -> None:
        if snapshot_id in self.created_snapshots:
            del self.created_snapshots[snapshot_id]
        self.deleted_snapshots.append(snapshot_id)


class VssSnapshot:
    """Gestionnaire de contexte pour la création et la libération garantie d'un cliché VSS (EF-06).

    Utilisation :
        with VssSnapshot(volume="C:") as snapshot_device_path:
            # Lire les fichiers depuis snapshot_device_path
            ...
        # Le cliché est automatiquement supprimé ici.
    """

    def __init__(
        self,
        volume: str = "C:",
        backend: VssBackend | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.volume = volume.upper().rstrip("\\")
        if not self.volume.endswith("\\"):
            self.volume += "\\"
        self.timeout_seconds = timeout_seconds

        if backend is not None:
            self.backend = backend
        elif sys.platform == "win32":
            self.backend = WmiVssBackend()
        else:
            self.backend = MockVssBackend()

        self.snapshot_id: str | None = None
        self.device_path: str | None = None
        self._lock_acquired = False

    def __enter__(self) -> str:
        # Acquisition du verrou exclusif pour éviter les conflits de clichés concurrents
        acquired = _GLOBAL_VSS_LOCK.acquire(timeout=self.timeout_seconds)
        if not acquired:
            raise VssError(f"Délai d'attente dépassé ({self.timeout_seconds}s) pour acquérir le verrou VSS")
        self._lock_acquired = True

        try:
            self.snapshot_id, self.device_path = self.backend.create_snapshot(self.volume)
            logger.info("Cliché VSS actif sur %s: %s (%s)", self.volume, self.snapshot_id, self.device_path)
            return self.device_path
        except Exception:
            # En cas d'échec à la création, relâcher immédiatement le verrou
            if self._lock_acquired:
                _GLOBAL_VSS_LOCK.release()
                self._lock_acquired = False
            raise

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if self.snapshot_id is not None:
                self.backend.delete_snapshot(self.snapshot_id)
                logger.info("Cliché VSS %s libéré", self.snapshot_id)
        finally:
            self.snapshot_id = None
            self.device_path = None
            if self._lock_acquired:
                _GLOBAL_VSS_LOCK.release()
                self._lock_acquired = False


def execute_with_vss_fallback(
    source_file: str,
    action_fn: Callable[[str], Any],
    vss_volume: str | None = "C:",
    vss_backend: VssBackend | None = None,
    max_retries: int = 3,
    retry_delay_s: float = 0.5,
) -> Any:
    """Tente d'exécuter une opération avec cliché VSS, ou bascule sur copie directe avec retry (EF-06).

    CDC EF-06 : En cas d'échec VSS, repli sur copie directe avec retry sur violation de partage
    (3 tentatives espacées).
    """
    # 1. Tentative avec VSS si disponible
    if vss_volume is not None:
        try:
            with VssSnapshot(volume=vss_volume, backend=vss_backend) as snap_device:
                # Transposition du chemin source vers le chemin du cliché
                # Ex: C:\Users\Alice\file.txt -> \\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\Users\Alice\file.txt
                drive, rel_path = os.path.splitdrive(source_file)
                vss_source = os.path.join(snap_device, rel_path.lstrip(r"\/"))
                return action_fn(vss_source)
        except VssError as e:
            logger.warning("VSS indisponible (%s), repli sur copie directe avec retries", e)

    # 2. Repli sur copie directe avec retries sur verrouillage (EF-06)
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return action_fn(source_file)
        except (PermissionError, OSError) as e:
            last_err = e
            logger.debug("Tentative %d/%d échouée pour %s: %s", attempt, max_retries, source_file, e)
            if attempt < max_retries:
                time.sleep(retry_delay_s * attempt)

    raise VssError(f"Impossible d'accéder au fichier '{source_file}' après {max_retries} tentatives: {last_err}") from last_err
