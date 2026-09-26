"""Test d'intégration : sauvegarde complète vers un drive (dossier local).

Simule un scénario réaliste :
1. Création de fichiers sources dans un dossier cible
2. Configuration du backend Drive
3. Mise en file + transfert via BackupEngine
4. Vérification des fichiers versionnés sur le drive
5. Application de la rétention
"""

import os
import time
from pathlib import Path

from systemorion.backup import BackupEngine
from systemorion.config import ConfigManager, DictRegistryBackend
from systemorion.logging_agent import OrionLogger
from systemorion.models import OrionConfig
from systemorion.state import StateDB
from systemorion.storage_backend import DriveStorageBackend


def test_drive_backup_end_to_end(tmp_path: Path) -> None:
    """Scénario complet : détection → file → transfert → versioning → rétention."""
    # 1. Arborescence source (simule ~/Documents)
    source_dir = tmp_path / "home" / "Documents"
    source_dir.mkdir(parents=True)
    (source_dir / "rapport.docx").write_text("contenu original")
    (source_dir / "notes.txt").write_text("notes importantes")
    (source_dir / "data.csv").write_text("a,b,c\n1,2,3")

    # 2. Drive cible (simule Google Drive / OneDrive)
    drive_root = tmp_path / "Drive"

    # 3. Configuration
    backend_reg = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend_reg)
    config = OrionConfig(
        target_paths=[str(source_dir)],
        storage_type="drive",
        drive_path=str(drive_root),
        backup_subfolder="SystemOrion",
        retention_max_versions=2,
        retention_max_days=90,
    )

    # 4. Initialisation des composants
    state_db = StateDB(db_path=str(tmp_path / "state.db"))
    logger = OrionLogger(log_dir=str(tmp_path / "logs"))
    drive_backend = DriveStorageBackend(drive_root)
    engine = BackupEngine(state_db=state_db, config=config, orion_logger=logger, storage_backend=drive_backend)

    # 5. Mise en file (simule la détection USN)
    for f in source_dir.iterdir():
        dest = drive_backend.resolve_destination(str(f), str(source_dir), config.backup_subfolder)
        engine.enqueue_file(str(f), dest, f.stat().st_size)

    # 6. Transfert
    stats = engine.process_queue(batch_limit=50)
    assert stats.files_saved == 3
    assert stats.files_errored == 0
    assert stats.bytes_transferred > 0

    # 7. Vérification des fichiers versionnés
    backup_dir = drive_root / "SystemOrion"
    assert backup_dir.is_dir()
    versioned_files = list(backup_dir.iterdir())
    assert len(versioned_files) == 3

    # Les fichiers doivent avoir un tag de version __YYYYMMDD_HHMM
    for f in versioned_files:
        assert "__" in f.name
        assert f.stat().st_size > 0

    # 8. Modification d'un fichier → nouvelle version
    time.sleep(1.1)  # Assure un tag de version différent (précision à la seconde)
    (source_dir / "rapport.docx").write_text("contenu modifié v2")
    state_db.reset_copying_to_pending()

    # Re-mise en file du fichier modifié
    modified = source_dir / "rapport.docx"
    dest = drive_backend.resolve_destination(str(modified), str(source_dir), config.backup_subfolder)
    engine.enqueue_file(str(modified), dest, modified.stat().st_size)

    stats2 = engine.process_queue(batch_limit=50)
    assert stats2.files_saved == 1

    # 9. Vérification : 2 versions de rapport.docx
    rapport_versions = [f for f in backup_dir.iterdir() if f.name.startswith("rapport")]
    assert len(rapport_versions) == 2

    # 10. Rétention : max 2 versions → pas de changement encore
    pruned = engine.apply_retention()
    assert pruned == 0

    # 11. 3ème version → la plus ancienne doit être purgée
    time.sleep(1.1)  # Assure un tag de version différent
    (source_dir / "rapport.docx").write_text("contenu modifié v3")
    state_db.reset_copying_to_pending()
    modified = source_dir / "rapport.docx"
    dest = drive_backend.resolve_destination(str(modified), str(source_dir), config.backup_subfolder)
    engine.enqueue_file(str(modified), dest, modified.stat().st_size)
    engine.process_queue(batch_limit=50)

    pruned = engine.apply_retention()
    assert pruned == 1

    # Il ne doit rester que 2 versions de rapport.docx
    rapport_versions = [f for f in backup_dir.iterdir() if f.name.startswith("rapport")]
    assert len(rapport_versions) == 2

    # 12. Vérification contenu préservé
    contents = [f.read_text() for f in rapport_versions]
    assert any("v2" in c or "v3" in c for c in contents)

    state_db.close()
