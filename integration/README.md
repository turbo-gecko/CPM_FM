# cpm-fm — Hardware-in-the-Loop (HIL) integration test harness

This suite drives the **real** `cpm-fm` code against a **real CP/M machine** on
the bench: protocol round-trips, the GUI over real serial, and widget-level
look-and-feel assertions. It automates the bulk of `docs/manual_test_plan.md`.

It is **separate** from the unit suite. The default `pytest` (root) only collects
`tests/` and never touches hardware; this suite is an explicit, separate
invocation: `pytest integration/`.

> Status: **Phase 0 scaffolding**. Later phases (protocol, GUI, destructive,
> visual) are added incrementally — see `temp/integration_test_harness_plan.md`.

## Quick start

1. Install dev deps: `python -m pip install -e .[dev]`
2. Copy the config template and edit it for your bench:
   `cp integration/hil_config.example.json integration/hil_config.json`
   (`hil_config.json` is gitignored — it holds your local ports/paths/drives.)
3. Wire up and power on the CP/M machine; confirm the serial port number.
4. Run the connectivity smoke test:
   `pytest integration/ -k smoke`
5. Use the interactive launcher to pick targets:
   `python integration/run.py`   (or `python -m integration.run`)

## Configuration (`hil_config.json`)

The harness is parameterised by **targets**. Each target points at one **app
settings file** — the same JSON the real app loads (flat or nested shape; parsed
with the app's own `utils/config_handler.py`). Ports, baud, EOL, and the remote
command templates come from there; the harness never duplicates them.

Bench-only metadata per target:

| Field | Meaning |
|---|---|
| `settings_file` | Path (absolute, or relative to repo root) to the **read-only** app config. |
| `two_port` | `true` when Terminal/Transport are distinct ports (gates `two_port` cases). |
| `spare_port` | A real-but-free port for the bad/busy-port error cases (`null` ⇒ those skip). |
| `scratch_drive` | The **disposable** CP/M drive for all destructive write testing. Must differ from `connect_drive` or destructive tests refuse to run. |
| `connect_drive` | The **declared protected** home/working drive. The destructive guard compares `scratch_drive` against this (not the live prompt), so a scratch drive can never coincide with the drive you consider precious. |
| `has_1k_sender` / `has_checksum_sender` | Per-target X-Modem sender capabilities; gate the MT-T10 1K / checksum variants. The 128-byte CRC path runs on every target. |
| `flow_control_peer` | Gates the flow-control peer case (MT-P05). |

### Settings-file immutability

The original settings file is **never modified** by a test run. Each test works
on a **fresh copy** (`tmp_path/<target>.json`), and the copy fixture asserts at
teardown that the original's SHA-256 is unchanged.

## Running

```
pytest integration/                       # default target (default_target)
pytest integration/ --target rc2014       # one target
pytest integration/ --target a --target b # several
pytest integration/ --all-targets         # every registered target
pytest integration/ --run-destructive     # also run destructive backup/restore
```

Results print labelled by target, e.g. `test_smoke.py::...[rc2014]`.

## Safety

- Destructive tests are **double-gated**: they need `--run-destructive` **and** a
  `scratch_drive` that differs from the live connect drive. Every wipe/seed is
  issued explicitly against `scratch_drive:`.
- Originals are read-only references; all mutation is on per-test copies.

## Results & history (plan §7)

Each run writes a self-contained artifact directory and appends to a committed
ledger:

```
integration/results/
  runs_ledger.json                     # COMMITTED: one entry per (run, target)
  <target>/<UTC-ts>_<git-sha>/         # GITIGNORED: run.json, report.md, junit.xml, console.log
```

Per-test outcome vocabulary: **Pass / Fail / Blocked / Skipped / N-A / Error**.
A test signals Blocked / N-A by skipping with a reason prefixed `BLOCKED:` /
`N/A:` (see `helpers/ids.py`).

The harness writes its **own** `report.md`/`run.json` only.
`docs/manual_test_scorecard.md` stays **hand-maintained**.

## Stays manual (not automated here)

- MT-V02 (OS light/dark follow at startup), MT-V11 (taskbar/dock icon render),
  MT-V10 (link → browser launch), MT-N02 (second OS).
- True pixel rendering — we assert the widget tree / stylesheet / layout, not
  screenshots.
- Best-effort / hardware-specific: MT-P05 (flow-control peer), MT-C10 (forced
  close failure) — opt-in, may end **Blocked**.
