"""Modelos ML con selección interna y evaluación externa purgadas."""

from __future__ import annotations

import importlib.metadata
import itertools
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from morosidad_bancaria.modeling.features import FeatureConfig, feature_names
from morosidad_bancaria.modeling.temporal import (
    TemporalFold,
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class MlBacktestError(RuntimeError):
    """Indica una configuración o evaluación ML inválida."""


@dataclass(frozen=True)
class MlConfig:
    metric: str
    retune_frequency: str
    inner_validation_origins: int
    minimum_inner_training_rows: int
    random_seed: int
    candidates: dict[str, tuple[dict, ...]]


@dataclass(frozen=True)
class MlBacktestSummary:
    folds: int
    evaluation_origins: int
    models: int
    prediction_rows: int
    tuning_candidates_evaluated: int
    inner_predictions_evaluated: int
    first_evaluation_origin: str
    last_evaluation_origin: str
    evaluated_splits: tuple[str, ...]


MODEL_NAMES = ("elastic_net", "random_forest", "xgboost")


def _product(**parameters) -> tuple[dict, ...]:
    names = tuple(parameters)
    return tuple(
        dict(zip(names, values))
        for values in itertools.product(*(parameters[name] for name in names))
    )


def load_ml_config(path: Path) -> MlConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        selection = raw["selection"]
        elastic = raw["elastic_net"]
        forest = raw["random_forest"]
        boosting = raw["xgboost"]
        candidates = {
            "elastic_net": _product(
                alpha=[float(value) for value in elastic["alphas"]],
                l1_ratio=[float(value) for value in elastic["l1_ratios"]],
                max_iter=[int(elastic["max_iter"])],
            ),
            "random_forest": _product(
                n_estimators=[int(forest["n_estimators"])],
                max_depth=[int(value) for value in forest["max_depths"]],
                min_samples_leaf=[int(value) for value in forest["min_samples_leaf"]],
                max_features=[float(value) for value in forest["max_features"]],
            ),
            "xgboost": _product(
                n_estimators=[int(boosting["n_estimators"])],
                max_depth=[int(value) for value in boosting["max_depths"]],
                learning_rate=[float(value) for value in boosting["learning_rates"]],
                min_child_weight=[float(value) for value in boosting["min_child_weights"]],
                subsample=[float(boosting["subsample"])],
                colsample_bytree=[float(boosting["colsample_bytree"])],
                reg_lambda=[float(boosting["reg_lambda"])],
            ),
        }
        config = MlConfig(
            metric=str(selection["metric"]),
            retune_frequency=str(selection["retune_frequency"]),
            inner_validation_origins=int(selection["inner_validation_origins"]),
            minimum_inner_training_rows=int(selection["minimum_inner_training_rows"]),
            random_seed=int(selection["random_seed"]),
            candidates=candidates,
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise MlBacktestError(f"Configuración ML inválida: {path.name}") from error

    if config.metric != "mae" or config.retune_frequency != "outer_fold":
        raise MlBacktestError("El MVP requiere MAE y ajuste de hiperparámetros por bloque")
    if min(config.inner_validation_origins, config.minimum_inner_training_rows) <= 0:
        raise MlBacktestError("La validación interna requiere tamaños positivos")
    if set(config.candidates) != set(MODEL_NAMES):
        raise MlBacktestError("La configuración no contiene los tres modelos del MVP")
    if any(not values for values in config.candidates.values()):
        raise MlBacktestError("Una grilla de hiperparámetros está vacía")
    return config


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise MlBacktestError(f"La columna {column} contiene un valor faltante")
    return float(value)


def inner_validation_rows(outer_training: list[dict], config: MlConfig) -> list[dict]:
    ordered = sorted(outer_training, key=lambda row: row["observation_date"])
    candidates = ordered[config.minimum_inner_training_rows :]
    selected = candidates[-config.inner_validation_origins :]
    if not selected:
        raise MlBacktestError("No hay orígenes disponibles para validación interna")
    return selected


def build_estimator(model_name: str, parameters: dict, random_seed: int):
    try:
        if model_name == "elastic_net":
            from sklearn.linear_model import ElasticNet
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler

            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        ElasticNet(
                            alpha=parameters["alpha"],
                            l1_ratio=parameters["l1_ratio"],
                            max_iter=parameters["max_iter"],
                            random_state=random_seed,
                        ),
                    ),
                ]
            )
        if model_name == "random_forest":
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(
                **parameters,
                random_state=random_seed,
                n_jobs=1,
            )
        if model_name == "xgboost":
            from xgboost import XGBRegressor

            return XGBRegressor(
                **parameters,
                objective="reg:squarederror",
                eval_metric="mae",
                random_state=random_seed,
                n_jobs=1,
                tree_method="hist",
                verbosity=0,
            )
    except ImportError as error:
        raise MlBacktestError(
            "Faltan dependencias; instale el extra de modelamiento"
        ) from error
    raise MlBacktestError(f"Modelo desconocido: {model_name}")


def fit_predict(
    model_name: str,
    parameters: dict,
    train_rows: list[dict],
    test_row: dict,
    feature_names: list[str],
    random_seed: int,
    target_column: str = "target_change_pp_h6",
) -> float:
    if not train_rows:
        raise MlBacktestError("No hay filas para estimar el modelo")
    x_train = [[_number(row, name) for name in feature_names] for row in train_rows]
    y_train = [_number(row, target_column) for row in train_rows]
    x_test = [[_number(test_row, name) for name in feature_names]]
    estimator = build_estimator(model_name, parameters, random_seed)
    estimator.fit(x_train, y_train)
    return float(estimator.predict(x_test)[0])


def select_parameters(
    model_name: str,
    all_rows: list[dict],
    outer_training: list[dict],
    feature_names: list[str],
    config: MlConfig,
    fold: TemporalFold,
    target_column: str = "target_change_pp_h6",
    availability_column: str = "target_available_date_h6",
    rolling_window_months: int | None = None,
) -> tuple[dict, float, list[dict]]:
    validation_rows = inner_validation_rows(outer_training, config)
    outer_test = next(
        row for row in all_rows if row["observation_date"] == fold.test_start
    )
    outer_issue_date = outer_test["forecast_issue_date"]
    if any(
        row[availability_column] > outer_issue_date for row in validation_rows
    ):
        raise MlBacktestError("La validación interna contiene una etiqueta aún no publicada")
    records: list[dict] = []
    for candidate_id, parameters in enumerate(config.candidates[model_name], start=1):
        absolute_errors: list[float] = []
        minimum_training_rows: int | None = None
        maximum_purged_rows = 0
        for validation_row in validation_rows:
            inner_training, purged = eligible_training_rows(
                all_rows,
                validation_row,
                purge_target_availability=True,
                target_column=target_column,
                availability_column=availability_column,
                rolling_window_months=rolling_window_months,
            )
            if len(inner_training) < config.minimum_inner_training_rows:
                raise MlBacktestError(
                    "La purga dejó menos filas que el mínimo de entrenamiento interno"
                )
            prediction = fit_predict(
                model_name,
                parameters,
                inner_training,
                validation_row,
                feature_names,
                config.random_seed,
                target_column,
            )
            absolute_errors.append(
                abs(prediction - _number(validation_row, target_column))
            )
            minimum_training_rows = (
                len(inner_training)
                if minimum_training_rows is None
                else min(minimum_training_rows, len(inner_training))
            )
            maximum_purged_rows = max(maximum_purged_rows, purged)
        records.append(
            {
                "fold_id": fold.fold_id,
                "outer_test_start": fold.test_start,
                "model": model_name,
                "candidate_id": candidate_id,
                "parameters": json.dumps(parameters, sort_keys=True, separators=(",", ":")),
                "inner_mae": sum(absolute_errors) / len(absolute_errors),
                "inner_validation_origins": len(validation_rows),
                "inner_validation_start": validation_rows[0]["observation_date"],
                "inner_validation_end": validation_rows[-1]["observation_date"],
                "minimum_inner_training_rows": minimum_training_rows,
                "maximum_inner_purged_rows": maximum_purged_rows,
                "selected": 0,
            }
        )
    selected = min(records, key=lambda row: (row["inner_mae"], row["parameters"]))
    selected["selected"] = 1
    return json.loads(selected["parameters"]), float(selected["inner_mae"]), records


def run_ml_backtest(
    rows: list[dict],
    feature_config: FeatureConfig,
    validation_config: ValidationConfig,
    ml_config: MlConfig,
) -> tuple[list[dict], list[dict], list[TemporalFold], MlBacktestSummary]:
    if not validation_config.holdout_locked:
        raise MlBacktestError("El MVP exige mantener bloqueado el holdout")
    if not validation_config.target_availability_purge:
        raise MlBacktestError("El MVP exige purgar las etiquetas todavía no publicadas")
    folds = build_expanding_folds(rows, validation_config)
    by_date = {row["observation_date"]: row for row in rows}
    model_features = feature_names(feature_config)

    predictions: list[dict] = []
    tuning_records: list[dict] = []
    inner_predictions = 0
    for fold in folds:
        first_test = by_date[fold.observation_dates[0]]
        outer_training, _ = eligible_training_rows(
            rows, first_test, purge_target_availability=True
        )
        selected: dict[str, tuple[dict, float]] = {}
        for model_name in MODEL_NAMES:
            parameters, inner_mae, records = select_parameters(
                model_name,
                rows,
                outer_training,
                model_features,
                ml_config,
                fold,
            )
            selected[model_name] = (parameters, inner_mae)
            tuning_records.extend(records)
            inner_predictions += sum(
                int(record["inner_validation_origins"]) for record in records
            )

        for observation_date in fold.observation_dates:
            test_row = by_date[observation_date]
            if test_row.get("split") != "development":
                raise MlBacktestError("La evaluación ML intentó acceder al holdout")
            training, purged = eligible_training_rows(
                rows,
                test_row,
                purge_target_availability=validation_config.target_availability_purge,
            )
            actual = _number(test_row, "target_change_pp_h6")
            for model_name in MODEL_NAMES:
                parameters, inner_mae = selected[model_name]
                prediction = fit_predict(
                    model_name,
                    parameters,
                    training,
                    test_row,
                    model_features,
                    ml_config.random_seed,
                )
                predictions.append(
                    {
                        "fold_id": fold.fold_id,
                        "observation_date": observation_date,
                        "forecast_issue_date": test_row["forecast_issue_date"],
                        "target_date_h6": test_row["target_date_h6"],
                        "model": model_name,
                        "actual_change_pp_h6": actual,
                        "predicted_change_pp_h6": prediction,
                        "error_pp": prediction - actual,
                        "training_rows": len(training),
                        "purged_rows": purged,
                        "selected_parameters": json.dumps(
                            parameters, sort_keys=True, separators=(",", ":")
                        ),
                        "inner_selection_mae": inner_mae,
                        "evaluated_split": "development",
                    }
                )

    origins = sorted({row["observation_date"] for row in predictions})
    summary = MlBacktestSummary(
        folds=len(folds),
        evaluation_origins=len(origins),
        models=len(MODEL_NAMES),
        prediction_rows=len(predictions),
        tuning_candidates_evaluated=len(tuning_records),
        inner_predictions_evaluated=inner_predictions,
        first_evaluation_origin=origins[0],
        last_evaluation_origin=origins[-1],
        evaluated_splits=("development",),
    )
    return predictions, tuning_records, folds, summary


def write_ml_metadata(
    config: MlConfig,
    folds: list[TemporalFold],
    summary: MlBacktestSummary,
    feature_names: list[str],
    destination: Path,
) -> None:
    payload = {
        "summary": asdict(summary),
        "models": list(MODEL_NAMES),
        "feature_columns": feature_names,
        "selection": {
            "metric": config.metric,
            "retune_frequency": config.retune_frequency,
            "inner_validation_origins": config.inner_validation_origins,
            "minimum_inner_training_rows": config.minimum_inner_training_rows,
            "random_seed": config.random_seed,
        },
        "folds": [asdict(fold) for fold in folds],
        "library_versions": {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "xgboost")
        },
        "holdout_policy": "No se seleccionó, ajustó ni evaluó sobre el holdout.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
