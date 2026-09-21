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
