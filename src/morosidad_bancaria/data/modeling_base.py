"""Construcción point-in-time de la base mensual para modelamiento."""

from __future__ import annotations

import csv
import json
import tomllib
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.bcch_series import BcchObservation, BcchSeriesSpec


class ModelingBaseError(RuntimeError):
    """Indica una inconsistencia temporal o de cobertura en la base integrada."""


@dataclass(frozen=True)
class ModelingConfig:
    horizon_months: int
    development_end: date
    holdout_start: date
    holdout_end: date


@dataclass(frozen=True)
class ModelingCoverage:
    rows: int
    labeled_rows: int
    development_rows: int
    holdout_rows: int
    forecast_rows: int
    feature_count: int
    missing_feature_values: dict[str, int]
    availability_violations: int


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def load_modeling_config(path: Path) -> ModelingConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        return ModelingConfig(
            horizon_months=int(raw["target"]["horizon_months"]),
            development_end=date.fromisoformat(raw["split"]["development_end"]),
            holdout_start=date.fromisoformat(raw["split"]["holdout_start"]),
            holdout_end=date.fromisoformat(raw["split"]["holdout_end"]),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        raise ModelingBaseError(f"Configuración de modelamiento inválida: {path.name}") from error


def conservative_available_date(observation_date: date, spec: BcchSeriesSpec) -> date:
    availability_month = add_months(observation_date, spec.availability_month_offset)
    day = min(
        spec.availability_day,
        monthrange(availability_month.year, availability_month.month)[1],
    )
    return date(availability_month.year, availability_month.month, day)


def select_as_of(
    observations: list[BcchObservation],
    spec: BcchSeriesSpec,
    forecast_issue_date: date,
) -> tuple[BcchObservation, date] | None:
    eligible = [
        (item, conservative_available_date(item.observation_date, spec))
        for item in observations
        if item.value is not None
        and conservative_available_date(item.observation_date, spec) <= forecast_issue_date
    ]
    return max(eligible, key=lambda pair: pair[0].observation_date) if eligible else None


def load_target(path: Path) -> dict[date, float]:
    with path.open(encoding="utf-8", newline="") as file:
        return {
            date.fromisoformat(row["observation_date"]): float(
                row["npl90_consumption_percent"]
            )
            for row in csv.DictReader(file)
        }


def load_publication_calendar(path: Path) -> dict[date, date]:
    with path.open(encoding="utf-8", newline="") as file:
        return {
            date.fromisoformat(row["observation_date"]): date.fromisoformat(
                row["forecast_issue_date"]
            )
            for row in csv.DictReader(file)
        }


def build_modeling_rows(
    target: dict[date, float],
    publication_calendar: dict[date, date],
    specs: list[BcchSeriesSpec],
    features: dict[str, list[BcchObservation]],
    config: ModelingConfig,
) -> tuple[list[dict], ModelingCoverage]:
    missing_calendar = sorted(set(target) - set(publication_calendar))
    if missing_calendar:
        raise ModelingBaseError(
            f"Faltan {len(missing_calendar)} fechas de publicación para la serie objetivo"
        )
    rows: list[dict] = []
    missing = {spec.name: 0 for spec in specs}
    violations = 0

    for observation_date in sorted(target):
        issue_date = publication_calendar[observation_date]
        future_date = add_months(observation_date, config.horizon_months)
        future_value = target.get(future_date)
        future_available_date = publication_calendar.get(future_date)
        if future_value is None:
            split = "forecast"
        elif config.holdout_start <= observation_date <= config.holdout_end:
            split = "holdout"
        elif observation_date <= config.development_end:
            split = "development"
        else:
            raise ModelingBaseError(f"La fecha {observation_date} no pertenece a ningún split")

        row = {
            "observation_date": observation_date.isoformat(),
            "forecast_issue_date": issue_date.isoformat(),
            "split": split,
            "npl90_consumption_percent_t": target[observation_date],
            "target_date_h6": future_date.isoformat(),
            "target_available_date_h6": (
                future_available_date.isoformat() if future_available_date else None
            ),
            "target_npl90_percent_h6": future_value,
            "target_change_pp_h6": (
                None if future_value is None else future_value - target[observation_date]
            ),
        }
        for spec in specs:
            selected = select_as_of(features[spec.name], spec, issue_date)
            prefix = spec.name
            if selected is None:
                missing[spec.name] += 1
                row[prefix] = None
                row[f"{prefix}__observation_date"] = None
                row[f"{prefix}__available_date"] = None
                continue
            value, available_date = selected
            if available_date > issue_date:
                violations += 1
            row[prefix] = value.value
            row[f"{prefix}__observation_date"] = value.observation_date.isoformat()
            row[f"{prefix}__available_date"] = available_date.isoformat()
        rows.append(row)

    coverage = ModelingCoverage(
        rows=len(rows),
        labeled_rows=sum(row["target_change_pp_h6"] is not None for row in rows),
        development_rows=sum(row["split"] == "development" for row in rows),
        holdout_rows=sum(row["split"] == "holdout" for row in rows),
        forecast_rows=sum(row["split"] == "forecast" for row in rows),
        feature_count=len(specs),
        missing_feature_values=missing,
        availability_violations=violations,
    )
    return rows, coverage


def write_modeling_base(rows: list[dict], destination: Path) -> None:
    if not rows:
        raise ModelingBaseError("No hay filas para escribir")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def write_modeling_coverage(report: ModelingCoverage, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
