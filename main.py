"""
main.py - Direct entry point for agytask.

Usage:
1. Desktop GUI (PySide6):
    python main.py

2. Command-Line Interface (CLI):
    python main.py --help
    python main.py -p . -i
"""

import sys
from agytask.ui import launch_ui
from agytask.cli import main as cli_main

if __name__ == "__main__":
    # Launch the PySide6 desktop UI when invoked with no arguments or with --ui / --gui.
    if len(sys.argv) <= 1 or (len(sys.argv) == 2 and sys.argv[1] in ("--ui", "--gui")):
        launch_ui()
    else:
        cli_main()
