"""Create 20 small, deterministic raw Intake cases; generated CSVs are disposable."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
OUT = ROOT / "cases"

CASES = [
    ("01_clear_rain_flow", {"Time": ["2024-01-01 00:00", "2024-01-01 01:00"], "Rain": [1.0, 0.0], "Flow": [2.0, 2.2]}),
    ("02_gauge_blanks", {"Time": ["2024-01-01 00:00", "2024-01-01 01:00"], "GB_rain": [None, 4.0], "GZ_out": [3.0, 3.2]}),
    ("03_short_names", {"date": ["2024-01-01", "2024-01-02"], "P": [2.0, 0.0], "Q": [1.0, 1.1]}),
    ("04_no_timestamp", {"Rain": [2.0, 0.0], "Flow": [1.0, 1.1]}),
    ("05_bad_timestamp", {"Time": ["yesterday", "never"], "Rain": [2.0, 0.0]}),
    ("06_temperature_only", {"timestamp": ["2024-01-01", "2024-01-02"], "Temp": [5.0, 7.0]}),
    ("07_rain_only", {"timestamp": ["2024-01-01", "2024-01-02"], "precipitation": [3.0, 0.0]}),
    ("08_flow_only", {"timestamp": ["2024-01-01", "2024-01-02"], "discharge": [2.0, 2.1]}),
    ("09_irregular_time", {"Time": ["2024-01-01 00:00", "2024-01-01 01:00", "2024-01-01 03:00"], "Rain": [1.0, 0.0, 2.0]}),
    ("10_duplicate_time", {"Time": ["2024-01-01", "2024-01-01"], "Rain": [1.0, 2.0]}),
    ("11_unknown_columns", {"Time": ["2024-01-01", "2024-01-02"], "A": [1.0, 2.0], "B": [3.0, 4.0]}),
    ("12_pet_and_temp", {"Time": ["2024-01-01", "2024-01-02"], "Rain": [2.0, 0.0], "PET": [0.5, 0.6], "Temp": [3.0, 4.0]}),
    ("13_rainfall_word", {"Date": ["2024-01-01", "2024-01-02"], "Rainfall_mm": [3.0, 0.0]}),
    ("14_streamflow_word", {"Date": ["2024-01-01", "2024-01-02"], "Streamflow": [5.0, 5.2]}),
    ("15_operational_flows", {"Time": ["2024-01-01", "2024-01-02"], "GB_out": [1.0, 2.0], "GZ_in": [2.0, 3.0], "E0": [0.2, 0.2]}),
    ("16_mixed_case", {"TIME": ["2024-01-01", "2024-01-02"], "AVG_RAIN": [1.0, None], "FLOW": [4.0, 4.1]}),
    ("17_numeric_date", {"date": [45292, 45293], "Rain": [2.0, 0.0]}),
    ("18_partial_bad_dates", {"Time": ["2024-01-01", "bad", "2024-01-03"], "Rain": [2.0, 1.0, 0.0]}),
    ("19_multi_gauge", {"Time": ["2024-01-01", "2024-01-02"], "GB_rain": [1.0, None], "DF_rain": [2.0, 0.0], "avg_rain": [1.5, 0.0]}),
    ("20_model_ready_shape", {"timestamp": ["2024-01-01", "2024-01-02"], "precipitation": [3.0, 0.0], "discharge": [1.0, 1.2], "temperature": [5.0, 5.0], "pet": [0.2, 0.2]}),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    expectations = []
    for name, data in CASES:
        path = OUT / f"{name}.csv"; pd.DataFrame(data).to_csv(path, index=False)
        rain = any("rain" in col.lower() or col.lower() in {"p", "precipitation"} for col in data)
        missing_rain = rain and any(pd.isna(value) for col, values in data.items() if "rain" in col.lower() or col.lower() in {"p", "precipitation"} for value in values)
        has_valid_timestamp = name not in {"04_no_timestamp", "05_bad_timestamp", "18_partial_bad_dates"}
        expected = ["units"] + (["timezone"] if has_valid_timestamp else []) + (["rain_missingness"] if missing_rain else [])
        expectations.append({"id": name, "input": f"cases/{path.name}", "expected_required_question_ids": expected, "agent_task": "Prepare this file for rainfall-runoff analysis using HydroTune. Inspect it first and ask only necessary scientific questions before normalizing it."})
    (ROOT / "cases.json").write_text(json.dumps({"version": "intake-v0.1", "cases": expectations}, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {len(CASES)} cases in {OUT}")


if __name__ == "__main__":
    main()
