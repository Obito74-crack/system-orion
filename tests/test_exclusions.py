"""Tests unitaires pour systemorion.exclusions (ExclusionEngine).

Vérifie la conformité avec :
- CDC EF-05 : Décision sauvegarder / ignorer
- CDC D2 : Sauvegarde ciblée (uniquement arborescences configurées)
- CDC EF-01a : Répertoires exclus par défaut (Corbeille, node_modules, etc.)
"""

import pytest
from systemorion.exclusions import ExclusionEngine
from systemorion.models import OrionConfig


@pytest.fixture
def config() -> OrionConfig:
    cfg = OrionConfig()
    cfg.target_paths = [
        r"C:\Users\Alice\Documents",
        r"C:\Users\Alice\Desktop",
    ]
    cfg.excluded_dirs = ["node_modules", ".git", "$RECYCLE.BIN", "AppData"]
    cfg.exclusion_patterns = ["*.tmp", "~$*", "thumbs.db", "desktop.ini"]
    cfg.exclusion_extensions = [".tmp", ".bak", ".log"]
    return cfg


@pytest.fixture
def engine(config: OrionConfig) -> ExclusionEngine:
    return ExclusionEngine(config=config, user_profile=r"C:\Users\Alice")


def test_valid_file_accepted(engine: ExclusionEngine) -> None:
    """Un fichier légitime dans Documents doit être sauvegardé."""
    exclude, reason = engine.should_exclude(r"C:\Users\Alice\Documents\report.docx", file_size=2048)
    assert exclude is False
    assert reason == ""


def test_out_of_target_excluded(engine: ExclusionEngine) -> None:
    r"""CDC D2 : Un fichier hors arborescence cible (ex: C:\Windows) doit être ignoré."""
    exclude, reason = engine.should_exclude(r"C:\Windows\System32\notepad.exe", file_size=1024)
    assert exclude is True
    assert "Hors arborescence cible" in reason


def test_excluded_directories(engine: ExclusionEngine) -> None:
    """CDC EF-05 : Les fichiers dans des répertoires exclus doivent être ignorés."""
    p1 = r"C:\Users\Alice\Documents\webproject\node_modules\package\index.js"
    exclude, reason = engine.should_exclude(p1, file_size=500)
    assert exclude is True
    assert "node_modules" in reason

    p2 = r"C:\Users\Alice\Documents\code\.git\config"
    exclude, reason = engine.should_exclude(p2, file_size=100)
    assert exclude is True
    assert ".git" in reason


def test_temporary_and_lock_patterns(engine: ExclusionEngine) -> None:
    """CDC EF-05 : Fichiers temporaires et verrous Office (~$*)."""
    # Verrou Office Word
    exclude, reason = engine.should_exclude(r"C:\Users\Alice\Documents\~$Budget2026.xlsx", file_size=165)
    assert exclude is True

    # Motif thumbs.db
    exclude, reason = engine.should_exclude(r"C:\Users\Alice\Desktop\Thumbs.db", file_size=1000)
    assert exclude is True

    # Extension .tmp
    exclude, reason = engine.should_exclude(r"C:\Users\Alice\Documents\temp_data.TMP", file_size=500)
    assert exclude is True


def test_zero_byte_files(engine: ExclusionEngine) -> None:
    """CDC EF-05 : Taille nulle non pertinente."""
    exclude, reason = engine.should_exclude(r"C:\Users\Alice\Documents\empty.txt", file_size=0)
    assert exclude is True
    assert "0 octet" in reason


def test_case_insensitivity(engine: ExclusionEngine) -> None:
    """Vérifie l'insensibilité à la casse Windows NTFS."""
    exclude, _ = engine.should_exclude(r"c:\users\alice\documents\REPORT.DOCX", file_size=1024)
    assert exclude is False
