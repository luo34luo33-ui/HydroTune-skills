import unittest

import numpy as np
import pandas as pd

from hydrotune.models.hbv import HBV_BOUNDS, HBV_DEFAULTS, hbv
from hydrotune.models.tank import TANK_BOUNDS, TANK_DEFAULTS, tank


class NativeHBVTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-06-01", periods=12, freq="h"),
                "precipitation": [0.0, 15.0, 12.0, 8.0, 0.0, 4.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0],
                "pet": [0.1] * 12,
                "temperature": [15.0] * 12,
            }
        )

    def test_hbv_returns_finite_nonnegative_depth_with_rain_response(self):
        result = hbv(self.frame, {"dt_hours": 1.0, "fc": 20.0})

        self.assertEqual(len(result), len(self.frame))
        self.assertTrue(np.isfinite(result).all())
        self.assertTrue((result >= 0.0).all())
        self.assertTrue((result > 0.0).any())

    def test_hbv_legacy_aliases_and_canonical_precedence(self):
        shared = {"dt_hours": 24.0, "fc": 20.0, "beta": 1.0}
        canonical = hbv(self.frame, {**shared, "l": 3.0, "kp": 0.04})
        legacy = hbv(self.frame, {**shared, "uzl": 3.0, "perc": 0.04})
        preferred = hbv(
            self.frame,
            {**shared, "l": 3.0, "uzl": 40.0, "kp": 0.04, "perc": 0.9},
        )

        np.testing.assert_allclose(canonical, legacy)
        np.testing.assert_allclose(canonical, preferred)

    def test_hbv_pet_fallback_temperature_correction_and_snowmelt(self):
        no_pet = self.frame.drop(columns="pet")
        fallback = hbv(no_pet, {"dt_hours": 1.0, "fc": 20.0, "c": 0.07})
        uncorrected = hbv(no_pet, {"dt_hours": 1.0, "fc": 20.0, "c": 0.0})
        self.assertTrue(np.isfinite(fallback).all())
        self.assertFalse(np.allclose(fallback, uncorrected))

        snow = pd.DataFrame(
            {
                "timestamp": pd.date_range("2020-01-01", periods=4, freq="D"),
                "precipitation": [10.0, 0.0, 10.0, 0.0],
                "pet": [0.0] * 4,
                "temperature": [-5.0, 5.0, 5.0, 5.0],
            }
        )
        thawed = hbv(snow, {"dt_hours": 24.0, "fc": 1.0, "beta": 1.0, "cfmax": 5.0})
        frozen = hbv(snow.assign(temperature=-5.0), {"dt_hours": 24.0, "fc": 1.0})
        self.assertGreater(thawed.sum(), frozen.sum())

    def test_hbv_time_step_changes_daily_rate_application(self):
        hourly = hbv(self.frame, {"dt_hours": 1.0, "fc": 20.0, "beta": 1.0})
        daily = hbv(self.frame, {"dt_hours": 24.0, "fc": 20.0, "beta": 1.0})

        self.assertFalse(np.allclose(hourly, daily))
        self.assertTrue(np.isfinite(hourly).all())
        self.assertTrue(np.isfinite(daily).all())

    def test_hbv_exports_adapter_parameter_contract(self):
        self.assertEqual(set(HBV_BOUNDS), set(HBV_DEFAULTS))
        self.assertEqual(
            set(HBV_BOUNDS),
            {"fc", "beta", "c", "k0", "l", "k1", "k2", "kp", "lp"},
        )


class NativeTankTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "precipitation": [0.0, 30.0, 40.0, 25.0, 0.0, 0.0, 10.0, 0.0],
                "pet": [0.2] * 8,
            }
        )

    def test_tank_returns_finite_nonnegative_depth_with_rain_response(self):
        result = tank(self.frame, {"dt_hours": 1.0})

        self.assertEqual(len(result), len(self.frame))
        self.assertTrue(np.isfinite(result).all())
        self.assertTrue((result >= 0.0).all())
        self.assertTrue((result > 0.0).any())

    def test_tank_initial_storage_parameters_are_active(self):
        empty = {f"t{i}_is": 0.0 for i in range(4)}
        dry = pd.DataFrame({"precipitation": [0.0] * 4, "pet": [0.0] * 4})
        without_storage = tank(dry, {**empty, "dt_hours": 24.0})
        with_storage = tank(dry, {**empty, "t3_is": 20.0, "dt_hours": 24.0})

        self.assertTrue(np.allclose(without_storage, 0.0))
        self.assertGreater(with_storage.sum(), 0.0)

    def test_tank_legacy_aliases_and_canonical_precedence(self):
        canonical = tank(
            self.frame,
            {"dt_hours": 24.0, "t0_soc_uo": 0.2, "t0_soh_uo": 10.0},
        )
        legacy = tank(self.frame, {"dt_hours": 24.0, "a1": 0.2, "h1": 10.0})
        preferred = tank(
            self.frame,
            {
                "dt_hours": 24.0,
                "t0_soc_uo": 0.2,
                "a1": 0.8,
                "t0_soh_uo": 10.0,
                "h1": 100.0,
            },
        )

        np.testing.assert_allclose(canonical, legacy)
        np.testing.assert_allclose(canonical, preferred)

    def test_tank_hourly_and_daily_baseflow_are_time_consistent(self):
        empty = {f"t{i}_is": 0.0 for i in range(4)}
        daily_frame = pd.DataFrame({"precipitation": [0.0], "pet": [0.0]})
        hourly_frame = pd.DataFrame({"precipitation": [0.0] * 24, "pet": [0.0] * 24})
        params = {**empty, "t3_is": 10.0, "t3_soc": 0.5}
        daily = tank(daily_frame, {**params, "dt_hours": 24.0})
        hourly = tank(hourly_frame, {**params, "dt_hours": 1.0})

        self.assertLess(hourly[0], daily[0])
        self.assertAlmostEqual(hourly.sum(), daily.sum(), places=10)

    def test_tank_exports_complete_parameter_contract(self):
        self.assertEqual(set(TANK_BOUNDS), set(TANK_DEFAULTS))
        self.assertEqual(len(TANK_BOUNDS), 16)


if __name__ == "__main__":
    unittest.main()
