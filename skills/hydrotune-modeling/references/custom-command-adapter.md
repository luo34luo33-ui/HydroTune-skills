# Custom command adapter

`run.json` may set `model.kind` to `external-command`, include a `command` array, and declare `model_output_csv`. HydroTune executes the command with its working directory set to the run file's directory. The command must create the declared CSV with `timestamp` and `discharge_sim` columns. This adapter makes no model-specific scientific assumptions.
