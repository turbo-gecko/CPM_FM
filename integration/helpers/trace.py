"""Step-level tracing for the HIL harness.

A single ``logging`` namespace (``hil``) that the protocol-tier peer and the GUI
driver narrate their actions through, so an otherwise-silent bench run reports
what it is doing as it does it. Stdlib ``logging`` only — no Qt, no pytest — so
it is safe to import from ``peer`` (which honours CR-014) and from the test
modules alike.

The trace is surfaced two ways:

- **Live**, by pytest's native CLI logging — enabled by default in
  ``integration/pytest.ini`` (``log_cli = true``, ``log_cli_level = INFO``).
  Quiet it with ``--log-cli-level=WARNING``; see raw line I/O with
  ``--log-cli-level=DEBUG``.
- **Persisted**, because the results recorder folds pytest's captured log into
  each run's ``console.log`` artifact (see ``helpers/results.py``).

Use ``step(log, msg, *args)`` for INFO-level action narration and the logger's
own ``debug`` for high-volume detail (raw bytes sent/received).
"""

from __future__ import annotations

import logging

#: Root logger for the harness. Sub-loggers (``hil.peer``, ``hil.gui``) inherit
#: its level so a single ``--log-cli-level`` controls the whole trace.
ROOT = "hil"


def get_logger(name: str) -> logging.Logger:
    """Return the ``hil.<name>`` logger (e.g. ``get_logger("peer")``)."""
    return logging.getLogger(f"{ROOT}.{name}")


def step(log: logging.Logger, msg: str, *args: object) -> None:
    """Log one INFO-level action line (``%``-style args, lazily formatted)."""
    log.info(msg, *args)
