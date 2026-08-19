"""Robustez por horizonte y tamaño de ventana para campeón y challenger."""

from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.modeling_base import add_months
from morosidad_bancaria.modeling.features import FeatureConfig, feature_names
from morosidad_bancaria.modeling.metrics import regression_metrics
from morosidad_bancaria.modeling.ml_backtest import (
    MlConfig,
    fit_predict,
    select_parameters,
)
from morosidad_bancaria.modeling.robustness import moving_block_means, percentile
from morosidad_bancaria.modeling.temporal import (
    TemporalFold,
    ValidationConfig,
    build_expanding_folds,
    eligible_training_rows,
)


class HorizonRobustnessError(RuntimeError):
    """Indica una fuga o inconsistencia en la robustez de horizontes."""


@dataclass(frozen=True)
class HorizonRobustnessConfig:
    horizons_months: tuple[int, ...]
    training_schemes: tuple[str, ...]
    rolling_training_months: int
    bootstrap_replications: int
    bootstrap_random_seed: int
    challenger_model: str


@dataclass(frozen=True)
class HorizonRobustnessSummary:
    scenarios: int
    horizons: int
    training_schemes: int
    evaluation_origins_per_scenario: int
    prediction_rows: int
    tuning_candidates_evaluated: int
    inner_predictions_evaluated: int
    evaluated_splits: tuple[str, ...]


def load_horizon_robustness_config(path: Path) -> HorizonRobustnessConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)["horizon_robustness"]
        config = HorizonRobustnessConfig(
            horizons_months=tuple(int(value) for value in raw["horizons_months"]),
            training_schemes=tuple(raw["training_schemes"]),
            rolling_training_months=int(raw["rolling_training_months"]),
            bootstrap_replications=int(raw["bootstrap_replications"]),
            bootstrap_random_seed=int(raw["bootstrap_random_seed"]),
            challenger_model=str(raw["challenger_model"]),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise HorizonRobustnessError(
            f"Configuración de horizontes inválida: {path.name}"
        ) from error
    if config.horizons_months != (3, 6, 12):
        raise HorizonRobustnessError("El protocolo requiere horizontes 3, 6 y 12")
    if set(config.training_schemes) != {"expanding", "rolling"}:
        raise HorizonRobustnessError("El protocolo requiere ventanas expansiva y móvil")
    if config.challenger_model != "elastic_net":
        raise HorizonRobustnessError("El challenger congelado debe ser ElasticNet")
    if config.rolling_training_months <= 0 or config.bootstrap_replications < 1000:
        raise HorizonRobustnessError("Los tamaños de robustez son inválidos")
    return config


def add_horizon_targets(
    rows: list[dict], publication_calendar: dict[date, date], horizons: tuple[int, ...]
) -> list[dict]:
    target = {
        date.fromisoformat(row["observation_date"]): float(
            row["npl90_consumption_percent_t"]
        )
        for row in rows
    }
    result: list[dict] = []
    for source in rows:
        row = dict(source)
        observation = date.fromisoformat(row["observation_date"])
        current = target[observation]
        for horizon in horizons:
            future_date = add_months(observation, horizon)
            future_value = target.get(future_date)
            available = publication_calendar.get(future_date)
            if future_value is not None and available is None:
                raise HorizonRobustnessError(
                    f"Falta fecha de publicación para {future_date.isoformat()}"
                )
            row[f"target_date_h{horizon}"] = future_date.isoformat()
            row[f"target_available_date_h{horizon}"] = (
                None if available is None else available.isoformat()
            )
            row[f"target_npl90_percent_h{horizon}"] = future_value
            row[f"target_change_pp_h{horizon}"] = (
                None if future_value is None else future_value - current
            )
        result.append(row)
    return result


def _number(row: dict, column: str) -> float:
    value = row.get(column)
    if value in (None, ""):
        raise HorizonRobustnessError(f"La columna {column} contiene un valor faltante")
    return float(value)


def _training_rows(
    rows: list[dict],
    test_row: dict,
    target_column: str,
    availability_column: str,
    rolling_window_months: int | None,
) -> tuple[list[dict], int, int]:
    uncapped, purged = eligible_training_rows(
        rows,
        test_row,
        True,
        target_column,
        availability_column,
        None,
    )
    if rolling_window_months:
        training, purged = eligible_training_rows(
            rows,
            test_row,
            True,
            target_column,
            availability_column,
            rolling_window_months,
        )
    else:
        training = uncapped
    return training, purged, len(uncapped) - len(training)


def run_horizon_robustness(
    matrix_rows: list[dict],
    publication_calendar: dict[date, date],
    feature_config: FeatureConfig,
    validation_config: ValidationConfig,
    ml_config: MlConfig,
    config: HorizonRobustnessConfig,
) -> tuple[list[dict], list[dict], dict[str, list[TemporalFold]], HorizonRobustnessSummary]:
    if not validation_config.holdout_locked or not validation_config.target_availability_purge:
        raise HorizonRobustnessError("El protocolo exige holdout cerrado y purga activa")
    rows = add_horizon_targets(matrix_rows, publication_calendar, config.horizons_months)
    by_date = {row["observation_date"]: row for row in rows}
    features = feature_names(feature_config)
    predictions: list[dict] = []
    tuning: list[dict] = []
    folds_by_scenario: dict[str, list[TemporalFold]] = {}
    inner_predictions = 0
    reference_origins: tuple[str, ...] | None = None

    for horizon in config.horizons_months:
        target_column = f"target_change_pp_h{horizon}"
        availability_column = f"target_available_date_h{horizon}"
        target_date_column = f"target_date_h{horizon}"
        folds = build_expanding_folds(rows, validation_config, target_column)
        origins = tuple(value for fold in folds for value in fold.observation_dates)
        if reference_origins is None:
            reference_origins = origins
        elif origins != reference_origins:
            raise HorizonRobustnessError("Los horizontes no comparten los mismos orígenes")

        for scheme in config.training_schemes:
            scenario = f"h{horizon}_{scheme}"
            folds_by_scenario[scenario] = folds
            maximum = config.rolling_training_months if scheme == "rolling" else None
            for fold in folds:
                first_test = by_date[fold.observation_dates[0]]
                outer_training, _, _ = _training_rows(
                    rows,
                    first_test,
                    target_column,
                    availability_column,
                    maximum,
                )
                parameters, inner_mae, records = select_parameters(
                    config.challenger_model,
                    rows,
                    outer_training,
                    features,
                    ml_config,
                    fold,
                    target_column=target_column,
                    availability_column=availability_column,
                    rolling_window_months=maximum,
                )
                for record in records:
                    tuning.append(
                        {
                            **record,
                            "scenario": scenario,
                            "horizon_months": horizon,
                            "training_scheme": scheme,
                        }
                    )
                    inner_predictions += int(record["inner_validation_origins"])

                for observation_date in fold.observation_dates:
                    test_row = by_date[observation_date]
                    if test_row.get("split") != "development":
                        raise HorizonRobustnessError("La robustez intentó usar el holdout")
                    training, purged, window_dropped = _training_rows(
                        rows,
                        test_row,
                        target_column,
                        availability_column,
                        maximum,
                    )
                    actual = _number(test_row, target_column)
                    elastic_prediction = fit_predict(
                        config.challenger_model,
                        parameters,
                        training,
                        test_row,
                        features,
                        ml_config.random_seed,
                        target_column,
                    )
                    common = {
                        "scenario": scenario,
                        "horizon_months": horizon,
                        "training_scheme": scheme,
                        "fold_id": fold.fold_id,
                        "observation_date": observation_date,
                        "forecast_issue_date": test_row["forecast_issue_date"],
                        "target_date": test_row[target_date_column],
                        "actual_change_pp": actual,
                        "training_rows": len(training),
                        "purged_rows": purged,
                        "rolling_window_dropped_rows": window_dropped,
                        "evaluated_split": "development",
                    }
                    predictions.extend(
                        [
                            {
                                **common,
                                "model": "zero_change",
                                "predicted_change_pp": 0.0,
                                "error_pp": -actual,
                                "selected_parameters": None,
                                "inner_selection_mae": None,
                            },
                            {
                                **common,
                                "model": config.challenger_model,
                                "predicted_change_pp": elastic_prediction,
                                "error_pp": elastic_prediction - actual,
                                "selected_parameters": json.dumps(
                                    parameters, sort_keys=True, separators=(",", ":")
                                ),
                                "inner_selection_mae": inner_mae,
                            },
                        ]
                    )

    summary = HorizonRobustnessSummary(
        scenarios=len(folds_by_scenario),
        horizons=len(config.horizons_months),
        training_schemes=len(config.training_schemes),
        evaluation_origins_per_scenario=len(reference_origins or ()),
        prediction_rows=len(predictions),
        tuning_candidates_evaluated=len(tuning),
        inner_predictions_evaluated=inner_predictions,
        evaluated_splits=("development",),
    )
    return predictions, tuning, folds_by_scenario, summary


def summarize_horizon_metrics(predictions: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in predictions:
        groups.setdefault((row["scenario"], str(row["fold_id"]), row["model"]), []).append(
            row
        )
        groups.setdefault((row["scenario"], "all", row["model"]), []).append(row)
    result: list[dict] = []
    for (scenario, fold_id, model), rows in sorted(groups.items()):
        result.append(
            {
                "scenario": scenario,
                "horizon_months": rows[0]["horizon_months"],
                "training_scheme": rows[0]["training_scheme"],
                "fold_id": fold_id,
                "model": model,
                **regression_metrics(
                    [float(row["actual_change_pp"]) for row in rows],
                    [float(row["predicted_change_pp"]) for row in rows],
                ),
            }
        )
    zero_mae = {
        (row["scenario"], row["fold_id"]): float(row["mae"])
        for row in result
        if row["model"] == "zero_change"
    }
    for row in result:
        baseline = zero_mae[(row["scenario"], row["fold_id"])]
        row["mae_improvement_vs_zero_pct"] = (
            None if baseline == 0 else 100.0 * (baseline - float(row["mae"])) / baseline
        )
    return result


def horizon_bootstrap(
    predictions: list[dict], config: HorizonRobustnessConfig
) -> list[dict]:
    scenarios = sorted({row["scenario"] for row in predictions})
    result: list[dict] = []
    for scenario_index, scenario in enumerate(scenarios):
        rows = [row for row in predictions if row["scenario"] == scenario]
        zero = {
            row["observation_date"]: row for row in rows if row["model"] == "zero_change"
        }
        challenger = sorted(
            (row for row in rows if row["model"] == config.challenger_model),
            key=lambda row: row["observation_date"],
        )
        differences = [
            abs(float(row["error_pp"]))
            - abs(float(zero[row["observation_date"]]["error_pp"]))
            for row in challenger
        ]
        horizon = int(challenger[0]["horizon_months"])
        means = moving_block_means(
            differences,
            horizon,
            config.bootstrap_replications,
            config.bootstrap_random_seed + scenario_index,
        )
        lower = percentile(means, 0.025)
        upper = percentile(means, 0.975)
        conclusion = "inconclusive"
        if upper < 0:
            conclusion = "better_than_zero"
        elif lower > 0:
            conclusion = "worse_than_zero"
        result.append(
            {
                "scenario": scenario,
                "horizon_months": horizon,
                "training_scheme": challenger[0]["training_scheme"],
                "n": len(differences),
                "mae_difference_vs_zero_pp": sum(differences) / len(differences),
                "loss_difference_ci95_lower_pp": lower,
                "loss_difference_ci95_upper_pp": upper,
                "bootstrap_probability_better_than_zero": sum(value < 0 for value in means)
                / len(means),
                "paired_month_win_rate": sum(value < 0 for value in differences)
                / len(differences),
                "block_length_months": horizon,
                "bootstrap_replications": config.bootstrap_replications,
                "ci_conclusion": conclusion,
            }
        )
    return result


def window_bootstrap(
    predictions: list[dict], config: HorizonRobustnessConfig
) -> list[dict]:
    result: list[dict] = []
    for horizon_index, horizon in enumerate(config.horizons_months):
        expanding = {
            row["observation_date"]: row
            for row in predictions
            if row["scenario"] == f"h{horizon}_expanding"
            and row["model"] == config.challenger_model
        }
        rolling = {
            row["observation_date"]: row
            for row in predictions
            if row["scenario"] == f"h{horizon}_rolling"
            and row["model"] == config.challenger_model
        }
        if expanding.keys() != rolling.keys():
            raise HorizonRobustnessError("Las ventanas no comparten los mismos orígenes")
        dates = sorted(expanding)
        differences = [
            abs(float(rolling[item]["error_pp"]))
            - abs(float(expanding[item]["error_pp"]))
            for item in dates
        ]
        means = moving_block_means(
            differences,
            horizon,
            config.bootstrap_replications,
            config.bootstrap_random_seed + 100 + horizon_index,
        )
        lower = percentile(means, 0.025)
        upper = percentile(means, 0.975)
        conclusion = "inconclusive"
        if upper < 0:
            conclusion = "rolling_better"
        elif lower > 0:
            conclusion = "expanding_better"
        result.append(
            {
                "horizon_months": horizon,
                "n": len(dates),
                "mae_difference_rolling_minus_expanding_pp": sum(differences)
                / len(differences),
                "loss_difference_ci95_lower_pp": lower,
                "loss_difference_ci95_upper_pp": upper,
                "bootstrap_probability_rolling_better": sum(value < 0 for value in means)
                / len(means),
                "rolling_month_win_rate": sum(value < 0 for value in differences)
                / len(differences),
                "block_length_months": horizon,
                "bootstrap_replications": config.bootstrap_replications,
                "ci_conclusion": conclusion,
            }
        )
    return result


def write_horizon_metadata(
    config: HorizonRobustnessConfig,
    folds: dict[str, list[TemporalFold]],
    summary: HorizonRobustnessSummary,
    destination: Path,
) -> None:
    payload = {
        "summary": asdict(summary),
        "configuration": asdict(config),
        "folds": {
            scenario: [asdict(fold) for fold in values]
            for scenario, values in folds.items()
        },
        "bootstrap": "circular moving blocks with block length equal to horizon",
        "holdout_policy": "No se seleccionó, ajustó ni evaluó sobre el holdout.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def write_horizon_figure(metrics: list[dict], destination: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise HorizonRobustnessError("Matplotlib no está instalado") from error
    aggregate = [row for row in metrics if row["fold_id"] == "all"]
    scenarios = sorted(
        {row["scenario"] for row in aggregate},
        key=lambda value: (int(value.split("_")[0][1:]), value.split("_")[1]),
    )
    zero = {
        row["scenario"]: float(row["mae"])
        for row in aggregate
        if row["model"] == "zero_change"
    }
    elastic = {
        row["scenario"]: float(row["mae"])
        for row in aggregate
        if row["model"] == "elastic_net"
    }
    labels = [value.replace("expanding", "exp.").replace("rolling", "móvil") for value in scenarios]
    positions = list(range(len(scenarios)))
    figure, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    width = 0.38
    axes[0].bar(
        [value - width / 2 for value in positions],
        [zero[value] for value in scenarios],
        width,
        label="Cambio cero",
        color="#777777",
    )
    axes[0].bar(
        [value + width / 2 for value in positions],
        [elastic[value] for value in scenarios],
        width,
        label="ElasticNet",
        color="#3465a4",
    )
    axes[0].set_xticks(positions, labels, rotation=25, ha="right")
    axes[0].set_ylabel("MAE (puntos porcentuales)")
    axes[0].set_title("Error por escenario")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.25)

    improvement = [100.0 * (zero[value] - elastic[value]) / zero[value] for value in scenarios]
    axes[1].bar(
        positions,
        improvement,
        color=["#4e9a06" if value > 0 else "#cc0000" for value in improvement],
    )
    axes[1].axhline(0.0, color="#333333", linewidth=1.0)
    axes[1].set_xticks(positions, labels, rotation=25, ha="right")
    axes[1].set_ylabel("Mejora MAE frente a cambio cero (%)")
    axes[1].set_title("Aporte del challenger")
    axes[1].grid(axis="y", alpha=0.25)
    figure.suptitle("Robustez por horizonte y ventana de entrenamiento")
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, dpi=180)
    plt.close(figure)
