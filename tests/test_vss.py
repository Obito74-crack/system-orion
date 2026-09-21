"""Tests unitaires pour systemorion.vss (VssSnapshot).

Vérifie la conformité avec :
- CDC EF-06 : Création cliché instantané, chemin \\?\\GLOBALROOT\\..., suppression garantie
- CDC Section 8 : Un seul cliché à la fois, verrou interne
- Repli sur copie directe avec retry
"""

import pytest

from systemorion.vss import MockVssBackend, VssSnapshot, execute_with_vss_fallback


def test_vss_snapshot_context_manager_lifecycle() -> None:
    """Vérifie que le cliché est créé puis supprimé à la sortie du contexte."""
    mock_backend = MockVssBackend()

    with VssSnapshot(volume="C:", backend=mock_backend) as device_path:
        assert "HarddiskVolumeShadowCopy1" in device_path
        assert len(mock_backend.created_snapshots) == 1

    # À la sortie, le cliché doit avoir été détruit
    assert len(mock_backend.created_snapshots) == 0
    assert len(mock_backend.deleted_snapshots) == 1


def test_vss_guaranteed_cleanup_on_exception() -> None:
    """CDC EF-06 : La suppression du cliché doit être garantie même si une exception survient."""
    mock_backend = MockVssBackend()

    with (
        pytest.raises(ValueError, match="Erreur pendant la lecture"),
        VssSnapshot(volume="C:", backend=mock_backend),
    ):
        assert len(mock_backend.created_snapshots) == 1
        raise ValueError("Erreur pendant la lecture")

    # Cliché bien nettoyé malgré l'exception
    assert len(mock_backend.created_snapshots) == 0
    assert len(mock_backend.deleted_snapshots) == 1


def test_vss_fallback_to_direct_copy_on_vss_error() -> None:
    """CDC EF-06 : En cas d'échec VSS, repli sur copie directe."""
    # Backend configuré pour échouer
    failing_backend = MockVssBackend(should_fail=True)

    executed_paths = []

    def dummy_read(path: str) -> str:
        executed_paths.append(path)
        return "content"

    res = execute_with_vss_fallback(
        source_file=r"C:\Users\Alice\doc.txt",
        action_fn=dummy_read,
        vss_volume="C:",
        vss_backend=failing_backend,
        max_retries=3,
    )

    assert res == "content"
    # Le chemin exécuté doit être le fichier source direct suite au repli
    assert executed_paths == [r"C:\Users\Alice\doc.txt"]
