"""Carga de configuración pública y secretos locales del proyecto."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(RuntimeError):
    """Indica configuración ausente o inválida sin revelar su contenido."""


@dataclass(frozen=True, repr=False)
class Credentials:
    cmf_best_api_key: str
    bcch_api_user: str | None = None
    bcch_api_password: str | None = None

    def __repr__(self) -> str:
        return (
            "Credentials(cmf_best_api_key=<redacted>, "
            f"bcch_api_user={'<set>' if self.bcch_api_user else '<unset>'}, "
            f"bcch_api_password={'<set>' if self.bcch_api_password else '<unset>'})"
        )


@dataclass(frozen=True)
class CmfBestConfig:
    base_url: str
    chart_tag: str
    target_series_code: str
    known_start_date: str
    max_months_per_request: int
    min_interval_seconds: float
    timeout_seconds: int
    max_retries: int


@dataclass(frozen=True)
class ForecastConfig:
    observation_frequency: str
    horizon_months: int
    target_transformation: str
    issuance_rule: str


@dataclass(frozen=True)
class PublicationCalendarConfig:
    cmf_press_url: str
    sbif_archive_url: str
    timeout_seconds: int


@dataclass(frozen=True)
class BcchConfig:
    base_url: str
    timeout_seconds: int
    max_retries: int


@dataclass(frozen=True)
class ProjectConfig:
    cmf_best: CmfBestConfig
    forecast: ForecastConfig
    publication_calendar: PublicationCalendarConfig
    bcch: BcchConfig


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _strip_optional_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_file(path: Path) -> dict[str, str]:
    """Lee KEY=VALUE básico, aceptando valores con o sin comillas."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigurationError(f"Línea inválida en {path.name}:{line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigurationError(f"Clave vacía en {path.name}:{line_number}")
        values[key] = _strip_optional_quotes(raw_value)
    return values


def load_credentials(env_path: Path | None = None, *, require_bcch: bool = False) -> Credentials:
    local_values = read_env_file(env_path or project_root() / ".env")

    def value(name: str) -> str | None:
        candidate = os.environ.get(name, local_values.get(name, "")).strip()
        return candidate or None

    cmf_key = value("CMF_BEST_API_KEY")
    if not cmf_key:
        raise ConfigurationError("Falta CMF_BEST_API_KEY en el entorno o en .env")

    bcch_user = value("BCCH_API_USER")
    bcch_password = value("BCCH_API_PASSWORD")
    if require_bcch and (not bcch_user or not bcch_password):
        raise ConfigurationError("Faltan BCCH_API_USER o BCCH_API_PASSWORD")

    return Credentials(cmf_key, bcch_user, bcch_password)


def load_project_config(path: Path | None = None) -> ProjectConfig:
    config_path = path or project_root() / "configs" / "base.toml"
    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
        return ProjectConfig(
            cmf_best=CmfBestConfig(**raw["cmf_best"]),
            forecast=ForecastConfig(**raw["forecast"]),
            publication_calendar=PublicationCalendarConfig(**raw["publication_calendar"]),
            bcch=BcchConfig(**raw["bcch"]),
        )
    except (FileNotFoundError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        raise ConfigurationError(f"Configuración pública inválida: {config_path}") from error
