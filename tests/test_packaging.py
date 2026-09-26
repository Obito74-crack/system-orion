"""Tests de conformité pour les scripts et fichiers de packaging (CDC ET-01, EF-02)."""

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent.parent / "packaging"
SPEC_FILE = PACKAGING_DIR / "systemorion.spec"
ISS_FILE = PACKAGING_DIR / "installer.iss"
WXS_FILE = PACKAGING_DIR / "systemorion.wxs"
BUILD_FILE = PACKAGING_DIR / "build.py"


def _load_build_module():
    """Charge build.py comme module pour tester ses fonctions internes."""
    spec = importlib.util.spec_from_file_location("build", BUILD_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packaging_files_exist() -> None:
    """Vérifie la présence de tous les fichiers de packaging."""
    assert SPEC_FILE.exists(), "Fichier systemorion.spec manquant"
    assert ISS_FILE.exists(), "Fichier installer.iss manquant"
    assert WXS_FILE.exists(), "Fichier systemorion.wxs manquant"
    assert BUILD_FILE.exists(), "Fichier build.py manquant"


def test_spec_file_content() -> None:
    """Vérifie que la spécification PyInstaller déclare les deux exécutables attendus."""
    content = SPEC_FILE.read_text(encoding="utf-8")
    assert "SystemOrionService" in content
    assert "SystemOrionAdmin" in content
    assert "service.py" in content
    assert "main_window.py" in content


def test_spec_upx_disabled() -> None:
    """Vérifie que UPX est désactivé pour éviter les faux positifs EDR (D10)."""
    content = SPEC_FILE.read_text(encoding="utf-8")
    assert "upx=False" in content, "UPX doit être désactivé pour éviter les faux positifs EDR"


def test_inno_setup_file_content() -> None:
    """Vérifie la configuration de l'installateur Inno Setup."""
    content = ISS_FILE.read_text(encoding="utf-8")
    assert "AppName=System Orion" in content or 'MyAppName "System Orion"' in content
    assert "SystemOrion" in content
    assert "--install" in content
    assert "--remove" in content
    assert "uninsdeletekeyifempty" in content
    assert "SOFTWARE\\SystemOrion" in content


def test_wix_file_validity() -> None:
    """Vérifie la validité XML du fichier WiX MSI et la définition du service Windows."""
    tree = ET.parse(WXS_FILE)
    root = tree.getroot()
    assert "Wix" in root.tag

    ns = {"w": "http://schemas.microsoft.com/wix/2006/wi"}
    service_installs = root.findall(".//w:ServiceInstall", ns)
    assert len(service_installs) >= 1
    assert service_installs[0].attrib.get("Name") == "SystemOrion"

    reg_keys = root.findall(".//w:RegistryKey", ns)
    assert any(k.attrib.get("Key") == r"SOFTWARE\SystemOrion" for k in reg_keys)


def test_build_get_version() -> None:
    """Vérifie que get_version() retourne la version du projet."""
    build = _load_build_module()
    version = build.get_version()
    assert isinstance(version, str)
    assert len(version) > 0
    assert "." in version


def test_build_check_prerequisites() -> None:
    """Vérifie que check_prerequisites() retourne une liste."""
    build = _load_build_module()
    missing = build.check_prerequisites()
    assert isinstance(missing, list)
