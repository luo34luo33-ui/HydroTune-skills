import unittest

import numpy as np
import pandas as pd

from hydrotune.models.xaj import XAJ_BOUNDS, XinAnJiangModel, xaj


class XinAnJiangModelTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "precipitation": [0.0, 4.0, 18.0, 7.0, 0.0, 0.0, 2.0, 0.0],
                "pet": [0.2] * 8,
            }
        )

    def test_native_runner_returns_finite_nonnegative_depth(self):
        result = xaj(self.frame, {})

        self.assertEqual(len(result), len(self.frame))
        self.assertTrue(np.isfinite(result).all())
        self.assertTrue((result >= 0.0).all())
        self.assertTrue((result > 0.0).any())

    def test_routing_and_initial_state_parameters_are_supported(self):
        result = xaj(
            self.frame,
            {
                "n": 3.4,
                "L": 2.2,
                "WUM_init": 5.0,
                "WLM_init": 12.0,
                "WDM_init": 8.0,
                "FR1": 0.2,
                "S1": 4.0,
                "Q": 2.0,
                "dt_hours": 0.5,
            },
        )

        self.assertEqual(len(result), len(self.frame))
        self.assertTrue(np.isfinite(result).all())

    def test_notebook_bounds_exclude_external_reservoir_routing(self):
        expected = {
            "B", "C", "WM", "WUM", "WLM", "IM", "SM", "EX", "K", "KG", "KI",
            "CG", "CI", "CS", "L", "X", "n", "WUM_init", "WLM_init", "WDM_init",
            "FR1", "S1", "Q",
        }
        self.assertEqual(set(XAJ_BOUNDS), expected)
        self.assertNotIn("K_res", XAJ_BOUNDS)
        self.assertNotIn("X_res", XAJ_BOUNDS)

    def test_model_uses_final_reach_as_local_outflow(self):
        model = XinAnJiangModel()
        model.set_params(n=3)
        result = model.run_model(
            pd.DataFrame({"P": [0.0, 10.0, 0.0], "E0": [0.0] * 3})
        )

        np.testing.assert_allclose(result["Q_local"], result["Q4"])


if __name__ == "__main__":
    unittest.main()
