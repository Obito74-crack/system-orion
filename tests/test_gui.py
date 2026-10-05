"""Tests unitaires pour l'interface graphique PySide6 / Qt6 (CDC EF-01a).

Vérifie la conformité avec :
- CDC EF-01a : Navigation à 2 écrans (QStackedWidget)
- CDC EF-01a : Verrouillage GPO automatique et bandeau d'avertissement
- CDC D7 : Écriture dans le registre au clic sur Sauvegarder
- Ajout, suppression et réinitialisation des dossiers
"""

import os
from pathlib import Path

import pytest

# Configuration obligatoire pour exécuter les tests Qt en environnement headless / CI
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox

from systemorion.cible_ad import MockAdDirectoryResolver
from systemorion.config import ConfigManager, DictRegistryBackend
from systemorion.gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Fixture de l'instance singleton QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def gui_window(qapp: QApplication) -> MainWindow:
    """Fixture fournissant une MainWindow initialisée avec backend mémoire."""
    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    resolver = MockAdDirectoryResolver(user_directories={"domaine\\utilisateur": r"\\srv\home\utilisateur"})
    window = MainWindow(config_mgr=cfg_mgr, ad_resolver=resolver)
    window.show()
    yield window
    window.close()


def test_two_screen_navigation_lifecycle(gui_window: MainWindow) -> None:
    """CDC EF-01a : Navigation entre l'écran principal et l'écran des dossiers."""
    # Au démarrage, nous sommes sur l'Écran 1 (Index 0)
    assert gui_window.stack.currentIndex() == 0

    # Clic sur « Gérer les dossiers et exclusions → »
    gui_window.btn_goto_folders.click()
    assert gui_window.stack.currentIndex() == 1

    # Clic sur « ← Retour »
    gui_window._on_back_to_main_screen()
    assert gui_window.stack.currentIndex() == 0


def test_initial_data_population(gui_window: MainWindow) -> None:
    """Vérifie le chargement des valeurs par défaut dans les contrôles UI."""
    assert r"\\srv\home\utilisateur" in gui_window.txt_server_addr.text()
    assert gui_window.txt_subfolder.text() == "SystemOrion"

    # Vérification des ListWidgets sur l'Écran 2
    targets_count = gui_window.list_targets.count()
    assert targets_count == len(gui_window.working_config.target_paths)

    ignored_count = gui_window.list_ignored.count()
    expected_ignored = len(gui_window.working_config.excluded_dirs) + len(gui_window.working_config.exclusion_patterns)
    assert ignored_count == expected_ignored


def test_folder_manipulation_screen_2(gui_window: MainWindow) -> None:
    """Vérifie l'ajout et la suppression d'éléments sur l'Écran 2."""
    initial_count = len(gui_window.working_config.target_paths)

    # Ajout d'un chemin personnalisé
    custom_path = r"C:\Data\Projets"
    gui_window.working_config.target_paths.append(custom_path)
    gui_window._refresh_lists_and_summary()

    assert gui_window.list_targets.count() == initial_count + 1
    assert "Projets" in gui_window.list_targets.item(initial_count).text()

    # Suppression du dernier élément
    gui_window.list_targets.setCurrentRow(initial_count)
    gui_window._delete_target_folder()
    assert gui_window.list_targets.count() == initial_count


def test_gpo_locking_behavior(qapp: QApplication) -> None:
    """CDC EF-01a & D7 : Verrouillage total de l'interface si ManagedByGpo est actif."""
    backend = DictRegistryBackend(
        initial_data={
            r"SOFTWARE\Policies\SystemOrion": {"RetentionMaxVersions": 50},
        }
    )
    cfg_mgr = ConfigManager(backend=backend)
    assert cfg_mgr.is_managed_by_gpo() is True

    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Le bandeau GPO doit être visible
    assert not window.gpo_banner.isHidden()
    # Le bouton Sauvegarder doit être désactivé
    assert window.btn_save.isEnabled() is False
    # Les boutons d'édition doivent être désactivés
    assert window.btn_add_target.isEnabled() is False
    assert window.btn_del_target.isEnabled() is False
    assert window.btn_reset_defaults.isEnabled() is False
    assert window.txt_server_addr.isReadOnly() is True

    window.close()


def test_save_persists_to_config_backend(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    """CDC EF-01a : Le clic sur Sauvegarder persiste la configuration dans le registre."""
    # Mocker les boîtes de dialogue modales pour éviter le blocage
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Save)

    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Modification d'un champ
    window.txt_subfolder.setText("SauvegardeCustom")
    window.working_config.target_paths.append(str(tmp_path / "MonDossier"))

    # Déclenchement de la sauvegarde
    window._on_save_clicked()

    # Relecture depuis le backend
    saved_cfg = cfg_mgr.load()
    assert saved_cfg.backup_subfolder == "SauvegardeCustom"
    assert any("MonDossier" in p for p in saved_cfg.target_paths)

    window.close()


def test_save_drive_storage_type(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    """Le mode Drive est sauvegardé avec storage_type='drive' et drive_path."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Save)

    # Créer un dossier drive factice
    drive_dir = tmp_path / "GoogleDrive"
    drive_dir.mkdir()

    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Sélectionner le mode Drive
    idx = window.combo_location.findData("drive")
    assert idx >= 0, "L'option Drive doit être présente dans le combo"
    window.combo_location.setCurrentIndex(idx)

    # Définir le chemin drive
    window.txt_server_addr.setText(str(drive_dir))
    window.txt_subfolder.setText("SystemOrion")

    # Sauvegarder
    window._on_save_clicked()

    # Vérification
    saved_cfg = cfg_mgr.load()
    assert saved_cfg.storage_type == "drive"
    assert saved_cfg.drive_path == str(drive_dir)
    assert saved_cfg.unc_override is None

    window.close()


def test_drive_browse_button_visible_only_in_drive_mode(qapp: QApplication) -> None:
    """Le bouton Parcourir est visible uniquement en mode Drive."""
    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Mode SMB par défaut : bouton masqué
    idx_smb = window.combo_location.findData("smb")
    window.combo_location.setCurrentIndex(idx_smb)
    assert window.btn_browse_drive.isVisible() is False

    # Mode Drive : bouton visible
    idx_drive = window.combo_location.findData("drive")
    window.combo_location.setCurrentIndex(idx_drive)
    assert window.btn_browse_drive.isVisible() is True

    window.close()


def test_drive_save_fails_if_directory_not_exists(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    """La sauvegarde drive échoue si le dossier n'existe pas."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    warning_called = []

    def mock_warning(*args, **kwargs):
        warning_called.append(True)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)

    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Sélectionner Drive avec un dossier inexistant
    idx = window.combo_location.findData("drive")
    window.combo_location.setCurrentIndex(idx)
    window.txt_server_addr.setText(str(tmp_path / "dossier_inexistant"))

    # La sauvegarde doit être bloquée
    window._on_save_clicked()

    assert len(warning_called) == 1, "Un avertissement doit être affiché"
    assert window.isVisible(), "La fenêtre doit rester ouverte après échec"

    window.close()


def test_run_backup_now_button_exists(qapp: QApplication) -> None:
    """Le bouton 'Lancer la sauvegarde maintenant' est présent."""
    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    assert hasattr(window, "btn_run_backup"), "Le bouton de sauvegarde immédiate doit exister"
    assert window.btn_run_backup.isVisible(), "Le bouton de sauvegarde doit être visible"

    window.close()


def test_run_backup_now_copies_files(qapp: QApplication, tmp_path: Path, monkeypatch) -> None:
    """Le bouton 'Lancer la sauvegarde' copie réellement les fichiers vers le drive."""
    # Créer des fichiers source
    source_dir = tmp_path / "Documents"
    source_dir.mkdir()
    (source_dir / "fichier1.txt").write_text("contenu 1")
    (source_dir / "fichier2.txt").write_text("contenu 2")

    # Dossier drive cible
    drive_dir = tmp_path / "GoogleDrive"
    drive_dir.mkdir()

    # Mocker les dialogues
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    backend = DictRegistryBackend()
    cfg_mgr = ConfigManager(backend=backend)
    window = MainWindow(config_mgr=cfg_mgr)
    window.show()

    # Configurer le mode Drive
    idx = window.combo_location.findData("drive")
    window.combo_location.setCurrentIndex(idx)
    window.txt_server_addr.setText(str(drive_dir))
    window.txt_subfolder.setText("SystemOrion")

    # Ajouter le dossier source
    window.working_config.target_paths = [str(source_dir)]

    # Lancer la sauvegarde
    window._run_backup_now()

    # Vérifier que les fichiers ont été copiés
    backup_dir = drive_dir / "SystemOrion"
    assert backup_dir.is_dir(), "Le dossier de sauvegarde doit être créé"
    copied_files = list(backup_dir.iterdir())
    assert len(copied_files) == 2, f"2 fichiers doivent être copiés, trouvé: {len(copied_files)}"

    window.close()
