"""Point d'entrée exécutable pour python -m systemorion."""

import sys

from systemorion.cli import main

if __name__ == "__main__":
    sys.exit(main())
