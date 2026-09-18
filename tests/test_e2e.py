import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).parents[1]
CLI = ROOT / "scripts" / "hydrotune.py"


class HydroTuneE2E(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def write_raw(self, path: Path, n: int = 30):
        rain = np.where(np.arange(n) % 5 == 0, 8.0, 0.0)
        pd.DataFrame(
            {
                "Time": pd.date_range("2020-01-01", periods=n, freq="h"),
                "Rain": rain,
                "Flow": np.roll(rain, 1) * 0.2,
                "Temp": 5.0,
            }
        ).to_csv(path, index=False)

    def intake_args(self, raw: Path, out: Path):
        return (
            "intake",
            raw,
            out,
            "--time-column",
            "Time",
            "--role",
            "precipitation=Rain",
            "--role",
            "discharge=Flow",
            "--role",
            "temperature=Temp",
            "--unit",
            "precipitation=mm",
            "--unit",
            "discharge=mm",
            "--unit",
            "temperature=degC",
        )

    def write_minimal_geo_artifacts(self, root: Path):
        geo = root / "geo"
        geo.mkdir()
        (geo / "geo.json").write_text(
            json.dumps(
                {
                    "schema_version": "hydrotune.geo.v1",
                    "artifact_type": "geographic_dataset",
                    "status": "success",
                    "crs": "EPSG:3857",
                    "files": {
                        "basin": "basin.geojson",
                        "subbasins": "subbasins.geojson",
                        "streams": "streams.geojson",
                        "stations": "stations.geojson",
                        "parameters": "parameters.csv",
                    },
                    "subbasins": {"count": 2, "method": "agent_or_external_gis"},
                    "provenance": {"preprocessing": "agent_confirmed"},
                }
            ),
            encoding="utf-8",
        )
        (geo / "basin.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"basin_id": "basin"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]]],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (geo / "streams.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"stream_id": "stream-1"},
                            "geometry": {"type": "LineString", "coordinates": [[1, 0], [2, 2], [3, 4]]},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (geo / "subbasins.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"subbasin_id": "subbasin-001"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[0, 0], [2, 0], [2, 4], [0, 4], [0, 0]]],
                            },
                        },
                        {
                            "type": "Feature",
                            "properties": {"subbasin_id": "subbasin-002"},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[2, 0], [4, 0], [4, 4], [2, 4], [2, 0]]],
                            },
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (geo / "stations.geojson").write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"station_id": "rain-1", "role": "rain_gauge"},
                            "geometry": {"type": "Point", "coordinates": [1, 3]},
                        },
                        {
                            "type": "Feature",
                            "properties": {"station_id": "hydro-1", "role": "hydro_station"},
                            "geometry": {"type": "Point", "coordinates": [3, 1]},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (geo / "parameters.csv").write_text("subbasin_id,area_km2\nsubbasin-001,1\nsubbasin-002,2\n", encoding="utf-8")
        return geo

    def test_intake_requires_explicit_agent_confirmed_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.csv"
            out = root / "dataset"
            self.write_raw(raw)

            missing = self.run_cli("intake", raw, root / "missing", "--time-column", "Time")
            self.assertEqual(missing.returncode, 2)
            self.assertIn("role mapping", (root / "missing" / "result.json").read_text(encoding="utf-8"))

            result = self.run_cli(*self.intake_args(raw, out))
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["schema_version"], "hydrotune.dataset.v1")
            self.assertEqual(meta["provenance"]["preprocessing"], "agent_confirmed")
            self.assertEqual(meta["variables"][0]["role"], "precipitation")
            self.assertTrue((out / "dataset.parquet").exists())

    def test_core_analysis_model_diagnosis_and_calibration_still_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.csv"
            data = root / "dataset"
            analysis = root / "analysis"
            model = root / "model"
            diagnosis = root / "diagnosis"
            calibration = root / "calibration"
            xaj_calibration = root / "xaj-calibration"
            self.write_raw(raw)

            self.assertEqual(self.run_cli(*self.intake_args(raw, data), "--basin-area-km2", "10").returncode, 0)
            self.assertEqual(self.run_cli("analyze", data, analysis).returncode, 0)
            run = {
                "schema_version": "hydrotune.run.v1",
                "model": {"kind": "native", "name": "hbv"},
                "input_dataset": str(data),
                "parameters": {"precipitation_column": "Rain", "temperature_column": "Temp"},
            }
            run_path = root / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            self.assertEqual(self.run_cli("model", run_path, model).returncode, 0)
            self.assertEqual(self.run_cli("diagnose", data, model / "simulation.parquet", diagnosis).returncode, 0)
            self.assertEqual(self.run_cli("calibrate", data, calibration, "--optimizer", "sce", "--iterations", "3").returncode, 0)
            self.assertEqual(
                self.run_cli(
                    "calibrate",
                    data,
                    xaj_calibration,
                    "--model",
                    "xaj",
                    "--optimizer",
                    "sce",
                    "--iterations",
                    "1",
                ).returncode,
                0,
            )
            calibrated = json.loads((xaj_calibration / "calibration.json").read_text(encoding="utf-8"))
            self.assertEqual(calibrated["model"], "xaj")
            self.assertIn("n", calibrated["bounds"])

    def test_event_collection_preserves_events_and_requires_warmup_for_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "events"
            source.mkdir()
            data = root / "dataset"
            model = root / "model"
            for name, start in (("flood-a", "2020-01-01"), ("flood-b", "2020-02-01")):
                pd.DataFrame(
                    {
                        "Time": pd.date_range(start, periods=5, freq="h"),
                        "Rain": [4, 0, 0, 0, 0],
                        "Flow": [0, 1, 2, 1, 0],
                    }
                ).to_csv(source / f"{name}.csv", index=False)

            self.assertEqual(
                self.run_cli(
                    "intake",
                    source,
                    data,
                    "--time-column",
                    "Time",
                    "--series-mode",
                    "event_collection",
                    "--role",
                    "precipitation=Rain",
                    "--role",
                    "discharge=Flow",
                    "--unit",
                    "precipitation=mm",
                    "--unit",
                    "discharge=mm",
                ).returncode,
                0,
            )
            meta_path = data / "dataset.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["series_mode"], "event_collection")
            self.assertEqual(meta["splits"]["warmup_status"], "user_confirmation_required")

            run = {
                "schema_version": "hydrotune.run.v1",
                "model": {"kind": "native", "name": "xaj"},
                "input_dataset": str(data),
                "parameters": {"n": 2, "L": 1},
            }
            run_path = root / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            self.assertEqual(self.run_cli("model", run_path, model).returncode, 2)

            meta["splits"]["warmup_steps"] = 1
            meta["splits"]["warmup_status"] = "confirmed"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            self.assertEqual(self.run_cli("model", run_path, model).returncode, 0)
            simulation = pd.read_parquet(model / "simulation.parquet")
            self.assertEqual(
                list(simulation.columns),
                ["timestamp", "discharge_sim", "model", "event_id"],
            )
            self.assertEqual(simulation.event_id.nunique(), 2)
            self.assertEqual(set(simulation.model), {"xaj"})

    def test_intake_extracts_confirmed_flow_threshold_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.csv"
            data = root / "dataset"
            pd.DataFrame(
                {
                    "Time": pd.date_range("2020-01-01", periods=10, freq="h"),
                    "Rain": [0, 4, 0, 0, 5, 0, 0, 3, 0, 0],
                    "Flow": [0, 5, 4, 1, 0, 0, 6, 7, 1, 0],
                }
            ).to_csv(raw, index=False)
            result = self.run_cli(
                "intake",
                raw,
                data,
                "--time-column",
                "Time",
                "--role",
                "precipitation=Rain",
                "--role",
                "discharge=Flow",
                "--unit",
                "precipitation=mm",
                "--unit",
                "discharge=mm",
                "--extract-events",
                "--event-flow-threshold",
                "3",
                "--event-merge-gap-steps",
                "1",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = json.loads((data / "dataset.json").read_text(encoding="utf-8"))
            frame = pd.read_parquet(data / "dataset.parquet")
            self.assertEqual(meta["series_mode"], "event_collection")
            self.assertEqual(frame.event_id.nunique(), 2)
            self.assertEqual(meta["provenance"]["event_extraction"]["flow_threshold"], 3.0)

    def test_compare_still_runs_three_models_and_bma(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.csv"
            data = root / "dataset"
            comparison = root / "comparison"
            self.write_raw(raw)
            self.assertEqual(self.run_cli(*self.intake_args(raw, data)).returncode, 0)
            self.assertEqual(self.run_cli("compare", data, comparison, "--optimizer", "sce", "--iterations", "1").returncode, 0)
            payload = json.loads((comparison / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual({item["model"] for item in payload["ranking"]}, {"tank", "hbv", "xaj"})
            self.assertTrue((comparison / "bma-simulation.parquet").exists())

    def test_geo_cli_is_removed_but_existing_geo_artifacts_are_consumed(self):
        if not importlib.util.find_spec("geopandas"):
            self.skipTest("optional Geo visualization dependencies are not installed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.csv"
            data = root / "dataset"
            analysis = root / "analysis"
            geo_figure = root / "geo-figure"
            self.write_raw(raw)
            geo = self.write_minimal_geo_artifacts(root)

            self.assertNotEqual(self.run_cli("geo").returncode, 0)
            self.assertEqual(self.run_cli(*self.intake_args(raw, data)).returncode, 0)
            self.assertEqual(self.run_cli("analyze", data, analysis, "--geo", geo).returncode, 0)
            pre = json.loads((analysis / "preanalysis.json").read_text(encoding="utf-8"))
            self.assertEqual(pre["geographic_readiness"]["subbasin_count"], 2)
            self.assertEqual(self.run_cli("visualize", "geo", geo, geo_figure).returncode, 0)
            self.assertTrue((geo_figure / "geographic-overview.png").exists())


if __name__ == "__main__":
    unittest.main()
