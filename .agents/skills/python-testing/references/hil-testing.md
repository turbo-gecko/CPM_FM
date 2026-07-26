# Hardware-in-the-loop testing

Treat the CP/M peer, serial ports, application process, target configuration, scratch drive, and result capture as separate components.

- Verify target identity, connectivity, configuration compatibility, and safe initial state.
- Use bounded polling and monotonic deadlines instead of arbitrary sleeps.
- Distinguish command acceptance from the observable physical or remote-system result.
- Define cleanup and recovery for assertion failures and exceptions.
- Serialize tests that cannot safely share a target.
- Keep destructive backup/restore cases behind `--run-destructive`.
- Preserve actionable evidence: target, timestamps, commands, expected and observed values, and logs.
- Mark hardware absence or incompatibility explicitly according to integration-suite policy.
- Never describe simulation or an unexecuted case as a physical bench pass.
