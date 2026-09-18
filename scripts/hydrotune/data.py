"""HydroTune tabular data ingestion and semantic inference helpers."""

from __future__ import annotations
from pathlib import Path
import pandas as pd


ROLE_ALIASES = {"precipitation": ("precipitation", "precip", "rainfall", "rain", "ppt"), "upstream_discharge": ("upstream_discharge", "upstream_flow", "inflow", "in_flow"), "discharge": ("discharge", "streamflow", "flow", "runoff"), "temperature": ("temperature", "temp", "tmean"), "pet": ("pet", "evapotranspiration", "potential_et")}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv": return pd.read_csv(path)
    if path.suffix.lower() in {".xlsx", ".xls"}: return pd.read_excel(path)
    if path.suffix.lower() == ".parquet": return pd.read_parquet(path)
    raise ValueError("Supported inputs are CSV, XLSX/XLS, and Parquet.")
def parse_units(items: list[str]) -> dict[str, str]:
    answer = {}
    for item in items:
        if "=" not in item: raise ValueError(f"Invalid unit {item!r}; use column=unit.")
        key, value = item.split("=", 1); answer[key.strip()] = value.strip()
    return answer
def infer_role(column: str):
    lower = column.strip().lower().replace(" ", "_")
    for role, aliases in ROLE_ALIASES.items():
        if lower in aliases or any(alias in lower for alias in aliases): return role, "high", f"column name {column!r} matches {role} aliases"
    if lower in {"p", "q", "t"}: return {"p":"precipitation","q":"discharge","t":"temperature"}[lower], "medium", f"single-letter conventional name {column!r}"
    return None, "none", "no supported role-name evidence"
def infer_timestamp(frame: pd.DataFrame):
    candidates = [c for c in frame.columns if any(x in c.lower() for x in ("date", "time", "timestamp"))]
    candidates += [c for c in frame.columns if c not in candidates and (pd.api.types.is_object_dtype(frame[c]) or pd.api.types.is_datetime64_any_dtype(frame[c]))]
    for col in candidates:
        converted = pd.to_datetime(frame[col], errors="coerce", utc=True)
        if len(converted) and converted.notna().mean() >= .95: return col, converted.dt.tz_convert(None), f"{converted.notna().mean():.0%} of {col!r} parses as timestamps"
    return None, None, "no column parsed as timestamps"
def timestep(series: pd.Series) -> str | None:
    values = series.dropna().sort_values().drop_duplicates()
    if len(values) < 3: return None
    seconds = values.diff().dropna().dt.total_seconds()
    return pd.Timedelta(seconds=float(seconds.mode().iloc[0])).isoformat() if not seconds.empty else None
def source_paths(source: Path) -> list[Path]:
    return sorted(p for p in (source.glob("*") if source.is_dir() else [source]) if p.suffix.lower() in {".csv", ".xlsx", ".xls", ".parquet"})
