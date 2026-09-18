"""Native Xin'anjiang rainfall-runoff model runtime."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .common import as_nonnegative, forcing, timestep_hours


_EPS = 1e-12

XAJ_BOUNDS = {
    "B": (0.2, 0.4),
    "C": (0.10, 0.20),
    "WM": (120.0, 125.0),
    "WUM": (15.0, 30.0),
    "WLM": (60.0, 90.0),
    "IM": (0.010, 0.040),
    "SM": (10.0, 60.0),
    "EX": (1.0, 1.5),
    "K": (0.8, 1.2),
    "KG": (0.30, 0.50),
    "KI": (0.15, 0.40),
    "CG": (0.90, 1.00),
    "CI": (0.75, 0.95),
    "CS": (0.15, 0.80),
    "L": (0.0, 12.0),
    "X": (0.0, 0.5),
    "WUM_init": (0.5, 10.0),
    "WLM_init": (0.5, 50.0),
    "WDM_init": (0.5, 50.0),
    "FR1": (0.01, 0.99),
    "S1": (1.0, 20.0),
    "Q": (1.0, 10.0),
    "n": (1.0, 5.0),
}

XAJ_DEFAULTS = {
    "K": 1.1,
    "B": 0.3,
    "C": 0.15,
    "WM": 120.0,
    "WUM": 20.0,
    "WLM": 70.0,
    "IM": 0.01,
    "SM": 50.0,
    "EX": 1.5,
    "KG": 0.3,
    "KI": 0.15,
    "CG": 0.95,
    "CI": 0.8,
    "CS": 0.6,
    "L": 1,
    "X": 0.3,
    "n": 1,
    "WUM_init": 10.0,
    "WLM_init": 30.0,
    "WDM_init": 20.0,
    "S1": 10.0,
    "FR1": 0.3,
    "Q": 5.0,
}


def _clip01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0 - _EPS))


def _positive(value: float) -> float:
    return float(max(value, _EPS))


class XinAnJiangModel:
    """Three-layer Xin'anjiang model adapted from the research notebook."""

    def __init__(self, dt_hours: float = 1.0, area_km2: float = 1.0):
        for name, value in XAJ_DEFAULTS.items():
            if name != "n":
                setattr(self, name, value)
        self.n_reaches = int(XAJ_DEFAULTS["n"])
        self.T = max(float(dt_hours), _EPS)
        self.Area = max(float(area_km2), _EPS)
        self._update_derived_params()

    def _update_derived_params(self) -> None:
        self.WDM = max(0.0, float(self.WM - self.WUM - self.WLM))
        self.WUM_init = float(np.clip(self.WUM_init, 0.0, self.WUM))
        self.WLM_init = float(np.clip(self.WLM_init, 0.0, self.WLM))
        self.WDM_init = float(np.clip(self.WDM_init, 0.0, self.WDM))
        self.WMM = float(self.WM)
        self.SMM = float(self.SM)
        self.Sm = float(self.SM)

    def set_params(self, **params: float) -> None:
        for name, value in params.items():
            if name == "n":
                self.n_reaches = max(0, int(round(float(value))))
            elif name == "L":
                self.L = max(0, int(round(float(value))))
            elif hasattr(self, name) and name not in {"Area", "T"}:
                setattr(self, name, float(value))
        self._update_derived_params()

    def _calculate_soil_storage(self, df: pd.DataFrame, i: int) -> None:
        if i == 0:
            df.loc[i, ["WU", "WL", "WD"]] = [self.WUM_init, self.WLM_init, self.WDM_init]
            return

        infiltration = df.at[i - 1, "PE"] - df.at[i - 1, "R"]
        wu = df.at[i - 1, "WU"] + infiltration
        wl = df.at[i - 1, "WL"]
        wd = df.at[i - 1, "WD"]
        if wu < 0.0:
            wl += wu
            wu = 0.0
            if wl < 0.0:
                wd = max(0.0, wd + wl)
                wl = 0.0
        elif wu > self.WUM:
            wl += wu - self.WUM
            wu = self.WUM
            if wl > self.WLM:
                wd = min(self.WDM, wd + wl - self.WLM)
                wl = self.WLM
        df.loc[i, ["WU", "WL", "WD"]] = [wu, wl, wd]

    def _calculate_evaporation(self, df: pd.DataFrame, i: int) -> None:
        ep = df.at[i, "E0"] * self.K
        p_pervious = df.at[i, "P_perv"]
        wu = df.at[i, "WU"]
        wl = df.at[i, "WL"]
        eu = min(ep, wu + p_pervious)
        deficit = max(0.0, ep - eu)
        if deficit == 0.0:
            el = ed = 0.0
        elif wl >= self.C * self.WLM:
            el = deficit * wl / _positive(self.WLM)
            ed = 0.0
        elif wl >= self.C * deficit:
            el = self.C * deficit
            ed = 0.0
        else:
            el = wl
            ed = self.C * deficit - el
        evaporation = eu + el + ed
        df.loc[i, ["EP", "EU", "EL", "ED", "E", "PE"]] = [
            ep, eu, el, ed, evaporation, p_pervious - evaporation,
        ]
        df.at[i, "W"] = wu + wl + df.at[i, "WD"]

    def _calculate_runoff(self, df: pd.DataFrame, i: int) -> None:
        pe = df.at[i, "PE"]
        water = df.at[i, "W"]
        if pe <= 0.0:
            runoff = 0.0
        else:
            remaining = _clip01(1.0 - water / _positive(self.WM))
            a = self.WMM * (1.0 - math.pow(remaining, 1.0 / (1.0 + self.B)))
            if a + pe <= self.WMM:
                inner = _clip01(1.0 - (pe + a) / _positive(self.WMM))
                runoff = pe + water - self.WM + self.WM * math.pow(inner, self.B + 1.0)
            else:
                runoff = pe - (self.WM - water)
        runoff = max(0.0, float(runoff))
        df.at[i, "R"] = runoff
        if runoff > 0.0:
            df.at[i, "FR"] = float(np.clip(runoff / _positive(pe), 1e-9, 1.0))
        else:
            df.at[i, "FR"] = self.FR1 if i == 0 else df.at[i - 1, "FR"]

    def _separate_sources(self, df: pd.DataFrame, i: int) -> None:
        if i == 0:
            df.at[i, "S1"] = self.S1
        fr = max(float(df.at[i, "FR"]), 1e-9)
        previous_fr = max(float(df.at[i - 1, "FR"]) if i > 0 else self.FR1, 1e-9)
        adjusted_storage = float(df.at[i, "S1"]) * previous_fr / fr
        pe = float(df.at[i, "PE"])
        if pe > 0.0:
            ratio = _clip01(adjusted_storage / _positive(self.Sm))
            au = self.SMM * (1.0 - math.pow(1.0 - ratio, 1.0 / (1.0 + self.EX)))
            if pe + au < self.SMM:
                inner = _clip01(1.0 - (pe + au) / _positive(self.SMM))
                rs_raw = fr * (
                    pe + adjusted_storage - self.Sm
                    + self.Sm * math.pow(inner, 1.0 + self.EX)
                )
            else:
                rs_raw = fr * (pe + adjusted_storage - self.Sm)
            rs = float(np.clip(rs_raw, 0.0, df.at[i, "R"]))
            storage = adjusted_storage + (df.at[i, "R"] - rs) / fr
        else:
            rs = 0.0
            storage = adjusted_storage
        df.loc[i, ["RS", "RI", "RG"]] = [
            rs, self.KI * storage * fr, self.KG * storage * fr,
        ]
        if i < len(df) - 1:
            df.at[i + 1, "S1"] = max(0.0, storage * (1.0 - self.KI - self.KG))

    def _route_sources(self, df: pd.DataFrame, i: int, conversion: float) -> None:
        impermeable_runoff = float(df.at[i, "P_im"])
        qs = max(0.0, (df.at[i, "RS"] + impermeable_runoff) * conversion)
        if i == 0:
            qi = qg = self.Q / 3.0
        else:
            qi = self.CI * df.at[i - 1, "QI"] + (1.0 - self.CI) * df.at[i, "RI"] * conversion
            qg = self.CG * df.at[i - 1, "QG"] + (1.0 - self.CG) * df.at[i, "RG"] * conversion
        total = qs + qi + qg
        if i <= self.L:
            delayed = self.Q
        else:
            delayed = self.CS * df.at[i - 1, "Qt"] + (1.0 - self.CS) * df.at[i - self.L, "QT"]
        df.loc[i, ["R_im", "QS", "QI", "QG", "QT", "Qt"]] = [
            impermeable_runoff, qs, qi, qg, total, delayed,
        ]

    def _route_channel(self, df: pd.DataFrame, i: int) -> None:
        df.at[i, "Q1"] = df.at[i, "Qt"]
        if self.n_reaches <= 0:
            return
        channel_k = self.T
        channel_x = 0.5 - self.n_reaches * (1.0 - 2.0 * self.X) / 2.0
        denominator = 0.5 * self.T + channel_k - channel_k * channel_x
        c0 = (0.5 * self.T - channel_k * channel_x) / denominator
        c1 = (0.5 * self.T + channel_k * channel_x) / denominator
        c2 = 1.0 - c0 - c1
        for reach in range(self.n_reaches):
            inflow = df.at[i, f"Q{reach + 1}"]
            if i == 0:
                previous_inflow = previous_outflow = self.Q
            else:
                previous_inflow = df.at[i - 1, f"Q{reach + 1}"]
                previous_outflow = df.at[i - 1, f"Q{reach + 2}"]
            df.at[i, f"Q{reach + 2}"] = (
                c0 * inflow + c1 * previous_inflow + c2 * previous_outflow
            )

    def run_model(self, input_data: pd.DataFrame) -> pd.DataFrame:
        df = input_data.reset_index(drop=True).copy()
        state_columns = [
            "WU", "WL", "WD", "EP", "EU", "EL", "ED", "E", "PE", "W", "R", "FR",
            "S1", "RS", "RI", "RG", "QS", "QI", "QG", "QT", "Qt", "R_im",
        ]
        for column in state_columns:
            df[column] = 0.0
        df["P"] = pd.to_numeric(df["P"], errors="coerce").fillna(0.0).clip(lower=0.0)
        df["E0"] = pd.to_numeric(df["E0"], errors="coerce").fillna(0.0).clip(lower=0.0)
        df["P_perv"] = (1.0 - float(self.IM)) * df["P"]
        df["P_im"] = float(self.IM) * df["P"]
        for reach in range(1, self.n_reaches + 2):
            df[f"Q{reach}"] = 0.0
        conversion = self.Area / (3.6 * self.T)
        for i in range(len(df)):
            self._calculate_soil_storage(df, i)
            self._calculate_evaporation(df, i)
            self._calculate_runoff(df, i)
            self._separate_sources(df, i)
            self._route_sources(df, i, conversion)
            self._route_channel(df, i)
        final_column = f"Q{self.n_reaches + 1}"
        numeric_columns = state_columns + [
            f"Q{i}" for i in range(1, self.n_reaches + 2)
        ]
        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0).clip(lower=0.0)
        df["Q_local"] = df[final_column]
        return df


def xaj(frame: pd.DataFrame, params: dict) -> np.ndarray:
    """Run XAJ and return local-basin runoff depth in millimetres per step."""
    precipitation, pet, _ = forcing(frame, params)
    dt_hours = timestep_hours(params, 1.0)
    area_km2 = 1.0
    model = XinAnJiangModel(dt_hours=dt_hours, area_km2=area_km2)
    model.set_params(**params)
    inputs = pd.DataFrame({"P": precipitation, "E0": pet})
    result = model.run_model(inputs)
    depth = result["Q_local"].to_numpy(float) * 3.6 * dt_hours / area_km2
    return as_nonnegative(depth)
