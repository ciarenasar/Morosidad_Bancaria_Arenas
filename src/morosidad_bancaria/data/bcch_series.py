"""Registro, normalización y auditoría de series mensuales del Banco Central."""

from __future__ import annotations

import csv
import math
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from morosidad_bancaria.data.bcch import BcchApiError, _load_json_bytes


@dataclass(frozen=True)
class BcchSeriesSpec:
    name: str
    series_id: str
    role: str
    transformation: str
    availability_month_offset: int
    availability_day: int
    availability_quality: str


@dataclass(frozen=True)
class BcchObservation:
    observation_date: date
    feature_name: str
    series_id: str
    value: float | None
    status_code: str
    source_file: str


@dataclass(frozen=True)
class BcchCoverage:
    feature_name: str
    series_id: str
    role: str
    first_observation: str
    last_observation: str
    observations: int
    valid_observations: int
    target_period_observations: int
    missing_target_months: int
    availability_quality: str


def load_series_specs(path: Path) -> list[BcchSeriesSpec]:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
        specs = [BcchSeriesSpec(**item) for item in raw["series"]]
    except (FileNotFoundError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise BcchApiError(f"Registro de series inválido: {path.name}") from error
    names = [item.name for item in specs]
    series_ids = [item.series_id for item in specs]
    if len(names) != len(set(names)) or len(series_ids) != len(set(series_ids)):
        raise BcchApiError("El registro BCCh contiene nombres o códigos duplicados")
    return specs


def _parse_date(value: str) -> date:
    try:
        day, month, year = (int(part) for part in value.split("-"))
        return date(year, month, day)
    except (AttributeError, TypeError, ValueError) as error:
        raise BcchApiError(f"Fecha BCCh inválida: {value!r}") from error


def _parse_value(value) -> float | None:
    if value in (None, "", "NaN", "nan"):
        return None
    try:
        parsed = float(str(value).replace(",", "."))
    except ValueError as error:
        raise BcchApiError("La serie BCCh contiene un valor no numérico") from error
    return parsed if math.isfinite(parsed) else None


def parse_series_file(path: Path, spec: BcchSeriesSpec) -> list[BcchObservation]:
    try:
        payload = _load_json_bytes(path.read_bytes())
        series = payload["Series"]
        if series["seriesId"] != spec.series_id:
            raise BcchApiError(f"El código de {path.name} no coincide con el registro")
        values = series["Obs"]
    except (FileNotFoundError, KeyError, TypeError) as error:
        raise BcchApiError(f"Respuesta de serie inválida: {path.name}") from error
    observations = [
        BcchObservation(
            observation_date=_parse_date(item["indexDateString"]),
            feature_name=spec.name,
            series_id=spec.series_id,
            value=_parse_value(item.get("value")),
            status_code=str(item.get("statusCode", "")),
            source_file=path.name,
        )
        for item in values
    ]
    dates = [item.observation_date for item in observations]
    if len(dates) != len(set(dates)):
        raise BcchApiError(f"La serie {spec.name} contiene fechas duplicadas")
    return sorted(observations, key=lambda item: item.observation_date)


def _month_sequence(start: date, end: date):
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        yield cursor
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)


def audit_series(
    specs: list[BcchSeriesSpec],
    observations: dict[str, list[BcchObservation]],
    target_start: date,
    target_end: date,
) -> list[BcchCoverage]:
    expected = set(_month_sequence(target_start, target_end))
    reports: list[BcchCoverage] = []
    for spec in specs:
        values = observations[spec.name]
        if not values:
            raise BcchApiError(f"La serie {spec.name} no tiene observaciones")
        valid_dates = {item.observation_date for item in values if item.value is not None}
        target_valid = valid_dates & expected
        reports.append(
            BcchCoverage(
                feature_name=spec.name,
                series_id=spec.series_id,
                role=spec.role,
                first_observation=values[0].observation_date.isoformat(),
                last_observation=values[-1].observation_date.isoformat(),
                observations=len(values),
                valid_observations=sum(item.value is not None for item in values),
                target_period_observations=len(target_valid),
                missing_target_months=len(expected - target_valid),
                availability_quality=spec.availability_quality,
            )
        )
    return reports


def write_observations(
    observations: dict[str, list[BcchObservation]], destination: Path
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "observation_date",
                "feature_name",
                "series_id",
                "value",
                "status_code",
                "source_file",
            ],
        )
        writer.writeheader()
        for feature_name in sorted(observations):
            for item in observations[feature_name]:
                writer.writerow(
                    {
                        "observation_date": item.observation_date.isoformat(),
                        "feature_name": item.feature_name,
                        "series_id": item.series_id,
                        "value": "" if item.value is None else format(item.value, ".15g"),
                        "status_code": item.status_code,
                        "source_file": item.source_file,
                    }
                )
    temporary.replace(destination)


def write_coverage(reports: list[BcchCoverage], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(BcchCoverage.__dataclass_fields__))
        writer.writeheader()
        for report in reports:
            writer.writerow(report.__dict__)
    temporary.replace(destination)
