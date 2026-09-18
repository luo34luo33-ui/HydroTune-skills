"""Native model registry and lookup runtime."""

from __future__ import annotations

from .hbv import HBV_BOUNDS, HBV_DEFAULTS, hbv
from .tank import TANK_BOUNDS, TANK_DEFAULTS, tank
from .xaj import XAJ_BOUNDS, XAJ_DEFAULTS, xaj


MODELS = {
    "hbv": {"runner": hbv, "bounds": HBV_BOUNDS, "defaults": HBV_DEFAULTS},
    "xaj": {"runner": xaj, "bounds": XAJ_BOUNDS, "defaults": XAJ_DEFAULTS},
    "tank": {"runner": tank, "bounds": TANK_BOUNDS, "defaults": TANK_DEFAULTS},
}


def model_names() -> tuple[str, ...]: return tuple(MODELS)
def get_model(name: str) -> dict:
    try: return MODELS[name.lower()]
    except KeyError: raise ValueError(f"unsupported native model {name!r}; choose one of {', '.join(model_names())}")
