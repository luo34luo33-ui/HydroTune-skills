# HydroTune Intake v0.1 benchmark (archived)

This corpus belongs to the old runtime-driven `inspect -> intake` design. It is
kept as historical input data for future Agent evaluation, but it is no longer a
current CLI contract benchmark.

The current Intake boundary is Agent-first:

- The Agent inspects raw files directly.
- The Agent asks the user for scientifically material metadata.
- The Agent calls `hydrotune intake` only after `--time-column`, `--role`, `--unit`,
  and any needed `--series-mode` / basin metadata are confirmed.

`verify_cases.py` now reports this archive status instead of invoking the removed
`hydrotune inspect` command.
