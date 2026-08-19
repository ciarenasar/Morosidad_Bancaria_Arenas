import tempfile
import unittest
from pathlib import Path

from morosidad_bancaria.technical_closure import (
    build_regime_membership,
    build_reproduction_manifest,
    load_technical_closure_config,
)


class TechnicalClosureTests(unittest.TestCase):
    def config(self):
        root = Path(__file__).resolve().parents[1]
        return load_technical_closure_config(
            root / "configs" / "technical_closure.toml"
        )

    def test_regime_boundaries_are_inclusive_and_point_in_time(self):
        rows = [
            {
                "observation_date": "2021-02-01",
                "forecast_issue_date": "2021-03-31",
                "split": "development",
                "ipc_yoy": "6.0",
                "tpm_monthly_average": "5.0",
                "imacec_yoy_pct": "-0.1",
            },
            {
                "observation_date": "2021-03-01",
                "forecast_issue_date": "2021-04-30",
                "split": "development",
                "ipc_yoy": "5.9",
                "tpm_monthly_average": "4.9",
                "imacec_yoy_pct": "0.0",
            },
        ]
        result = build_regime_membership(
            rows, {row["observation_date"] for row in rows}, self.config()
        )
        self.assertEqual(result[0]["pandemic_period"], "pandemic")
        self.assertEqual(result[0]["inflation_regime"], "high_inflation")
        self.assertEqual(result[0]["policy_rate_regime"], "high_policy_rate")
        self.assertEqual(result[0]["activity_regime"], "activity_contraction")
        self.assertEqual(result[1]["pandemic_period"], "non_pandemic")
        self.assertEqual(result[1]["inflation_regime"], "lower_inflation")
        self.assertEqual(result[1]["policy_rate_regime"], "lower_policy_rate")
        self.assertEqual(
            result[1]["activity_regime"], "activity_non_contraction"
        )

    def test_manifest_excludes_secrets_and_environment_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("SECRET=value", encoding="utf-8")
            (root / ".env.local").write_text("SECRET=other", encoding="utf-8")
            (root / ".env.example").write_text("SECRET=", encoding="utf-8")
            (root / "result.txt").write_text("result", encoding="utf-8")
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "module.pyc").write_bytes(b"compiled")
            manifest = build_reproduction_manifest(root, self.config())
        paths = {row["path"] for row in manifest["files"]}
        self.assertEqual(paths, {".env.example", "result.txt"})


if __name__ == "__main__":
    unittest.main()
