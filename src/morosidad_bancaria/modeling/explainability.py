"""Atribuciones estrictamente fuera de muestra y análisis de meses críticos."""

from __future__ import annotations

import itertools
import json
import math
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.modeling.features import FeatureConfig, feature_names
from morosidad_bancaria.modeling.ml_backtest import build_estimator
from morosidad_bancaria.modeling.temporal import eligible_training_rows


class ExplainabilityError(RuntimeError):
    """Indica una explicación inconsistente con las predicciones externas."""


@dataclass(frozen=True)
class ExplainabilityConfig:
    models: tuple[str, ...]
    top_global_features: int
    critical_absolute_change_months: int
    critical_elastic_error_months: int
    local_drivers_per_direction: int
    additivity_tolerance: float
    coefficient_zero_tolerance: float
    context_features: tuple[str, ...]


@dataclass(frozen=True)
class ExplainabilitySummary:
    models: int
    evaluation_origins: int
    feature_count: int
    attribution_rows: int
    critical_months: int
    maximum_additivity_gap: float
    evaluated_splits: tuple[str, ...]


def load_explainability_config(path: Path) -> ExplainabilityConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)["explainability"]
        config = ExplainabilityConfig(
            models=tuple(raw["models"]),
            top_global_features=int(raw["top_global_features"]),
            critical_absolute_change_months=int(raw["critical_absolute_change_months"]),
            critical_elastic_error_months=int(raw["critical_elastic_error_months"]),
            local_drivers_per_direction=int(raw["local_drivers_per_direction"]),
            additivity_tolerance=float(raw["additivity_tolerance"]),
            coefficient_zero_tolerance=float(raw["coefficient_zero_tolerance"]),
            context_features=tuple(raw["context_features"]),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise ExplainabilityError(
            f"Configuración de explicabilidad inválida: {path.name}"
        ) from error
    if set(config.models) != {"elastic_net", "xgboost", "random_forest"}:
        raise ExplainabilityError("El protocolo debe explicar los tres modelos aprendidos")
    counts = (
        config.top_global_features,
        config.critical_absolute_change_months,
        config.critical_elastic_error_months,
        config.local_drivers_per_direction,
    )
    if min(counts) <= 0 or config.additivity_tolerance <= 0:
        raise ExplainabilityError("Los tamaños y la tolerancia deben ser positivos")
    return config


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise ExplainabilityError(f"La columna {column} contiene un valor faltante")
    return float(value)


def _fit_inputs(
    training: list[dict], test_row: dict, features: list[str]
) -> tuple[list[list[float]], list[float], list[list[float]]]:
    return (
        [[_number(row, name) for name in features] for row in training],
        [_number(row, "target_change_pp_h6") for row in training],
        [[_number(test_row, name) for name in features]],
    )


def _elastic_attributions(estimator, x_test: list[list[float]]):
    scaler = estimator.named_steps["scale"]
    model = estimator.named_steps["model"]
    standardized = scaler.transform(x_test)[0]
    coefficients = model.coef_
    contributions = standardized * coefficients
    return (
        [float(value) for value in contributions],
        [float(value) for value in coefficients],
        float(model.intercept_),
    )


def _xgboost_attributions(estimator, x_test: list[list[float]]):
    try:
        from xgboost import DMatrix
    except ImportError as error:
        raise ExplainabilityError("XGBoost no está instalado") from error
    contributions = estimator.get_booster().predict(
        DMatrix(x_test), pred_contribs=True
    )[0]
    return (
        [float(value) for value in contributions[:-1]],
        [None] * (len(contributions) - 1),
        float(contributions[-1]),
    )


def run_explainability(
    matrix_rows: list[dict],
    prediction_rows: list[dict],
    feature_config: FeatureConfig,
    config: ExplainabilityConfig,
    random_seed: int,
) -> tuple[list[dict], ExplainabilitySummary]:
    features = feature_names(feature_config)
    unknown_context = set(config.context_features) - set(features)
    if unknown_context:
        raise ExplainabilityError(f"Variables de contexto desconocidas: {unknown_context}")
    by_date = {row["observation_date"]: row for row in matrix_rows}
    selected_predictions = [
        row for row in prediction_rows if row.get("model") in config.models
    ]
    expected_origins = {
        row["observation_date"]
        for row in selected_predictions
        if row["model"] == config.models[0]
    }
    for model_name in config.models:
        model_rows = [row for row in selected_predictions if row["model"] == model_name]
        if len(model_rows) != len(expected_origins) or {
            row["observation_date"] for row in model_rows
        } != expected_origins:
            raise ExplainabilityError(f"{model_name} no comparte los orígenes externos")

    attributions: list[dict] = []
    maximum_gap = 0.0
    for prediction_row in sorted(
        selected_predictions,
        key=lambda row: (row["observation_date"], row["model"]),
    ):
        observation_date = prediction_row["observation_date"]
        test_row = by_date[observation_date]
        if test_row.get("split") != "development":
            raise ExplainabilityError("La explicación intentó acceder al holdout")
        training, purged = eligible_training_rows(matrix_rows, test_row, True)
        if len(training) != int(prediction_row["training_rows"]) or purged != int(
            prediction_row["purged_rows"]
        ):
            raise ExplainabilityError("La muestra explicativa no reproduce el backtest")
        parameters = json.loads(prediction_row["selected_parameters"])
        x_train, y_train, x_test = _fit_inputs(training, test_row, features)
        estimator = build_estimator(prediction_row["model"], parameters, random_seed)
        estimator.fit(x_train, y_train)
        direct_prediction = float(estimator.predict(x_test)[0])
        recorded_prediction = _number(prediction_row, "predicted_change_pp_h6")
        direct_gap = abs(direct_prediction - recorded_prediction)
        if direct_gap > config.additivity_tolerance:
            raise ExplainabilityError("El modelo reestimado no reproduce su predicción")

        model_name = prediction_row["model"]
        if model_name == "elastic_net":
            values, weights, baseline = _elastic_attributions(estimator, x_test)
            method = "standardized_linear_contribution"
            reconstructed = baseline + sum(values)
        elif model_name == "xgboost":
            values, weights, baseline = _xgboost_attributions(estimator, x_test)
            method = "tree_shap"
            reconstructed = baseline + sum(values)
        else:
            values = [None] * len(features)
            weights = [float(value) for value in estimator.feature_importances_]
            baseline = None
            reconstructed = direct_prediction
            method = "mean_decrease_impurity"

        additivity_gap = abs(reconstructed - recorded_prediction)
        maximum_gap = max(maximum_gap, additivity_gap)
        if additivity_gap > config.additivity_tolerance:
            raise ExplainabilityError(
                f"Las atribuciones de {model_name} no reconstruyen {observation_date}"
            )
        for index, feature in enumerate(features):
            attribution = values[index]
            weight = weights[index]
            importance = abs(attribution) if attribution is not None else abs(weight)
            attributions.append(
                {
                    "fold_id": prediction_row["fold_id"],
                    "observation_date": observation_date,
                    "model": model_name,
                    "method": method,
                    "feature": feature,
                    "feature_value": x_test[0][index],
                    "attribution_value": attribution,
                    "absolute_attribution": importance,
                    "model_weight": weight,
                    "baseline_value": baseline,
                    "recorded_prediction": recorded_prediction,
                    "additivity_gap": additivity_gap,
                    "evaluated_split": "development",
                }
            )

    summary = ExplainabilitySummary(
        models=len(config.models),
        evaluation_origins=len(expected_origins),
        feature_count=len(features),
        attribution_rows=len(attributions),
        critical_months=0,
        maximum_additivity_gap=maximum_gap,
        evaluated_splits=("development",),
    )
    return attributions, summary


def _optional_number(value) -> float | None:
    return None if value in (None, "") else float(value)


def aggregate_attributions(
    rows: list[dict], coefficient_zero_tolerance: float, by_fold: bool
) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (
            row["model"],
            row["method"],
            row["feature"],
            str(row["fold_id"]) if by_fold else "all",
        )
        groups.setdefault(key, []).append(row)

    aggregates: list[dict] = []
    for (model, method, feature, fold_id), values in groups.items():
        absolute = [_number(row, "absolute_attribution") for row in values]
        signed = [
            value
            for value in (_optional_number(row["attribution_value"]) for row in values)
            if value is not None
        ]
        weights = [
            value
            for value in (_optional_number(row["model_weight"]) for row in values)
            if value is not None
        ]
        positive = sum(value > coefficient_zero_tolerance for value in signed)
        negative = sum(value < -coefficient_zero_tolerance for value in signed)
        zero = len(signed) - positive - negative
        weight_positive = sum(value > coefficient_zero_tolerance for value in weights)
        weight_negative = sum(value < -coefficient_zero_tolerance for value in weights)
        weight_zero = len(weights) - weight_positive - weight_negative
        aggregates.append(
            {
                "fold_id": fold_id,
                "model": model,
                "method": method,
                "feature": feature,
                "origins": len(values),
                "mean_absolute_attribution": sum(absolute) / len(absolute),
                "normalized_importance": None,
                "mean_signed_attribution": (
                    None if not signed else sum(signed) / len(signed)
                ),
                "attribution_positive_share": (
                    None if not signed else positive / len(signed)
                ),
                "attribution_negative_share": (
                    None if not signed else negative / len(signed)
                ),
                "attribution_zero_share": None if not signed else zero / len(signed),
                "attribution_sign_consistency": (
                    None if not signed else max(positive, negative, zero) / len(signed)
                ),
                "mean_model_weight": (
                    None if not weights else sum(weights) / len(weights)
                ),
                "weight_positive_share": (
                    None if not weights else weight_positive / len(weights)
                ),
                "weight_negative_share": (
                    None if not weights else weight_negative / len(weights)
                ),
                "weight_zero_share": (
                    None if not weights else weight_zero / len(weights)
                ),
                "weight_sign_consistency": (
                    None
                    if not weights
                    else max(weight_positive, weight_negative, weight_zero) / len(weights)
                ),
                "rank": None,
            }
        )

    partitions: dict[tuple[str, str], list[dict]] = {}
    for row in aggregates:
        partitions.setdefault((row["model"], row["fold_id"]), []).append(row)
    for values in partitions.values():
        total = sum(float(row["mean_absolute_attribution"]) for row in values)
        ranked = sorted(
            values, key=lambda row: (-float(row["mean_absolute_attribution"]), row["feature"])
        )
        for row in ranked:
            row["normalized_importance"] = (
                None if total == 0 else float(row["mean_absolute_attribution"]) / total
            )
        index = 0
        while index < len(ranked):
            end = index + 1
            reference = float(ranked[index]["mean_absolute_attribution"])
            while end < len(ranked) and abs(
                float(ranked[end]["mean_absolute_attribution"]) - reference
            ) <= 1e-15:
                end += 1
            average_rank = (index + 1 + end) / 2.0
            for row in ranked[index:end]:
                row["rank"] = average_rank
            index = end
    return sorted(aggregates, key=lambda row: (row["fold_id"], row["model"], row["rank"]))


def _driver_text(rows: list[dict], positive: bool, count: int) -> str:
    signed = [row for row in rows if row["attribution_value"] not in (None, "")]
    eligible = [
        row
        for row in signed
        if (float(row["attribution_value"]) > 0) == positive
        and float(row["attribution_value"]) != 0
    ]
    ordered = sorted(
        eligible,
        key=lambda row: abs(float(row["attribution_value"])),
        reverse=True,
    )[:count]
    text = " | ".join(
        f"{row['feature']}:{float(row['attribution_value']):+.4f}" for row in ordered
    )
    return text or "none_nonzero"


def driver_rank_stability(fold_rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in fold_rows:
        groups.setdefault((row["model"], row["method"], row["feature"]), []).append(row)
    result: list[dict] = []
    for (model, method, feature), values in groups.items():
        ranks = [float(row["rank"]) for row in values]
        importances = [float(row["normalized_importance"]) for row in values]
        mean_rank = sum(ranks) / len(ranks)
        result.append(
            {
                "model": model,
                "method": method,
                "feature": feature,
                "folds": len(values),
                "mean_rank": mean_rank,
                "rank_standard_deviation": math.sqrt(
                    sum((rank - mean_rank) ** 2 for rank in ranks) / len(ranks)
                ),
                "best_rank": min(ranks),
                "worst_rank": max(ranks),
                "top_5_fold_share": sum(rank <= 5 for rank in ranks) / len(ranks),
                "top_10_fold_share": sum(rank <= 10 for rank in ranks) / len(ranks),
                "mean_normalized_importance": sum(importances) / len(importances),
                "importance_range": max(importances) - min(importances),
            }
        )
    return sorted(result, key=lambda row: (row["model"], row["mean_rank"], row["feature"]))


def _correlation(left: list[float], right: list[float]) -> float | None:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right)
    )
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    return None if left_ss == 0 or right_ss == 0 else covariance / math.sqrt(left_ss * right_ss)


def fold_rank_correlations(fold_rows: list[dict]) -> list[dict]:
    by_model_fold: dict[tuple[str, str], dict[str, float]] = {}
    methods: dict[str, str] = {}
    for row in fold_rows:
        model = row["model"]
        fold = str(row["fold_id"])
        methods[model] = row["method"]
        by_model_fold.setdefault((model, fold), {})[row["feature"]] = float(row["rank"])
    result: list[dict] = []
    for model in sorted(methods):
        folds = sorted(fold for candidate, fold in by_model_fold if candidate == model)
        for left_fold, right_fold in itertools.combinations(folds, 2):
            left = by_model_fold[(model, left_fold)]
            right = by_model_fold[(model, right_fold)]
            features = sorted(set(left) & set(right))
            result.append(
                {
                    "model": model,
                    "method": methods[model],
                    "left_fold": left_fold,
                    "right_fold": right_fold,
                    "features": len(features),
                    "spearman_rank_correlation": _correlation(
                        [float(left[feature]) for feature in features],
                        [float(right[feature]) for feature in features],
                    ),
                }
            )
    return result


def build_critical_months(
    matrix_rows: list[dict],
    baseline_predictions: list[dict],
    ml_predictions: list[dict],
    attribution_rows: list[dict],
    config: ExplainabilityConfig,
) -> list[dict]:
    zero_rows = {
        row["observation_date"]: row
        for row in baseline_predictions
        if row["model"] == "zero_change"
    }
    ml_by_key = {(row["model"], row["observation_date"]): row for row in ml_predictions}
    matrix_by_date = {row["observation_date"]: row for row in matrix_rows}
    largest_changes = sorted(
        zero_rows.values(),
        key=lambda row: abs(_number(row, "actual_change_pp_h6")),
        reverse=True,
    )[: config.critical_absolute_change_months]
    elastic_rows = [row for row in ml_predictions if row["model"] == "elastic_net"]
    largest_errors = sorted(
        elastic_rows,
        key=lambda row: abs(_number(row, "error_pp")),
        reverse=True,
    )[: config.critical_elastic_error_months]
    reasons: dict[str, set[str]] = {}
    for row in largest_changes:
        reasons.setdefault(row["observation_date"], set()).add("largest_actual_change")
    for row in largest_errors:
        reasons.setdefault(row["observation_date"], set()).add("largest_elastic_error")
    attribution_by_key: dict[tuple[str, str], list[dict]] = {}
    for row in attribution_rows:
        attribution_by_key.setdefault((row["model"], row["observation_date"]), []).append(
            row
        )

    result: list[dict] = []
    for observation_date in sorted(reasons):
        zero = zero_rows[observation_date]
        matrix = matrix_by_date[observation_date]
        row = {
            "observation_date": observation_date,
            "forecast_issue_date": zero["forecast_issue_date"],
            "target_date_h6": zero["target_date_h6"],
            "critical_reason": "|".join(sorted(reasons[observation_date])),
            "actual_change_pp_h6": _number(zero, "actual_change_pp_h6"),
            "zero_prediction": _number(zero, "predicted_change_pp_h6"),
            "zero_absolute_error": abs(_number(zero, "error_pp")),
        }
        for model_name in ("elastic_net", "xgboost", "random_forest"):
            prediction = ml_by_key[(model_name, observation_date)]
            row[f"{model_name}_prediction"] = _number(
                prediction, "predicted_change_pp_h6"
            )
            row[f"{model_name}_absolute_error"] = abs(_number(prediction, "error_pp"))
        for model_name in ("elastic_net", "xgboost"):
            local = attribution_by_key[(model_name, observation_date)]
            row[f"{model_name}_positive_drivers"] = _driver_text(
                local, True, config.local_drivers_per_direction
            )
            row[f"{model_name}_negative_drivers"] = _driver_text(
                local, False, config.local_drivers_per_direction
            )
        for feature in config.context_features:
            row[feature] = _number(matrix, feature)
        row["evaluated_split"] = "development"
        result.append(row)
    return result


def write_explainability_metadata(
    config: ExplainabilityConfig,
    summary: ExplainabilitySummary,
    destination: Path,
) -> None:
    payload = {
        "summary": asdict(summary),
        "models": list(config.models),
        "methods": {
            "elastic_net": "standardized_linear_contribution",
            "xgboost": "exact_tree_shap_pred_contribs",
            "random_forest": "mean_decrease_impurity",
        },
        "rank_ties": "average_rank_for_equal_mean_absolute_attribution",
        "critical_month_selection": {
            "largest_absolute_actual_changes": config.critical_absolute_change_months,
            "largest_elastic_net_absolute_errors": config.critical_elastic_error_months,
        },
        "additivity_tolerance": config.additivity_tolerance,
        "holdout_policy": "Todas las explicaciones corresponden a development.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def write_explainability_figures(
    global_importance: list[dict],
    baseline_predictions: list[dict],
    ml_predictions: list[dict],
    destination: Path,
    top_features: int,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise ExplainabilityError("Matplotlib no está instalado") from error

    destination.mkdir(parents=True, exist_ok=True)
    labels = {
        "elastic_net": "ElasticNet",
        "xgboost": "XGBoost (TreeSHAP)",
        "random_forest": "Random Forest",
    }
    figure, axes = plt.subplots(1, 3, figsize=(16, 6))
    for axis, model_name in zip(axes, labels):
        rows = sorted(
            (row for row in global_importance if row["model"] == model_name),
            key=lambda row: float(row["rank"]),
        )[:top_features]
        rows.reverse()
        axis.barh(
            [row["feature"] for row in rows],
            [100.0 * float(row["normalized_importance"]) for row in rows],
            color="#3465a4",
        )
        axis.set_title(labels[model_name])
        axis.set_xlabel("Importancia normalizada (%)")
        axis.grid(axis="x", alpha=0.25)
    figure.suptitle("Drivers globales fuera de muestra")
    figure.tight_layout()
    figure.savefig(destination / "global_feature_importance.png", dpi=180)
    plt.close(figure)

    zero = sorted(
        (row for row in baseline_predictions if row["model"] == "zero_change"),
        key=lambda row: row["observation_date"],
    )
    by_key = {(row["model"], row["observation_date"]): row for row in ml_predictions}
    dates = [date.fromisoformat(row["observation_date"]) for row in zero]
    figure, axis = plt.subplots(figsize=(13, 6))
    axis.plot(
        dates,
        [_number(row, "actual_change_pp_h6") for row in zero],
        color="#202020",
        linewidth=2.4,
        label="Cambio observado",
    )
    axis.axhline(0.0, color="#777777", linestyle="--", linewidth=1.2, label="Cambio cero")
    colors = {
        "elastic_net": "#3465a4",
        "xgboost": "#cc0000",
        "random_forest": "#4e9a06",
    }
    for model_name, color in colors.items():
        axis.plot(
            dates,
            [
                _number(
                    by_key[(model_name, row["observation_date"])],
                    "predicted_change_pp_h6",
                )
                for row in zero
            ],
            linewidth=1.5,
            color=color,
            label=labels[model_name].replace(" (TreeSHAP)", ""),
        )
    axis.axvspan(date(2020, 3, 1), date(2021, 2, 1), color="#f4a460", alpha=0.15)
    axis.set_title("Pronósticos fuera de muestra, horizonte de seis meses")
    axis.set_ylabel("Cambio de morosidad (puntos porcentuales)")
    axis.grid(alpha=0.25)
    axis.legend(ncol=3, frameon=False)
    figure.tight_layout()
    figure.savefig(destination / "oos_predictions_timeline.png", dpi=180)
    plt.close(figure)
