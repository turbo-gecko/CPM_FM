#!/usr/bin/env python3
"""
Main entry point for the CP/M File Manager application.
Initializes and runs the GUI application.
"""

from gui.app import App
import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
