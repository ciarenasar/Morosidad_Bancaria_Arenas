import json
import tempfile
import unittest
from pathlib import Path

from morosidad_bancaria.data.target import TargetDataError, extract_target


class TargetExtractionTests(unittest.TestCase):
    def make_file(self, second_value: float = 2.0) -> Path:
        payload = {
            "cuadroInfo": {"tag": "CHART"},
            "series": [
                {
                    "serieInfo": {"cod_serie": "TARGET"},
                    "valores": [
                        {"fecha": 20250101, "valor": 1.0},
                        {"fecha": 20250201, "valor": second_value},
                    ],
                },
                {
                    "serieInfo": {"cod_serie": "TARGET"},
                    "valores": [
                        {"fecha": 20250101, "valor": 1.0},
                        {"fecha": 20250201, "valor": second_value},
                    ],
                },
            ],
        }
        temporary = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        self.addCleanup(lambda: Path(temporary.name).unlink(missing_ok=True))
        with temporary:
            json.dump(payload, temporary)
        return Path(temporary.name)

    def test_collapses_identical_duplicate_series(self):
        observations, report = extract_target([self.make_file()], "CHART", "TARGET")
        self.assertEqual(len(observations), 2)
        self.assertEqual(report.duplicate_series_entries_collapsed, 1)
        self.assertEqual(report.missing_months, [])

    def test_detects_conflicting_files(self):
        with self.assertRaisesRegex(TargetDataError, "Valores contradictorios"):
            extract_target([self.make_file(2.0), self.make_file(3.0)], "CHART", "TARGET")


if __name__ == "__main__":
    unittest.main()
