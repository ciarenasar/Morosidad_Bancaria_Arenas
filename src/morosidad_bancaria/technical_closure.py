"""Cierre técnico, análisis por regímenes y trazabilidad del MVP."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.modeling.metrics import (
    classification_metrics,
    regression_metrics,
)


class TechnicalClosureError(RuntimeError):
    """Indica que el cierre técnico no satisface el protocolo congelado."""


@dataclass(frozen=True)
class TechnicalClosureConfig:
    pandemic_start: date
    pandemic_end: date
    high_inflation_threshold_pct: float
    high_policy_rate_threshold_pct: float
    activity_contraction_threshold_pct: float
    expected_monthly_rows: int
    expected_feature_count: int
    expected_complete_development_rows: int
    expected_holdout_rows: int
    expected_evaluation_origins: int
    expected_regression_models: tuple[str, ...]
    expected_alert_models: tuple[str, ...]
    manifest_algorithm: str
    exclude_names: tuple[str, ...]


REGIME_DIMENSIONS = (
    ("pandemic_period", "pandemic", "non_pandemic"),
    ("inflation_regime", "high_inflation", "lower_inflation"),
    ("policy_rate_regime", "high_policy_rate", "lower_policy_rate"),
    ("activity_regime", "activity_contraction", "activity_non_contraction"),
)


def load_technical_closure_config(path: Path) -> TechnicalClosureConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        regimes = raw["regimes"]
        acceptance = raw["acceptance"]
        reproduction = raw["reproduction"]
        config = TechnicalClosureConfig(
            pandemic_start=date.fromisoformat(regimes["pandemic_start"]),
            pandemic_end=date.fromisoformat(regimes["pandemic_end"]),
            high_inflation_threshold_pct=float(
                regimes["high_inflation_threshold_pct"]
            ),
            high_policy_rate_threshold_pct=float(
                regimes["high_policy_rate_threshold_pct"]
            ),
            activity_contraction_threshold_pct=float(
                regimes["activity_contraction_threshold_pct"]
            ),
            expected_monthly_rows=int(acceptance["expected_monthly_rows"]),
            expected_feature_count=int(acceptance["expected_feature_count"]),
            expected_complete_development_rows=int(
                acceptance["expected_complete_development_rows"]
            ),
            expected_holdout_rows=int(acceptance["expected_holdout_rows"]),
            expected_evaluation_origins=int(
                acceptance["expected_evaluation_origins"]
            ),
            expected_regression_models=tuple(
                str(value) for value in acceptance["expected_regression_models"]
            ),
            expected_alert_models=tuple(
                str(value) for value in acceptance["expected_alert_models"]
            ),
            manifest_algorithm=str(reproduction["manifest_algorithm"]),
            exclude_names=tuple(
                str(value) for value in reproduction["exclude_names"]
            ),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise TechnicalClosureError(
            f"Configuración de cierre técnico inválida: {path.name}"
        ) from error
    if config.pandemic_start > config.pandemic_end:
        raise TechnicalClosureError("El régimen pandemia tiene fechas invertidas")
    if min(
        config.expected_monthly_rows,
        config.expected_feature_count,
        config.expected_complete_development_rows,
        config.expected_holdout_rows,
        config.expected_evaluation_origins,
    ) <= 0:
        raise TechnicalClosureError("Los conteos de aceptación deben ser positivos")
    if config.manifest_algorithm != "sha256":
        raise TechnicalClosureError("El manifiesto reproducible requiere SHA-256")
    if not config.expected_regression_models or not config.expected_alert_models:
        raise TechnicalClosureError("Deben declararse los modelos esperados")
    return config


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise TechnicalClosureError(f"La columna {column} contiene un faltante")
    return float(value)


def build_regime_membership(
    matrix_rows: list[dict],
    evaluation_dates: set[str],
    config: TechnicalClosureConfig,
) -> list[dict]:
    by_date = {row["observation_date"]: row for row in matrix_rows}
    if not evaluation_dates or not evaluation_dates <= set(by_date):
        raise TechnicalClosureError("La matriz no contiene todos los orígenes evaluados")
    results: list[dict] = []
    for observation_date in sorted(evaluation_dates):
        row = by_date[observation_date]
        if row.get("split") != "development":
            raise TechnicalClosureError("Un régimen intentó incorporar el holdout")
        observation = date.fromisoformat(observation_date)
        inflation = _number(row, "ipc_yoy")
        policy_rate = _number(row, "tpm_monthly_average")
        activity = _number(row, "imacec_yoy_pct")
        results.append(
            {
                "observation_date": observation_date,
                "forecast_issue_date": row["forecast_issue_date"],
                "pandemic_period": (
                    "pandemic"
                    if config.pandemic_start <= observation <= config.pandemic_end
                    else "non_pandemic"
                ),
                "inflation_regime": (
                    "high_inflation"
                    if inflation >= config.high_inflation_threshold_pct
                    else "lower_inflation"
                ),
                "policy_rate_regime": (
                    "high_policy_rate"
                    if policy_rate >= config.high_policy_rate_threshold_pct
                    else "lower_policy_rate"
                ),
                "activity_regime": (
                    "activity_contraction"
                    if activity < config.activity_contraction_threshold_pct
                    else "activity_non_contraction"
                ),
                "ipc_yoy": inflation,
                "tpm_monthly_average": policy_rate,
                "imacec_yoy_pct": activity,
                "evaluated_split": "development",
            }
        )
    return results


def _validate_prediction_panel(
    predictions: list[dict], expected_models: tuple[str, ...]
) -> set[str]:
    model_names = {row["model"] for row in predictions}
    if model_names != set(expected_models):
        raise TechnicalClosureError(
            f"Modelos inesperados: {sorted(model_names)}"
        )
    dates_by_model = {
        model: [
            row["observation_date"]
            for row in predictions
            if row["model"] == model
        ]
        for model in expected_models
    }
    expected_dates = set(dates_by_model[expected_models[0]])
    for model, dates in dates_by_model.items():
        if len(dates) != len(set(dates)) or set(dates) != expected_dates:
            raise TechnicalClosureError(f"Panel temporal inconsistente para {model}")
    if any(row.get("evaluated_split") != "development" for row in predictions):
        raise TechnicalClosureError("El panel de predicciones contiene holdout")
    return expected_dates


def evaluate_regression_by_regime(
    predictions: list[dict],
    membership: list[dict],
    config: TechnicalClosureConfig,
) -> list[dict]:
    expected_dates = _validate_prediction_panel(
        predictions, config.expected_regression_models
    )
    membership_by_date = {row["observation_date"]: row for row in membership}
    if expected_dates != set(membership_by_date):
        raise TechnicalClosureError("Los regímenes no comparten los orígenes de regresión")
    results: list[dict] = []
    for dimension, first_regime, second_regime in REGIME_DIMENSIONS:
        for regime in (first_regime, second_regime):
            regime_dates = {
                observation_date
                for observation_date, row in membership_by_date.items()
                if row[dimension] == regime
            }
            if not regime_dates:
                raise TechnicalClosureError(f"El régimen {regime} está vacío")
            zero_rows = sorted(
                (
                    row
                    for row in predictions
                    if row["model"] == "zero_change"
                    and row["observation_date"] in regime_dates
                ),
                key=lambda row: row["observation_date"],
            )
            zero_mae = float(
                regression_metrics(
                    [_number(row, "actual_change_pp_h6") for row in zero_rows],
                    [_number(row, "predicted_change_pp_h6") for row in zero_rows],
                )["mae"]
            )
            for model in config.expected_regression_models:
                rows = sorted(
                    (
                        row
                        for row in predictions
                        if row["model"] == model
                        and row["observation_date"] in regime_dates
                    ),
                    key=lambda row: row["observation_date"],
                )
                metrics = regression_metrics(
                    [_number(row, "actual_change_pp_h6") for row in rows],
                    [_number(row, "predicted_change_pp_h6") for row in rows],
                )
                model_mae = float(metrics["mae"])
                results.append(
                    {
                        "regime_dimension": dimension,
                        "regime": regime,
                        "model": model,
                        **metrics,
                        "mae_improvement_vs_zero_pct": (
                            100.0 * (zero_mae - model_mae) / zero_mae
                        ),
                    }
                )
    return results


def evaluate_alerts_by_regime(
    predictions: list[dict],
    membership: list[dict],
    config: TechnicalClosureConfig,
) -> list[dict]:
    expected_dates = _validate_prediction_panel(
        predictions, config.expected_alert_models
    )
    membership_by_date = {row["observation_date"]: row for row in membership}
    if expected_dates != set(membership_by_date):
        raise TechnicalClosureError("Los regímenes no comparten los orígenes de alerta")
    results: list[dict] = []
    for dimension, first_regime, second_regime in REGIME_DIMENSIONS:
        for regime in (first_regime, second_regime):
            regime_dates = {
                observation_date
                for observation_date, row in membership_by_date.items()
                if row[dimension] == regime
            }
            benchmark_rows = [
                row
                for row in predictions
                if row["model"] == "historical_prevalence"
                and row["observation_date"] in regime_dates
            ]
            benchmark_brier = float(
                classification_metrics(
                    [int(row["actual_event"]) for row in benchmark_rows],
                    [float(row["predicted_probability"]) for row in benchmark_rows],
                    predicted=[
                        int(row["predicted_event"]) for row in benchmark_rows
                    ],
                )["brier_score"]
            )
            for model in config.expected_alert_models:
                rows = sorted(
                    (
                        row
                        for row in predictions
                        if row["model"] == model
                        and row["observation_date"] in regime_dates
                    ),
                    key=lambda row: row["observation_date"],
                )
                metrics = classification_metrics(
                    [int(row["actual_event"]) for row in rows],
                    [float(row["predicted_probability"]) for row in rows],
                    predicted=[int(row["predicted_event"]) for row in rows],
                )
                brier = float(metrics["brier_score"])
                results.append(
                    {
                        "regime_dimension": dimension,
                        "regime": regime,
                        "model": model,
                        **metrics,
                        "brier_improvement_vs_prevalence_pct": (
                            100.0 * (benchmark_brier - brier) / benchmark_brier
                        ),
                    }
                )
    return results


def _load_csv(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error) as error:
        raise TechnicalClosureError(f"No se pudo leer {path.name}") from error


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TechnicalClosureError(f"No se pudo leer {path.name}") from error


def build_acceptance_report(
    root: Path, config: TechnicalClosureConfig
) -> dict:
    checks: list[dict] = []

    def add_check(identifier: str, observed, expected, passed: bool) -> None:
        checks.append(
            {
                "id": identifier,
                "passed": passed,
                "observed": observed,
                "expected": expected,
            }
        )

    modeling = _load_json(root / "data" / "metadata" / "modeling_base_coverage.json")
    features = _load_json(root / "data" / "metadata" / "feature_coverage.json")
    add_check(
        "monthly_rows",
        int(modeling["rows"]),
        config.expected_monthly_rows,
        int(modeling["rows"]) == config.expected_monthly_rows,
    )
    add_check(
        "availability_violations",
        int(modeling["availability_violations"]),
        0,
        int(modeling["availability_violations"]) == 0,
    )
    add_check(
        "feature_count",
        int(features["feature_count"]),
        config.expected_feature_count,
        int(features["feature_count"]) == config.expected_feature_count,
    )
    add_check(
        "complete_development_rows",
        int(features["development_complete_rows"]),
        config.expected_complete_development_rows,
        int(features["development_complete_rows"])
        == config.expected_complete_development_rows,
    )
    add_check(
        "holdout_rows_reserved",
        int(modeling["holdout_rows"]),
        config.expected_holdout_rows,
        int(modeling["holdout_rows"]) == config.expected_holdout_rows,
    )

    baseline = _load_csv(
        root / "reports" / "tables" / "baseline_predictions_development.csv"
    )
    ml = _load_csv(root / "reports" / "tables" / "ml_predictions_development.csv")
    regression = [
        row
        for row in [*baseline, *ml]
        if row["model"] in config.expected_regression_models
    ]
    regression_dates = _validate_prediction_panel(
        regression, config.expected_regression_models
    )
    add_check(
        "regression_evaluation_origins",
        len(regression_dates),
        config.expected_evaluation_origins,
        len(regression_dates) == config.expected_evaluation_origins,
    )
    alerts = _load_csv(
        root / "reports" / "tables" / "stress_alert_predictions_development.csv"
    )
    alert_dates = _validate_prediction_panel(alerts, config.expected_alert_models)
    add_check(
        "alert_evaluation_origins",
        len(alert_dates),
        config.expected_evaluation_origins,
        len(alert_dates) == config.expected_evaluation_origins,
    )
    valid_probabilities = all(
        0.0 <= float(row["predicted_probability"]) <= 1.0 for row in alerts
    )
    add_check("alert_probability_bounds", valid_probabilities, True, valid_probabilities)

    evaluated_paths = (
        root / "reports" / "tables" / "baseline_predictions_development.csv",
        root / "reports" / "tables" / "ml_predictions_development.csv",
        root / "reports" / "tables" / "horizon_robustness_predictions.csv",
        root / "reports" / "tables" / "stress_alert_predictions_development.csv",
        root / "reports" / "tables" / "feature_attributions_oos.csv",
    )
    non_development_rows = 0
    for path in evaluated_paths:
        non_development_rows += sum(
            row.get("evaluated_split") != "development" for row in _load_csv(path)
        )
    add_check(
        "holdout_rows_evaluated",
        non_development_rows,
        0,
        non_development_rows == 0,
    )

    required_paths = (
        root / "docs" / "model_card_v1.md",
        root / "docs" / "technical_closure_v1.md",
        root / "docs" / "reproduction.md",
        root / "reports" / "tables" / "regime_membership_development.csv",
        root / "reports" / "tables" / "regression_metrics_by_regime.csv",
        root / "reports" / "tables" / "stress_alert_metrics_by_regime.csv",
    )
    missing = [path.relative_to(root).as_posix() for path in required_paths if not path.is_file()]
    add_check("required_closure_artifacts", missing, [], not missing)
    gitignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    env_ignored = ".env" in {line.strip() for line in gitignore}
    add_check("env_ignore_rule", env_ignored, True, env_ignored)
    return {
        "status": "passed" if all(check["passed"] for check in checks) else "failed",
        "checks_passed": sum(check["passed"] for check in checks),
        "checks_total": len(checks),
        "checks": checks,
        "holdout_policy": "El holdout permanece cerrado.",
    }


def _git_state(root: Path) -> dict:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

    head = run("rev-parse", "--verify", "HEAD")
    status = run("status", "--short")
    entries = [line for line in status.stdout.splitlines() if line]
    return {
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "head_available": head.returncode == 0,
        "worktree_clean": not entries,
        "status_entries": entries,
    }


def build_reproduction_manifest(
    root: Path, config: TechnicalClosureConfig
) -> dict:
    excluded_parts = {
        ".git",
        ".idea",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "htmlcov",
        "venv",
    }
    files: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in excluded_parts for part in path.parts):
            continue
        if any(part.endswith(".egg-info") for part in path.parts):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.name in config.exclude_names or path.suffix in {".pyc", ".pyo"}:
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    packages = {}
    for name in ("matplotlib", "numpy", "pandas", "scikit-learn", "xgboost"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "algorithm": config.manifest_algorithm,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": packages,
        },
        "git": _git_state(root),
        "excluded_names": list(config.exclude_names),
        "secret_policy": "El archivo .env se excluye del manifiesto y de Git.",
    }


def write_json(payload: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def _find(rows: list[dict], **conditions) -> dict:
    matches = [
        row
        for row in rows
        if all(str(row.get(key)) == str(value) for key, value in conditions.items())
    ]
    if len(matches) != 1:
        raise TechnicalClosureError(f"No se encontró una fila única para {conditions}")
    return matches[0]


def _decimal(value, digits: int = 3) -> str:
    if value in (None, ""):
        return "no definido"
    return f"{float(value):.{digits}f}".replace(".", ",")


def write_model_card(
    regression_overall: list[dict],
    alert_overall: list[dict],
    regression_regimes: list[dict],
    destination: Path,
) -> None:
    zero = _find(regression_overall, fold_id="all", model="zero_change")
    elastic = _find(regression_overall, fold_id="all", model="elastic_net")
    logistic = _find(alert_overall, fold_id="all", model="logistic_regression")
    prevalence = _find(
        alert_overall, fold_id="all", model="historical_prevalence"
    )
    elastic_regimes = [
        row for row in regression_regimes if row["model"] == "elastic_net"
    ]
    best_regime = max(
        elastic_regimes, key=lambda row: float(row["mae_improvement_vs_zero_pct"])
    )
    worst_regime = min(
        elastic_regimes, key=lambda row: float(row["mae_improvement_vs_zero_pct"])
    )
    text = f"""# Model card v1

## Sistema evaluado

- Unidad: sistema bancario chileno agregado, cartera de consumo, frecuencia mensual.
- Fecha de observación: mes `t`; emisión: publicación CMF efectiva de `t`.
- Target principal: cambio de mora de 90 días o más entre `t` y `t+6`.
- Alerta secundaria: cambio h=6 superior al percentil 80 disponible en train.
- Desarrollo externo: 46 orígenes, marzo de 2020 a diciembre de 2023.
- Holdout reservado: enero de 2024 a diciembre de 2025, no evaluado.

## Campeón de regresión

El campeón es **cambio cero**, no un modelo ajustado. Pronostica que la variación
de mora h=6 será cero. Su MAE de desarrollo es {_decimal(zero['mae'])} pp y su
RMSE es {_decimal(zero['rmse'])} pp.

ElasticNet completo es el challenger aprendido. Obtiene MAE
{_decimal(elastic['mae'])} pp, una mejora relativa de
{_decimal(elastic['mae_improvement_vs_zero_pct'], 1)}% frente al campeón. La
mejora negativa y el bootstrap por bloques justifican mantener cambio cero.

El mejor resultado descriptivo de ElasticNet por régimen ocurre en
`{best_regime['regime']}` ({_decimal(best_regime['mae_improvement_vs_zero_pct'], 1)}%)
y el peor en `{worst_regime['regime']}`
({_decimal(worst_regime['mae_improvement_vs_zero_pct'], 1)}%). Estos cortes no
se usan para seleccionar el modelo.

## Challenger de alerta

La regresión logística es el mejor ranking de estrés: AP
{_decimal(logistic['average_precision'])}, ROC-AUC
{_decimal(logistic['roc_auc'])}, recall
{_decimal(100 * float(logistic['recall']), 1)}% y precision
{_decimal(100 * float(logistic['precision']), 1)}%. Su Brier
({_decimal(logistic['brier_score'])}) es peor que la prevalencia histórica
({_decimal(prevalence['brier_score'])}), por lo que no se presenta como una
probabilidad calibrada ni se promueve a alerta operativa.

## Variables y estimación

Los modelos aprendidos usan 23 variables de historia de mora, actividad,
inflación, desempleo, tasas, tipo de cambio, crédito, dinero y estacionalidad.
La imputación, el escalamiento y el ajuste ocurren dentro de cada muestra
temporal. Las etiquetas no publicadas se purgan antes de entrenar.

## Uso previsto

- Investigación académica sobre predictibilidad agregada de morosidad.
- Benchmark reproducible y diagnóstico de señales macrofinancieras.
- Priorización exploratoria de meses para revisión humana.

## Usos no previstos

- Scoring de personas, aprobación de crédito o decisiones automáticas.
- Inferencia causal o recomendación regulatoria definitiva.
- Uso de las probabilidades de estrés como probabilidades calibradas.
- Producción en tiempo real sin validación adicional y monitoreo de drift.

## Limitaciones materiales

- Solo 46 orígenes externos y dos episodios efectivos de estrés.
- Las series macro son el vintage vigente, no el vintage histórico completo.
- El período de evaluación incluye quiebres por pandemia e inflación.
- El análisis agregado no representa heterogeneidad entre bancos o carteras.
- El repositorio debe registrar un commit antes de una entrega versionada.

## Estado

- Campeón h=6: cambio cero.
- Challenger de regresión: ElasticNet completo.
- Challenger de ranking de estrés: regresión logística.
- Alerta operativa: no aprobada.
- Holdout: cerrado.
"""
    destination.write_text(text, encoding="utf-8")


def write_technical_report(
    regression_regimes: list[dict],
    alert_regimes: list[dict],
    destination: Path,
) -> None:
    regression_lines = []
    alert_lines = []
    for dimension, first_regime, second_regime in REGIME_DIMENSIONS:
        for regime in (first_regime, second_regime):
            zero = _find(
                regression_regimes,
                regime_dimension=dimension,
                regime=regime,
                model="zero_change",
            )
            elastic = _find(
                regression_regimes,
                regime_dimension=dimension,
                regime=regime,
                model="elastic_net",
            )
            logistic = _find(
                alert_regimes,
                regime_dimension=dimension,
                regime=regime,
                model="logistic_regression",
            )
            regression_lines.append(
                "| "
                + " | ".join(
                    (
                        dimension,
                        regime,
                        str(zero["n"]),
                        _decimal(zero["mae"]),
                        _decimal(elastic["mae"]),
                        _decimal(elastic["mae_improvement_vs_zero_pct"], 1) + "%",
                    )
                )
                + " |"
            )
            alert_lines.append(
                "| "
                + " | ".join(
                    (
                        dimension,
                        regime,
                        str(logistic["n"]),
                        str(logistic["events"]),
                        _decimal(logistic["average_precision"]),
                        _decimal(logistic["brier_score"]),
                        _decimal(100 * float(logistic["recall"]), 1) + "%",
                    )
                )
                + " |"
            )
    text = """# Cierre técnico v1

## Alcance

Este cierre consolida métricas por régimen sin reabrir la selección de modelos.
Todas las filas pertenecen a desarrollo y usan variables disponibles en la
fecha de emisión. Los regímenes pueden solaparse entre dimensiones.

![Desempeño por régimen](../reports/figures/regime_performance.png)

## Regresión h=6

| Dimensión | Régimen | n | MAE cero | MAE ElasticNet | Mejora ElasticNet |
|---|---|---:|---:|---:|---:|
""" + "\n".join(regression_lines) + """

## Alerta logística

| Dimensión | Régimen | n | Eventos | AP | Brier | Recall |
|---|---|---:|---:|---:|---:|---:|
""" + "\n".join(alert_lines) + """

Las métricas sin ambas clases se muestran como `no definido`. Los cortes son
diagnósticos: no constituyen evidencia causal ni autorización para desplegar
los modelos.

## Controles y trazabilidad

- `technical_acceptance_v001.json` registra checks de cobertura y holdout.
- `reproduction_manifest_v001.json` registra hashes SHA-256 y entorno.
- `reproduction.md` describe la ejecución local de punta a punta.
- `model_card_v1.md` documenta usos, métricas y limitaciones.

El holdout permanece cerrado para el informe final.
"""
    destination.write_text(text, encoding="utf-8")


def write_regime_figure(
    regression_regimes: list[dict],
    alert_regimes: list[dict],
    destination: Path,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise TechnicalClosureError(
            "Falta matplotlib; instale el extra de modelamiento"
        ) from error

    labels = {
        "pandemic": "Pandemia",
        "non_pandemic": "Fuera de pandemia",
        "high_inflation": "Inflación alta",
        "lower_inflation": "Inflación baja",
        "high_policy_rate": "TPM alta",
        "lower_policy_rate": "TPM baja",
        "activity_contraction": "Contracción",
        "activity_non_contraction": "Sin contracción",
    }
    ordered_regimes = [
        regime
        for _, first_regime, second_regime in REGIME_DIMENSIONS
        for regime in (first_regime, second_regime)
    ]
    elastic = {
        row["regime"]: float(row["mae_improvement_vs_zero_pct"])
        for row in regression_regimes
        if row["model"] == "elastic_net"
    }
    logistic = {
        row["regime"]: row
        for row in alert_regimes
        if row["model"] == "logistic_regression"
    }
    figure, axes = plt.subplots(1, 2, figsize=(15, 6))
    improvements = [elastic[regime] for regime in ordered_regimes]
    axes[0].barh(
        [labels[regime] for regime in ordered_regimes],
        improvements,
        color=["#4c9f38" if value > 0 else "#c00000" for value in improvements],
    )
    axes[0].axvline(0, color="#333333", linewidth=1)
    axes[0].set_xlabel("Mejora MAE de ElasticNet frente a cambio cero (%)")
    axes[0].set_title("Regresión h=6")
    axes[0].grid(axis="x", alpha=0.25)
    axes[0].invert_yaxis()

    average_precision = [
        (
            float(logistic[regime]["average_precision"])
            if logistic[regime]["average_precision"] is not None
            else 0.0
        )
        for regime in ordered_regimes
    ]
    prevalence = [float(logistic[regime]["prevalence"]) for regime in ordered_regimes]
    positions = list(range(len(ordered_regimes)))
    axes[1].barh(
        positions,
        average_precision,
        color="#3b6ea8",
        alpha=0.85,
        label="Average Precision",
    )
    axes[1].scatter(
        prevalence,
        positions,
        color="#d9822b",
        marker="D",
        label="Prevalencia",
        zorder=4,
    )
    axes[1].set_yticks(positions, [labels[regime] for regime in ordered_regimes])
    axes[1].set_xlim(0, 1.05)
    axes[1].set_xlabel("Métrica")
    axes[1].set_title("Ranking de alerta logística")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].legend(loc="lower right")
    axes[1].invert_yaxis()
    figure.suptitle("Desempeño fuera de muestra por régimen")
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(figure)
