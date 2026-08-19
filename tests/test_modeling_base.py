import unittest
from datetime import date

from morosidad_bancaria.data.bcch_series import BcchObservation, BcchSeriesSpec
from morosidad_bancaria.data.modeling_base import (
    ModelingConfig,
    add_months,
    build_modeling_rows,
    conservative_available_date,
    select_as_of,
)


class ModelingBaseTests(unittest.TestCase):
    def setUp(self):
        self.spec = BcchSeriesSpec("macro", "ID", "role", "level", 2, 5, "proxy")

    def observation(self, month: int, value: float) -> BcchObservation:
        return BcchObservation(date(2025, month, 1), "macro", "ID", value, "OK", "raw.json")

    def test_available_date_crosses_year(self):
        self.assertEqual(
            conservative_available_date(date(2025, 12, 1), self.spec),
            date(2026, 2, 5),
        )

    def test_as_of_selection_excludes_unpublished_month(self):
        selected = select_as_of(
            [self.observation(5, 100.0), self.observation(6, 101.0)],
            self.spec,
            date(2025, 7, 30),
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0].observation_date, date(2025, 5, 1))

    def test_builds_six_month_target_without_lookahead(self):
        target = {
            date(2025, 1, 1): 2.0,
            date(2025, 7, 1): 2.3,
        }
        calendar = {
            date(2025, 1, 1): date(2025, 2, 28),
            date(2025, 7, 1): date(2025, 8, 29),
        }
        observations = [BcchObservation(date(2024, 12, 1), "macro", "ID", 10.0, "OK", "raw")]
        config = ModelingConfig(6, date(2025, 12, 1), date(2026, 1, 1), date(2026, 12, 1))
        rows, report = build_modeling_rows(
            target,
            calendar,
            [self.spec],
            {"macro": observations},
            config,
        )
        self.assertAlmostEqual(rows[0]["target_change_pp_h6"], 0.3)
        self.assertEqual(rows[0]["target_available_date_h6"], "2025-08-29")
        self.assertEqual(rows[0]["macro__available_date"], "2025-02-05")
        self.assertEqual(report.availability_violations, 0)
        self.assertEqual(add_months(date(2025, 7, 1), 6), date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
