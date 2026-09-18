"""Shared HydroTune artifact and result contract helpers."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_VERSION = "hydrotune.dataset.v1"
RUN_VERSION = "hydrotune.run.v1"
RESULT_VERSION = "hydrotune.result.v1"


def stamp() -> str: return datetime.now(timezone.utc).isoformat()

def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
def result(operation: str, errors: list[str] | None = None, warnings: list[str] | None = None, outputs: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    errors, warnings, outputs = errors or [], warnings or [], outputs or []
    return {"schema_version": RESULT_VERSION, "artifact_type": "result", "operation": operation, "status": "error" if errors else "warning" if warnings else "success", "created_at": stamp(), "errors": errors, "warnings": warnings, "output_artifacts": outputs, **extra}
def finish(out: Path, payload: dict[str, Any]) -> int:
    write_json(out / "result.json", payload); print(json.dumps({"status": payload["status"], "result": str(out / "result.json")}, ensure_ascii=False)); return 2 if payload["status"] == "error" else 0
