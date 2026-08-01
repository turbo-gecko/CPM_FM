# cpm-fm — Hardware-in-the-Loop (HIL) integration test harness

This suite drives the **real** `cpm-fm` code against a **real CP/M machine** on
the bench: protocol round-trips, the GUI over real serial, and widget-level
look-and-feel assertions. Its current MT mappings support part of
`docs/manual_test_plan.md`; they do not replace retained manual evidence.

It is **separate** from the unit suite. The default `pytest` (root) only collects
`tests/` and never touches hardware; this suite is an explicit, separate
invocation: `.venv/Scripts/python.exe -m pytest integration/`.

> Status: **Phase 0 complete (2026-08-01).** Static validation and the
> target-free tier pass; MT-CF05 also passes on all five physical targets at
> clean commit `84f0be5`. Phase 1 remains partial, with MT-C02--MT-C04 now
> covered in the target-free GUI tier; later scenarios continue incrementally.
> See `temp/integration_test_harness_plan.md` for the audited evidence matrix.

## Quick start

1. Install dev deps: `.venv/Scripts/python.exe -m pip install -e .[dev]`
2. Copy the config template and edit it for your bench:
   `cp integration/hil_config.example.json integration/hil_config.json`
   (`hil_config.json` is gitignored — it holds your local ports/paths/drives.)
3. Wire up and power on the CP/M machine; confirm the serial port number.
4. Run the connectivity smoke test:
   `.venv/Scripts/python.exe -m pytest integration/ -k smoke`
5. Use the interactive launcher to pick targets:
   `.venv/Scripts/python.exe integration/run.py`

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
| `spare_port` | Reserved bench metadata for future controlled physical port-fault cases; the deterministic MT-C02/MT-C04 CI cases inject failure at the serial boundary. |
| `scratch_drive` | The **disposable** CP/M drive for all destructive write testing. Must differ from `connect_drive` or destructive tests refuse to run. |
| `connect_drive` | The **declared protected** home/working drive. The destructive guard compares `scratch_drive` against this (not the live prompt), so a scratch drive can never coincide with the drive you consider precious. |
| `has_1k_sender` / `has_checksum_sender` | Per-target X-Modem sender capabilities; gate the MT-T10 1K / checksum variants. The 128-byte CRC path runs on every target. |
| `flow_control_peer` | Gates the flow-control peer case (MT-P05). |

### Settings-file immutability

The original settings file is **never modified** by a test run. Each test works
on a **fresh copy** (`tmp_path/<target>.json`), and the copy fixture asserts at
teardown that the original's SHA-256 is unchanged.

## Running

```text
.venv/Scripts/python.exe -m pytest integration/                       # default target
.venv/Scripts/python.exe -m pytest integration/ --target rc2014       # one target
.venv/Scripts/python.exe -m pytest integration/ --target a --target b # several
.venv/Scripts/python.exe -m pytest integration/ --all-targets         # every target
.venv/Scripts/python.exe -m pytest integration/ --run-destructive     # destructive
```

Results print labelled by target, e.g. `test_smoke.py::...[rc2014]`.

Target-free and traceability gates:

```text
.venv/Scripts/python.exe -m pytest integration/ -m "visual or gui_integration"
.venv/Scripts/python.exe -m pytest integration/ --collect-only -q
.venv/Scripts/python.exe -m integration.generate_coverage --check
```

The `gui_integration` lane drives the real offscreen `MainWindow` but replaces
the operating-system serial boundary. MT-C02--MT-C04 therefore verify the
dialogs, workflow, flags, indicators, and probe gating deterministically while
their manual cases remain required for evidence from genuinely free/busy ports.

### Watching a run

The harness narrates each step it takes through a `logging` trace (the
`hil.peer` and `hil.gui` loggers — connect, drive change, list, send/recv,
button clicks, worker quiesce). **It is on by default** (`log_cli`/
`log_cli_level = INFO` in `pytest.ini`), so a bench run streams what it is doing
as it does it:

```
12:04:31 INFO    hil.gui: GUI connect…
12:04:33 INFO    hil.peer: connecting: terminal=COM5 transport=COM5 (shared port)
12:04:35 INFO    hil.peer: connected; CCP drive = A:
12:04:35 INFO    hil.gui: probe = ok (drive A:)
12:04:36 INFO    hil.peer: send HELLO.TXT → B: [128] (37 bytes)
12:04:39 INFO    hil.peer: send HELLO.TXT → OK
```

- Quieter (only timeout/quiesce warnings — the most useful lines when a run
  *hangs*):
  `.venv/Scripts/python.exe -m pytest integration/ --log-cli-level=WARNING`
- Noisier: `--log-cli-level=DEBUG` adds raw line I/O (`→ "DIR"`) and capture
  byte counts/timings.
- The same trace is captured into each run's `results/<target>/<run>/console.log`
  (under a `----- log -----` section per test), so it is reviewable after the
  fact even if the live log was quieted.

Flags pass through the launcher (the `--` separator is optional):
`.venv/Scripts/python.exe integration/run.py --log-cli-level=DEBUG`.

## Safety

- Every whole-drive wipe is **double-gated** by
  `--run-destructive` and a configured `scratch_drive` that differs from the
  declared protected `connect_drive`, with live preflight and trace evidence.
- The coverage validator statically rejects `wipe_drive`, Backup, or Restore
  calls outside a destructive-marked test. Target-free selections do not open
  serial hardware even when a local `hil_config.json` exists.
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
  close failure) — opt-in, may end **Blocked**. Real free/busy-port observation
  for MT-C02--MT-C04 also remains manual despite deterministic GUI coverage.
