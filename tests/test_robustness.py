import unittest
from datetime import date
from pathlib import Path

from morosidad_bancaria.modeling.robustness import (
    RobustnessConfig,
    load_robustness_config,
    stability_against_zero,
)


class RobustnessTests(unittest.TestCase):
    def test_project_feature_sets_have_declared_sizes(self):
        root = Path(__file__).resolve().parents[1]
        config = load_robustness_config(root / "configs" / "robustness.toml")
        self.assertEqual(
            {item.name: len(item.features) for item in config.feature_sets},
            {"full_23": 23, "core_10": 10, "macro_core_8": 8, "ar_core_5": 5},
        )

    def test_block_bootstrap_is_deterministic_for_dominant_model(self):
        predictions = []
        for month in range(1, 13):
            observation = f"2020-{month:02d}-01"
            predictions.extend(
                [
                    {
                        "model": "zero_change",
                        "observation_date": observation,
                        "error_pp": 1.0,
                    },
                    {
                        "model": "perfect",
                        "observation_date": observation,
                        "error_pp": 0.0,
                    },
                ]
            )
        config = RobustnessConfig(6, 1000, 42, date(2020, 6, 1), ())
        result = stability_against_zero(predictions, config)[0]
        self.assertEqual(result["mae_difference_vs_zero_pp"], -1.0)
        self.assertEqual(result["bootstrap_probability_better_than_zero"], 1.0)
        self.assertEqual(result["ci_conclusion"], "better_than_zero")


if __name__ == "__main__":
    unittest.main()
