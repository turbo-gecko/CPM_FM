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
> clean commit `84f0be5`. Phase 1 remains partial, with MT-C02--MT-C04, MT-C10,
> MT-C12/12a/12b/12c, and MT-C13--MT-C15 now covered in the target-free GUI
> tier. MT-BR01/BR02 now cover Backup pane refresh, safe-default confirmation,
> and both rejection paths; MT-BR04 covers Restore destination refresh and safe
> cancellation; MT-BR06 covers mid-transfer batch cancellation; MT-BR08 covers
> disconnected-port rejection for both whole-drive actions; and MT-BR07 covers
> Restore filename validation, all without touching hardware. The planned
> connection/recovery and backup/restore automation backlogs are complete.
> The planned disk-image target-free backlog is also complete through MT-DI22.
> Destructive MT-BR09 passes on all five physical targets at clean commit
> `cadda8d`.
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
| `cpm_type` | CP/M family used to gate specialized Phase 3 tests. Allowed values are `2.2`, `ZSDOS`, `ZCPR`, and `QPM`; omitted defaults to `2.2`. `ZSDOS` uses the same base test selection as `2.2`; `ZCPR` represents ZCPR/NZCOM. |
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
dialogs, workflow, flags, indicators, and probe gating deterministically;
MT-C10 verifies close-failure cancellation and list preservation; and
MT-C12/12a/12b/12c verify retry, dialog structure, and all three actions.
MT-C13 verifies ZCPR-style prompt recognition and drive refresh; MT-C14 verifies
boot-script recovery and a successful post-boot probe; MT-C15 verifies that an
empty script bypasses recovery and proceeds directly to the dialog. MT-BR08
verifies that either disconnected status flag blocks both Backup and Restore
before a worker, refresh, deletion, or transfer can begin. MT-BR01 verifies that
the Backup worker refreshes both real panes before its real modal confirmation,
whose Cancel button is the safe default, without permitting a wipe or transfer.
MT-BR02 verifies both Cancel and window-close propagate through the production
worker handshake, preserve every host file byte-for-byte, and leave no worker
behind. MT-BR04 verifies that Restore refreshes the real Remote pane before its
real modal confirmation and Cancel prevents the remote wipe and upload.
MT-BR06 verifies that Restore reuses the real batch progress dialog and that its
Cancel button stops all remaining uploads after the wipe boundary without an
error dialog or lingering worker. MT-BR07 drives the real invalid-name dialog
through Rename, Skip, and Cancel and verifies the production batch/history
outcomes. These manual cases remain required for physical peer and genuinely
free/busy/failing-port evidence.

The same lane supplies target-free disk-image evidence for MT-DI01--DI03,
DI05--DI08, the local portions of DI10 and DI12, DI13, DI15--DI20, and the
local save/reopen portion of DI21, plus DI22. These cases drive the real
File-menu actions, CP/M image parser/extractor/writer, geometry-selection
contract, Host pane, Change Directory button, in-place save and reopen,
transactional write failures, the Save/Discard/Cancel dialog, status bar,
action enablement, Remote-mount dialog, local Copy buttons, dual-pane close
restoration, new-image creation in both panes, first Save-As path adoption,
independent image-directory persistence, named-versus-new save behavior,
confirmed local image Backup/Restore mirroring, temporary-directory cleanup,
multi-user-area rendering and duplicate-name disambiguation, area-preserving
save/reopen, user-area filtering in both panes and its close-time reset, and
the read-only Image Details dialog against deterministic IBM-3740 images
containing known files. Native file choices are made
deterministic for headless CI; the manual cases remain retained for
operator-observed menu/dialog and filesystem evidence.

The configuration slice adds target-free MT-P02--MT-P04 and MT-P06 evidence
through the real Config > Serial action and dialog. It verifies the translated
Port Settings/Transmit Delay grouping and two-column forms, exact serial-option
lists and defaults, strict 0--255 delay input, and same-port Save/reopen JSON
persistence. MT-P05 remains a best-effort physical flow-control case.

MT-BR09 additionally runs as destructive HIL: Restore with an empty temporary
host directory still wipes the nominated scratch drive, starts no transfer
batch, reports "Nothing to transfer", and refreshes to an empty Remote pane. It
passed on all five configured targets at clean commit `cadda8d` on 2026-08-01;
see the result ledger and the audited plan for the per-target artifact paths.

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
- Best-effort / hardware-specific MT-P05 (flow-control peer) may end
  **Blocked**. Real free/busy-port observation for MT-C02--MT-C04 and a
  physically induced close failure for MT-C10 remain manual despite
  deterministic GUI coverage. MT-C12 also retains the real unreachable-peer
  observation and visible modal interaction; MT-C13 retains live ZCPR/NZCOM
  peer evidence; MT-C14 retains live keystroke playback into a non-auto-booting
  remote; MT-C15 retains the corresponding unreachable live-peer observation.
