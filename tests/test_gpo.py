"""Tests de validation syntaxique et sémantique des modèles GPO (ADMX / ADML).

Vérifie :
- Validité XML de SystemOrion.admx et SystemOrion.adml (CDC EF-02)
- Correspondance stricte entre les clés de registre de l'ADMX et celles de ConfigManager
- Présence de toutes les chaînes et présentations requises dans l'ADML
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from systemorion.config import GPO_POLICY_KEY

GPO_DIR = Path(__file__).resolve().parent.parent / "gpo"
ADMX_FILE = GPO_DIR / "SystemOrion.admx"
ADML_FILE = GPO_DIR / "fr-FR" / "SystemOrion.adml"


def test_gpo_files_exist() -> None:
    """Vérifie que les fichiers de stratégie GPO sont présents."""
    assert ADMX_FILE.exists(), f"Fichier introuvable : {ADMX_FILE}"
    assert ADML_FILE.exists(), f"Fichier introuvable : {ADML_FILE}"


def test_admx_xml_validity() -> None:
    """Vérifie que SystemOrion.admx est un XML bien formé."""
    tree = ET.parse(ADMX_FILE)
    root = tree.getroot()
    assert "policyDefinitions" in root.tag


def test_adml_xml_validity() -> None:
    """Vérifie que SystemOrion.adml est un XML bien formé."""
    tree = ET.parse(ADML_FILE)
    root = tree.getroot()
    assert "policyDefinitionResources" in root.tag


def test_gpo_admx_keys_match_config_manager() -> None:
    """Vérifie que les clés et valeurs définies dans l'ADMX correspondent aux champs gérés par ConfigManager."""
    tree = ET.parse(ADMX_FILE)
    root = tree.getroot()

    # Espace de noms ADMX
    ns = {"p": "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"}

    # Vérification des politiques
    policies = root.findall(".//p:policy", ns)
    assert len(policies) >= 6

    expected_values = {
        "ManagedByGpo",
        "UncOverride",
        "BackupSubfolder",
        "TargetPaths",
        "ExcludedDirs",
        "ExclusionPatterns",
        "ExclusionExtensions",
        "RetentionMaxVersions",
        "RetentionMaxDays",
        "UsnJournalSizeMb",
        "UsnAlertThresholdPct",
        "UsnMinCoverageHours",
        "BandwidthLimitKbps",
        "ReconnectJitterMaxS",
        "BackoffInitialS",
        "BackoffMaxS",
        "CycleIntervalS",
    }

    found_values = set()
    for policy in policies:
        # Vérification de la clé de registre racine
        key = policy.attrib.get("key")
        assert key == GPO_POLICY_KEY, f"Clé incorrecte : {key} != {GPO_POLICY_KEY}"

        # Valeur directe
        val_name = policy.attrib.get("valueName")
        if val_name:
            found_values.add(val_name)

        # Valeurs dans les sous-éléments
        for el in policy.findall(".//p:elements/*", ns):
            el_val = el.attrib.get("valueName")
            if el_val:
                found_values.add(el_val)

    # Toutes les valeurs critiques attendues par ConfigManager doivent être couvertes
    missing = expected_values - found_values
    assert not missing, f"Valeurs manquantes dans l'ADMX : {missing}"


def test_adml_strings_cover_admx() -> None:
    """Vérifie que toutes les références $(string.XXX) et $(presentation.YYY) existent dans l'ADML."""
    admx_text = ADMX_FILE.read_text(encoding="utf-8")
    tree_adml = ET.parse(ADML_FILE)
    root_adml = tree_adml.getroot()
    ns = {"p": "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"}

    # Récolte des identifiants définis dans l'ADML
    string_ids = {s.attrib["id"] for s in root_adml.findall(".//p:stringTable/p:string", ns)}
    presentation_ids = {p.attrib["id"] for p in root_adml.findall(".//p:presentationTable/p:presentation", ns)}

    # Vérification des strings référencées dans l'ADMX
    import re

    used_strings = set(re.findall(r"\$\(string\.([A-Za-z0-9_]+)\)", admx_text))
    missing_strings = used_strings - string_ids
    assert not missing_strings, f"Identifiants string manquants dans l'ADML : {missing_strings}"

    # Vérification des présentations
    used_presentations = set(re.findall(r"\$\(presentation\.([A-Za-z0-9_]+)\)", admx_text))
    missing_pres = used_presentations - presentation_ids
    assert not missing_pres, f"Identifiants presentation manquants dans l'ADML : {missing_pres}"
