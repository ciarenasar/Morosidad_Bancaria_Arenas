import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.bcch_series import (
    BcchSeriesSpec,
    audit_series,
    parse_series_file,
)


class BcchSeriesTests(unittest.TestCase):
    def setUp(self):
        self.spec = BcchSeriesSpec("feature", "SERIES.ID", "role", "level", 1, 15, "proxy")

    def make_response(self) -> Path:
        payload = {
            "Codigo": 0,
            "Series": {
                "seriesId": "SERIES.ID",
                "Obs": [
                    {"indexDateString": "01-01-2025", "value": "1,5", "statusCode": "OK"},
                    {"indexDateString": "01-02-2025", "value": "NaN", "statusCode": "ND"},
                ],
            },
        }
        temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.addCleanup(lambda: Path(temporary.name).unlink(missing_ok=True))
        with temporary:
            temporary.write(json.dumps(payload).encode())
        return Path(temporary.name)

    def test_parses_values_and_missing_marker(self):
        observations = parse_series_file(self.make_response(), self.spec)
        self.assertEqual(observations[0].value, 1.5)
        self.assertIsNone(observations[1].value)

    def test_audits_target_months(self):
        observations = parse_series_file(self.make_response(), self.spec)
        report = audit_series(
            [self.spec],
            {self.spec.name: observations},
            date(2025, 1, 1),
            date(2025, 2, 1),
        )[0]
        self.assertEqual(report.target_period_observations, 1)
        self.assertEqual(report.missing_target_months, 1)


if __name__ == "__main__":
    unittest.main()
