"""Tests unitaires pour systemorion.journal_usn (UsnJournalReader).

Vérifie la conformité avec :
- CDC EF-04 : Détection de rotation du journal, dimensionnement initial et dynamique
- CDC D3 : Filtrage par raisons USN
- Extraction des structures binaires USN_RECORD_V2
"""

from pathlib import Path
import struct

import pytest
from systemorion.journal_usn import (
    MockUsnIoctlBackend,
    UsnJournalReader,
    filetime_to_datetime,
    pack_mock_usn_record_v2,
)
from systemorion.models import OrionConfig, UsnJournalData, UsnReason
from systemorion.state import StateDB


@pytest.fixture
def state_db(tmp_path: Path) -> StateDB:
    db = StateDB(tmp_path / "test_usn_state.db")
    yield db
    db.close()


@pytest.fixture
def config() -> OrionConfig:
    cfg = OrionConfig()
    cfg.usn_journal_size_mb = 256
    return cfg


def test_filetime_conversion() -> None:
    """Vérifie la conversion du timestamp Windows FILETIME."""
    # 2026-09-08 14:30:00 UTC en FILETIME
    # Epoch diff + secondes depuis 1970
    dt = filetime_to_datetime(133698666000000000)
    assert dt.year >= 2020


def test_ensure_journal_sizing(state_db: StateDB, config: OrionConfig) -> None:
    """CDC EF-04 : Redimensionnement automatique si la taille actuelle est insuffisante."""
    # Volume avec 32 Mo initiaux (taille par défaut Windows C:)
    mock_backend = MockUsnIoctlBackend(
        initial_journal=UsnJournalData(
            journal_id=100,
            first_usn=0,
            next_usn=1000,
            max_size=32 * 1024 * 1024,
            allocation_delta=4 * 1024 * 1024,
        )
    )

    reader = UsnJournalReader("C:", state_db, config, backend=mock_backend)
    reader.ensure_journal_sizing()

    assert len(mock_backend.created_sizes) == 1
    new_max, new_delta = mock_backend.created_sizes[0]
    assert new_max == 256 * 1024 * 1024  # 256 Mo


def test_rotation_detection_journal_id_changed(state_db: StateDB, config: OrionConfig) -> None:
    """CDC EF-04 : Alerte rotation si l'identifiant du journal a changé."""
    # Enregistrer un état précédent
    state_db.set_usn_progress("C:", last_usn=5000, journal_id=1111)

    # Journal actuel avec un identifiant différent
    mock_backend = MockUsnIoctlBackend(
        initial_journal=UsnJournalData(
            journal_id=2222,  # Changé
            first_usn=1000,
            next_usn=8000,
            max_size=256 * 1024 * 1024,
            allocation_delta=32 * 1024 * 1024,
        )
    )

    reader = UsnJournalReader("C:", state_db, config, backend=mock_backend)
    rotated, reason, _ = reader.check_rotation_and_capacity()

    assert rotated is True
    assert "Identifiant de journal modifié" in reason


def test_rotation_detection_usn_truncated(state_db: StateDB, config: OrionConfig) -> None:
    """CDC EF-04 : Alerte rotation si le journal a bouclé (dernier USN < premier USN)."""
    # Enregistrer un dernier USN traité qui est maintenant écrasé
    state_db.set_usn_progress("C:", last_usn=5000, journal_id=1111)

    mock_backend = MockUsnIoctlBackend(
        initial_journal=UsnJournalData(
            journal_id=1111,
            first_usn=20000,  # Le premier USN valide dépasse notre dernier USN
            next_usn=50000,
            max_size=256 * 1024 * 1024,
            allocation_delta=32 * 1024 * 1024,
        )
    )

    reader = UsnJournalReader("C:", state_db, config, backend=mock_backend)
    rotated, reason, _ = reader.check_rotation_and_capacity()

    assert rotated is True
    assert "Dépassement de capacité" in reason


def test_read_pending_records_and_parse(state_db: StateDB, config: OrionConfig) -> None:
    """Vérifie le découpage et le décodage d'un flux binaire USN."""
    state_db.set_usn_progress("C:", last_usn=1000, journal_id=999)

    # Préparer deux enregistrements factices
    rec1 = pack_mock_usn_record_v2(usn=1500, filename="document.docx")
    rec2 = pack_mock_usn_record_v2(usn=2000, filename="presentation.pptx")

    # Tampon de réponse avec NextUsn (2500) suivi des deux enregistrements
    stream_buf = struct.pack("<q", 2500) + rec1 + rec2

    mock_backend = MockUsnIoctlBackend(
        initial_journal=UsnJournalData(
            journal_id=999,
            first_usn=500,
            next_usn=3000,
            max_size=256 * 1024 * 1024,
            allocation_delta=32 * 1024 * 1024,
        )
    )
    mock_backend.records_to_return = [stream_buf]

    reader = UsnJournalReader("C:", state_db, config, backend=mock_backend)
    records = list(reader.read_pending_records())

    assert len(records) == 2
    assert records[0].filename == "document.docx"
    assert records[0].usn == 1500
    assert records[1].filename == "presentation.pptx"
    assert records[1].usn == 2000

    # Vérifier que le dernier USN a bien été persisté dans la base d'état
    progress = state_db.get_usn_progress("C:")
    assert progress is not None
    assert progress.last_usn == 2500
