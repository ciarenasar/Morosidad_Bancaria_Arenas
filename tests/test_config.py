import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morosidad_bancaria.config import (
    ConfigurationError,
    load_credentials,
    load_project_config,
    read_env_file,
)


class EnvFileTests(unittest.TestCase):
    def write_env(self, content: str) -> Path:
        temporary = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
        self.addCleanup(lambda: Path(temporary.name).unlink(missing_ok=True))
        with temporary:
            temporary.write(content)
        return Path(temporary.name)

    def test_accepts_quoted_and_unquoted_values(self):
        path = self.write_env("A='uno'\nB=dos\nC=\"tres cuatro\"\n")
        self.assertEqual(read_env_file(path), {"A": "uno", "B": "dos", "C": "tres cuatro"})

    def test_environment_overrides_file_and_repr_redacts_secret(self):
        path = self.write_env("CMF_BEST_API_KEY=from-file\n")
        with patch.dict(os.environ, {"CMF_BEST_API_KEY": "top-secret"}, clear=False):
            credentials = load_credentials(path)
        self.assertEqual(credentials.cmf_best_api_key, "top-secret")
        self.assertNotIn("top-secret", repr(credentials))

    def test_missing_cmf_key_raises_safe_error(self):
        path = self.write_env("")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "Falta CMF_BEST_API_KEY"):
                load_credentials(path)

    def test_public_project_config_loads(self):
        config = load_project_config()
        self.assertEqual(config.forecast.observation_frequency, "monthly")
        self.assertEqual(config.forecast.horizon_months, 6)
        self.assertEqual(config.cmf_best.max_months_per_request, 12)
        self.assertGreaterEqual(config.cmf_best.min_interval_seconds, 6.0)
        self.assertIn("bcentral.cl", config.bcch.base_url)
        self.assertIn("cmfchile.cl", config.publication_calendar.cmf_press_url)


if __name__ == "__main__":
    unittest.main()
