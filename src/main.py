"""
LogNeedle – entry point.

Usage:
    python -m src.main          # from the repo root
    python src/main.py          # also works
"""

from __future__ import annotations

import sys
import os

# Ensure the project root is on sys.path when run as a script
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("LogNeedle")
    app.setOrganizationName("LogNeedle")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
