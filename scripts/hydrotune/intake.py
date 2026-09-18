"""Thin HydroTune dataset artifact runtime.

The Agent handles raw-data exploration and scientific confirmation. This module
only writes the canonical dataset artifacts required by the core hydrologic
runtime: analysis, modeling, calibration, comparison, and diagnosis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .common import DATASET_VERSION, finish, result, stamp, write_json
from .data import parse_units, read_table, source_paths, timestep
from .flood_events import FloodEventConfig, extract_flood_event_collection


SUPPORTED_SERIES_MODES = ("continuous", "event_collection")
SUPPORTED_ROLES = ("precipitation", "discharge", "upstream_discharge", "temperature", "pet")
MODELING_INTENTS = ("rainfall_runoff", "artifact_only")
CONTINUOUS_SPLIT_FRACTIONS = {"warmup": 0.10, "calibration": 0.70, "validation": 0.20}
EVENT_SPLIT_FRACTIONS = {"calibration": 0.70, "validation": 0.30}

__all__ = [
    "SUPPORTED_SERIES_MODES",
    "cmd_intake",
    "intake_dataset",
    "load_dataset",
    "select_scoring_frame",
]


def _parse_roles(items: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid role mapping {item!r}; use role=column.")
        role, column = item.split("=", 1)
        role = role.strip()
        column = column.strip()
        if role not in SUPPORTED_ROLES:
            raise ValueError(f"unsupported role: {role}")
        if not column:
            raise ValueError(f"empty column for role: {role}")
        roles[role] = column
    return roles


def _load_source(source: Path, time_column: str, series_mode: str | None) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    paths = source_paths(source)
    if not paths:
        raise ValueError("no supported data files found")
    if source.is_dir() and not series_mode:
        raise ValueError("series_mode is required for directory input")

    frames = []
    files = []
    input_mode = series_mode or "continuous"
    for path in paths:
        frame = read_table(path)
        if time_column not in frame.columns:
            raise ValueError(f"time column {time_column!r} not found in {path.name}")
        timestamps = pd.to_datetime(frame[time_column], errors="coerce")
        if timestamps.isna().any():
            raise ValueError(f"time column {time_column!r} contains unparseable values in {path.name}")

        normalized = frame.copy()
        normalized["timestamp"] = timestamps
        normalized["source_file"] = path.name
        if input_mode == "event_collection":
            normalized["event_id"] = path.stem
        frames.append(normalized)
        files.append(
            {
                "path": str(path),
                "event_id": path.stem,
                "rows": int(len(frame)),
                "time_start": timestamps.min().isoformat(),
                "time_end": timestamps.max().isoformat(),
                "timestep": timestep(timestamps),
            }
        )

    merged = pd.concat(frames, ignore_index=True)
    if input_mode == "continuous":
        merged = merged.sort_values("timestamp").reset_index(drop=True)
        if merged.timestamp.duplicated().any():
            raise ValueError("duplicate timestamps prohibit continuous merging")
    return merged, files


def _build_continuous_splits(frame: pd.DataFrame) -> dict[str, Any]:
    ordered = frame.sort_values("timestamp").reset_index(drop=True)
    sample_count = len(ordered)
    if sample_count < 3:
        return {"strategy": "chronological_10_70_20", "status": "unavailable: fewer than three samples"}
    warmup_end = max(1, int(sample_count * CONTINUOUS_SPLIT_FRACTIONS["warmup"]))
    validation_start = min(sample_count - 1, max(2, int(sample_count * (1 - CONTINUOUS_SPLIT_FRACTIONS["validation"]))))
    return {
        "strategy": "chronological_10_70_20",
        "warmup": {
            "start": ordered.timestamp.iloc[0].isoformat(),
            "end": ordered.timestamp.iloc[warmup_end - 1].isoformat(),
            "samples": warmup_end,
        },
        "calibration": {
            "start": ordered.timestamp.iloc[warmup_end].isoformat(),
            "end": ordered.timestamp.iloc[validation_start - 1].isoformat(),
            "samples": validation_start - warmup_end,
        },
        "validation": {
            "start": ordered.timestamp.iloc[validation_start].isoformat(),
            "end": ordered.timestamp.iloc[-1].isoformat(),
            "samples": sample_count - validation_start,
        },
    }


def _build_event_splits(files: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(files, key=lambda item: item["time_start"] or item["event_id"])
    cut = max(1, int(len(ordered) * EVENT_SPLIT_FRACTIONS["calibration"]))
    return {
        "strategy": "event_start_chronological_70_30",
        "calibration_event_ids": [item["event_id"] for item in ordered[:cut]],
        "validation_event_ids": [item["event_id"] for item in ordered[cut:]],
        "warmup_steps": None,
        "warmup_status": "user_confirmation_required",
    }


def _build_splits(frame: pd.DataFrame, series_mode: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    return _build_continuous_splits(frame) if series_mode == "continuous" else _build_event_splits(files)


def _variables(frame: pd.DataFrame, roles: dict[str, str], units: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    variables = []
    errors = []
    for role, column in roles.items():
        if column not in frame.columns:
            errors.append(f"column {column!r} for role {role!r} not found")
            continue
        unit = units.get(role) or units.get(column)
        if not unit:
            errors.append(f"required unit unresolved for {column!r} ({role})")
        variables.append({"column": column, "role": role, "unit": unit})
    if not variables:
        errors.append("at least one hydrologic role mapping is required")
    return variables, errors


def _data_state(frame: pd.DataFrame, variables: list[dict[str, Any]]) -> dict[str, Any]:
    states = {}
    flags = []
    for variable in variables:
        column = variable["column"]
        missing_count = int(frame[column].isna().sum())
        states[variable["role"]] = {
            "column": column,
            "state": "complete" if missing_count == 0 else "has_missing_observations",
            "missing_samples_raw": missing_count,
            "missing_fraction_raw": float(missing_count / len(frame)) if len(frame) else 0.0,
            "imputed_in_dataset": False,
        }
        if variable["role"] == "precipitation" and missing_count:
            flags.append("precipitation_missingness_affects_event_classification")
    return {"variables": states, "uncertainty_flags": flags}


def _modeling_readiness(
    variables: list[dict[str, Any]],
    basin: dict[str, Any],
    series_mode: str,
    splits: dict[str, Any],
    timestep_value: str | None,
) -> dict[str, Any]:
    roles = {variable["role"] for variable in variables}
    blocking = []
    warnings = []
    enrichment_required = []
    if "precipitation" not in roles:
        blocking.append("missing precipitation variable")
    if "discharge" not in roles:
        blocking.append("missing observed discharge variable")
    if "pet" not in roles:
        enrichment_required.append("pet")
        warnings.append("PET missing; enrichment required before models that require PET")
    if not basin.get("area_km2"):
        warnings.append("basin area missing; m3/s conversion and runoff coefficients may be unavailable")
    if not timestep_value:
        warnings.append("temporal resolution could not be inferred")
    if series_mode == "event_collection" and splits.get("warmup_steps") is None:
        warnings.append("event_collection warmup_steps requires confirmation")
    return {
        "artifact_status": "success",
        "modeling_status": "not_ready" if blocking else "ready_with_warnings" if warnings or enrichment_required else "ready",
        "blocking": blocking,
        "warnings": warnings,
        "enrichment_required": enrichment_required,
    }


def _write_dataset_artifacts(output: Path, frame: pd.DataFrame, manifest: dict[str, Any], errors: list[str]) -> list[str]:
    if not errors:
        frame.to_parquet(output / "dataset.parquet", index=False)
    write_json(output / "dataset.json", manifest)
    return ["dataset.json"] if errors else ["dataset.json", "dataset.parquet"]


def intake_dataset(
    source: Path,
    output: Path,
    *,
    time_column: str | None,
    roles: dict[str, str],
    units: dict[str, str],
    series_mode: str | None = None,
    basin_id: str | None = None,
    basin_area_km2: float | None = None,
    extract_events: bool = False,
    event_config: Path | None = None,
    modeling_intent: str = "rainfall_runoff",
) -> int:
    output.mkdir(parents=True, exist_ok=True)
    if not time_column:
        return finish(output, result("intake", errors=["--time-column is required"]))
    if modeling_intent not in MODELING_INTENTS:
        return finish(output, result("intake", errors=[f"unsupported modeling_intent: {modeling_intent}"]))

    try:
        if extract_events and series_mode == "event_collection":
            raise ValueError("--extract-events cannot be used with --series-mode event_collection")
        if extract_events and event_config is None:
            raise ValueError("--event-config is required when --extract-events is used")
        if not extract_events and event_config is not None:
            raise ValueError("--event-config requires --extract-events")
        flood_config = None
        if event_config is not None:
            flood_config = FloodEventConfig.from_mapping(
                json.loads(event_config.read_text(encoding="utf-8"))
            )

        input_mode = series_mode or "continuous"
        frame, files = _load_source(source, time_column, series_mode)
        variables, errors = _variables(frame, roles, units)
        basin: dict[str, Any] = {"id": basin_id}
        if basin_area_km2 is not None:
            if basin_area_km2 <= 0:
                errors.append("basin_area_km2 must be positive")
            else:
                basin["area_km2"] = basin_area_km2

        output_mode = input_mode
        event_extraction = None
        events = None
        extraction_warnings = []
        if extract_events:
            discharge_column = roles.get("discharge")
            if discharge_column is None:
                errors.append("event extraction requires a discharge role mapping")
            if not errors:
                extraction = extract_flood_event_collection(
                    frame=frame,
                    discharge_column=discharge_column,
                    source=source,
                    config=flood_config,
                )
                frame = extraction.frame
                files = extraction.files
                events = extraction.events
                event_extraction = extraction.metadata
                extraction_warnings = extraction.warnings
                output_mode = "event_collection"

        timestep_value = (
            pd.Timedelta(seconds=event_extraction["timestep_seconds"]).isoformat()
            if event_extraction is not None
            else timestep(frame.timestamp)
        )
        data_state = _data_state(frame, variables)
        splits = _build_splits(frame, output_mode, files)
        if event_extraction is not None:
            splits["warmup_steps"] = flood_config.warmup_steps
            splits["warmup_status"] = "confirmed_from_event_config"
            splits["warmup_filter"] = "is_warmup_column"
        readiness = _modeling_readiness(variables, basin, output_mode, splits, timestep_value)
        warnings = extraction_warnings + list(readiness["warnings"])
        if readiness["modeling_status"] == "not_ready":
            warnings.extend(readiness["blocking"])

        manifest = {
            "schema_version": DATASET_VERSION,
            "artifact_type": "dataset",
            "status": "error" if errors else "warning" if warnings else "success",
            "artifact_status": "error" if errors else "success",
            "created_at": stamp(),
            "data_file": "dataset.parquet",
            "time_column": "timestamp",
            "source_time_column": time_column,
            "timestep": timestep_value,
            "series_mode": output_mode,
            "files": files,
            "splits": splits,
            "variables": variables,
            "basin": basin,
            "data_state": data_state,
            "semantic_validation": {"modeling_intent": modeling_intent, "status": "agent_confirmed", "blocking": [], "warnings": []},
            "modeling_readiness": readiness,
            "uncertainty": {
                "flags": data_state["uncertainty_flags"],
                "status": "present" if data_state["uncertainty_flags"] else "none_detected",
            },
            "provenance": {
                "source": str(source.resolve()),
                "source_format": "directory" if source.is_dir() else source.suffix.lower(),
                "preprocessing": "agent_confirmed",
            },
        }
        if event_extraction is not None:
            manifest["provenance"]["event_extraction"] = event_extraction
            manifest["events"] = events
        outputs = _write_dataset_artifacts(output, frame, manifest, errors)
        return finish(
            output,
            result(
                "intake",
                errors=errors,
                warnings=warnings,
                outputs=outputs,
                dataset_status=manifest["status"],
                modeling_status=readiness["modeling_status"],
            ),
        )
    except Exception as exc:
        return finish(output, result("intake", errors=[str(exc)]))


def load_dataset(directory: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = json.loads((directory / "dataset.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != DATASET_VERSION:
        raise ValueError("dataset.json does not use hydrotune.dataset.v1")
    if manifest.get("status") == "error":
        raise ValueError("Dataset artifact has error status")
    return pd.read_parquet(directory / manifest["data_file"]), manifest


def select_scoring_frame(frame: pd.DataFrame, meta: dict[str, Any], purpose: str) -> pd.DataFrame:
    if meta.get("series_mode", "continuous") == "continuous":
        split = meta["splits"][purpose]
        return frame[
            (frame.timestamp >= pd.Timestamp(split["start"]))
            & (frame.timestamp <= pd.Timestamp(split["end"]))
        ]

    selected = frame[frame.event_id.isin(meta["splits"].get(f"{purpose}_event_ids", []))].copy()
    warmup = meta["splits"].get("warmup_steps")
    if warmup is None:
        raise ValueError("event_collection requires confirmed warmup_steps before scoring")
    if "is_warmup" in selected.columns:
        return selected[~selected.is_warmup.fillna(False).astype(bool)]
    return selected[selected.groupby("event_id").cumcount() >= int(warmup)]


def scoring_frame(frame: pd.DataFrame, meta: dict[str, Any], purpose: str) -> pd.DataFrame:
    return select_scoring_frame(frame, meta, purpose)


def cmd_intake(args) -> int:
    try:
        units = parse_units(args.unit)
        roles = _parse_roles(args.role)
    except Exception as exc:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        return finish(output, result("intake", errors=[str(exc)]))

    return intake_dataset(
        source=Path(args.input),
        output=Path(args.output),
        time_column=args.time_column,
        roles=roles,
        units=units,
        series_mode=args.series_mode,
        basin_id=args.basin_id,
        basin_area_km2=args.basin_area_km2,
        extract_events=args.extract_events,
        event_config=Path(args.event_config) if args.event_config else None,
        modeling_intent=args.modeling_intent,
    )
