"""HydroTune ensemble weighting operations."""

from __future__ import annotations
import numpy as np


def bma_weights(scores: list[float], temperature: float = 2.0) -> np.ndarray:
    values = np.asarray(scores, dtype=float); valid = np.isfinite(values)
    if not valid.any(): return np.full(len(values), 1 / len(values))
    safe = np.where(valid, values, values[valid].min() - 10); logits = (safe - safe.max()) / max(float(temperature), 1e-9); weights = np.exp(logits); return weights / weights.sum()

def bma(simulations: list[np.ndarray], weights: np.ndarray) -> np.ndarray:
    if not simulations or len(simulations) != len(weights): raise ValueError("simulations and weights must have the same non-zero length")
    return np.average(np.vstack(simulations), axis=0, weights=weights)
