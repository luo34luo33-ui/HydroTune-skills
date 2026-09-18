"""Shared native-model forcing and output helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def numeric_series(frame: pd.DataFrame, column: str, default: float) -> np.ndarray:
    """Read a numeric forcing column, replacing missing or invalid values."""
    values = frame[column] if column in frame else pd.Series(default, index=frame.index)
    return pd.to_numeric(values, errors="coerce").fillna(default).to_numpy(float)


def forcing(frame: pd.DataFrame, params: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    precipitation_column = params.get("precipitation_column", "precipitation")
    if precipitation_column not in frame:
        raise ValueError(f"missing precipitation column {precipitation_column!r}")
    p = numeric_series(frame, precipitation_column, 0.0)
    pet = numeric_series(frame, params.get("pet_column", "pet"), 0.0)
    temp = numeric_series(frame, params.get("temperature_column", "temperature"), 5.0)
    return p, pet, temp


def timestep_hours(params: dict, default: float) -> float:
    """Return a finite, positive model time step in hours."""
    value = float(params.get("dt_hours", default))
    if not np.isfinite(value) or value <= 0.0:
        raise ValueError("dt_hours must be a finite positive number")
    return value


def scale_daily_fraction(daily_fraction: float, dt_hours: float) -> float:
    """Convert a daily fractional release to an equivalent step fraction."""
    fraction = float(daily_fraction)
    if not np.isfinite(fraction):
        raise ValueError("daily fraction must be finite")
    fraction = float(np.clip(fraction, 0.0, 1.0))
    return 1.0 - (1.0 - fraction) ** (timestep_hours({"dt_hours": dt_hours}, 24.0) / 24.0)


def calendar_months(frame: pd.DataFrame, column: str = "timestamp") -> np.ndarray:
    """Return one-based calendar months, defaulting invalid timestamps to January."""
    if column not in frame:
        return np.ones(len(frame), dtype=int)
    timestamps = pd.to_datetime(frame[column], errors="coerce")
    return timestamps.dt.month.fillna(1).to_numpy(int)


def as_nonnegative(values: np.ndarray) -> np.ndarray:
    return np.maximum(np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0), 0.0)
