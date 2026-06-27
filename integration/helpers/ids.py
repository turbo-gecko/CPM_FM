"""MT-ID <-> pytest marker helpers (plan §6).

Each test carries its manual-test-plan ID (and the requirement IDs it verifies)
via a single ``mt`` marker::

    @pytest.mark.mt("MT-T03", "FR-081", "FR-082")
    def test_single_file_round_trip(...):
        ...

The first marker argument is the MT-ID; any remaining arguments are requirement
IDs. The results plugin reads these to label per-test outcomes and to record the
requirement coverage of each run.
"""

from __future__ import annotations

# Skip-reason prefixes the results plugin maps to distinct outcomes so a
# gated/blocked case is distinguishable from an ordinary skip in the report.
BLOCKED_PREFIX = "BLOCKED:"
NA_PREFIX = "N/A:"


def mt_info(item) -> tuple[str | None, list[str]]:
    """Return ``(mt_id, [requirement_ids])`` for a pytest item.

    ``mt_id`` is ``None`` when the test carries no ``mt`` marker.
    """
    marker = item.get_closest_marker("mt")
    if marker is None or not marker.args:
        return None, []
    mt_id = str(marker.args[0])
    reqs = [str(a) for a in marker.args[1:]]
    return mt_id, reqs
