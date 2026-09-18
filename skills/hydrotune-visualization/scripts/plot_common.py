from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

TEMPLATE_VERSION = "hydrotune.plots.v1"

def load(dataset: str, simulation: str, metadata: str):
    meta = json.loads(Path(metadata).read_text(encoding="utf-8"))
    data = pd.read_parquet(dataset); sim = pd.read_parquet(simulation)
    discharge = next((v["column"] for v in meta["variables"] if v["role"] == "discharge"), None)
    if not discharge: raise ValueError("dataset lacks observed discharge")
    keys = ["timestamp"] + (["event_id"] if meta.get("series_mode") == "event_collection" else [])
    frame = data.merge(sim, on=keys, how="inner")
    return frame, meta, discharge

def output_metadata(output: Path, template: str, meta: dict, extra: dict):
    figure = {"schema_version": TEMPLATE_VERSION, "template": template, "created_at": datetime.now(timezone.utc).isoformat(), "series_mode": meta.get("series_mode"), "splits": meta.get("splits"), "output_png": str(output), "input_provenance": meta.get("provenance"), **extra}
    output.with_name("figure.json").write_text(json.dumps(figure, indent=2) + "\n", encoding="utf-8")
    output.with_name("result.json").write_text(json.dumps({"schema_version": "hydrotune.result.v1", "artifact_type": "result", "operation": "visualization", "status": "success", "errors": [], "warnings": [], "output_artifacts": [str(output), str(output.with_name('figure.json'))]}, indent=2) + "\n", encoding="utf-8")
