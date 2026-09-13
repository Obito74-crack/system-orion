"""Package de l'interface graphique d'administration System Orion (CDC EF-01a).

Interface PySide6/Qt6 en navigation à deux écrans, style sombre Adwaita/GNOME,
exécutée avec privilèges administrateur en session utilisateur.
"""

from systemorion.gui.main_window import MainWindow, run_gui

__all__ = ["MainWindow", "run_gui"]
