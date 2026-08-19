"""Comparación parsimoniosa e incertidumbre con bloques para el horizonte h=6."""

from __future__ import annotations

import json
import math
import random
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.modeling.features import FeatureConfig, feature_names
from morosidad_bancaria.modeling.ml_backtest import (
    MlConfig,
    fit_predict,
    select_parameters,
)
from morosidad_bancaria.modeling.temporal import (
    TemporalFold,
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class RobustnessError(RuntimeError):
    """Indica una especificación parsimoniosa o comparación inválida."""


@dataclass(frozen=True)
class FeatureSetSpec:
    name: str
    features: tuple[str, ...]


@dataclass(frozen=True)
class RobustnessConfig:
    block_length_months: int
    replications: int
    random_seed: int
    pandemic_period_end: date
    feature_sets: tuple[FeatureSetSpec, ...]


@dataclass(frozen=True)
class ParsimoniousSummary:
    folds: int
    evaluation_origins: int
    feature_sets: int
    prediction_rows: int
    tuning_candidates_evaluated: int
    inner_predictions_evaluated: int
    evaluated_splits: tuple[str, ...]


def load_robustness_config(path: Path) -> RobustnessConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        bootstrap = raw["bootstrap"]
        feature_sets = tuple(
            FeatureSetSpec(str(item["name"]), tuple(item["features"]))
            for item in raw["feature_sets"]
        )
        config = RobustnessConfig(
            block_length_months=int(bootstrap["block_length_months"]),
            replications=int(bootstrap["replications"]),
            random_seed=int(bootstrap["random_seed"]),
            pandemic_period_end=date.fromisoformat(bootstrap["pandemic_period_end"]),
            feature_sets=feature_sets,
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise RobustnessError(f"Configuración de robustez inválida: {path.name}") from error
    names = [item.name for item in config.feature_sets]
    if len(names) != len(set(names)) or any(not item.features for item in feature_sets):
        raise RobustnessError("Los feature sets deben ser únicos y no vacíos")
    if config.block_length_months <= 0 or config.replications < 1000:
        raise RobustnessError("El bootstrap requiere bloques positivos y al menos 1.000 réplicas")
    return config


def validate_feature_sets(config: RobustnessConfig, feature_config: FeatureConfig) -> None:
    available = set(feature_names(feature_config))
    for specification in config.feature_sets:
        unknown = set(specification.features) - available
        if unknown:
            raise RobustnessError(
                f"{specification.name} contiene variables desconocidas: {sorted(unknown)}"
            )
        if len(specification.features) != len(set(specification.features)):
            raise RobustnessError(f"{specification.name} contiene variables repetidas")


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise RobustnessError(f"La columna {column} contiene un valor faltante")
    return float(value)


def run_parsimonious_backtest(
    rows: list[dict],
    feature_config: FeatureConfig,
    validation_config: ValidationConfig,
    ml_config: MlConfig,
    robustness_config: RobustnessConfig,
) -> tuple[list[dict], list[dict], list[TemporalFold], ParsimoniousSummary]:
    validate_feature_sets(robustness_config, feature_config)
    if not validation_config.holdout_locked:
        raise RobustnessError("El MVP exige mantener bloqueado el holdout")
    if not validation_config.target_availability_purge:
        raise RobustnessError("El MVP exige purgar etiquetas todavía no publicadas")
    folds = build_expanding_folds(rows, validation_config)
    by_date = {row["observation_date"]: row for row in rows}
    predictions: list[dict] = []
    tuning: list[dict] = []
    inner_predictions = 0

    for fold in folds:
        first_test = by_date[fold.observation_dates[0]]
        outer_training, _ = eligible_training_rows(rows, first_test, True)
        selected: dict[str, tuple[dict, float]] = {}
        for specification in robustness_config.feature_sets:
            parameters, inner_mae, records = select_parameters(
                "elastic_net",
                rows,
                outer_training,
                list(specification.features),
                ml_config,
                fold,
            )
            model_name = f"elastic_net_{specification.name}"
            selected[specification.name] = (parameters, inner_mae)
            for record in records:
                tuning.append(
                    {
                        **record,
                        "model": model_name,
                        "feature_set": specification.name,
                        "feature_count": len(specification.features),
                    }
                )
                inner_predictions += int(record["inner_validation_origins"])

        for observation_date in fold.observation_dates:
            test_row = by_date[observation_date]
            if test_row.get("split") != "development":
                raise RobustnessError("La comparación parsimoniosa intentó usar el holdout")
            training, purged = eligible_training_rows(rows, test_row, True)
            actual = _number(test_row, "target_change_pp_h6")
            for specification in robustness_config.feature_sets:
                parameters, inner_mae = selected[specification.name]
                prediction = fit_predict(
                    "elastic_net",
                    parameters,
                    training,
                    test_row,
                    list(specification.features),
                    ml_config.random_seed,
                )
                predictions.append(
                    {
                        "fold_id": fold.fold_id,
                        "observation_date": observation_date,
                        "forecast_issue_date": test_row["forecast_issue_date"],
                        "target_date_h6": test_row["target_date_h6"],
                        "model": f"elastic_net_{specification.name}",
                        "feature_set": specification.name,
                        "feature_count": len(specification.features),
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
    summary = ParsimoniousSummary(
        folds=len(folds),
        evaluation_origins=len(origins),
        feature_sets=len(robustness_config.feature_sets),
        prediction_rows=len(predictions),
        tuning_candidates_evaluated=len(tuning),
        inner_predictions_evaluated=inner_predictions,
        evaluated_splits=("development",),
    )
    return predictions, tuning, folds, summary


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def moving_block_means(
    values: list[float], block_length: int, replications: int, seed: int
) -> list[float]:
    if not values:
        raise RobustnessError("El bootstrap no recibió diferencias de pérdida")
    generator = random.Random(seed)
    sample_size = len(values)
    blocks = math.ceil(sample_size / block_length)
    means: list[float] = []
    for _ in range(replications):
        sample: list[float] = []
        for _ in range(blocks):
            start = generator.randrange(sample_size)
            sample.extend(
                values[(start + offset) % sample_size]
                for offset in range(block_length)
            )
        means.append(sum(sample[:sample_size]) / sample_size)
    return means


def stability_against_zero(
    predictions: list[dict], config: RobustnessConfig
) -> list[dict]:
    by_model: dict[str, list[dict]] = {}
    for row in predictions:
        by_model.setdefault(row["model"], []).append(row)
    if "zero_change" not in by_model:
        raise RobustnessError("La comparación requiere el benchmark de cambio cero")
    zero_rows = sorted(by_model["zero_change"], key=lambda row: row["observation_date"])
    zero_by_date = {row["observation_date"]: row for row in zero_rows}
    if len(zero_by_date) != len(zero_rows):
        raise RobustnessError("El benchmark de cambio cero repite orígenes")
    expected_dates = set(zero_by_date)
    zero_mae = sum(abs(_number(row, "error_pp")) for row in zero_rows) / len(zero_rows)
    results: list[dict] = []

    model_names = sorted(set(by_model) - {"zero_change"})
    for model_index, model_name in enumerate(model_names):
        rows = sorted(by_model[model_name], key=lambda row: row["observation_date"])
        if len(rows) != len(expected_dates) or {
            row["observation_date"] for row in rows
        } != expected_dates:
            raise RobustnessError(f"{model_name} no comparte todos los orígenes")
        loss_differences = [
            abs(_number(row, "error_pp"))
            - abs(_number(zero_by_date[row["observation_date"]], "error_pp"))
            for row in rows
        ]
        bootstrap_means = moving_block_means(
            loss_differences,
            config.block_length_months,
            config.replications,
            config.random_seed + model_index,
        )
        absolute_errors = [abs(_number(row, "error_pp")) for row in rows]
        errors = [_number(row, "error_pp") for row in rows]
        ex_pandemic = [
            row
            for row in rows
            if date.fromisoformat(row["observation_date"])
            > config.pandemic_period_end
        ]
        ex_pandemic_zero = [
            zero_by_date[row["observation_date"]] for row in ex_pandemic
        ]
        if not ex_pandemic:
            raise RobustnessError("No hay observaciones fuera del período pandémico")
        ex_model_mae = sum(abs(_number(row, "error_pp")) for row in ex_pandemic) / len(
            ex_pandemic
        )
        ex_zero_mae = sum(
            abs(_number(row, "error_pp")) for row in ex_pandemic_zero
        ) / len(ex_pandemic_zero)
        lower = percentile(bootstrap_means, 0.025)
        upper = percentile(bootstrap_means, 0.975)
        conclusion = "inconclusive"
        if upper < 0:
            conclusion = "better_than_zero"
        elif lower > 0:
            conclusion = "worse_than_zero"
        results.append(
            {
                "model": model_name,
                "n": len(rows),
                "mae": sum(absolute_errors) / len(absolute_errors),
                "mae_difference_vs_zero_pp": sum(loss_differences) / len(loss_differences),
                "mae_improvement_vs_zero_pct": (
                    100.0
                    * (zero_mae - sum(absolute_errors) / len(absolute_errors))
                    / zero_mae
                ),
                "loss_difference_ci95_lower_pp": lower,
                "loss_difference_ci95_upper_pp": upper,
                "bootstrap_probability_better_than_zero": sum(
                    value < 0 for value in bootstrap_means
                )
                / len(bootstrap_means),
                "paired_month_win_rate": sum(value < 0 for value in loss_differences)
                / len(loss_differences),
                "mean_error_bias_pp": sum(errors) / len(errors),
                "p90_absolute_error_pp": percentile(absolute_errors, 0.9),
                "maximum_absolute_error_pp": max(absolute_errors),
                "ex_pandemic_n": len(ex_pandemic),
                "ex_pandemic_mae": ex_model_mae,
                "ex_pandemic_mae_difference_vs_zero_pp": ex_model_mae - ex_zero_mae,
                "block_length_months": config.block_length_months,
                "bootstrap_replications": config.replications,
                "ci_conclusion": conclusion,
            }
        )
    return results


def write_robustness_metadata(
    config: RobustnessConfig,
    folds: list[TemporalFold],
    summary: ParsimoniousSummary,
    destination: Path,
) -> None:
    payload = {
        "summary": asdict(summary),
        "feature_sets": [asdict(item) for item in config.feature_sets],
        "bootstrap": {
            "method": "circular_moving_block_bootstrap",
            "loss": "absolute_error_difference_model_minus_zero",
            "block_length_months": config.block_length_months,
            "replications": config.replications,
            "random_seed": config.random_seed,
        },
        "pandemic_period_end": config.pandemic_period_end.isoformat(),
        "folds": [asdict(fold) for fold in folds],
        "holdout_policy": "No se seleccionó, ajustó ni evaluó sobre el holdout.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
