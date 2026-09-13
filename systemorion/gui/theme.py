"""Thème et styles GNOME / Adwaita sombre pour l'interface System Orion (EF-01a).

Transposition fidèle du design Adwaita Dark sous Qt6 / PySide6 :
- Fond sombre sobre (#242424 / #1e1e1e)
- Conteneurs de cartes arrondis (border-radius 8px / #2d2d2d)
- Accent bleu Adwaita (#3584e4)
- Bandeaux d'avertissement et états de verrouillage GPO
"""

ADWAITA_DARK_QSS = """
/* Fenêtre et fond principal */
QMainWindow, QDialog, QWidget#centralWidget {
    background-color: #242424;
    color: #f6f6f6;
    font-family: "Segoe UI", "Cantarell", "Noto Sans", sans-serif;
    font-size: 13px;
}

/* En-tête / Header Bar */
QWidget#headerBar {
    background-color: #303030;
    border-bottom: 1px solid #3d3d3d;
    padding: 8px 16px;
}

QLabel#headerTitle {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
}

/* Bandeau GPO (EF-01a, D7) */
QFrame#gpoBanner {
    background-color: #4a3800;
    border: 1px solid #855b00;
    border-radius: 6px;
    padding: 8px 12px;
}

QLabel#gpoBannerText {
    color: #f6d32d;
    font-weight: bold;
    font-size: 13px;
}

/* Cartes et sections (Adwaita Preferences Groups) */
QFrame.cardSection {
    background-color: #2d2d2d;
    border: 1px solid #3d3d3d;
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 12px;
}

QLabel.sectionTitle {
    font-size: 14px;
    font-weight: bold;
    color: #dedede;
    margin-bottom: 6px;
}

QLabel.sectionSubtitle {
    font-size: 12px;
    color: #9a9996;
}

/* Champs de saisie et listes déroulantes */
QLineEdit, QComboBox, QListWidget {
    background-color: #383838;
    color: #ffffff;
    border: 1px solid #4a4a4a;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #3584e4;
    selection-color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QListWidget:focus {
    border: 1px solid #3584e4;
    background-color: #3e3e3e;
}

QLineEdit:disabled, QComboBox:disabled, QListWidget:disabled {
    background-color: #2a2a2a;
    color: #777777;
    border: 1px solid #333333;
}

/* ListWidget des dossiers */
QListWidget::item {
    padding: 8px 10px;
    border-bottom: 1px solid #363636;
}

QListWidget::item:selected {
    background-color: #3584e4;
    color: #ffffff;
    border-radius: 4px;
}

/* Boutons standards */
QPushButton {
    background-color: #3d3d3d;
    color: #ffffff;
    border: 1px solid #4d4d4d;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #484848;
    border: 1px solid #5d5d5d;
}

QPushButton:pressed {
    background-color: #323232;
}

QPushButton:disabled {
    background-color: #282828;
    color: #666666;
    border: 1px solid #333333;
}

/* Bouton primaire (Sauvegarder) */
QPushButton#primaryButton {
    background-color: #3584e4;
    color: #ffffff;
    border: 1px solid #1b6acb;
    font-weight: bold;
}

QPushButton#primaryButton:hover {
    background-color: #1b6acb;
}

QPushButton#primaryButton:pressed {
    background-color: #15539e;
}

/* Bouton destructif / Réinitialiser */
QPushButton#destructiveButton {
    background-color: #382424;
    color: #ff7b63;
    border: 1px solid #5a3030;
}

QPushButton#destructiveButton:hover {
    background-color: #c01c28;
    color: #ffffff;
}

/* Bouton discret / icône */
QPushButton.toolButton {
    background-color: transparent;
    border: none;
    padding: 4px 8px;
    font-size: 14px;
}

QPushButton.toolButton:hover {
    background-color: #404040;
    border-radius: 4px;
}

/* Ascenseurs */
QScrollBar:vertical {
    border: none;
    background: #242424;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #4a4a4a;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #5a5a5a;
}
"""
