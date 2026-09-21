"""Boîte de dialogue d'assistance à la restauration (EF-09+).

Permet à l'administrateur ou à l'utilisateur de :
- Sélectionner un fichier local dont on souhaite retrouver l'historique.
- Consulter la liste des versions sauvegardées (date, taille, version).
- Restaurer la version sélectionnée vers un dossier ou fichier au choix.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from systemorion.gui.theme import ADWAITA_DARK_QSS
from systemorion.models import BackupRecord
from systemorion.restore import find_backup_versions, restore_file
from systemorion.state import StateDB


def _format_file_size(size_bytes: int) -> str:
    """Formate une taille en octets de manière lisible."""
    if size_bytes < 1024:
        return f"{size_bytes} o"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} Ko"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} Mo"


class RestoreDialog(QDialog):
    """Dialogue de recherche et de restauration de versions antérieures."""

    def __init__(
        self,
        state_db: StateDB | None = None,
        backup_unc_root: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.state_db = state_db
        self.backup_unc_root = backup_unc_root
        self.found_versions: list[BackupRecord] = []

        self.setWindowTitle("System Orion — Restauration de fichiers")
        self.resize(640, 520)
        self.setStyleSheet(ADWAITA_DARK_QSS)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # En-tête
        lbl_title = QLabel("Restaurer un fichier sauvegardé")
        lbl_title.setProperty("class", "sectionTitle")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Sélectionnez le fichier original ou saisissez son chemin pour retrouver ses versions archivées."
        )
        lbl_desc.setProperty("class", "sectionSubtitle")
        layout.addWidget(lbl_desc)

        # Sélection du fichier
        card_select = QFrame()
        card_select.setProperty("class", "cardSection")
        select_layout = QVBoxLayout(card_select)

        file_row = QHBoxLayout()
        self.txt_file_path = QLineEdit()
        self.txt_file_path.setPlaceholderText(r"C:\Users\...\document.docx")
        file_row.addWidget(self.txt_file_path)

        btn_browse = QPushButton("Parcourir…")
        btn_browse.clicked.connect(self._on_browse_file)
        file_row.addWidget(btn_browse)

        btn_search = QPushButton("Rechercher")
        btn_search.setObjectName("primaryButton")
        btn_search.clicked.connect(self._on_search_versions)
        file_row.addWidget(btn_search)

        select_layout.addLayout(file_row)
        layout.addWidget(card_select)

        # Tableau des versions
        self.table_versions = QTableWidget()
        self.table_versions.setColumnCount(3)
        self.table_versions.setHorizontalHeaderLabels(["Date de sauvegarde", "Taille", "Version / Emplacement"])
        self.table_versions.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_versions.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_versions.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_versions.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_versions.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_versions.verticalHeader().setVisible(False)
        self.table_versions.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_versions)

        # Barre d'actions
        bottom_row = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("class", "sectionSubtitle")
        bottom_row.addWidget(self.lbl_status)

        bottom_row.addStretch()

        self.btn_restore = QPushButton("Restaurer la sélection…")
        self.btn_restore.setObjectName("primaryButton")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._on_restore_clicked)
        bottom_row.addWidget(self.btn_restore)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.reject)
        bottom_row.addWidget(btn_close)

        layout.addLayout(bottom_row)

        self.table_versions.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un fichier à restaurer")
        if file_path:
            self.txt_file_path.setText(file_path)
            self._on_search_versions()

    def _on_search_versions(self) -> None:
        path = self.txt_file_path.text().strip()
        if not path:
            QMessageBox.warning(self, "Attention", "Veuillez spécifier un chemin de fichier.")
            return

        self.found_versions = find_backup_versions(
            source_path=path,
            state_db=self.state_db,
            backup_search_dir=self.backup_unc_root,
        )

        self.table_versions.setRowCount(len(self.found_versions))
        for row_idx, rec in enumerate(self.found_versions):
            dt_str = rec.backed_up_at.strftime("%d/%m/%Y %H:%M:%S")
            item_date = QTableWidgetItem(dt_str)
            item_size = QTableWidgetItem(_format_file_size(rec.file_size))
            item_loc = QTableWidgetItem(rec.dest_path)

            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight)

            self.table_versions.setItem(row_idx, 0, item_date)
            self.table_versions.setItem(row_idx, 1, item_size)
            self.table_versions.setItem(row_idx, 2, item_loc)

        if not self.found_versions:
            self.lbl_status.setText("Aucune version trouvée.")
            self.btn_restore.setEnabled(False)
        else:
            self.lbl_status.setText(f"{len(self.found_versions)} version(s) archivée(s) trouvée(s).")
            self.table_versions.selectRow(0)

    def _on_selection_changed(self) -> None:
        selected_rows = self.table_versions.selectionModel().selectedRows()
        self.btn_restore.setEnabled(bool(selected_rows))

    def _on_restore_clicked(self) -> None:
        selected_rows = self.table_versions.selectionModel().selectedRows()
        if not selected_rows:
            return

        selected_idx = selected_rows[0].row()
        record = self.found_versions[selected_idx]

        dest_dir = QFileDialog.getExistingDirectory(self, "Choisir le dossier de destination pour la restauration")
        if not dest_dir:
            return

        try:
            result = restore_file(record.dest_path, dest_dir, overwrite=False)
            QMessageBox.information(
                self,
                "Restauration réussie",
                f"Le fichier a été restauré avec succès dans :\n{result.restored_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur de restauration",
                f"Impossible de restaurer le fichier :\n{e}",
            )
