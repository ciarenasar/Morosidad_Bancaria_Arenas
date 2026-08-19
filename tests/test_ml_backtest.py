import unittest
from pathlib import Path

from morosidad_bancaria.modeling.ml_backtest import (
    MlConfig,
    inner_validation_rows,
    load_ml_config,
)


class MlBacktestTests(unittest.TestCase):
    def config(self):
        return MlConfig(
            metric="mae",
            retune_frequency="outer_fold",
            inner_validation_origins=3,
            minimum_inner_training_rows=4,
            random_seed=42,
            candidates={"elastic_net": ({},), "random_forest": ({},), "xgboost": ({},)},
        )

    def test_inner_validation_uses_latest_known_rows_after_minimum(self):
        rows = [{"observation_date": f"2020-{month:02d}-01"} for month in range(1, 11)]
        selected = inner_validation_rows(rows, self.config())
        self.assertEqual(
            [row["observation_date"] for row in selected],
            ["2020-08-01", "2020-09-01", "2020-10-01"],
        )

    def test_project_grid_has_expected_candidate_counts(self):
        root = Path(__file__).resolve().parents[1]
        config = load_ml_config(root / "configs" / "models.toml")
        self.assertEqual(
            {name: len(values) for name, values in config.candidates.items()},
            {"elastic_net": 12, "random_forest": 8, "xgboost": 8},
        )


if __name__ == "__main__":
    unittest.main()
