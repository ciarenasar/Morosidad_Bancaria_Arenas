import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from morosidad_bancaria.config import BcchConfig
from morosidad_bancaria.data.bcch import BcchClient, load_catalog


class BcchClientTests(unittest.TestCase):
    def setUp(self):
        self.client = BcchClient(BcchConfig("https://example.test", 30, 0), "user", "secret")

    def test_credentials_are_private_attributes(self):
        self.assertNotIn("secret", repr(self.client))

    def test_rejects_invalid_series_code_before_request(self):
        with self.assertRaisesRegex(ValueError, "Código de serie BCCh inválido"):
            self.client.download_series(
                "../bad",
                date(2025, 1, 1),
                date(2025, 2, 1),
                Path("unused"),
                Path("unused-manifest"),
            )

    def test_loads_latin1_catalog(self):
        payload = {
            "SeriesInfos": [
                {"seriesId": "TEST", "spanishTitle": "Índice de producción"}
            ]
        }
        temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.addCleanup(lambda: Path(temporary.name).unlink(missing_ok=True))
        with temporary:
            temporary.write(json.dumps(payload, ensure_ascii=False).encode("iso-8859-1"))
        catalog = load_catalog(Path(temporary.name))
        self.assertEqual(catalog[0]["spanishTitle"], "Índice de producción")


if __name__ == "__main__":
    unittest.main()
