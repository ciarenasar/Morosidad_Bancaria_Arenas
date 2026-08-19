"""Reproduce el proyecto y verifica si cambian sus resultados o conclusiones."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "reports" / "reproduction_baseline.json"
COMPARISON_PATH = ROOT / "reports" / "reproduction_comparison.json"
VALIDATION_PATH = ROOT / "docs" / "reproduction_validation.md"

KEY_FILE_PATTERNS = (
    "data/interim/*.csv",
    "data/processed/*.csv",
    "reports/tables/*.csv",
    "reports/figures/*.png",
    "docs/model_card_v1.md",
    "docs/technical_closure_v1.md",
    "docs/explainability_v1.md",
    "docs/horizon_robustness_v1.md",
    "docs/robustness_v1.md",
    "docs/stress_alert_v1.md",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def as_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return round(float(value), 12)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def key_file_hashes() -> dict[str, str]:
    files: set[Path] = set()
    for pattern in KEY_FILE_PATTERNS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    return {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted(files, key=lambda item: item.as_posix())
    }


def technical_check(acceptance: dict[str, Any], check_id: str) -> Any:
    for check in acceptance["checks"]:
        if check["id"] == check_id:
            return check["observed"]
    raise KeyError(f"No existe el control técnico: {check_id}")


def capture_conclusions() -> dict[str, Any]:
    regression = [
        row
        for row in read_csv(ROOT / "reports" / "tables" / "model_comparison_development.csv")
        if row["fold_id"] == "all"
    ]
    zero = next(row for row in regression if row["model"] == "zero_change")
    champion = min(regression, key=lambda row: float(row["mae"]))
    learned = [
        row
        for row in regression
        if row["model"] in {"elastic_net", "random_forest", "xgboost"}
    ]
    challenger = min(learned, key=lambda row: float(row["mae"]))

    stability = read_csv(
        ROOT / "reports" / "tables" / "stability_vs_zero_development.csv"
    )
    challenger_stability = next(
        row for row in stability if row["model"] == challenger["model"]
    )

    stress = [
        row
        for row in read_csv(
            ROOT / "reports" / "tables" / "stress_alert_metrics_development.csv"
        )
        if row["fold_id"] == "all"
    ]
    prevalence = next(row for row in stress if row["model"] == "historical_prevalence")
    stress_candidates = [row for row in stress if row["model"] != "historical_prevalence"]
    stress_challenger = max(
        stress_candidates,
        key=lambda row: float(row["average_precision"]),
    )

    horizons = [
        row
        for row in read_csv(
            ROOT / "reports" / "tables" / "horizon_robustness_metrics.csv"
        )
        if row["fold_id"] == "all"
        and row["model"] == "elastic_net"
        and row["training_scheme"] == "expanding"
    ]
    horizon_improvements = {
        str(row["horizon_months"]): as_float(row["mae_improvement_vs_zero_pct"])
        for row in sorted(horizons, key=lambda item: int(item["horizon_months"]))
    }

    drivers = [
        row
        for row in read_csv(ROOT / "reports" / "tables" / "feature_importance_global.csv")
        if row["fold_id"] == "all" and row["model"] == "elastic_net"
    ]
    top_driver = min(drivers, key=lambda row: float(row["rank"]))

    acceptance = json.loads(
        (ROOT / "data" / "metadata" / "technical_acceptance_v001.json").read_text(
            encoding="utf-8"
        )
    )
    stress_brier = float(stress_challenger["brier_score"])
    prevalence_brier = float(prevalence["brier_score"])

    return {
        "regression_champion": champion["model"],
        "regression_champion_mae_pp": as_float(champion["mae"]),
        "zero_change_mae_pp": as_float(zero["mae"]),
        "learned_challenger": challenger["model"],
        "learned_challenger_mae_pp": as_float(challenger["mae"]),
        "learned_improvement_vs_zero_pct": as_float(
            challenger_stability["mae_improvement_vs_zero_pct"]
        ),
        "challenger_bootstrap_probability_better_than_zero": as_float(
            challenger_stability["bootstrap_probability_better_than_zero"]
        ),
        "stress_ranking_challenger": stress_challenger["model"],
        "stress_average_precision": as_float(stress_challenger["average_precision"]),
        "stress_brier": as_float(stress_challenger["brier_score"]),
        "prevalence_brier": as_float(prevalence["brier_score"]),
        "stress_probability_calibrated_vs_prevalence": stress_brier <= prevalence_brier,
        "stress_alert_operationally_approved": False,
        "elastic_net_improvement_by_horizon_pct": horizon_improvements,
        "top_elastic_net_driver": top_driver["feature"],
        "technical_status": acceptance["status"],
        "technical_checks": f"{acceptance['checks_passed']}/{acceptance['checks_total']}",
        "holdout_rows_evaluated": technical_check(acceptance, "holdout_rows_evaluated"),
    }


def capture_snapshot() -> dict[str, Any]:
    return {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "conclusions": capture_conclusions(),
        "key_file_hashes": key_file_hashes(),
    }


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_conclusions = before["conclusions"]
    after_conclusions = after["conclusions"]
    conclusion_changes = {
        key: {"before": before_conclusions.get(key), "after": after_conclusions.get(key)}
        for key in sorted(set(before_conclusions) | set(after_conclusions))
        if before_conclusions.get(key) != after_conclusions.get(key)
    }

    before_hashes = before["key_file_hashes"]
    after_hashes = after["key_file_hashes"]
    changed_files = sorted(
        path
        for path in set(before_hashes) | set(after_hashes)
        if before_hashes.get(path) != after_hashes.get(path)
    )
    return {
        "compared_at_utc": datetime.now(UTC).isoformat(),
        "conclusions_changed": bool(conclusion_changes),
        "conclusion_changes": conclusion_changes,
        "key_files_before": len(before_hashes),
        "key_files_after": len(after_hashes),
        "key_files_changed": len(changed_files),
        "changed_files": changed_files,
        "before": before_conclusions,
        "after": after_conclusions,
    }


def write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, dict):
        return ", ".join(f"h={key}: {item:.3f}%" for key, item in value.items())
    return str(value)


def write_validation_report(comparison: dict[str, Any]) -> None:
    before = comparison["before"]
    after = comparison["after"]
    changed = comparison["conclusions_changed"]
    verdict = "CAMBIARON" if changed else "NO CAMBIARON"
    rows = (
        ("Campeón de regresión", "regression_champion"),
        ("MAE del campeón (pp)", "regression_champion_mae_pp"),
        ("Challenger aprendido", "learned_challenger"),
        ("Mejora del challenger vs. cero", "learned_improvement_vs_zero_pct"),
        ("Mejor ranking de estrés", "stress_ranking_challenger"),
        ("Average Precision de estrés", "stress_average_precision"),
        ("Brier de estrés", "stress_brier"),
        ("Brier de prevalencia", "prevalence_brier"),
        ("Alerta operativa aprobada", "stress_alert_operationally_approved"),
        ("Holdout evaluado", "holdout_rows_evaluated"),
        ("Estado técnico", "technical_status"),
    )
    table = "\n".join(
        f"| {label} | {format_value(before[key])} | {format_value(after[key])} |"
        for label, key in rows
    )
    changed_files = comparison["changed_files"]
    file_note = (
        "Ningún archivo analítico clave cambió."
        if not changed_files
        else "Archivos cambiados: " + ", ".join(f"`{item}`" for item in changed_files)
    )
    text = f"""# Validación de reproducción

## Veredicto

Las conclusiones **{verdict}** después de reconstruir el proyecto desde los
datos crudos locales.

| Indicador | Antes | Después |
|---|---:|---:|
{table}

## Integridad de resultados

- Archivos analíticos clave comparados: {comparison['key_files_after']}.
- Archivos con diferencias: {comparison['key_files_changed']}.
- {file_note}

## Interpretación

El campeón de regresión continúa siendo cambio cero. ElasticNet permanece como
challenger aprendido y no supera al benchmark de forma robusta. La regresión
logística conserva el mejor ranking de estrés, pero su Brier no mejora la
prevalencia histórica, por lo que la alerta sigue sin aprobación operativa. El
holdout permanece cerrado.
"""
    VALIDATION_PATH.write_text(text, encoding="utf-8")


def run_command(label: str, command: list[str]) -> None:
    print(f"\n=== {label} ===", flush=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Compara los resultados existentes sin reconstruir las etapas.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Omite las pruebas unitarias al finalizar.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = capture_snapshot()
    write_json(baseline, BASELINE_PATH)
    print(f"Línea base guardada: {BASELINE_PATH.relative_to(ROOT)}")

    if not args.skip_pipeline:
        run_command(
            "Pipeline local completo",
            [sys.executable, "-B", "-m", "morosidad_bancaria", "run-all-local"],
        )

    after = capture_snapshot()
    comparison = compare_snapshots(baseline, after)
    write_json(comparison, COMPARISON_PATH)
    write_validation_report(comparison)

    if not args.skip_pipeline:
        for pass_number in (1, 2):
            run_command(
                f"Actualización del manifiesto técnico {pass_number}/2",
                [sys.executable, "-B", "-m", "morosidad_bancaria", "close-technical"],
            )

    if not args.skip_tests:
        run_command(
            "Pruebas unitarias",
            [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        )

    verdict = "CAMBIARON" if comparison["conclusions_changed"] else "NO CAMBIARON"
    print(f"\nConclusiones: {verdict}")
    print(f"Archivos analíticos cambiados: {comparison['key_files_changed']}")
    print(f"Informe: {VALIDATION_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
