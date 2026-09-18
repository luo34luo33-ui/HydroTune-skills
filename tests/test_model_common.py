import unittest

import numpy as np
import pandas as pd

from hydrotune.models.common import (
    as_nonnegative,
    calendar_months,
    forcing,
    numeric_series,
    scale_daily_fraction,
    timestep_hours,
)


class NativeModelCommonTests(unittest.TestCase):
    def test_forcing_uses_configured_columns_and_defaults(self):
        frame = pd.DataFrame({"rain": [1.0, "bad", None]})
        precipitation, pet, temperature = forcing(
            frame, {"precipitation_column": "rain"}
        )

        np.testing.assert_allclose(precipitation, [1.0, 0.0, 0.0])
        np.testing.assert_allclose(pet, [0.0, 0.0, 0.0])
        np.testing.assert_allclose(temperature, [5.0, 5.0, 5.0])

    def test_forcing_requires_precipitation(self):
        with self.assertRaisesRegex(ValueError, "missing precipitation column"):
            forcing(pd.DataFrame({"pet": [1.0]}), {})

    def test_numeric_series_and_calendar_months_handle_invalid_values(self):
        frame = pd.DataFrame(
            {"value": ["2", "bad"], "timestamp": ["2020-06-01", "bad"]}
        )

        np.testing.assert_allclose(numeric_series(frame, "value", 3.0), [2.0, 3.0])
        np.testing.assert_array_equal(calendar_months(frame), [6, 1])

    def test_daily_fraction_is_time_consistent(self):
        daily = scale_daily_fraction(0.5, 24.0)
        hourly = scale_daily_fraction(0.5, 1.0)

        self.assertAlmostEqual(daily, 0.5)
        self.assertAlmostEqual(1.0 - (1.0 - hourly) ** 24, daily)

    def test_timestep_validation_and_output_sanitizing(self):
        self.assertEqual(timestep_hours({}, 6.0), 6.0)
        for value in (0.0, -1.0, np.nan, np.inf):
            with self.assertRaisesRegex(ValueError, "dt_hours"):
                timestep_hours({"dt_hours": value}, 1.0)
        np.testing.assert_allclose(
            as_nonnegative(np.array([-1.0, np.nan, np.inf, 2.0])),
            [0.0, 0.0, 0.0, 2.0],
        )


if __name__ == "__main__":
    unittest.main()
