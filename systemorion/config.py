r"""Lecture/écriture du magasin de configuration unique.

Cf. CDC D7 : magasin unique (registre HKLM\SOFTWARE\SystemOrion) alimenté
soit par l'assistant manuel (EF-01/EF-01a), soit par GPO (EF-02, modèle ADMX).
Doit exposer un indicateur ManagedByGpo pour le verrouillage de l'UI (EF-01a).
Architecture DA-02 : abstraction de backend registre pour testabilité multi-plateforme.
"""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from typing import Any

from systemorion.models import ConfigError, OrionConfig

logger = logging.getLogger("systemorion.config")

REGISTRY_BASE_KEY = r"SOFTWARE\SystemOrion"
GPO_POLICY_KEY = r"SOFTWARE\Policies\SystemOrion"


class RegistryBackend(ABC):
    """Interface d'accès au magasin de registre (Windows ou mocké)."""

    @abstractmethod
    def read_values(self, key_path: str) -> dict[str, Any]:
        """Lit l'ensemble des valeurs (nom -> valeur) sous la clé HKLM spécifiée."""
        ...

    @abstractmethod
    def write_values(self, key_path: str, values: dict[str, tuple[Any, int]]) -> None:
        """Écrit des valeurs sous la clé HKLM spécifiée.

        values est un dict: nom -> (valeur, type_reg)
        type_reg correspond aux constantes winreg (1=SZ, 4=DWORD, 7=MULTI_SZ).
        """
        ...

    @abstractmethod
    def key_exists(self, key_path: str) -> bool:
        """Vérifie si la clé HKLM existe."""
        ...


class WinregBackend(RegistryBackend):
    """Implémentation concrète utilisant le module standard winreg sous Windows."""

    def __init__(self) -> None:
        self._winreg: Any = None
        if sys.platform != "win32":
            raise ConfigError("WinregBackend n'est supporté que sous Windows.")
        import winreg  # type: ignore

        self._winreg = winreg

    def key_exists(self, key_path: str) -> bool:
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_LOCAL_MACHINE, key_path, 0, self._winreg.KEY_READ):
                return True
        except (FileNotFoundError, OSError):
            return False

    def read_values(self, key_path: str) -> dict[str, Any]:
        values: dict[str, Any] = {}
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_LOCAL_MACHINE, key_path, 0, self._winreg.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        name, val, _ = self._winreg.EnumValue(key, index)
                        values[name] = val
                        index += 1
                    except OSError:
                        break
        except (FileNotFoundError, OSError):
            pass
        return values

    def write_values(self, key_path: str, values: dict[str, tuple[Any, int]]) -> None:
        try:
            with self._winreg.CreateKeyEx(
                self._winreg.HKEY_LOCAL_MACHINE,
                key_path,
                0,
                self._winreg.KEY_SET_VALUE | self._winreg.KEY_WRITE,
            ) as key:
                for name, (val, reg_type) in values.items():
                    self._winreg.SetValueEx(key, name, 0, reg_type, val)
        except OSError as e:
            raise ConfigError(f"Erreur d'écriture dans le registre HKLM\\{key_path}: {e}") from e


class DictRegistryBackend(RegistryBackend):
    """Backend en mémoire pour les tests et le développement non-Windows."""

    def __init__(self, initial_data: dict[str, dict[str, Any]] | None = None) -> None:
        self._store: dict[str, dict[str, Any]] = initial_data or {}

    def key_exists(self, key_path: str) -> bool:
        return key_path in self._store

    def read_values(self, key_path: str) -> dict[str, Any]:
        return dict(self._store.get(key_path, {}))

    def write_values(self, key_path: str, values: dict[str, tuple[Any, int]]) -> None:
        if key_path not in self._store:
            self._store[key_path] = {}
        for name, (val, _) in values.items():
            self._store[key_path][name] = val


class ConfigManager:
    """Gestionnaire de configuration unifié pour System Orion (D7).

    Gère le chargement, la sauvegarde et l'inspection de la configuration.
    Prend en compte la précédence de la stratégie GPO (Policies\\SystemOrion)
    sur la configuration locale (SOFTWARE\\SystemOrion).
    """

    # Types de registre winreg équivalents
    REG_SZ = 1
    REG_DWORD = 4
    REG_MULTI_SZ = 7

    def __init__(self, backend: RegistryBackend | None = None) -> None:
        if backend is not None:
            self._backend = backend
        elif sys.platform == "win32":
            self._backend = WinregBackend()
        else:
            self._backend = DictRegistryBackend()

    @property
    def backend(self) -> RegistryBackend:
        return self._backend

    def is_managed_by_gpo(self) -> bool:
        """Indique si la configuration est verrouillée par GPO (EF-01a, D7)."""
        # 1. Vérifie si la clé de stratégie de groupe existe
        if self._backend.key_exists(GPO_POLICY_KEY):
            return True
        # 2. Vérifie la valeur explicite ManagedByGpo dans la clé standard
        vals = self._backend.read_values(REGISTRY_BASE_KEY)
        return bool(vals.get("ManagedByGpo", 0))

    def load(self) -> OrionConfig:
        """Charge la configuration depuis le registre.

        Fusionne les valeurs par défaut avec la clé locale HKLM\\SOFTWARE\\SystemOrion
        et les surcharges éventuelles de GPO HKLM\\SOFTWARE\\Policies\\SystemOrion.
        """
        config = OrionConfig()

        # Lecture des clés registre
        local_vals = self._backend.read_values(REGISTRY_BASE_KEY)
        gpo_vals = self._backend.read_values(GPO_POLICY_KEY)

        # Les valeurs GPO ont priorité absolue sur les valeurs locales
        merged = {**local_vals, **gpo_vals}

        if not merged:
            logger.debug("Aucune configuration trouvée dans le registre, utilisation des valeurs par défaut.")
            return config

        try:
            if "TargetPaths" in merged:
                config.target_paths = list(merged["TargetPaths"])
            if "ExclusionPatterns" in merged:
                config.exclusion_patterns = list(merged["ExclusionPatterns"])
            if "ExclusionExtensions" in merged:
                config.exclusion_extensions = list(merged["ExclusionExtensions"])
            if "ExcludedDirs" in merged:
                config.excluded_dirs = list(merged["ExcludedDirs"])

            if "UncOverride" in merged and merged["UncOverride"]:
                config.unc_override = str(merged["UncOverride"])
            if "BackupSubfolder" in merged:
                config.backup_subfolder = str(merged["BackupSubfolder"])

            if "RetentionMaxVersions" in merged:
                config.retention_max_versions = int(merged["RetentionMaxVersions"])
            if "RetentionMaxDays" in merged:
                config.retention_max_days = int(merged["RetentionMaxDays"])

            if "UsnJournalSizeMb" in merged:
                config.usn_journal_size_mb = int(merged["UsnJournalSizeMb"])
            if "UsnAlertThresholdPct" in merged:
                config.usn_alert_threshold_pct = int(merged["UsnAlertThresholdPct"])
            if "UsnMinCoverageHours" in merged:
                config.usn_min_coverage_hours = int(merged["UsnMinCoverageHours"])

            if "BandwidthLimitKbps" in merged and merged["BandwidthLimitKbps"] > 0:
                config.bandwidth_limit_kbps = int(merged["BandwidthLimitKbps"])
            if "ReconnectJitterMaxS" in merged:
                config.reconnect_jitter_max_s = int(merged["ReconnectJitterMaxS"])
            if "BackoffInitialS" in merged:
                config.backoff_initial_s = int(merged["BackoffInitialS"])
            if "BackoffMaxS" in merged:
                config.backoff_max_s = int(merged["BackoffMaxS"])
            if "CycleIntervalS" in merged:
                config.cycle_interval_s = int(merged["CycleIntervalS"])

            config.managed_by_gpo = self.is_managed_by_gpo()

            if "LogDir" in merged:
                config.log_dir = str(merged["LogDir"])
            if "StateDbPath" in merged:
                config.state_db_path = str(merged["StateDbPath"])

        except (ValueError, TypeError) as e:
            raise ConfigError(f"Valeur invalide dans le registre de configuration: {e}") from e

        return config

    def save(self, config: OrionConfig) -> None:
        """Écrit la configuration dans HKLM\\SOFTWARE\\SystemOrion (EF-01a).

        Refuse l'écriture si la configuration est actuellement verrouillée par GPO.
        """
        if self.is_managed_by_gpo():
            raise ConfigError("Impossible de modifier la configuration : gérée par votre organisation (GPO).")

        values: dict[str, tuple[Any, int]] = {
            "TargetPaths": (config.target_paths, self.REG_MULTI_SZ),
            "ExclusionPatterns": (config.exclusion_patterns, self.REG_MULTI_SZ),
            "ExclusionExtensions": (config.exclusion_extensions, self.REG_MULTI_SZ),
            "ExcludedDirs": (config.excluded_dirs, self.REG_MULTI_SZ),
            "UncOverride": (config.unc_override or "", self.REG_SZ),
            "BackupSubfolder": (config.backup_subfolder, self.REG_SZ),
            "RetentionMaxVersions": (config.retention_max_versions, self.REG_DWORD),
            "RetentionMaxDays": (config.retention_max_days, self.REG_DWORD),
            "UsnJournalSizeMb": (config.usn_journal_size_mb, self.REG_DWORD),
            "UsnAlertThresholdPct": (config.usn_alert_threshold_pct, self.REG_DWORD),
            "UsnMinCoverageHours": (config.usn_min_coverage_hours, self.REG_DWORD),
            "BandwidthLimitKbps": (config.bandwidth_limit_kbps or 0, self.REG_DWORD),
            "ReconnectJitterMaxS": (config.reconnect_jitter_max_s, self.REG_DWORD),
            "BackoffInitialS": (config.backoff_initial_s, self.REG_DWORD),
            "BackoffMaxS": (config.backoff_max_s, self.REG_DWORD),
            "CycleIntervalS": (config.cycle_interval_s, self.REG_DWORD),
            "ManagedByGpo": (1 if config.managed_by_gpo else 0, self.REG_DWORD),
            "LogDir": (config.log_dir, self.REG_SZ),
            "StateDbPath": (config.state_db_path, self.REG_SZ),
        }

        self._backend.write_values(REGISTRY_BASE_KEY, values)
        logger.info("Configuration System Orion enregistrée avec succès dans le registre.")

    def reset_to_defaults(self) -> OrionConfig:
        """Réinitialise la configuration locale aux valeurs par défaut (EF-01a)."""
        defaults = OrionConfig()
        self.save(defaults)
        return defaults


def expand_path(path_template: str, user_profile: str | None = None) -> str:
    """Étend les variables de chemin comme ~ ou %USERPROFILE%."""
    if path_template.startswith("~"):
        base = user_profile or os.path.expanduser("~")
        suffix = path_template[1:].lstrip("\\/")
        sep = "\\" if "\\" in base or "\\" in path_template else "/"
        base_clean = base.rstrip("\\/")
        return f"{base_clean}{sep}{suffix}" if suffix else base
    return os.path.expandvars(path_template)
