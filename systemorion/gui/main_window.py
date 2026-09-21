"""Fenêtre principale et navigation à deux écrans du panneau de configuration (EF-01a).

Architecture conforme au CDC v1.3 section 6.1 (EF-01a) :
- Navigation à deux écrans (QStackedWidget) :
    1. Écran 1 : Emplacement de stockage, résumé des dossiers, boutons Sauvegarder/Annuler
    2. Écran 2 : Gestion complète des dossiers à sauvegarder et dossiers/motifs à ignorer
- Verrouillage GPO automatique avec bandeau d'information
- Style sombre Adwaita / GNOME
- Validation et contrôle de connectivité avant écriture dans le registre HKLM
"""

from __future__ import annotations

import copy
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from systemorion.cible_ad import (
    AdDirectoryResolver,
    AdsiDirectoryResolver,
    MockAdDirectoryResolver,
)
from systemorion.config import ConfigManager
from systemorion.gui.theme import ADWAITA_DARK_QSS
from systemorion.models import OrionConfig


class MainWindow(QMainWindow):
    """Fenêtre d'administration principale de System Orion (EF-01a)."""

    def __init__(
        self,
        config_mgr: ConfigManager | None = None,
        ad_resolver: AdDirectoryResolver | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_mgr = config_mgr or ConfigManager()
        self.ad_resolver = ad_resolver or (
            AdsiDirectoryResolver() if sys.platform == "win32" else MockAdDirectoryResolver()
        )

        # Copie de travail en mémoire : les modifications ne sont écrites qu'au clic sur Sauvegarder
        self.original_config = self.config_mgr.load()
        self.working_config = copy.deepcopy(self.original_config)
        self.is_gpo_locked = self.config_mgr.is_managed_by_gpo()

        self.setWindowTitle("System Orion — Configuration")
        self.resize(680, 720)
        self.setMinimumSize(580, 600)
        self.setStyleSheet(ADWAITA_DARK_QSS)

        self._build_ui()
        self._load_config_into_ui()

    def _build_ui(self) -> None:
        """Construit l'interface utilisateur avec navigation QStackedWidget."""
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # En-tête globale (Header Bar)
        self.header_bar = QWidget()
        self.header_bar.setObjectName("headerBar")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 12, 16, 12)

        # Bouton Annuler / Retour
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        header_layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignLeft)

        # Titre central
        self.lbl_header_title = QLabel("System Orion")
        self.lbl_header_title.setObjectName("headerTitle")
        header_layout.addWidget(self.lbl_header_title, alignment=Qt.AlignmentFlag.AlignCenter)

        # Bouton Sauvegarder
        self.btn_save = QPushButton("Sauvegarder")
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.clicked.connect(self._on_save_clicked)
        header_layout.addWidget(self.btn_save, alignment=Qt.AlignmentFlag.AlignRight)

        root_layout.addWidget(self.header_bar)

        # Bandeau d'information GPO (D7, EF-01a)
        self.gpo_banner = QFrame()
        self.gpo_banner.setObjectName("gpoBanner")
        gpo_layout = QHBoxLayout(self.gpo_banner)
        gpo_layout.setContentsMargins(12, 8, 12, 8)
        self.lbl_gpo_text = QLabel("🔒 Géré par votre organisation — Paramètres verrouillés par GPO")
        self.lbl_gpo_text.setObjectName("gpoBannerText")
        gpo_layout.addWidget(self.lbl_gpo_text)
        self.gpo_banner.setVisible(self.is_gpo_locked)
        root_layout.addWidget(self.gpo_banner)

        # Pile d'écrans (2 écrans de navigation)
        self.stack = QStackedWidget()
        self.screen_main = self._build_screen_1_main()
        self.screen_folders = self._build_screen_2_folders()

        self.stack.addWidget(self.screen_main)  # Index 0
        self.stack.addWidget(self.screen_folders)  # Index 1
        root_layout.addWidget(self.stack)

    # -----------------------------------------------------------------------
    # Écran 1 — Fenêtre principale (EF-01a)
    # -----------------------------------------------------------------------

    def _build_screen_1_main(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        # Section 1 : Stockage
        card_storage = QFrame()
        card_storage.setProperty("class", "cardSection")
        storage_layout = QVBoxLayout(card_storage)

        lbl_storage_title = QLabel("Stockage")
        lbl_storage_title.setProperty("class", "sectionTitle")
        storage_layout.addWidget(lbl_storage_title)

        # Emplacement
        lbl_location = QLabel("Emplacement cible")
        lbl_location.setProperty("class", "sectionSubtitle")
        storage_layout.addWidget(lbl_location)

        self.combo_location = QComboBox()
        self.combo_location.addItem("Serveur réseau (partage d'entreprise SMB)")
        storage_layout.addWidget(self.combo_location)

        # Adresse du serveur
        lbl_server = QLabel("Adresse du serveur distant")
        lbl_server.setProperty("class", "sectionSubtitle")
        storage_layout.addWidget(lbl_server)

        server_row = QHBoxLayout()
        self.txt_server_addr = QLineEdit()
        self.txt_server_addr.setPlaceholderText(r"\\serveur\partage")
        self.txt_server_addr.setReadOnly(True)
        server_row.addWidget(self.txt_server_addr)

        self.btn_edit_server = QPushButton("✏️")
        self.btn_edit_server.setToolTip("Modifier l'adresse cible manuellement")
        self.btn_edit_server.setProperty("class", "toolButton")
        self.btn_edit_server.clicked.connect(self._toggle_edit_server)
        server_row.addWidget(self.btn_edit_server)

        self.btn_info_ad = QPushButton("ⓘ")
        self.btn_info_ad.setToolTip("Détails de la résolution Active Directory")
        self.btn_info_ad.setProperty("class", "toolButton")
        self.btn_info_ad.clicked.connect(self._show_ad_info)
        server_row.addWidget(self.btn_info_ad)

        storage_layout.addLayout(server_row)

        # Dossier sous-jacent
        lbl_subfolder = QLabel("Sous-dossier de destination")
        lbl_subfolder.setProperty("class", "sectionSubtitle")
        storage_layout.addWidget(lbl_subfolder)

        self.txt_subfolder = QLineEdit()
        self.txt_subfolder.setPlaceholderText("SystemOrion")
        storage_layout.addWidget(self.txt_subfolder)

        layout.addWidget(card_storage)

        # Section 2 : Dossiers à sauvegarder (Résumé)
        card_folders_summary = QFrame()
        card_folders_summary.setProperty("class", "cardSection")
        summary_layout = QVBoxLayout(card_folders_summary)

        lbl_folders_title = QLabel("Dossiers à sauvegarder")
        lbl_folders_title.setProperty("class", "sectionTitle")
        summary_layout.addWidget(lbl_folders_title)

        self.lbl_folders_count = QLabel("4 dossiers configurés pour la sauvegarde")
        self.lbl_folders_count.setProperty("class", "sectionSubtitle")
        summary_layout.addWidget(self.lbl_folders_count)

        self.lbl_exclusions_count = QLabel("7 motifs et dossiers exclus")
        self.lbl_exclusions_count.setProperty("class", "sectionSubtitle")
        summary_layout.addWidget(self.lbl_exclusions_count)

        self.btn_goto_folders = QPushButton("Gérer les dossiers et exclusions →")
        self.btn_goto_folders.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        summary_layout.addWidget(self.btn_goto_folders, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(card_folders_summary)
        layout.addStretch()

        return container

    # -----------------------------------------------------------------------
    # Écran 2 — Sous-écran Dossiers & Exclusions (EF-01a)
    # -----------------------------------------------------------------------

    def _build_screen_2_folders(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Bouton retour
        btn_back = QPushButton("← Retour à la fenêtre principale")
        btn_back.clicked.connect(self._on_back_to_main_screen)
        layout.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignLeft)

        # Section Dossiers à sauvegarder
        card_saved = QFrame()
        card_saved.setProperty("class", "cardSection")
        saved_layout = QVBoxLayout(card_saved)

        saved_hdr = QHBoxLayout()
        lbl_saved_title = QLabel("Dossiers à sauvegarder")
        lbl_saved_title.setProperty("class", "sectionTitle")
        saved_hdr.addWidget(lbl_saved_title)

        self.btn_add_target = QPushButton("+ Ajouter un dossier…")
        self.btn_add_target.clicked.connect(self._add_target_folder)
        saved_hdr.addWidget(self.btn_add_target, alignment=Qt.AlignmentFlag.AlignRight)

        self.btn_del_target = QPushButton("🗑")
        self.btn_del_target.setToolTip("Supprimer le dossier sélectionné")
        self.btn_del_target.setProperty("class", "toolButton")
        self.btn_del_target.clicked.connect(self._delete_target_folder)
        saved_hdr.addWidget(self.btn_del_target)

        saved_layout.addLayout(saved_hdr)

        self.list_targets = QListWidget()
        saved_layout.addWidget(self.list_targets)
        layout.addWidget(card_saved)

        # Section Dossiers et motifs à ignorer
        card_ignored = QFrame()
        card_ignored.setProperty("class", "cardSection")
        ignored_layout = QVBoxLayout(card_ignored)

        ignored_hdr = QHBoxLayout()
        lbl_ignored_title = QLabel("Dossiers et motifs à ignorer")
        lbl_ignored_title.setProperty("class", "sectionTitle")
        ignored_hdr.addWidget(lbl_ignored_title)

        btn_info_patterns = QPushButton("ⓘ Syntaxe")
        btn_info_patterns.setProperty("class", "toolButton")
        btn_info_patterns.clicked.connect(self._show_pattern_syntax_info)
        ignored_hdr.addWidget(btn_info_patterns)

        self.btn_add_ignored = QPushButton("+ Ajouter un motif…")
        self.btn_add_ignored.clicked.connect(self._add_ignored_pattern)
        ignored_hdr.addWidget(self.btn_add_ignored, alignment=Qt.AlignmentFlag.AlignRight)

        self.btn_del_ignored = QPushButton("🗑")
        self.btn_del_ignored.setToolTip("Supprimer le motif sélectionné")
        self.btn_del_ignored.setProperty("class", "toolButton")
        self.btn_del_ignored.clicked.connect(self._delete_ignored_pattern)
        ignored_hdr.addWidget(self.btn_del_ignored)

        ignored_layout.addLayout(ignored_hdr)

        self.list_ignored = QListWidget()
        ignored_layout.addWidget(self.list_ignored)
        layout.addWidget(card_ignored)

        # Bouton Réinitialiser aux valeurs par défaut
        self.btn_reset_defaults = QPushButton("Réinitialiser tous les dossiers aux valeurs par défaut…")
        self.btn_reset_defaults.setObjectName("destructiveButton")
        self.btn_reset_defaults.clicked.connect(self._confirm_reset_defaults)
        layout.addWidget(self.btn_reset_defaults, alignment=Qt.AlignmentFlag.AlignCenter)

        return container

    # -----------------------------------------------------------------------
    # Chargement et Synchronisation des Données
    # -----------------------------------------------------------------------

    def _load_config_into_ui(self) -> None:
        """Remplit les contrôles graphiques avec la configuration active."""
        # 1. Adresse cible
        target_unc = self.working_config.unc_override
        if not target_unc:
            # Résolution automatique AD
            username = os.environ.get("USERNAME", "Utilisateur")
            domain = os.environ.get("USERDOMAIN", "DOMAINE")
            resolved = self.ad_resolver.get_user_home_directory(domain, username)
            target_unc = resolved or r"\\serveur\partage\utilisateurs$"

        self.txt_server_addr.setText(target_unc)
        self.txt_subfolder.setText(self.working_config.backup_subfolder)

        # 2. Listes de dossiers
        self._refresh_lists_and_summary()

        # 3. Application du verrouillage GPO si applicable (EF-01a, D7)
        if self.is_gpo_locked:
            self._apply_gpo_locking()

    def _refresh_lists_and_summary(self) -> None:
        """Actualise les ListWidgets et les textes de résumé."""
        # Dossiers cibles
        self.list_targets.clear()
        for p in self.working_config.target_paths:
            self.list_targets.addItem(p)

        # Dossiers et motifs exclus
        self.list_ignored.clear()
        for d in self.working_config.excluded_dirs:
            self.list_ignored.addItem(f"[Dossier] {d}")
        for pat in self.working_config.exclusion_patterns:
            self.list_ignored.addItem(f"[Motif] {pat}")

        # Textes de résumé sur l'Écran 1
        t_count = len(self.working_config.target_paths)
        e_count = len(self.working_config.excluded_dirs) + len(self.working_config.exclusion_patterns)
        self.lbl_folders_count.setText(f"{t_count} dossier(s) configuré(s) pour la sauvegarde")
        self.lbl_exclusions_count.setText(f"{e_count} motif(s) et répertoire(s) exclu(s)")

    def _apply_gpo_locking(self) -> None:
        """Verrouille tous les contrôles en lecture seule sous gestion GPO (EF-01a)."""
        self.btn_save.setEnabled(False)
        self.btn_save.setToolTip("La configuration est gérée par votre organisation (GPO)")
        self.txt_server_addr.setReadOnly(True)
        self.txt_subfolder.setReadOnly(True)
        self.btn_edit_server.setEnabled(False)
        self.combo_location.setEnabled(False)
        self.btn_add_target.setEnabled(False)
        self.btn_del_target.setEnabled(False)
        self.btn_add_ignored.setEnabled(False)
        self.btn_del_ignored.setEnabled(False)
        self.btn_reset_defaults.setEnabled(False)

    # -----------------------------------------------------------------------
    # Actions Utilisateur
    # -----------------------------------------------------------------------

    def _toggle_edit_server(self) -> None:
        if self.is_gpo_locked:
            return
        is_readonly = self.txt_server_addr.isReadOnly()
        self.txt_server_addr.setReadOnly(not is_readonly)
        if is_readonly:
            self.btn_edit_server.setText("💾")
            self.txt_server_addr.setFocus()
        else:
            self.btn_edit_server.setText("✏️")
            self.working_config.unc_override = self.txt_server_addr.text().strip()

    def _show_ad_info(self) -> None:
        domain = os.environ.get("USERDOMAIN", "DOMAINE")
        user = os.environ.get("USERNAME", "Utilisateur")
        resolved = self.ad_resolver.get_user_home_directory(domain, user)
        resolved_display = resolved if resolved else "<i>Non configuré dans l'annuaire</i>"
        msg = (
            f"<b>Résolution Active Directory (EF-03)</b><br><br>"
            f"<b>Utilisateur :</b> {domain}\\{user}<br>"
            f"<b>homeDirectory AD :</b> {resolved_display}<br><br>"
            f"En exploitation normale, System Orion sauvegarde sous le chemin UNC personnel de l'utilisateur."
        )
        QMessageBox.information(self, "Détails Active Directory", msg)

    def _show_pattern_syntax_info(self) -> None:
        msg = (
            "<b>Syntaxe des motifs d'exclusion (EF-05) :</b><br><br>"
            "• <code>*.tmp</code> : ignore tous les fichiers se terminant par .tmp<br>"
            "• <code>~$*</code> : ignore les fichiers temporaires de verrouillage Microsoft Office<br>"
            "• <code>node_modules</code> : ignore tout dossier nommé node_modules et son contenu<br>"
            "• <code>.git</code> : ignore les dépôts de versioning locaux<br><br>"
            "Les jokers <code>*</code> (zéro ou plusieurs caractères) et <code>?</code> (un caractère) sont supportés."
        )
        QMessageBox.information(self, "Syntaxe des motifs", msg)

    def _add_target_folder(self) -> None:
        if self.is_gpo_locked:
            return
        folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier à sauvegarder")
        if folder and folder not in self.working_config.target_paths:
            self.working_config.target_paths.append(folder)
            self._refresh_lists_and_summary()

    def _delete_target_folder(self) -> None:
        if self.is_gpo_locked:
            return
        row = self.list_targets.currentRow()
        if row >= 0 and row < len(self.working_config.target_paths):
            del self.working_config.target_paths[row]
            self._refresh_lists_and_summary()

    def _add_ignored_pattern(self) -> None:
        if self.is_gpo_locked:
            return
        text, ok = QInputDialog.getText(
            self,
            "Ajouter une règle d'exclusion",
            "Nom de dossier ou motif (ex: *.bak, Téléchargements, node_modules) :",
        )
        if ok and text.strip():
            pat = text.strip()
            if pat.startswith("*") or "." in pat:
                if pat not in self.working_config.exclusion_patterns:
                    self.working_config.exclusion_patterns.append(pat)
            else:
                if pat not in self.working_config.excluded_dirs:
                    self.working_config.excluded_dirs.append(pat)
            self._refresh_lists_and_summary()

    def _delete_ignored_pattern(self) -> None:
        if self.is_gpo_locked:
            return
        row = self.list_ignored.currentRow()
        if row < 0:
            return
        item_text = self.list_ignored.currentItem().text()
        if item_text.startswith("[Dossier] "):
            val = item_text.replace("[Dossier] ", "", 1)
            if val in self.working_config.excluded_dirs:
                self.working_config.excluded_dirs.remove(val)
        elif item_text.startswith("[Motif] "):
            val = item_text.replace("[Motif] ", "", 1)
            if val in self.working_config.exclusion_patterns:
                self.working_config.exclusion_patterns.remove(val)
        self._refresh_lists_and_summary()

    def _confirm_reset_defaults(self) -> None:
        if self.is_gpo_locked:
            return
        reply = QMessageBox.question(
            self,
            "Confirmation de réinitialisation",
            "Voulez-vous vraiment réinitialiser la liste des dossiers sauvegardés et ignorés aux valeurs par défaut ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            defaults = OrionConfig()
            self.working_config.target_paths = list(defaults.target_paths)
            self.working_config.excluded_dirs = list(defaults.excluded_dirs)
            self.working_config.exclusion_patterns = list(defaults.exclusion_patterns)
            self._refresh_lists_and_summary()

    def _on_back_to_main_screen(self) -> None:
        self.stack.setCurrentIndex(0)

    def _on_cancel_clicked(self) -> None:
        """Bouton Annuler : abandonne toutes les modifications sans écrire dans le registre."""
        self.close()

    def _on_save_clicked(self) -> None:
        """Bouton Sauvegarder : valide la connectivité et persiste dans HKLM\\SOFTWARE\\SystemOrion."""
        if self.is_gpo_locked:
            return

        # 1. Validation de l'adresse cible
        server_val = self.txt_server_addr.text().strip()
        if server_val:
            self.working_config.unc_override = server_val
        self.working_config.backup_subfolder = self.txt_subfolder.text().strip() or "SystemOrion"

        # 2. Test de connectivité préalable proposé (EF-01a)
        if server_val.startswith(r"\\") and not os.path.exists(server_val):
            res = QMessageBox.warning(
                self,
                "Avertissement connectivité réseau",
                f"Le partage réseau cible '{server_val}' n'est pas joignable actuellement.\n\n"
                "Voulez-vous tout de même enregistrer cette configuration ?\n"
                "(Les sauvegardes seront conservées en file d'attente locale jusqu'au rétablissement du réseau)",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if res != QMessageBox.StandardButton.Save:
                return

        # 3. Persistance dans le magasin unique (D7)
        try:
            self.config_mgr.save(self.working_config)
            QMessageBox.information(
                self,
                "Succès",
                "La configuration de System Orion a été enregistrée avec succès dans le registre.",
            )
            self.close()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur d'enregistrement",
                f"Impossible d'enregistrer la configuration : {e}",
            )


def run_gui() -> int:
    """Point d'entrée de lancement de l'application graphique."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
