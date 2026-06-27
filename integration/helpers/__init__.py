"""Helper package for the cpm-fm hardware-in-the-loop (HIL) integration harness.

These helpers are deliberately free of any pytest dependency where possible so
they can be reused from ``run.py`` (the interactive launcher) and from the
conftest plugin alike. The protocol-tier helpers (``peer``, ``integrity``) also
avoid importing anything from ``cpm_fm.gui`` so they honour CR-014 (no GUI
toolkit imports in the non-GUI layers) and run without a Qt application.
"""
