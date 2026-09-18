"""Native HBV rainfall-runoff model runtime."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .common import (
    as_nonnegative,
    calendar_months,
    numeric_series,
    scale_daily_fraction,
    timestep_hours,
)


HBV_BOUNDS = {
    "fc": (100.0, 200.0),
    "beta": (1.0, 7.0),
    "c": (0.01, 0.07),
    "k0": (0.05, 0.2),
    "l": (2.0, 5.0),
    "k1": (0.01, 0.1),
    "k2": (0.01, 0.05),
    "kp": (0.01, 0.05),
    "lp": (0.3, 1.0),
}

HBV_DEFAULTS = {
    "fc": 195.0,
    "beta": 2.6143,
    "c": 0.07,
    "k0": 0.163,
    "l": 4.87,
    "k1": 0.029,
    "k2": 0.049,
    "kp": 0.050,
    "lp": 0.5,
}

DEFAULT_MONTHLY_TEMP = np.array(
    [2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 28.0, 27.0, 22.0, 15.0, 8.0, 3.0]
)
DEFAULT_MONTHLY_PET = np.array(
    [1.0, 1.5, 2.5, 4.0, 5.5, 6.5, 7.0, 6.5, 5.0, 3.0, 1.5, 1.0]
)


def _configuration(params: dict) -> dict:
    cfg = {**HBV_DEFAULTS, **params}
    if "l" not in params and "uzl" in params:
        cfg["l"] = float(params["uzl"])
    if "kp" not in params and "perc" in params:
        cfg["kp"] = float(params["perc"])
    return cfg


def hbv(frame: pd.DataFrame, params: dict) -> np.ndarray:
    """Run HBV and return local-basin runoff depth in millimetres per step."""
    cfg = _configuration(params)
    dt_hours = timestep_hours(params, 24.0)
    dt_days = dt_hours / 24.0
    precipitation_column = params.get("precipitation_column", "precipitation")
    pet_column = params.get("pet_column", "pet")
    temperature_column = params.get("temperature_column", "temperature")
    if precipitation_column not in frame:
        raise ValueError(f"missing precipitation column {precipitation_column!r}")
    precipitation = np.maximum(numeric_series(frame, precipitation_column, 0.0), 0.0)
    temperature = numeric_series(frame, temperature_column, 5.0)
    months = calendar_months(frame)
    climate_temperature = DEFAULT_MONTHLY_TEMP[months - 1]

    if pet_column in frame:
        pet = np.maximum(numeric_series(frame, pet_column, 0.0), 0.0)
    else:
        pet = DEFAULT_MONTHLY_PET[months - 1] * dt_days
    if temperature_column in frame:
        pet *= np.maximum(0.0, 1.0 + float(cfg["c"]) * (temperature - climate_temperature))

    fc = max(float(cfg["fc"]), 1e-12)
    beta = max(float(cfg["beta"]), 0.0)
    lp = max(float(cfg["lp"]), 1e-12)
    threshold = max(float(cfg["l"]), 0.0)
    k0 = scale_daily_fraction(float(cfg["k0"]), dt_hours)
    k1 = scale_daily_fraction(float(cfg["k1"]), dt_hours)
    k2 = scale_daily_fraction(float(cfg["k2"]), dt_hours)
    kp = scale_daily_fraction(float(cfg["kp"]), dt_hours)
    tt = float(params.get("tt", 0.0))
    cfmax = max(float(params.get("cfmax", 2.0)), 0.0) * dt_days

    snow = soil = upper = lower = 0.0
    runoff = np.zeros(len(frame), dtype=float)
    for i in range(len(frame)):
        rain = precipitation[i] if temperature[i] > tt else 0.0
        snow += precipitation[i] if temperature[i] <= tt else 0.0
        melt = min(snow, max(0.0, cfmax * (temperature[i] - tt)))
        snow -= melt
        water = rain + melt

        recharge = water * (soil / fc) ** beta
        evap = pet[i] * min(soil / (lp * fc), 1.0)
        soil = float(np.clip(soil + water - recharge - evap, 0.0, fc))
        upper += recharge

        quick = k0 * max(upper - threshold, 0.0)
        interflow = k1 * upper
        transfer = kp * upper
        total_upper_outflow = quick + interflow + transfer
        if total_upper_outflow > upper and total_upper_outflow > 0.0:
            scale = upper / total_upper_outflow
            quick *= scale
            interflow *= scale
            transfer *= scale
        upper = max(0.0, upper - quick - interflow - transfer)

        lower += transfer
        baseflow = min(lower, k2 * lower)
        lower -= baseflow
        runoff[i] = quick + interflow + baseflow
    return as_nonnegative(runoff)
