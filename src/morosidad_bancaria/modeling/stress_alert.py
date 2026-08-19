"""Alerta de estrés con umbrales y validación estrictamente temporales."""

from __future__ import annotations

import importlib.metadata
import itertools
import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.modeling_base import add_months
from morosidad_bancaria.modeling.features import FeatureConfig, feature_names
from morosidad_bancaria.modeling.metrics import classification_metrics
from morosidad_bancaria.modeling.robustness import (
    moving_block_means,
    percentile,
)
from morosidad_bancaria.modeling.temporal import (
    TemporalFold,
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class StressAlertError(RuntimeError):
    """Indica una configuración inválida o fuga en el backtest de alertas."""


@dataclass(frozen=True)
class StressAlertConfig:
    horizon_months: int
    training_quantile: float
    comparison: str
    metric: str
    threshold_metric: str
    retune_frequency: str
    inner_validation_origins: int
    minimum_inner_training_rows: int
    decision_thresholds: tuple[float, ...]
    random_seed: int
    models: tuple[str, ...]
    candidates: dict[str, tuple[dict, ...]]
    calibration_bins: int
    bootstrap_block_length_months: int
    bootstrap_replications: int
    bootstrap_random_seed: int


@dataclass(frozen=True)
class StressAlertSummary:
    folds: int
    evaluation_origins: int
    models_including_benchmark: int
    prediction_rows: int
    tuning_candidates_evaluated: int
    threshold_candidates_evaluated: int
    inner_predictions_evaluated: int
    first_evaluation_origin: str
    last_evaluation_origin: str
    evaluated_splits: tuple[str, ...]


MODEL_NAMES = ("logistic_regression", "random_forest", "xgboost")
BENCHMARK_NAME = "historical_prevalence"


def _product(**parameters) -> tuple[dict, ...]:
    names = tuple(parameters)
    return tuple(
        dict(zip(names, values))
        for values in itertools.product(*(parameters[name] for name in names))
    )


def load_stress_alert_config(path: Path) -> StressAlertConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        event = raw["event"]
        selection = raw["selection"]
        models = raw["models"]
        logistic = raw["logistic_regression"]
        forest = raw["random_forest"]
        boosting = raw["xgboost"]
        evaluation = raw["evaluation"]
        candidates = {
            "logistic_regression": _product(
                C=[float(value) for value in logistic["c_values"]],
                max_iter=[int(logistic["max_iter"])],
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
                min_child_weight=[
                    float(value) for value in boosting["min_child_weights"]
                ],
                subsample=[float(boosting["subsample"])],
                colsample_bytree=[float(boosting["colsample_bytree"])],
                reg_lambda=[float(boosting["reg_lambda"])],
            ),
        }
        config = StressAlertConfig(
            horizon_months=int(event["horizon_months"]),
            training_quantile=float(event["training_quantile"]),
            comparison=str(event["comparison"]),
            metric=str(selection["metric"]),
            threshold_metric=str(selection["threshold_metric"]),
            retune_frequency=str(selection["retune_frequency"]),
            inner_validation_origins=int(selection["inner_validation_origins"]),
            minimum_inner_training_rows=int(
                selection["minimum_inner_training_rows"]
            ),
            decision_thresholds=tuple(
                float(value) for value in selection["decision_thresholds"]
            ),
            random_seed=int(selection["random_seed"]),
            models=tuple(str(value) for value in models["names"]),
            candidates=candidates,
            calibration_bins=int(evaluation["calibration_bins"]),
            bootstrap_block_length_months=int(
                evaluation["bootstrap_block_length_months"]
            ),
            bootstrap_replications=int(evaluation["bootstrap_replications"]),
            bootstrap_random_seed=int(evaluation["bootstrap_random_seed"]),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise StressAlertError(
            f"Configuración de alerta inválida: {path.name}"
        ) from error

    if config.horizon_months != 6:
        raise StressAlertError("El MVP de alerta requiere horizonte de seis meses")
    if not 0.5 < config.training_quantile < 1.0:
        raise StressAlertError("El percentil de estrés debe estar entre 0,5 y 1")
    if config.comparison != "strictly_greater":
        raise StressAlertError("El evento debe usar comparación estrictamente mayor")
    if (
        config.metric != "average_precision"
        or config.threshold_metric != "f1"
        or config.retune_frequency != "outer_fold"
    ):
        raise StressAlertError("El protocolo exige AP, F1 y reajuste por bloque")
    if config.models != MODEL_NAMES or set(config.candidates) != set(MODEL_NAMES):
        raise StressAlertError("La configuración no contiene los tres clasificadores")
    if any(not values for values in config.candidates.values()):
        raise StressAlertError("Una grilla de clasificación está vacía")
    if not config.decision_thresholds or any(
        not 0.0 < value < 1.0 for value in config.decision_thresholds
    ):
        raise StressAlertError("Los umbrales de alerta deben estar entre cero y uno")
    if tuple(sorted(set(config.decision_thresholds))) != config.decision_thresholds:
        raise StressAlertError("Los umbrales deben ser únicos y estar ordenados")
    if min(
        config.inner_validation_origins,
        config.minimum_inner_training_rows,
        config.calibration_bins,
        config.bootstrap_block_length_months,
        config.bootstrap_replications,
    ) <= 0:
        raise StressAlertError("Los tamaños del protocolo deben ser positivos")
    return config


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise StressAlertError(f"La columna {column} contiene un valor faltante")
    return float(value)


def define_stress_event(
    training_rows: list[dict],
    test_row: dict,
    target_column: str,
    training_quantile: float,
) -> tuple[float, int, float]:
    """Calcula umbral, evento de prueba y prevalencia usando solo entrenamiento."""
    if not training_rows:
        raise StressAlertError("No hay historia para definir el evento de estrés")
    changes = [_number(row, target_column) for row in training_rows]
    cutoff = percentile(changes, training_quantile)
    labels = [int(value > cutoff) for value in changes]
    if not any(labels) or all(labels):
        raise StressAlertError("El umbral produjo una clase de entrenamiento degenerada")
    actual_event = int(_number(test_row, target_column) > cutoff)
    return cutoff, actual_event, sum(labels) / len(labels)


def _training_labels(
    training_rows: list[dict], target_column: str, cutoff: float
) -> list[int]:
    labels = [int(_number(row, target_column) > cutoff) for row in training_rows]
    if not any(labels) or all(labels):
        raise StressAlertError("El clasificador requiere ambas clases en entrenamiento")
    return labels


def _build_classifier(
    model_name: str,
    parameters: dict,
    training_labels: list[int],
    random_seed: int,
):
    try:
        if model_name == "logistic_regression":
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler

            return Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            **parameters,
                            class_weight="balanced",
                            random_state=random_seed,
                        ),
                    ),
                ]
            )
        if model_name == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                **parameters,
                class_weight="balanced",
                random_state=random_seed,
                n_jobs=1,
            )
        if model_name == "xgboost":
            from xgboost import XGBClassifier

            positives = sum(training_labels)
            negatives = len(training_labels) - positives
            return XGBClassifier(
                **parameters,
                objective="binary:logistic",
                eval_metric="logloss",
                scale_pos_weight=negatives / positives,
                random_state=random_seed,
                n_jobs=1,
                tree_method="hist",
                verbosity=0,
            )
    except ImportError as error:
        raise StressAlertError(
            "Faltan dependencias; instale el extra de modelamiento"
        ) from error
    raise StressAlertError(f"Clasificador desconocido: {model_name}")


def fit_event_probability(
    model_name: str,
    parameters: dict,
    training_rows: list[dict],
    training_labels: list[int],
    test_row: dict,
    model_features: list[str],
    random_seed: int,
) -> float:
    x_train = [
        [_number(row, feature) for feature in model_features]
        for row in training_rows
    ]
    x_test = [[_number(test_row, feature) for feature in model_features]]
    estimator = _build_classifier(
        model_name, parameters, training_labels, random_seed
    )
    estimator.fit(x_train, training_labels)
    probability = float(estimator.predict_proba(x_test)[0][1])
    return min(1.0, max(0.0, probability))


def _inner_validation_rows(
    outer_training: list[dict], config: StressAlertConfig
) -> list[dict]:
    ordered = sorted(outer_training, key=lambda row: row["observation_date"])
    candidates = ordered[config.minimum_inner_training_rows :]
    selected = candidates[-config.inner_validation_origins :]
    if len(selected) < config.inner_validation_origins:
        raise StressAlertError("No hay suficientes orígenes internos para clasificación")
    return selected


def _select_model_and_threshold(
    model_name: str,
    all_rows: list[dict],
    outer_training: list[dict],
    model_features: list[str],
    config: StressAlertConfig,
    fold: TemporalFold,
) -> tuple[dict, float, float, list[dict], list[dict], int]:
    target_column = f"target_change_pp_h{config.horizon_months}"
    availability_column = f"target_available_date_h{config.horizon_months}"
    validation_rows = _inner_validation_rows(outer_training, config)
    outer_test = next(
        row for row in all_rows if row["observation_date"] == fold.test_start
    )
    outer_issue_date = outer_test["forecast_issue_date"]
    if any(
        row[availability_column] > outer_issue_date for row in validation_rows
    ):
        raise StressAlertError("La validación interna contiene una etiqueta no publicada")

    tuning: list[dict] = []
    predictions_by_candidate: dict[int, tuple[list[int], list[float]]] = {}
    for candidate_id, parameters in enumerate(config.candidates[model_name], start=1):
        actual: list[int] = []
        probability: list[float] = []
        minimum_training_rows: int | None = None
        maximum_purged_rows = 0
        for validation_row in validation_rows:
            inner_training, purged = eligible_training_rows(
                all_rows,
                validation_row,
                purge_target_availability=True,
                target_column=target_column,
                availability_column=availability_column,
            )
            if len(inner_training) < config.minimum_inner_training_rows:
                raise StressAlertError(
                    "La purga dejó pocas filas para la selección interna"
                )
            cutoff, actual_event, _ = define_stress_event(
                inner_training,
                validation_row,
                target_column,
                config.training_quantile,
            )
            labels = _training_labels(inner_training, target_column, cutoff)
            probability.append(
                fit_event_probability(
                    model_name,
                    parameters,
                    inner_training,
                    labels,
                    validation_row,
                    model_features,
                    config.random_seed,
                )
            )
            actual.append(actual_event)
            minimum_training_rows = (
                len(inner_training)
                if minimum_training_rows is None
                else min(minimum_training_rows, len(inner_training))
            )
            maximum_purged_rows = max(maximum_purged_rows, purged)
        metrics = classification_metrics(actual, probability)
        predictions_by_candidate[candidate_id] = (actual, probability)
        tuning.append(
            {
                "fold_id": fold.fold_id,
                "outer_test_start": fold.test_start,
                "model": model_name,
                "candidate_id": candidate_id,
                "parameters": json.dumps(
                    parameters, sort_keys=True, separators=(",", ":")
                ),
                "inner_average_precision": metrics["average_precision"],
                "inner_roc_auc": metrics["roc_auc"],
                "inner_brier_score": metrics["brier_score"],
                "inner_event_rate": metrics["prevalence"],
                "inner_validation_origins": len(validation_rows),
                "inner_validation_start": validation_rows[0]["observation_date"],
                "inner_validation_end": validation_rows[-1]["observation_date"],
                "minimum_inner_training_rows": minimum_training_rows,
                "maximum_inner_purged_rows": maximum_purged_rows,
                "selected": 0,
            }
        )
    selected = min(
        tuning,
        key=lambda row: (
            -float(row["inner_average_precision"] or -1.0),
            float(row["inner_brier_score"]),
            row["parameters"],
        ),
    )
    selected["selected"] = 1
    selected_id = int(selected["candidate_id"])
    actual, probability = predictions_by_candidate[selected_id]

    threshold_records: list[dict] = []
    for threshold in config.decision_thresholds:
        metrics = classification_metrics(
            actual, probability, decision_threshold=threshold
        )
        threshold_records.append(
            {
                "fold_id": fold.fold_id,
                "outer_test_start": fold.test_start,
                "model": model_name,
                "decision_threshold": threshold,
                "inner_precision": metrics["precision"],
                "inner_recall": metrics["recall"],
                "inner_f1": metrics["f1"],
                "inner_balanced_accuracy": metrics["balanced_accuracy"],
                "inner_alert_rate": metrics["alert_rate"],
                "inner_true_positives": metrics["true_positives"],
                "inner_false_positives": metrics["false_positives"],
                "inner_false_negatives": metrics["false_negatives"],
                "selected": 0,
            }
        )
    selected_threshold = min(
        threshold_records,
        key=lambda row: (
            -float(row["inner_f1"]),
            -float(row["inner_recall"]),
            -float(row["inner_precision"]),
            float(row["decision_threshold"]),
        ),
    )
    selected_threshold["selected"] = 1
    return (
        json.loads(selected["parameters"]),
        float(selected_threshold["decision_threshold"]),
        float(selected["inner_average_precision"]),
        tuning,
        threshold_records,
        len(validation_rows) * len(tuning),
    )


def run_stress_alert_backtest(
    rows: list[dict],
    feature_config: FeatureConfig,
    validation_config: ValidationConfig,
    config: StressAlertConfig,
) -> tuple[
    list[dict],
    list[dict],
    list[dict],
    list[TemporalFold],
    StressAlertSummary,
]:
    if not validation_config.holdout_locked:
        raise StressAlertError("El MVP exige mantener bloqueado el holdout")
    if not validation_config.target_availability_purge:
        raise StressAlertError("El MVP exige purgar etiquetas no publicadas")
    target_column = f"target_change_pp_h{config.horizon_months}"
    availability_column = f"target_available_date_h{config.horizon_months}"
    folds = build_expanding_folds(rows, validation_config, target_column)
    by_date = {row["observation_date"]: row for row in rows}
    model_features = feature_names(feature_config)
    predictions: list[dict] = []
    tuning: list[dict] = []
    threshold_tuning: list[dict] = []
    inner_predictions = 0

    for fold in folds:
        first_test = by_date[fold.observation_dates[0]]
        outer_training, _ = eligible_training_rows(
            rows,
            first_test,
            purge_target_availability=True,
            target_column=target_column,
            availability_column=availability_column,
        )
        selected: dict[str, tuple[dict, float, float]] = {}
        for model_name in config.models:
            (
                parameters,
                decision_threshold,
                inner_average_precision,
                model_tuning,
                model_thresholds,
                evaluated,
            ) = _select_model_and_threshold(
                model_name,
                rows,
                outer_training,
                model_features,
                config,
                fold,
            )
            selected[model_name] = (
                parameters,
                decision_threshold,
                inner_average_precision,
            )
            tuning.extend(model_tuning)
            threshold_tuning.extend(model_thresholds)
            inner_predictions += evaluated

        for observation_date in fold.observation_dates:
            test_row = by_date[observation_date]
            if test_row.get("split") != "development":
                raise StressAlertError("La alerta intentó evaluar el holdout")
            training, purged = eligible_training_rows(
                rows,
                test_row,
                purge_target_availability=True,
                target_column=target_column,
                availability_column=availability_column,
            )
            cutoff, actual_event, prevalence = define_stress_event(
                training,
                test_row,
                target_column,
                config.training_quantile,
            )
            labels = _training_labels(training, target_column, cutoff)
            common = {
                "fold_id": fold.fold_id,
                "observation_date": observation_date,
                "forecast_issue_date": test_row["forecast_issue_date"],
                "target_date_h6": test_row["target_date_h6"],
                "actual_change_pp_h6": _number(test_row, target_column),
                "stress_cutoff_pp": cutoff,
                "actual_event": actual_event,
                "training_rows": len(training),
                "training_events": sum(labels),
                "training_event_rate": prevalence,
                "purged_rows": purged,
                "lead_time_months": config.horizon_months,
                "evaluated_split": "development",
            }
            predictions.append(
                {
                    **common,
                    "model": BENCHMARK_NAME,
                    "predicted_probability": prevalence,
                    "decision_threshold": 0.5,
                    "predicted_event": int(prevalence >= 0.5),
                    "selected_parameters": "",
                    "inner_selection_average_precision": "",
                }
            )
            for model_name in config.models:
                parameters, decision_threshold, inner_ap = selected[model_name]
                probability = fit_event_probability(
                    model_name,
                    parameters,
                    training,
                    labels,
                    test_row,
                    model_features,
                    config.random_seed,
                )
                predictions.append(
                    {
                        **common,
                        "model": model_name,
                        "predicted_probability": probability,
                        "decision_threshold": decision_threshold,
                        "predicted_event": int(probability >= decision_threshold),
                        "selected_parameters": json.dumps(
                            parameters, sort_keys=True, separators=(",", ":")
                        ),
                        "inner_selection_average_precision": inner_ap,
                    }
                )

    origins = sorted({row["observation_date"] for row in predictions})
    summary = StressAlertSummary(
        folds=len(folds),
        evaluation_origins=len(origins),
        models_including_benchmark=1 + len(config.models),
        prediction_rows=len(predictions),
        tuning_candidates_evaluated=len(tuning),
        threshold_candidates_evaluated=len(threshold_tuning),
        inner_predictions_evaluated=inner_predictions,
        first_evaluation_origin=origins[0],
        last_evaluation_origin=origins[-1],
        evaluated_splits=("development",),
    )
    return predictions, tuning, threshold_tuning, folds, summary


def summarize_stress_metrics(predictions: list[dict]) -> list[dict]:
    benchmark: dict[tuple[str, str], float] = {}
    results: list[dict] = []
    fold_ids = sorted({int(row["fold_id"]) for row in predictions})
    model_names = sorted({row["model"] for row in predictions})
    for fold_id in [*fold_ids, "all"]:
        for model_name in model_names:
            rows = [
                row
                for row in predictions
                if row["model"] == model_name
                and (fold_id == "all" or int(row["fold_id"]) == fold_id)
            ]
            rows.sort(key=lambda row: row["observation_date"])
            metrics = classification_metrics(
                [int(row["actual_event"]) for row in rows],
                [float(row["predicted_probability"]) for row in rows],
                predicted=[int(row["predicted_event"]) for row in rows],
            )
            fold_key = str(fold_id)
            if model_name == BENCHMARK_NAME:
                benchmark[(fold_key, "brier")] = float(metrics["brier_score"])
            results.append(
                {
                    "fold_id": fold_id,
                    "model": model_name,
                    **metrics,
                    "average_decision_threshold": sum(
                        float(row["decision_threshold"]) for row in rows
                    )
                    / len(rows),
                    "minimum_stress_cutoff_pp": min(
                        float(row["stress_cutoff_pp"]) for row in rows
                    ),
                    "maximum_stress_cutoff_pp": max(
                        float(row["stress_cutoff_pp"]) for row in rows
                    ),
                }
            )
    for row in results:
        baseline_brier = benchmark[(str(row["fold_id"]), "brier")]
        row["brier_improvement_vs_prevalence_pct"] = (
            100.0
            * (baseline_brier - float(row["brier_score"]))
            / baseline_brier
        )
    return results


def build_calibration_table(predictions: list[dict], bins: int) -> list[dict]:
    results: list[dict] = []
    for model_name in sorted({row["model"] for row in predictions}):
        rows = [row for row in predictions if row["model"] == model_name]
        grouped: dict[int, list[dict]] = {}
        for row in rows:
            probability = float(row["predicted_probability"])
            bin_id = min(int(probability * bins), bins - 1)
            grouped.setdefault(bin_id, []).append(row)
        for bin_id in range(bins):
            members = grouped.get(bin_id, [])
            if not members:
                continue
            mean_probability = sum(
                float(row["predicted_probability"]) for row in members
            ) / len(members)
            event_rate = sum(int(row["actual_event"]) for row in members) / len(
                members
            )
            results.append(
                {
                    "model": model_name,
                    "bin_id": bin_id + 1,
                    "probability_lower": bin_id / bins,
                    "probability_upper": (bin_id + 1) / bins,
                    "n": len(members),
                    "mean_probability": mean_probability,
                    "event_rate": event_rate,
                    "calibration_gap": mean_probability - event_rate,
                }
            )
    return results


def brier_bootstrap(
    predictions: list[dict], config: StressAlertConfig
) -> list[dict]:
    benchmark_rows = {
        row["observation_date"]: row
        for row in predictions
        if row["model"] == BENCHMARK_NAME
    }
    results: list[dict] = []
    for model_index, model_name in enumerate(config.models):
        rows = sorted(
            (row for row in predictions if row["model"] == model_name),
            key=lambda row: row["observation_date"],
        )
        if {row["observation_date"] for row in rows} != set(benchmark_rows):
            raise StressAlertError(f"{model_name} no comparte todos los orígenes")
        differences: list[float] = []
        for row in rows:
            actual = int(row["actual_event"])
            model_loss = (float(row["predicted_probability"]) - actual) ** 2
            benchmark = benchmark_rows[row["observation_date"]]
            benchmark_loss = (
                float(benchmark["predicted_probability"]) - actual
            ) ** 2
            differences.append(model_loss - benchmark_loss)
        means = moving_block_means(
            differences,
            config.bootstrap_block_length_months,
            config.bootstrap_replications,
            config.bootstrap_random_seed + model_index,
        )
        lower = percentile(means, 0.025)
        upper = percentile(means, 0.975)
        conclusion = "inconclusive"
        if upper < 0:
            conclusion = "better_than_prevalence"
        elif lower > 0:
            conclusion = "worse_than_prevalence"
        results.append(
            {
                "model": model_name,
                "n": len(rows),
                "brier_difference_vs_prevalence": sum(differences)
                / len(differences),
                "loss_difference_ci95_lower": lower,
                "loss_difference_ci95_upper": upper,
                "bootstrap_probability_better_than_prevalence": sum(
                    value < 0 for value in means
                )
                / len(means),
                "paired_month_win_rate": sum(value < 0 for value in differences)
                / len(differences),
                "block_length_months": config.bootstrap_block_length_months,
                "bootstrap_replications": config.bootstrap_replications,
                "ci_conclusion": conclusion,
            }
        )
    return results


def classification_errors(predictions: list[dict]) -> list[dict]:
    results: list[dict] = []
    for row in predictions:
        if row["model"] == BENCHMARK_NAME:
            continue
        actual = int(row["actual_event"])
        forecast = int(row["predicted_event"])
        if actual == forecast:
            continue
        results.append(
            {
                "observation_date": row["observation_date"],
                "forecast_issue_date": row["forecast_issue_date"],
                "target_date_h6": row["target_date_h6"],
                "model": row["model"],
                "error_type": "false_positive" if forecast else "false_negative",
                "actual_change_pp_h6": row["actual_change_pp_h6"],
                "stress_cutoff_pp": row["stress_cutoff_pp"],
                "predicted_probability": row["predicted_probability"],
                "decision_threshold": row["decision_threshold"],
            }
        )
    return sorted(results, key=lambda row: (row["observation_date"], row["model"]))


def episode_detection(predictions: list[dict]) -> list[dict]:
    """Resume cuánto tarda cada modelo en detectar cada racha de estrés."""
    reference = sorted(
        (row for row in predictions if row["model"] == BENCHMARK_NAME),
        key=lambda row: row["observation_date"],
    )
    event_rows = [row for row in reference if int(row["actual_event"]) == 1]
    episodes: list[list[dict]] = []
    for row in event_rows:
        observation = date.fromisoformat(row["observation_date"])
        if not episodes:
            episodes.append([row])
            continue
        previous = date.fromisoformat(episodes[-1][-1]["observation_date"])
        if observation == add_months(previous, 1):
            episodes[-1].append(row)
        else:
            episodes.append([row])

    by_model_date = {
        (row["model"], row["observation_date"]): row for row in predictions
    }
    results: list[dict] = []
    for episode_id, episode in enumerate(episodes, start=1):
        dates = [row["observation_date"] for row in episode]
        for model_name in sorted(
            {row["model"] for row in predictions} - {BENCHMARK_NAME}
        ):
            alerts = [
                by_model_date[(model_name, observation)]
                for observation in dates
                if int(
                    by_model_date[(model_name, observation)]["predicted_event"]
                )
                == 1
            ]
            first_alert = alerts[0] if alerts else None
            delay = (
                dates.index(first_alert["observation_date"])
                if first_alert is not None
                else None
            )
            results.append(
                {
                    "episode_id": episode_id,
                    "model": model_name,
                    "episode_start_origin": dates[0],
                    "episode_end_origin": dates[-1],
                    "event_origins": len(dates),
                    "detected": int(first_alert is not None),
                    "first_true_alert_origin": (
                        first_alert["observation_date"] if first_alert else ""
                    ),
                    "detection_delay_months": delay,
                    "true_alerts_in_episode": len(alerts),
                    "episode_recall": len(alerts) / len(dates),
                    "forecast_horizon_months": int(episode[0]["lead_time_months"]),
                }
            )
    return results


def write_stress_metadata(
    config: StressAlertConfig,
    folds: list[TemporalFold],
    summary: StressAlertSummary,
    model_features: list[str],
    destination: Path,
) -> None:
    payload = {
        "summary": asdict(summary),
        "event": {
            "horizon_months": config.horizon_months,
            "definition": "target_change_pp_h6 > expanding training quantile",
            "training_quantile": config.training_quantile,
            "comparison": config.comparison,
        },
        "selection": {
            "metric": config.metric,
            "threshold_metric": config.threshold_metric,
            "retune_frequency": config.retune_frequency,
            "inner_validation_origins": config.inner_validation_origins,
            "minimum_inner_training_rows": config.minimum_inner_training_rows,
            "decision_thresholds": list(config.decision_thresholds),
            "random_seed": config.random_seed,
        },
        "models": [BENCHMARK_NAME, *config.models],
        "feature_columns": model_features,
        "folds": [asdict(fold) for fold in folds],
        "bootstrap": {
            "method": "circular moving blocks",
            "loss": "Brier score difference versus historical prevalence",
            "block_length_months": config.bootstrap_block_length_months,
            "replications": config.bootstrap_replications,
            "random_seed": config.bootstrap_random_seed,
        },
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


def write_stress_figure(
    predictions: list[dict], calibration: list[dict], destination: Path
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise StressAlertError(
            "Falta matplotlib; instale el extra de modelamiento"
        ) from error

    colors = {
        "logistic_regression": "#3b6ea8",
        "random_forest": "#d9822b",
        "xgboost": "#5b8f29",
        BENCHMARK_NAME: "#808080",
    }
    labels = {
        "logistic_regression": "Logística",
        "random_forest": "Random Forest",
        "xgboost": "XGBoost",
        BENCHMARK_NAME: "Prevalencia histórica",
    }
    figure, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    for model_name in [BENCHMARK_NAME, *MODEL_NAMES]:
        rows = sorted(
            (row for row in predictions if row["model"] == model_name),
            key=lambda row: row["observation_date"],
        )
        axes[0].plot(
            [date.fromisoformat(row["observation_date"]) for row in rows],
            [float(row["predicted_probability"]) for row in rows],
            label=labels[model_name],
            color=colors[model_name],
            linewidth=1.6,
        )
    event_rows = sorted(
        {
            row["observation_date"]: row
            for row in predictions
            if int(row["actual_event"]) == 1
        }.values(),
        key=lambda row: row["observation_date"],
    )
    axes[0].scatter(
        [date.fromisoformat(row["observation_date"]) for row in event_rows],
        [1.02] * len(event_rows),
        marker="v",
        color="#b30000",
        label="Estrés observado",
        zorder=5,
    )
    axes[0].set_ylim(-0.02, 1.08)
    axes[0].set_ylabel("Probabilidad pronosticada")
    axes[0].set_title("Alertas fuera de muestra")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8, loc="upper left")

    axes[1].plot([0, 1], [0, 1], color="#333333", linestyle="--", linewidth=1)
    for model_name in [BENCHMARK_NAME, *MODEL_NAMES]:
        rows = [row for row in calibration if row["model"] == model_name]
        axes[1].plot(
            [float(row["mean_probability"]) for row in rows],
            [float(row["event_rate"]) for row in rows],
            marker="o",
            label=labels[model_name],
            color=colors[model_name],
        )
    axes[1].set_xlim(0, 1)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("Probabilidad media")
    axes[1].set_ylabel("Frecuencia observada")
    axes[1].set_title("Calibración por intervalos")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8, loc="upper left")
    figure.suptitle("Alerta de estrés de morosidad a seis meses")
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(figure)
