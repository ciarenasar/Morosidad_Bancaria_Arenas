import unittest
from pathlib import Path

from morosidad_bancaria.modeling.stress_alert import (
    define_stress_event,
    episode_detection,
    load_stress_alert_config,
)


class StressAlertTests(unittest.TestCase):
    def test_project_protocol_has_frozen_models_grid_and_thresholds(self):
        root = Path(__file__).resolve().parents[1]
        config = load_stress_alert_config(root / "configs" / "stress_alert.toml")
        self.assertEqual(config.horizon_months, 6)
        self.assertEqual(config.training_quantile, 0.8)
        self.assertEqual(
            {name: len(values) for name, values in config.candidates.items()},
            {"logistic_regression": 3, "random_forest": 8, "xgboost": 8},
        )
        self.assertEqual(len(config.decision_thresholds), 7)

    def test_stress_cutoff_uses_training_values_only(self):
        training = [
            {"target_change_pp_h6": str(value)}
            for value in (0.0, 1.0, 2.0, 3.0, 4.0)
        ]
        high_test = {"target_change_pp_h6": "100.0"}
        low_test = {"target_change_pp_h6": "-100.0"}
        high_cutoff, high_event, prevalence = define_stress_event(
            training, high_test, "target_change_pp_h6", 0.8
        )
        low_cutoff, low_event, _ = define_stress_event(
            training, low_test, "target_change_pp_h6", 0.8
        )
        self.assertAlmostEqual(high_cutoff, 3.2)
        self.assertEqual(high_cutoff, low_cutoff)
        self.assertEqual(high_event, 1)
        self.assertEqual(low_event, 0)
        self.assertAlmostEqual(prevalence, 0.2)

    def test_episode_detection_reports_delay_and_missed_episode(self):
        predictions = []
        for observation, actual, alert in (
            ("2020-01-01", 1, 0),
            ("2020-02-01", 1, 1),
            ("2020-03-01", 0, 0),
            ("2020-04-01", 1, 0),
        ):
            common = {
                "observation_date": observation,
                "actual_event": actual,
                "lead_time_months": 6,
            }
            predictions.append(
                {
                    **common,
                    "model": "historical_prevalence",
                    "predicted_event": 0,
                }
            )
            predictions.append(
                {**common, "model": "logistic_regression", "predicted_event": alert}
            )
        result = episode_detection(predictions)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["detection_delay_months"], 1)
        self.assertEqual(result[0]["episode_recall"], 0.5)
        self.assertEqual(result[1]["detected"], 0)
        self.assertIsNone(result[1]["detection_delay_months"])


if __name__ == "__main__":
    unittest.main()
