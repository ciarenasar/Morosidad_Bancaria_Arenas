"""Backtest de benchmarks sobre desarrollo, con reentrenamiento mensual purgado."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.modeling_base import add_months
from morosidad_bancaria.modeling.features import FeatureConfig, load_csv_rows
from morosidad_bancaria.modeling.metrics import regression_metrics
from morosidad_bancaria.modeling.temporal import (
    TemporalFold,
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class BacktestError(RuntimeError):
    """Indica que el backtest no puede ejecutarse sin comprometer su diseño."""


@dataclass(frozen=True)
class BacktestSummary:
    folds: int
    evaluation_origins: int
    models: int
    prediction_rows: int
    first_evaluation_origin: str
    last_evaluation_origin: str
    minimum_effective_training_rows: int
    maximum_effective_training_rows: int
    maximum_purged_rows: int
    evaluated_splits: tuple[str, ...]


MODEL_NAMES = (
    "zero_change",
    "last_observed_change",
    "moving_average_change_12",
    "seasonal_naive_change_12",
    "autoregressive_ols",
)


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise BacktestError(f"La columna {column} contiene un valor faltante")
    return float(value)


def _autoregressive_ols(
    train_rows: list[dict], test_row: dict, feature_names: tuple[str, ...]
) -> float:
    try:
        from sklearn.linear_model import LinearRegression
    except ImportError as error:
        raise BacktestError(
            "El benchmark OLS requiere instalar las dependencias de modelamiento"
        ) from error
    x_train = [[_number(row, name) for name in feature_names] for row in train_rows]
    y_train = [_number(row, "target_change_pp_h6") for row in train_rows]
    x_test = [[_number(test_row, name) for name in feature_names]]
    return float(LinearRegression().fit(x_train, y_train).predict(x_test)[0])


def predict_benchmarks(
    train_rows: list[dict], test_row: dict, feature_config: FeatureConfig
) -> dict[str, float]:
    if not train_rows:
        raise BacktestError("No hay etiquetas disponibles para el origen de evaluación")
    ordered = sorted(train_rows, key=lambda row: row["observation_date"])
    targets = [_number(row, "target_change_pp_h6") for row in ordered]
    seasonal_date = add_months(date.fromisoformat(test_row["observation_date"]), -12)
    seasonal_matches = [
        row
        for row in ordered
        if date.fromisoformat(row["observation_date"]) == seasonal_date
    ]
    if not seasonal_matches:
        raise BacktestError(
            f"No existe benchmark estacional para {test_row['observation_date']}"
        )
    return {
        "zero_change": 0.0,
        "last_observed_change": targets[-1],
        "moving_average_change_12": sum(targets[-12:]) / min(12, len(targets)),
        "seasonal_naive_change_12": _number(
            seasonal_matches[0], "target_change_pp_h6"
        ),
        "autoregressive_ols": _autoregressive_ols(
            ordered, test_row, feature_config.autoregressive_features
        ),
    }


def run_backtest(
    rows: list[dict],
    feature_config: FeatureConfig,
    validation_config: ValidationConfig,
) -> tuple[list[dict], list[dict], list[TemporalFold], BacktestSummary]:
    if not validation_config.holdout_locked:
        raise BacktestError("El MVP exige mantener bloqueado el holdout")
    folds = build_expanding_folds(rows, validation_config)
    by_date = {row["observation_date"]: row for row in rows}
    predictions: list[dict] = []
    training_sizes: list[int] = []
    purged_sizes: list[int] = []

    for fold in folds:
        for observation_date in fold.observation_dates:
            test_row = by_date[observation_date]
            if test_row.get("split") != "development":
                raise BacktestError("El backtest intentó acceder a una fila fuera de desarrollo")
            training, purged = eligible_training_rows(
                rows,
                test_row,
                purge_target_availability=validation_config.target_availability_purge,
            )
            forecasts = predict_benchmarks(training, test_row, feature_config)
            actual = _number(test_row, "target_change_pp_h6")
            training_sizes.append(len(training))
            purged_sizes.append(purged)
            for model in MODEL_NAMES:
                prediction = forecasts[model]
                predictions.append(
                    {
                        "fold_id": fold.fold_id,
                        "observation_date": observation_date,
                        "forecast_issue_date": test_row["forecast_issue_date"],
                        "target_date_h6": test_row["target_date_h6"],
                        "model": model,
                        "actual_change_pp_h6": actual,
                        "predicted_change_pp_h6": prediction,
                        "error_pp": prediction - actual,
                        "training_rows": len(training),
                        "purged_rows": purged,
                        "evaluated_split": "development",
                    }
                )

    metrics = summarize_metrics(predictions)
    origins = sorted({row["observation_date"] for row in predictions})
    summary = BacktestSummary(
        folds=len(folds),
        evaluation_origins=len(origins),
        models=len(MODEL_NAMES),
        prediction_rows=len(predictions),
        first_evaluation_origin=origins[0],
        last_evaluation_origin=origins[-1],
        minimum_effective_training_rows=min(training_sizes),
        maximum_effective_training_rows=max(training_sizes),
        maximum_purged_rows=max(purged_sizes),
        evaluated_splits=("development",),
    )
    return predictions, metrics, folds, summary


def summarize_metrics(predictions: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in predictions:
        groups.setdefault((str(row["fold_id"]), row["model"]), []).append(row)
        groups.setdefault(("all", row["model"]), []).append(row)

    metrics: list[dict] = []
    for (fold_id, model), rows in sorted(groups.items()):
        actual = [float(row["actual_change_pp_h6"]) for row in rows]
        predicted = [float(row["predicted_change_pp_h6"]) for row in rows]
        metrics.append(
            {
                "fold_id": fold_id,
                "model": model,
                **regression_metrics(actual, predicted),
            }
        )
    zero_mae = {
        row["fold_id"]: float(row["mae"])
        for row in metrics
        if row["model"] == "zero_change"
    }
    for row in metrics:
        baseline = zero_mae[row["fold_id"]]
        row["mae_improvement_vs_zero_pct"] = (
            None if baseline == 0 else 100.0 * (baseline - float(row["mae"])) / baseline
        )
    return metrics


def write_csv(rows: list[dict], destination: Path) -> None:
    if not rows:
        raise BacktestError("No hay resultados para escribir")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def write_backtest_metadata(
    folds: list[TemporalFold], summary: BacktestSummary, destination: Path
) -> None:
    payload = {
        "summary": asdict(summary),
        "folds": [asdict(fold) for fold in folds],
        "holdout_policy": "No se seleccionó ni evaluó ninguna fila del holdout.",
        "purge_rule": (
            "En cada origen, target_available_date_h6 debe ser anterior o igual a "
            "forecast_issue_date."
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def load_model_matrix(path: Path) -> list[dict[str, str]]:
    return load_csv_rows(path)
