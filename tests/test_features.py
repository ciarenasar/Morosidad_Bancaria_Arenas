import unittest
from datetime import date

from morosidad_bancaria.modeling.features import (
    FeatureConfig,
    MacroFeatureSpec,
    build_feature_rows,
)


class FeatureEngineeringTests(unittest.TestCase):
    def config(self):
        return FeatureConfig(
            name="test_v1",
            npl_lags=(1,),
            npl_changes=(1,),
            npl_rolling_means=(2,),
            include_month_seasonality=True,
            macro_features=(MacroFeatureSpec("macro_yoy", "macro", "pct_change", 12),),
            autoregressive_features=("npl90_level_t",),
        )

    def row(self, month: str, target: float, selected_macro_month: str):
        return {
            "observation_date": month,
            "forecast_issue_date": month,
            "split": "development",
            "npl90_consumption_percent_t": str(target),
            "macro__observation_date": selected_macro_month,
        }

    def test_uses_selected_macro_month_not_forecast_month(self):
        rows = [
            self.row("2024-12-01", 2.0, "2024-10-01"),
            self.row("2025-01-01", 2.2, "2024-11-01"),
        ]
        history = {
            "macro": {
                date(2023, 11, 1): 100.0,
                date(2024, 11, 1): 110.0,
                date(2025, 1, 1): 999.0,
            }
        }
        engineered, _ = build_feature_rows(rows, history, self.config())
        self.assertAlmostEqual(engineered[1]["macro_yoy"], 10.0)
        self.assertAlmostEqual(engineered[1]["npl90_change_1m_pp"], 0.2)
        self.assertEqual(engineered[1]["complete_features"], 1)

    def test_initial_row_is_incomplete_when_lags_do_not_exist(self):
        rows = [self.row("2025-01-01", 2.0, "2024-11-01")]
        history = {
            "macro": {date(2023, 11, 1): 100.0, date(2024, 11, 1): 110.0}
        }
        engineered, coverage = build_feature_rows(rows, history, self.config())
        self.assertEqual(engineered[0]["complete_features"], 0)
        self.assertEqual(coverage.complete_rows, 0)


if __name__ == "__main__":
    unittest.main()
