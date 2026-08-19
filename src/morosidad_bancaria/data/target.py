"""Extracción y auditoría de la serie objetivo desde respuestas crudas de CMF."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any


class TargetDataError(RuntimeError):
    """Indica estructura inesperada o datos contradictorios en archivos crudos."""


@dataclass(frozen=True)
class TargetObservation:
    observation_date: date
    value_percent: float
    source_file: str


@dataclass(frozen=True)
class CoverageReport:
    chart_tag: str
    target_series_code: str
    first_observation: str
    last_observation: str
    observation_count: int
    expected_month_count: int
    missing_months: list[str]
    source_file_count: int
    duplicate_series_entries_collapsed: int


def _parse_api_date(value: Any) -> date:
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise TargetDataError(f"Fecha CMF inválida: {text!r}")
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as error:
        raise TargetDataError(f"Fecha CMF inválida: {text!r}") from error


def _month_sequence(start: date, end: date):
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cursor <= last:
        yield cursor
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)


def extract_target(
    raw_files: list[Path], chart_tag: str, target_series_code: str
) -> tuple[list[TargetObservation], CoverageReport]:
    observations: dict[date, TargetObservation] = {}
    duplicate_entries = 0

    for path in sorted(raw_files):
        try:
            payload = json.loads(path.read_bytes())
            payload_tag = payload["cuadroInfo"]["tag"]
            series = payload["series"]
        except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as error:
            raise TargetDataError(f"Estructura CMF inválida en {path.name}") from error
        if payload_tag != chart_tag:
            raise TargetDataError(f"El cuadro de {path.name} no coincide con el configurado")

        matches = [
            item
            for item in series
            if item.get("serieInfo", {}).get("cod_serie") == target_series_code
        ]
        if not matches:
            raise TargetDataError(f"No se encontró la serie objetivo en {path.name}")

        canonical_values = matches[0].get("valores")
        for duplicate in matches[1:]:
            if duplicate.get("valores") != canonical_values:
                raise TargetDataError(
                    f"Series objetivo duplicadas y contradictorias en {path.name}"
                )
            duplicate_entries += 1

        if not isinstance(canonical_values, list):
            raise TargetDataError(
                f"La serie objetivo no contiene una lista de valores en {path.name}"
            )
        for item in canonical_values:
            try:
                observation_date = _parse_api_date(item["fecha"])
                value = float(item["valor"])
            except (KeyError, TypeError, ValueError) as error:
                raise TargetDataError(f"Observación inválida en {path.name}") from error
            candidate = TargetObservation(observation_date, value, path.name)
            existing = observations.get(observation_date)
            if existing and existing.value_percent != value:
                raise TargetDataError(
                    f"Valores contradictorios para {observation_date.isoformat()}"
                )
            observations.setdefault(observation_date, candidate)

    ordered = [observations[key] for key in sorted(observations)]
    if not ordered:
        raise TargetDataError("No hay observaciones de la serie objetivo")

    expected = list(_month_sequence(ordered[0].observation_date, ordered[-1].observation_date))
    observed_months = {
        date(item.observation_date.year, item.observation_date.month, 1) for item in ordered
    }
    missing = [month.isoformat() for month in expected if month not in observed_months]
    report = CoverageReport(
        chart_tag=chart_tag,
        target_series_code=target_series_code,
        first_observation=ordered[0].observation_date.isoformat(),
        last_observation=ordered[-1].observation_date.isoformat(),
        observation_count=len(ordered),
        expected_month_count=len(expected),
        missing_months=missing,
        source_file_count=len(raw_files),
        duplicate_series_entries_collapsed=duplicate_entries,
    )
    return ordered, report


def write_target_csv(observations: list[TargetObservation], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["observation_date", "npl90_consumption_percent", "source_file"],
        )
        writer.writeheader()
        for observation in observations:
            writer.writerow(
                {
                    "observation_date": observation.observation_date.isoformat(),
                    "npl90_consumption_percent": format(observation.value_percent, ".15g"),
                    "source_file": observation.source_file,
                }
            )
    temporary.replace(destination)


def write_coverage_report(report: CoverageReport, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
