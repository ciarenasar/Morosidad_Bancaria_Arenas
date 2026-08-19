import unittest
from datetime import date

from morosidad_bancaria.config import CmfBestConfig
from morosidad_bancaria.data.cmf_best import BestClient, iter_month_windows


class MonthWindowTests(unittest.TestCase):
    def test_splits_history_into_at_most_twelve_months(self):
        windows = list(iter_month_windows(date(2014, 3, 1), date(2015, 4, 30)))
        self.assertEqual(
            windows,
            [
                (date(2014, 3, 1), date(2015, 2, 28)),
                (date(2015, 3, 1), date(2015, 4, 30)),
            ],
        )

    def test_rejects_reverse_range(self):
        with self.assertRaises(ValueError):
            list(iter_month_windows(date(2025, 2, 1), date(2025, 1, 1)))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        config = CmfBestConfig(
            "https://example.test", "TAG", "TARGET", "2014-03-01", 12, 6.1, 30, 0
        )
        self.client = BestClient(config, "secret")

    def test_endpoint_contains_dates_but_not_secret(self):
        endpoint = self.client._endpoint_path("VALID_TAG", date(2025, 1, 1), date(2025, 12, 31))
        self.assertEqual(
            endpoint,
            "/api/v1/cuadros/data/VALID_TAG/range/20250101/20251231",
        )
        self.assertNotIn("secret", endpoint)

    def test_rejects_unsafe_chart_tag(self):
        with self.assertRaises(ValueError):
            self.client._endpoint_path("../invalid", date(2025, 1, 1), date(2025, 1, 31))


if __name__ == "__main__":
    unittest.main()
