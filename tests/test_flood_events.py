import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from hydrotune.flood_events import (
    FloodEventConfig,
    build_raw_events,
    detect_peaks,
    eckhardt_baseflow,
    extract_flood_event_collection,
    merge_events,
    refine_events_around_main_peak,
)


def event_config(**updates):
    values = {
        "bfi_max": 0.5,
        "alpha": 0.9,
        "peak_quantile": 0.5,
        "prominence_factor": 0.05,
        "min_peak_distance_hours": 12.0,
        "boundary_fraction": 0.1,
        "boundary_persistence_steps": 2,
        "max_search_days": 0.5,
        "merge_gap_hours": 2.0,
        "valley_ratio_threshold": 0.8,
        "min_event_duration_hours": 1.0,
        "min_peak_flow": None,
        "min_event_volume": None,
        "warmup_steps": 2,
    }
    values.update(updates)
    return FloodEventConfig.from_mapping(values)


def synthetic_flow():
    flow = np.ones(120, dtype=float)
    shape = np.array([2, 4, 8, 14, 8, 4, 2], dtype=float)
    flow[27:34] = shape
    flow[82:89] = shape * 0.8
    return flow


class FloodEventTests(unittest.TestCase):
    def test_baseflow_peaks_and_boundaries_are_consistent(self):
        config = event_config()
        flow = synthetic_flow()
        baseflow = eckhardt_baseflow(flow, config.alpha, config.bfi_max)
        quickflow = np.maximum(flow - baseflow, 0.0)

        self.assertTrue(np.all(baseflow >= 0))
        self.assertTrue(np.all(baseflow <= flow))
        np.testing.assert_allclose(baseflow + quickflow, flow)

        peaks = detect_peaks(quickflow, 3600.0, config)
        raw = build_raw_events(peaks, flow, 3600.0, config)
        merged = merge_events(raw, flow, 3600.0, config)
        refined = refine_events_around_main_peak(merged, quickflow, 3600.0, config)

        self.assertEqual(len(peaks), 2)
        self.assertEqual(len(refined), 2)
        for event in refined:
            self.assertLessEqual(event["start_idx"], event["peak_idx"])
            self.assertLessEqual(event["peak_idx"], event["end_idx"])

    def test_extraction_builds_event_collection_with_warmup_flags(self):
        flow = synthetic_flow()
        frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=len(flow), freq="h"),
                "Flow": flow,
                "source_file": "synthetic.csv",
            }
        )
        result = extract_flood_event_collection(
            frame,
            discharge_column="Flow",
            source=Path("synthetic.csv"),
            config=event_config(),
        )

        self.assertEqual(result.metadata["method"], "eckhardt_peak_boundary_v1")
        self.assertEqual(result.metadata["final_event_count"], 2)
        self.assertEqual(result.frame.event_id.nunique(), 2)
        self.assertTrue({"baseflow", "quickflow", "quickflow_ratio", "is_warmup"}.issubset(result.frame))
        self.assertTrue(result.frame.groupby("event_id").is_warmup.any().all())


if __name__ == "__main__":
    unittest.main()
