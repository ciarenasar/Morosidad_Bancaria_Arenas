import unittest

from morosidad_bancaria.modeling.metrics import (
    classification_metrics,
    regression_metrics,
)


class RegressionMetricTests(unittest.TestCase):
    def test_metrics_and_direction(self):
        metrics = regression_metrics([1.0, -1.0, 2.0], [0.5, -2.0, -1.0])
        self.assertAlmostEqual(metrics["mae"], 1.5)
        self.assertAlmostEqual(metrics["rmse"], (10.25 / 3) ** 0.5)
        self.assertAlmostEqual(metrics["directional_accuracy"], 2 / 3)

    def test_constant_prediction_has_no_correlation(self):
        metrics = regression_metrics([1.0, 2.0], [0.0, 0.0])
        self.assertIsNone(metrics["correlation"])

    def test_binary_metrics_include_ranking_calibration_and_confusion(self):
        metrics = classification_metrics(
            [1, 0, 1, 0],
            [0.9, 0.8, 0.4, 0.1],
            decision_threshold=0.5,
        )
        self.assertAlmostEqual(metrics["average_precision"], 5 / 6)
        self.assertAlmostEqual(metrics["roc_auc"], 0.75)
        self.assertAlmostEqual(metrics["brier_score"], 0.255)
        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["false_positives"], 1)
        self.assertEqual(metrics["false_negatives"], 1)
        self.assertAlmostEqual(metrics["f1"], 0.5)


if __name__ == "__main__":
    unittest.main()
