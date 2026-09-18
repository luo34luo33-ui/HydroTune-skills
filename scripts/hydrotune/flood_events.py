"""Deterministic baseflow, peak, and flood-boundary extraction for Intake."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


FLOOD_EVENT_METHOD = "eckhardt_peak_boundary_v1"


@dataclass(frozen=True)
class FloodEventConfig:
    bfi_max: float
    alpha: float | None
    peak_quantile: float
    prominence_factor: float
    min_peak_distance_hours: float
    boundary_fraction: float
    boundary_persistence_steps: int
    max_search_days: float
    merge_gap_hours: float
    valley_ratio_threshold: float
    min_event_duration_hours: float
    min_peak_flow: float | None
    min_event_volume: float | None
    warmup_steps: int

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "FloodEventConfig":
        if not isinstance(values, dict):
            raise ValueError("event config must be a JSON object")
        expected = set(cls.__annotations__)
        missing = sorted(expected - set(values))
        unknown = sorted(set(values) - expected)
        if missing:
            raise ValueError(f"event config missing keys: {', '.join(missing)}")
        if unknown:
            raise ValueError(f"event config has unknown keys: {', '.join(unknown)}")

        def number(name: str, *, optional: bool = False) -> float | None:
            value = values[name]
            if value is None and optional:
                return None
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"event config {name} must be numeric")
            parsed = float(value)
            if not np.isfinite(parsed):
                raise ValueError(f"event config {name} must be finite")
            return parsed

        def integer(name: str) -> int:
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                raise ValueError(f"event config {name} must be an integer")
            return int(value)

        config = cls(
            bfi_max=float(number("bfi_max")),
            alpha=number("alpha", optional=True),
            peak_quantile=float(number("peak_quantile")),
            prominence_factor=float(number("prominence_factor")),
            min_peak_distance_hours=float(number("min_peak_distance_hours")),
            boundary_fraction=float(number("boundary_fraction")),
            boundary_persistence_steps=integer("boundary_persistence_steps"),
            max_search_days=float(number("max_search_days")),
            merge_gap_hours=float(number("merge_gap_hours")),
            valley_ratio_threshold=float(number("valley_ratio_threshold")),
            min_event_duration_hours=float(number("min_event_duration_hours")),
            min_peak_flow=number("min_peak_flow", optional=True),
            min_event_volume=number("min_event_volume", optional=True),
            warmup_steps=integer("warmup_steps"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not 0 < self.bfi_max < 1:
            raise ValueError("event config bfi_max must be in (0, 1)")
        if self.alpha is not None and not 0 < self.alpha < 1:
            raise ValueError("event config alpha must be null or in (0, 1)")
        if not 0 <= self.peak_quantile <= 1:
            raise ValueError("event config peak_quantile must be in [0, 1]")
        if self.prominence_factor < 0:
            raise ValueError("event config prominence_factor must be nonnegative")
        if self.min_peak_distance_hours <= 0:
            raise ValueError("event config min_peak_distance_hours must be positive")
        if not 0 <= self.boundary_fraction <= 1:
            raise ValueError("event config boundary_fraction must be in [0, 1]")
        if self.boundary_persistence_steps < 1:
            raise ValueError("event config boundary_persistence_steps must be positive")
        if self.max_search_days <= 0:
            raise ValueError("event config max_search_days must be positive")
        if self.merge_gap_hours < 0:
            raise ValueError("event config merge_gap_hours must be nonnegative")
        if not 0 <= self.valley_ratio_threshold <= 1:
            raise ValueError("event config valley_ratio_threshold must be in [0, 1]")
        if self.min_event_duration_hours < 0:
            raise ValueError("event config min_event_duration_hours must be nonnegative")
        if self.min_peak_flow is not None and self.min_peak_flow < 0:
            raise ValueError("event config min_peak_flow must be null or nonnegative")
        if self.min_event_volume is not None and self.min_event_volume < 0:
            raise ValueError("event config min_event_volume must be null or nonnegative")
        if self.warmup_steps < 0:
            raise ValueError("event config warmup_steps must be nonnegative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FloodEventExtraction:
    frame: pd.DataFrame
    events: list[dict[str, Any]]
    files: list[dict[str, Any]]
    metadata: dict[str, Any]
    warnings: list[str]


def infer_timestep_seconds(time: pd.Series) -> tuple[float, float]:
    timestamps = pd.to_datetime(time, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("event extraction requires fully parseable timestamps")
    differences = timestamps.diff().dt.total_seconds().dropna().to_numpy(dtype=float)
    if len(differences) == 0:
        raise ValueError("event extraction cannot infer a time step")
    median = float(np.median(differences))
    if median <= 0 or np.any(differences <= 0):
        raise ValueError("event extraction requires strictly increasing timestamps")
    tolerance = max(1.0, 0.01 * median)
    regularity = float(np.mean(np.abs(differences - median) <= tolerance))
    return median, regularity


def estimate_recession_alpha(discharge: np.ndarray) -> float:
    flow = np.asarray(discharge, dtype=float)
    previous = flow[:-1]
    current = flow[1:]
    mask = (
        np.isfinite(previous)
        & np.isfinite(current)
        & (previous > 0)
        & (current > 0)
        & (current < previous)
    )
    ratios = current[mask] / previous[mask]
    ratios = ratios[(ratios > 0) & (ratios < 1)]
    if len(ratios) < 20:
        return 0.95
    return float(np.clip(np.quantile(ratios, 0.90), 0.80, 0.9999))


def eckhardt_baseflow(discharge: np.ndarray, alpha: float, bfi_max: float) -> np.ndarray:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if not 0 < bfi_max < 1:
        raise ValueError("bfi_max must be in (0, 1)")
    flow = np.asarray(discharge, dtype=float)
    if len(flow) == 0 or not np.isfinite(flow).all() or np.any(flow < 0):
        raise ValueError("Eckhardt baseflow requires finite nonnegative discharge")
    baseflow = np.empty_like(flow)
    baseflow[0] = flow[0]
    denominator = 1.0 - alpha * bfi_max
    for index in range(1, len(flow)):
        value = (
            (1.0 - bfi_max) * alpha * baseflow[index - 1]
            + (1.0 - alpha) * bfi_max * flow[index]
        ) / denominator
        baseflow[index] = min(max(value, 0.0), flow[index])
    return baseflow


def detect_peaks(quickflow: np.ndarray, dt_seconds: float, config: FloodEventConfig) -> np.ndarray:
    values = np.asarray(quickflow, dtype=float)
    positive = values[values > 0]
    if len(positive) == 0:
        return np.array([], dtype=int)
    height = float(np.quantile(positive, config.peak_quantile))
    prominence = max(np.finfo(float).eps, config.prominence_factor * float(np.nanstd(values)))
    distance = max(1, int(round(config.min_peak_distance_hours * 3600 / dt_seconds)))
    peaks, _ = find_peaks(values, height=height, prominence=prominence, distance=distance)
    return peaks.astype(int)


def find_left_boundary(
    peak: int,
    values: np.ndarray,
    persistence: int,
    fraction: float,
    max_steps: int,
) -> int:
    left_limit = max(0, peak - max_steps)
    segment = values[left_limit : peak + 1]
    baseline = float(np.nanmin(segment))
    threshold = baseline + fraction * max(float(values[peak]) - baseline, 0.0)
    for index in range(peak - 1, left_limit + persistence - 2, -1):
        start = index - persistence + 1
        if start < left_limit:
            break
        block = values[start : index + 1]
        if len(block) == persistence and np.all(block <= threshold):
            return index
    return left_limit + int(np.nanargmin(segment))


def find_right_boundary(
    peak: int,
    values: np.ndarray,
    persistence: int,
    fraction: float,
    max_steps: int,
) -> int:
    right_limit = min(len(values) - 1, peak + max_steps)
    segment = values[peak : right_limit + 1]
    baseline = float(np.nanmin(segment))
    threshold = baseline + fraction * max(float(values[peak]) - baseline, 0.0)
    for index in range(peak + 1, right_limit - persistence + 2):
        block = values[index : index + persistence]
        if len(block) == persistence and np.all(block <= threshold):
            return index
    return peak + int(np.nanargmin(segment))


def build_raw_events(
    peaks: np.ndarray,
    discharge: np.ndarray,
    dt_seconds: float,
    config: FloodEventConfig,
) -> list[dict[str, int]]:
    max_steps = max(1, int(round(config.max_search_days * 86400 / dt_seconds)))
    events = []
    for peak in peaks:
        start = find_left_boundary(
            int(peak), discharge, config.boundary_persistence_steps, config.boundary_fraction, max_steps
        )
        end = find_right_boundary(
            int(peak), discharge, config.boundary_persistence_steps, config.boundary_fraction, max_steps
        )
        if start <= peak <= end:
            events.append({"start_idx": int(start), "peak_idx": int(peak), "end_idx": int(end)})
    return events


def merge_events(
    raw_events: list[dict[str, int]],
    discharge: np.ndarray,
    dt_seconds: float,
    config: FloodEventConfig,
) -> list[dict[str, int]]:
    if not raw_events:
        return []
    ordered = sorted(raw_events, key=lambda event: event["start_idx"])
    merged = [ordered[0].copy()]
    max_gap_steps = max(0, int(round(config.merge_gap_hours * 3600 / dt_seconds)))
    for current in ordered[1:]:
        previous = merged[-1]
        overlap = current["start_idx"] <= previous["end_idx"]
        gap_steps = max(0, current["start_idx"] - previous["end_idx"] - 1)
        valley_merge = False
        if not overlap and gap_steps <= max_gap_steps:
            left_peak, right_peak = sorted((previous["peak_idx"], current["peak_idx"]))
            valley = float(np.min(discharge[left_peak : right_peak + 1]))
            smaller_peak = float(min(discharge[previous["peak_idx"]], discharge[current["peak_idx"]]))
            valley_merge = smaller_peak > 0 and valley / smaller_peak >= config.valley_ratio_threshold
        if overlap or valley_merge:
            start = min(previous["start_idx"], current["start_idx"])
            end = max(previous["end_idx"], current["end_idx"])
            peak = start + int(np.argmax(discharge[start : end + 1]))
            merged[-1] = {"start_idx": start, "peak_idx": peak, "end_idx": end}
        else:
            merged.append(current.copy())
    return merged


def refine_events_around_main_peak(
    events: list[dict[str, int]],
    quickflow: np.ndarray,
    dt_seconds: float,
    config: FloodEventConfig,
) -> list[dict[str, int]]:
    max_steps = max(1, int(round(config.max_search_days * 86400 / dt_seconds)))
    refined = []
    for event in events:
        peak = int(event["peak_idx"])
        refined.append(
            {
                "start_idx": find_left_boundary(
                    peak, quickflow, config.boundary_persistence_steps, config.boundary_fraction, max_steps
                ),
                "peak_idx": peak,
                "end_idx": find_right_boundary(
                    peak, quickflow, config.boundary_persistence_steps, config.boundary_fraction, max_steps
                ),
            }
        )
    return refined


def _volume(values: np.ndarray, dt_seconds: float) -> float:
    trapezoid = getattr(np, "trapezoid", np.trapz)
    return float(trapezoid(values, dx=dt_seconds))


def extract_flood_event_collection(
    frame: pd.DataFrame,
    discharge_column: str,
    source: Path,
    config: FloodEventConfig,
) -> FloodEventExtraction:
    reserved = {"event_id", "baseflow", "quickflow", "quickflow_ratio", "is_warmup", "relative_step", "hours_from_start"}
    conflicts = sorted(reserved.intersection(frame.columns))
    if conflicts:
        raise ValueError(f"event extraction output columns already exist: {', '.join(conflicts)}")
    if discharge_column not in frame.columns:
        raise ValueError(f"event extraction discharge column not found: {discharge_column}")
    if len(frame) < 10:
        raise ValueError("event extraction requires at least 10 samples")

    discharge = pd.to_numeric(frame[discharge_column], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(discharge).all():
        raise ValueError("event extraction requires discharge without missing or nonnumeric values")
    if np.any(discharge < 0):
        raise ValueError("event extraction requires nonnegative discharge")

    dt_seconds, regularity = infer_timestep_seconds(frame["timestamp"])
    alpha = config.alpha if config.alpha is not None else estimate_recession_alpha(discharge)
    baseflow = eckhardt_baseflow(discharge, alpha, config.bfi_max)
    quickflow = np.maximum(discharge - baseflow, 0.0)
    quickflow_ratio = quickflow / np.maximum(discharge, np.finfo(float).eps)

    work = frame.copy()
    work["baseflow"] = baseflow
    work["quickflow"] = quickflow
    work["quickflow_ratio"] = quickflow_ratio

    peaks = detect_peaks(quickflow, dt_seconds, config)
    raw_events = build_raw_events(peaks, discharge, dt_seconds, config)
    merged_events = merge_events(raw_events, discharge, dt_seconds, config)
    refined_events = refine_events_around_main_peak(merged_events, quickflow, dt_seconds, config)

    event_frames = []
    event_records = []
    event_files = []
    filtered_count = 0
    for event in refined_events:
        start, peak, end = event["start_idx"], event["peak_idx"], event["end_idx"]
        duration_hours = (end - start) * dt_seconds / 3600.0
        total_volume = _volume(discharge[start : end + 1], dt_seconds)
        if duration_hours < config.min_event_duration_hours:
            filtered_count += 1
            continue
        if config.min_peak_flow is not None and discharge[peak] < config.min_peak_flow:
            filtered_count += 1
            continue
        if config.min_event_volume is not None and total_volume < config.min_event_volume:
            filtered_count += 1
            continue

        sequence = len(event_records) + 1
        event_id = f"flood-{work.timestamp.iloc[start].strftime('%Y%m%dT%H%M%S')}-{sequence:03d}"
        export_start = max(0, start - config.warmup_steps)
        part = work.iloc[export_start : end + 1].copy()
        part.insert(0, "event_id", event_id)
        source_indices = np.arange(export_start, end + 1, dtype=int)
        part["is_warmup"] = source_indices < start
        part["relative_step"] = source_indices - start
        part["hours_from_start"] = (source_indices - start) * dt_seconds / 3600.0
        event_frames.append(part)

        quick_volume = _volume(quickflow[start : end + 1], dt_seconds)
        base_volume = _volume(baseflow[start : end + 1], dt_seconds)
        local_peaks, _ = find_peaks(discharge[start : end + 1])
        record = {
            "event_id": event_id,
            "warmup_start": work.timestamp.iloc[export_start].isoformat(),
            "start": work.timestamp.iloc[start].isoformat(),
            "peak_time": work.timestamp.iloc[peak].isoformat(),
            "end": work.timestamp.iloc[end].isoformat(),
            "warmup_samples": int(start - export_start),
            "samples": int(end - export_start + 1),
            "start_flow": float(discharge[start]),
            "peak_discharge": float(discharge[peak]),
            "end_flow": float(discharge[end]),
            "duration_hours": float(duration_hours),
            "total_volume": total_volume,
            "quickflow_volume": quick_volume,
            "baseflow_volume": base_volume,
            "quickflow_fraction": quick_volume / total_volume if total_volume > 0 else None,
            "n_local_peaks": int(len(local_peaks)),
        }
        event_records.append(record)
        event_files.append(
            {
                "path": str(source),
                "source_files": sorted(part.source_file.astype(str).unique().tolist()),
                "event_id": event_id,
                "rows": int(len(part)),
                "warmup_start": record["warmup_start"],
                "time_start": record["start"],
                "time_end": record["end"],
                "timestep": pd.Timedelta(seconds=dt_seconds).isoformat(),
            }
        )

    if not event_frames:
        raise ValueError("event extraction produced no events after peak, boundary, and size filters")

    warnings = []
    if regularity < 0.99:
        warnings.append(
            f"event extraction time regularity is {regularity:.1%}; fixed median timestep was used"
        )
    metadata = {
        "method": FLOOD_EVENT_METHOD,
        "timestep_seconds": dt_seconds,
        "time_regularity": regularity,
        "alpha": float(alpha),
        "alpha_source": "confirmed" if config.alpha is not None else "estimated_recession_quantile",
        "candidate_peak_count": int(len(peaks)),
        "raw_event_count": int(len(raw_events)),
        "merged_event_count": int(len(merged_events)),
        "refined_event_count": int(len(refined_events)),
        "filtered_event_count": int(filtered_count),
        "final_event_count": int(len(event_records)),
        "config": config.to_dict(),
    }
    return FloodEventExtraction(
        frame=pd.concat(event_frames, ignore_index=True),
        events=event_records,
        files=event_files,
        metadata=metadata,
        warnings=warnings,
    )
