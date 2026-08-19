"""Construcción reproducible de variables a partir de la base point-in-time."""

from __future__ import annotations

import csv
import json
import math
import tomllib
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.modeling_base import add_months


class FeatureEngineeringError(RuntimeError):
    """Indica que la especificación o los insumos de variables son inválidos."""


@dataclass(frozen=True)
class MacroFeatureSpec:
    name: str
    source: str
    operation: str
    periods: int


@dataclass(frozen=True)
class FeatureConfig:
    name: str
    npl_lags: tuple[int, ...]
    npl_changes: tuple[int, ...]
    npl_rolling_means: tuple[int, ...]
    include_month_seasonality: bool
    macro_features: tuple[MacroFeatureSpec, ...]
    autoregressive_features: tuple[str, ...]


@dataclass(frozen=True)
class FeatureCoverage:
    rows: int
    feature_count: int
    complete_rows: int
    development_complete_rows: int
    holdout_complete_rows: int
    forecast_complete_rows: int
    first_complete_observation: str | None
    missing_by_feature: dict[str, int]


def load_feature_config(path: Path) -> FeatureConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        feature_set = raw["feature_set"]
        macro_features = tuple(MacroFeatureSpec(**item) for item in raw["macro_features"])
        config = FeatureConfig(
            name=str(feature_set["name"]),
            npl_lags=tuple(int(value) for value in feature_set["npl_lags"]),
            npl_changes=tuple(int(value) for value in feature_set["npl_changes"]),
            npl_rolling_means=tuple(
                int(value) for value in feature_set["npl_rolling_means"]
            ),
            include_month_seasonality=bool(feature_set["include_month_seasonality"]),
            macro_features=macro_features,
            autoregressive_features=tuple(raw["autoregressive_baseline"]["features"]),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise FeatureEngineeringError(
            f"Configuración de variables inválida: {path.name}"
        ) from error

    operations = {item.operation for item in config.macro_features}
    if not operations <= {"level", "difference", "pct_change"}:
        raise FeatureEngineeringError("La configuración contiene una transformación desconocida")
    names = [item.name for item in config.macro_features]
    if len(names) != len(set(names)):
        raise FeatureEngineeringError("La configuración contiene variables macro duplicadas")
    numeric_groups = (config.npl_lags, config.npl_changes, config.npl_rolling_means)
    if any(value <= 0 for group in numeric_groups for value in group):
        raise FeatureEngineeringError("Los rezagos y ventanas deben ser positivos")
    return config


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
    except FileNotFoundError as error:
        raise FeatureEngineeringError(f"No existe el insumo {path}") from error
    if not rows:
        raise FeatureEngineeringError(f"El insumo {path.name} no contiene filas")
    return rows


def load_macro_history(path: Path) -> dict[str, dict[date, float]]:
    histories: dict[str, dict[date, float]] = {}
    for row in load_csv_rows(path):
        if not row.get("value"):
            continue
        feature_name = row["feature_name"]
        observation_date = date.fromisoformat(row["observation_date"])
        history = histories.setdefault(feature_name, {})
        if observation_date in history:
            raise FeatureEngineeringError(
                f"La serie {feature_name} repite {observation_date.isoformat()}"
            )
        history[observation_date] = float(row["value"])
    return histories


def feature_names(config: FeatureConfig) -> list[str]:
    names = ["npl90_level_t"]
    names.extend(f"npl90_lag_{period}m" for period in config.npl_lags)
    names.extend(f"npl90_change_{period}m_pp" for period in config.npl_changes)
    names.extend(
        f"npl90_rolling_mean_{window}m" for window in config.npl_rolling_means
    )
    names.extend(item.name for item in config.macro_features)
    if config.include_month_seasonality:
        names.extend(["month_sin", "month_cos"])
    return names


def _macro_value(
    spec: MacroFeatureSpec,
    selected_date: date,
    histories: dict[str, dict[date, float]],
) -> float | None:
    history = histories.get(spec.source, {})
    current = history.get(selected_date)
    if current is None:
        return None
    if spec.operation == "level":
        return current
    previous = history.get(add_months(selected_date, -spec.periods))
    if previous is None:
        return None
    if spec.operation == "difference":
        return current - previous
    if previous == 0:
        return None
    return 100.0 * (current / previous - 1.0)


def build_feature_rows(
    base_rows: list[dict[str, str]],
    macro_history: dict[str, dict[date, float]],
    config: FeatureConfig,
) -> tuple[list[dict], FeatureCoverage]:
    """Crea variables usando solamente meses seleccionados en la base point-in-time."""
    ordered = sorted(base_rows, key=lambda row: row["observation_date"])
    target_history = {
        date.fromisoformat(row["observation_date"]): float(
            row["npl90_consumption_percent_t"]
        )
        for row in ordered
    }
    names = feature_names(config)
    result: list[dict] = []

    for base in ordered:
        observation_date = date.fromisoformat(base["observation_date"])
        current = target_history[observation_date]
        row: dict = dict(base)
        row["feature_set"] = config.name
        row["npl90_level_t"] = current

        for period in config.npl_lags:
            row[f"npl90_lag_{period}m"] = target_history.get(
                add_months(observation_date, -period)
            )
        for period in config.npl_changes:
            previous = target_history.get(add_months(observation_date, -period))
            row[f"npl90_change_{period}m_pp"] = (
                None if previous is None else current - previous
            )
        for window in config.npl_rolling_means:
            values = [
                target_history.get(add_months(observation_date, -period))
                for period in range(window)
            ]
            row[f"npl90_rolling_mean_{window}m"] = (
                None if any(value is None for value in values) else sum(values) / window
            )

        for spec in config.macro_features:
            selected = base.get(f"{spec.source}__observation_date", "")
            row[spec.name] = (
                None
                if not selected
                else _macro_value(spec, date.fromisoformat(selected), macro_history)
            )

        if config.include_month_seasonality:
            angle = 2.0 * math.pi * (observation_date.month - 1) / 12.0
            row["month_sin"] = math.sin(angle)
            row["month_cos"] = math.cos(angle)

        row["complete_features"] = int(all(row.get(name) is not None for name in names))
        result.append(row)

    missing = {name: sum(row.get(name) is None for row in result) for name in names}
    complete = [row for row in result if row["complete_features"]]
    coverage = FeatureCoverage(
        rows=len(result),
        feature_count=len(names),
        complete_rows=len(complete),
        development_complete_rows=sum(row["split"] == "development" for row in complete),
        holdout_complete_rows=sum(row["split"] == "holdout" for row in complete),
        forecast_complete_rows=sum(row["split"] == "forecast" for row in complete),
        first_complete_observation=(complete[0]["observation_date"] if complete else None),
        missing_by_feature=missing,
    )
    return result, coverage


def write_feature_rows(rows: list[dict], destination: Path) -> None:
    if not rows:
        raise FeatureEngineeringError("No hay filas de variables para escribir")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def write_feature_metadata(
    config: FeatureConfig,
    coverage: FeatureCoverage,
    specification_path: Path,
    coverage_path: Path,
) -> None:
    specification = {
        "feature_set": config.name,
        "feature_columns": feature_names(config),
        "autoregressive_features": list(config.autoregressive_features),
        "macro_features": [asdict(item) for item in config.macro_features],
        "point_in_time_rule": (
            "Cada transformación macro termina en el observation_date seleccionado "
            "por available_date en modeling_base.csv."
        ),
    }
    for path, payload in (
        (specification_path, specification),
        (coverage_path, asdict(coverage)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
