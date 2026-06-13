"""
CP/M File Manager - transfer files to/from legacy CP/M systems over serial.
"""

from cpm_fm.version import get_version

# DR-040/DR-041: the package version is sourced from src/version.txt so it
# stays in lock-step with the SRS version.
__version__ = get_version()
