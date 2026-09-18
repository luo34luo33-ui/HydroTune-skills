"""Native four-tank rainfall-runoff model runtime."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .common import as_nonnegative, forcing, scale_daily_fraction, timestep_hours


TANK_BOUNDS = {
    "t0_is": (0.0, 50.0),
    "t0_boc": (0.15, 0.5),
    "t0_soc_uo": (0.2, 0.6),
    "t0_soc_lo": (0.15, 0.5),
    "t0_soh_uo": (50.0, 120.0),
    "t0_soh_lo": (10.0, 50.0),
    "t1_is": (0.0, 50.0),
    "t1_boc": (0.1, 0.4),
    "t1_soc": (0.1, 0.4),
    "t1_soh": (20.0, 80.0),
    "t2_is": (0.0, 50.0),
    "t2_boc": (0.05, 0.3),
    "t2_soc": (0.05, 0.3),
    "t2_soh": (10.0, 60.0),
    "t3_is": (0.0, 50.0),
    "t3_soc": (0.001, 0.05),
}

TANK_DEFAULTS = {
    "t0_is": 10.0,
    "t0_boc": 0.3,
    "t0_soc_uo": 0.4,
    "t0_soc_lo": 0.3,
    "t0_soh_uo": 80.0,
    "t0_soh_lo": 30.0,
    "t1_is": 10.0,
    "t1_boc": 0.25,
    "t1_soc": 0.25,
    "t1_soh": 50.0,
    "t2_is": 10.0,
    "t2_boc": 0.15,
    "t2_soc": 0.15,
    "t2_soh": 35.0,
    "t3_is": 10.0,
    "t3_soc": 0.02,
}

_LEGACY_ALIASES = {
    "a1": "t0_soc_uo",
    "a2": "t0_soc_lo",
    "a3": "t1_soc",
    "a4": "t3_soc",
    "b1": "t0_boc",
    "b2": "t1_boc",
    "b3": "t2_boc",
    "h1": "t0_soh_uo",
    "h2": "t0_soh_lo",
    "h3": "t1_soh",
}


def _configuration(params: dict) -> dict:
    cfg = dict(TANK_DEFAULTS)
    for legacy, canonical in _LEGACY_ALIASES.items():
        if legacy in params and canonical not in params:
            cfg[canonical] = float(params[legacy])
    for name in TANK_DEFAULTS:
        if name in params:
            cfg[name] = float(params[name])
    return cfg


def _bounded_outflows(storage: float, *flows: float) -> tuple[float, ...]:
    total = sum(flows)
    if total <= storage or total <= 0.0:
        return tuple(max(0.0, flow) for flow in flows)
    scale = storage / total
    return tuple(max(0.0, flow * scale) for flow in flows)


def tank(frame: pd.DataFrame, params: dict) -> np.ndarray:
    """Run the four-tank model and return runoff depth in mm per time step."""
    precipitation, pet, _ = forcing(frame, params)
    precipitation = np.maximum(precipitation, 0.0)
    pet = np.maximum(pet, 0.0)
    cfg = _configuration(params)
    dt_hours = timestep_hours(params, 24.0)
    coefficients = {
        name: scale_daily_fraction(cfg[name], dt_hours)
        for name in (
            "t0_boc", "t0_soc_uo", "t0_soc_lo", "t1_boc", "t1_soc",
            "t2_boc", "t2_soc", "t3_soc",
        )
    }
    stores = np.array([cfg[f"t{i}_is"] for i in range(4)], dtype=float)
    runoff = np.zeros(len(frame), dtype=float)

    for i, rain in enumerate(precipitation):
        stores[0] = max(0.0, stores[0] + rain - pet[i])
        t0_upper = coefficients["t0_soc_uo"] * max(0.0, stores[0] - cfg["t0_soh_uo"])
        t0_lower = coefficients["t0_soc_lo"] * max(0.0, stores[0] - cfg["t0_soh_lo"])
        t0_bottom = coefficients["t0_boc"] * stores[0]
        t0_upper, t0_lower, t0_bottom = _bounded_outflows(
            stores[0], t0_upper, t0_lower, t0_bottom
        )
        stores[0] -= t0_upper + t0_lower + t0_bottom
        stores[1] += t0_bottom

        t1_side = coefficients["t1_soc"] * max(0.0, stores[1] - cfg["t1_soh"])
        t1_bottom = coefficients["t1_boc"] * stores[1]
        t1_side, t1_bottom = _bounded_outflows(stores[1], t1_side, t1_bottom)
        stores[1] -= t1_side + t1_bottom
        stores[2] += t1_bottom

        t2_side = coefficients["t2_soc"] * max(0.0, stores[2] - cfg["t2_soh"])
        t2_bottom = coefficients["t2_boc"] * stores[2]
        t2_side, t2_bottom = _bounded_outflows(stores[2], t2_side, t2_bottom)
        stores[2] -= t2_side + t2_bottom
        stores[3] += t2_bottom

        t3_side = min(stores[3], coefficients["t3_soc"] * stores[3])
        stores[3] -= t3_side
        runoff[i] = t0_upper + t0_lower + t1_side + t2_side + t3_side
    return as_nonnegative(runoff)
