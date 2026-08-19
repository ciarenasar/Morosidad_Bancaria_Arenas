import unittest
from datetime import date
from pathlib import Path

from morosidad_bancaria.modeling.horizon_robustness import (
    add_horizon_targets,
    load_horizon_robustness_config,
)


class HorizonRobustnessTests(unittest.TestCase):
    def test_project_protocol_has_six_scenarios(self):
        root = Path(__file__).resolve().parents[1]
        config = load_horizon_robustness_config(
            root / "configs" / "horizon_robustness.toml"
        )
        self.assertEqual(len(config.horizons_months) * len(config.training_schemes), 6)

    def test_adds_target_and_publication_date_for_each_horizon(self):
        rows = [
            {"observation_date": "2020-01-01", "npl90_consumption_percent_t": "2.0"},
            {"observation_date": "2020-04-01", "npl90_consumption_percent_t": "2.2"},
        ]
        calendar = {date(2020, 4, 1): date(2020, 5, 29)}
        result = add_horizon_targets(rows, calendar, (3,))
        self.assertAlmostEqual(result[0]["target_change_pp_h3"], 0.2)
        self.assertEqual(result[0]["target_available_date_h3"], "2020-05-29")
        self.assertIsNone(result[1]["target_change_pp_h3"])


if __name__ == "__main__":
    unittest.main()
