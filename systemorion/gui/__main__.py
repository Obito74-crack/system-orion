"""Point d'entrée exécutable pour python -m systemorion.gui"""

import sys

from systemorion.gui.main_window import run_gui

if __name__ == "__main__":
    sys.exit(run_gui())
