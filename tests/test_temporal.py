import unittest
from datetime import date

from morosidad_bancaria.data.modeling_base import add_months
from morosidad_bancaria.modeling.temporal import (
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class TemporalValidationTests(unittest.TestCase):
    def config(self):
        return ValidationConfig("expanding_window", 3, 2, 2, "monthly", True, True)

    def rows(self):
        result = []
        for index in range(7):
            observation = add_months(date(2020, 1, 1), index)
            result.append(
                {
                    "observation_date": observation.isoformat(),
                    "forecast_issue_date": add_months(observation, 1).isoformat(),
                    "target_available_date_h6": add_months(observation, 2).isoformat(),
                    "target_change_pp_h6": "0.1",
                    "complete_features": "1",
                    "split": "holdout" if index == 6 else "development",
                }
            )
        return result

    def test_folds_never_include_holdout(self):
        folds = build_expanding_folds(self.rows(), self.config())
        dates = [value for fold in folds for value in fold.observation_dates]
        self.assertEqual(dates, ["2020-04-01", "2020-05-01", "2020-06-01"])
        self.assertNotIn("2020-07-01", dates)

    def test_training_purges_unavailable_labels(self):
        rows = self.rows()
        training, purged = eligible_training_rows(rows, rows[4])
        self.assertEqual([row["observation_date"] for row in training], [
            "2020-01-01",
            "2020-02-01",
            "2020-03-01",
            "2020-04-01",
        ])
        self.assertEqual(purged, 0)
        rows[3]["target_available_date_h6"] = "2020-07-01"
        training, purged = eligible_training_rows(rows, rows[4])
        self.assertEqual(len(training), 3)
        self.assertEqual(purged, 1)

    def test_training_can_apply_a_calendar_rolling_window_before_purge(self):
        rows = self.rows()
        rows[4]["target_available_date_h6"] = "2020-08-01"
        training, purged = eligible_training_rows(
            rows, rows[5], rolling_window_months=2
        )
        self.assertEqual(
            [row["observation_date"] for row in training],
            ["2020-04-01"],
        )
        self.assertEqual(purged, 1)


if __name__ == "__main__":
    unittest.main()
