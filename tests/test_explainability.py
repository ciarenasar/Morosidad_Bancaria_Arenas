import unittest
from pathlib import Path

from morosidad_bancaria.modeling.explainability import (
    aggregate_attributions,
    driver_rank_stability,
    fold_rank_correlations,
    load_explainability_config,
)


class ExplainabilityTests(unittest.TestCase):
    def test_project_protocol_explains_all_learned_models(self):
        root = Path(__file__).resolve().parents[1]
        config = load_explainability_config(root / "configs" / "explainability.toml")
        self.assertEqual(set(config.models), {"elastic_net", "xgboost", "random_forest"})

    def test_aggregate_ranks_and_normalizes_importance(self):
        rows = []
        for observation in ("2020-01-01", "2020-02-01"):
            rows.extend(
                [
                    {
                        "fold_id": 1,
                        "model": "elastic_net",
                        "method": "linear",
                        "feature": "a",
                        "observation_date": observation,
                        "attribution_value": 2.0,
                        "absolute_attribution": 2.0,
                        "model_weight": 1.0,
                    },
                    {
                        "fold_id": 1,
                        "model": "elastic_net",
                        "method": "linear",
                        "feature": "b",
                        "observation_date": observation,
                        "attribution_value": -1.0,
                        "absolute_attribution": 1.0,
                        "model_weight": -0.5,
                    },
                ]
            )
        result = aggregate_attributions(rows, 1e-10, by_fold=False)
        by_feature = {row["feature"]: row for row in result}
        self.assertEqual(by_feature["a"]["rank"], 1)
        self.assertAlmostEqual(by_feature["a"]["normalized_importance"], 2 / 3)
        self.assertEqual(by_feature["b"]["weight_negative_share"], 1.0)

    def test_identical_fold_rankings_have_perfect_correlation(self):
        rows = []
        for fold in (1, 2):
            for rank, feature in enumerate(("a", "b", "c"), start=1):
                rows.append(
                    {
                        "fold_id": str(fold),
                        "model": "model",
                        "method": "method",
                        "feature": feature,
                        "rank": rank,
                        "normalized_importance": 0.5 / rank,
                    }
                )
        stability = driver_rank_stability(rows)
        correlations = fold_rank_correlations(rows)
        self.assertEqual(stability[0]["rank_standard_deviation"], 0.0)
        self.assertAlmostEqual(correlations[0]["spearman_rank_correlation"], 1.0)


if __name__ == "__main__":
    unittest.main()
