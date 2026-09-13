"""Tests unitaires pour systemorion.config (ConfigManager).

Vérifie la conformité avec :
- CDC D7 : Magasin unique de configuration HKLM\\SOFTWARE\\SystemOrion
- CDC EF-01a : Verrouillage GPO et réinitialisation par défaut
- CDC EF-02 : Précédence de la configuration GPO
"""

import pytest
from systemorion.config import (
    GPO_POLICY_KEY,
    REGISTRY_BASE_KEY,
    ConfigManager,
    DictRegistryBackend,
    expand_path,
)
from systemorion.models import ConfigError, OrionConfig


@pytest.fixture
def memory_backend() -> DictRegistryBackend:
    return DictRegistryBackend()


@pytest.fixture
def config_mgr(memory_backend: DictRegistryBackend) -> ConfigManager:
    return ConfigManager(backend=memory_backend)


def test_default_config_loading(config_mgr: ConfigManager) -> None:
    """Vérifie le chargement des valeurs par défaut lorsque le registre est vide."""
    cfg = config_mgr.load()
    assert isinstance(cfg, OrionConfig)
    assert r"~\Documents" in cfg.target_paths
    assert "*.tmp" in cfg.exclusion_patterns
    assert cfg.retention_max_versions == 10
    assert cfg.usn_journal_size_mb == 256
    assert cfg.managed_by_gpo is False


def test_save_and_reload(config_mgr: ConfigManager) -> None:
    """Vérifie la sérialisation et relecture de la configuration."""
    cfg = config_mgr.load()
    cfg.target_paths = [r"C:\Important", r"D:\Work"]
    cfg.retention_max_versions = 50
    cfg.unc_override = r"\\srv\custom_share"

    config_mgr.save(cfg)

    reloaded = config_mgr.load()
    assert reloaded.target_paths == [r"C:\Important", r"D:\Work"]
    assert reloaded.retention_max_versions == 50
    assert reloaded.unc_override == r"\\srv\custom_share"


def test_gpo_override_and_locking(memory_backend: DictRegistryBackend) -> None:
    """CDC D7 / EF-01a : Les règles GPO ont priorité et verrouillent l'écriture locale."""
    # 1. Config locale normale
    memory_backend.write_values(
        REGISTRY_BASE_KEY,
        {
            "RetentionMaxVersions": (15, 4),
            "UncOverride": ("\\\\srv\\local", 1),
        },
    )

    mgr = ConfigManager(backend=memory_backend)
    assert mgr.is_managed_by_gpo() is False
    assert mgr.load().retention_max_versions == 15

    # 2. Ajout de politique GPO
    memory_backend.write_values(
        GPO_POLICY_KEY,
        {
            "RetentionMaxVersions": (100, 4),
        },
    )

    assert mgr.is_managed_by_gpo() is True
    loaded = mgr.load()
    # GPO a pris le dessus sur la clé locale
    assert loaded.retention_max_versions == 100
    # Le champ non défini en GPO reste celui du local
    assert loaded.unc_override == "\\\\srv\\local"
    assert loaded.managed_by_gpo is True

    # 3. Tentative d'écriture locale refusée car verrouillée par GPO
    with pytest.raises(ConfigError, match="gérée par votre organisation"):
        mgr.save(loaded)


def test_reset_to_defaults(config_mgr: ConfigManager) -> None:
    """CDC EF-01a : Le bouton Réinitialiser remet les paramètres d'usine."""
    cfg = config_mgr.load()
    cfg.retention_max_versions = 999
    config_mgr.save(cfg)
    assert config_mgr.load().retention_max_versions == 999

    resetted = config_mgr.reset_to_defaults()
    assert resetted.retention_max_versions == 10
    assert config_mgr.load().retention_max_versions == 10


def test_expand_path() -> None:
    """Vérifie le remplacement de ~ et des variables d'environnement."""
    user_home = r"C:\Users\Bob"
    expanded = expand_path(r"~\Documents\file.txt", user_profile=user_home)
    assert expanded == r"C:\Users\Bob\Documents\file.txt"
