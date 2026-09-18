"""HydroTune channel-routing operations."""

from __future__ import annotations
import numpy as np


def muskingum(inflow: np.ndarray, K: float, X: float, dt: float, reaches: int = 1, initial_flow: float | None = None) -> np.ndarray:
    inflow = np.asarray(inflow, dtype=float)
    if not len(inflow): return inflow.copy()
    K, X, dt = max(float(K), 1e-12), float(np.clip(X, 0.0, .5)), max(float(dt), 1e-12)
    current = inflow.copy()
    for _ in range(max(1, int(reaches))):
        k = K / max(1, int(reaches)); denominator = k - k * X + .5 * dt
        c0, c1, c2 = (-k * X + .5 * dt) / denominator, (k * X + .5 * dt) / denominator, (k - k * X - .5 * dt) / denominator
        coefficients = np.clip(np.array([c0, c1, c2]), 0, 1); coefficients /= coefficients.sum() if coefficients.sum() else 1
        output = np.zeros_like(current); output[0] = current[0] if initial_flow is None else initial_flow
        for i in range(1, len(current)): output[i] = coefficients[0] * current[i] + coefficients[1] * current[i - 1] + coefficients[2] * output[i - 1]
        current = np.maximum(output, 0)
    return current
