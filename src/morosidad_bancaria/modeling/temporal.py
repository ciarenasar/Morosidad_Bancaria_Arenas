"""Particiones temporales expansivas con purga por disponibilidad del objetivo."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.modeling_base import add_months


class TemporalValidationError(RuntimeError):
    """Indica una partición temporal inválida o una fuga hacia el holdout."""


@dataclass(frozen=True)
class ValidationConfig:
    scheme: str
    minimum_training_months: int
    test_window_months: int
    step_months: int
    refit_frequency: str
    target_availability_purge: bool
    holdout_locked: bool


@dataclass(frozen=True)
class TemporalFold:
    fold_id: int
    test_start: str
    test_end: str
    observation_dates: tuple[str, ...]


def load_validation_config(path: Path) -> ValidationConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)["validation"]
        config = ValidationConfig(
            scheme=str(raw["scheme"]),
            minimum_training_months=int(raw["minimum_training_months"]),
            test_window_months=int(raw["test_window_months"]),
            step_months=int(raw["step_months"]),
            refit_frequency=str(raw["refit_frequency"]),
            target_availability_purge=bool(raw["target_availability_purge"]),
            holdout_locked=bool(raw["holdout_locked"]),
        )
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        raise TemporalValidationError(
            f"Configuración de validación inválida: {path.name}"
        ) from error
    if config.scheme != "expanding_window" or config.refit_frequency != "monthly":
        raise TemporalValidationError("El MVP requiere ventana expansiva y ajuste mensual")
    if min(
        config.minimum_training_months,
        config.test_window_months,
        config.step_months,
    ) <= 0:
        raise TemporalValidationError("Las ventanas temporales deben ser positivas")
    return config


def _is_complete(row: dict) -> bool:
    return str(row.get("complete_features", "")).casefold() in {"1", "true"}


def development_rows(
    rows: list[dict], target_column: str = "target_change_pp_h6"
) -> list[dict]:
    return sorted(
        (
            row
            for row in rows
            if row.get("split") == "development"
            and _is_complete(row)
            and row.get(target_column) not in (None, "")
        ),
        key=lambda row: row["observation_date"],
    )


def build_expanding_folds(
    rows: list[dict], config: ValidationConfig, target_column: str = "target_change_pp_h6"
) -> list[TemporalFold]:
    eligible = development_rows(rows, target_column)
    if len(eligible) <= config.minimum_training_months:
        raise TemporalValidationError(
            "No hay observaciones suficientes después del historial mínimo"
        )
    folds: list[TemporalFold] = []
    start = config.minimum_training_months
    fold_id = 1
    while start < len(eligible):
        test_rows = eligible[start : start + config.test_window_months]
        observation_dates = tuple(row["observation_date"] for row in test_rows)
        folds.append(
            TemporalFold(
                fold_id=fold_id,
                test_start=observation_dates[0],
                test_end=observation_dates[-1],
                observation_dates=observation_dates,
            )
        )
        fold_id += 1
        start += config.step_months
    return folds


def eligible_training_rows(
    rows: list[dict],
    test_row: dict,
    purge_target_availability: bool = True,
    target_column: str = "target_change_pp_h6",
    availability_column: str = "target_available_date_h6",
    rolling_window_months: int | None = None,
) -> tuple[list[dict], int]:
    """Devuelve solo etiquetas que se conocían en la emisión de la fila de prueba."""
    test_observation = date.fromisoformat(test_row["observation_date"])
    issue_date = date.fromisoformat(test_row["forecast_issue_date"])
    prior = [
        row
        for row in development_rows(rows, target_column)
        if date.fromisoformat(row["observation_date"]) < test_observation
    ]
    if rolling_window_months:
        cutoff = add_months(test_observation, -rolling_window_months)
        prior = [
            row
            for row in prior
            if date.fromisoformat(row["observation_date"]) >= cutoff
        ]
    if not purge_target_availability:
        return prior, 0
    eligible: list[dict] = []
    for row in prior:
        available = row.get(availability_column)
        if available and date.fromisoformat(available) <= issue_date:
            eligible.append(row)
    purged = len(prior) - len(eligible)
    return eligible, purged
