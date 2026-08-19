"""Cliente seguro para la API REST de la Base de Datos Estadísticos del BCCh."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from morosidad_bancaria.config import BcchConfig

_VALID_SERIES_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_VALID_FREQUENCIES = {"DAILY", "MONTHLY", "QUARTERLY", "ANNUAL"}


class BcchApiError(RuntimeError):
    """Error sanitizado de la API del Banco Central."""


def _load_json_bytes(body: bytes):
    for encoding in ("utf-8-sig", "iso-8859-1"):
        try:
            return json.loads(body.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise BcchApiError("El Banco Central respondió contenido no válido")


@dataclass(frozen=True)
class BcchDownloadRecord:
    source: str
    operation: str
    frequency: str | None
    series_id: str | None
    start_date: str | None
    end_date: str | None
    downloaded_at_utc: str
    http_status: int
    bytes: int
    sha256: str
    local_path: str


class BcchClient:
    def __init__(self, config: BcchConfig, user: str, password: str):
        if not user or not password:
            raise ValueError("Las credenciales del Banco Central no pueden estar vacías")
        self.config = config
        self._user = user
        self._password = password

    def _request(self, public_params: dict[str, str]) -> tuple[int, bytes]:
        params = {"user": self._user, "pass": self._password, **public_params}
        url = f"{self.config.base_url}?{urlencode(params)}"
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        for attempt in range(self.config.max_retries + 1):
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    body = response.read()
                    status = response.status
                payload = _load_json_bytes(body)
                if payload.get("Codigo") != 0:
                    code = payload.get("Codigo", "desconocido")
                    raise BcchApiError(f"El Banco Central rechazó la consulta (código {code})")
                return status, body
            except HTTPError as error:
                if attempt >= self.config.max_retries or error.code < 500:
                    raise BcchApiError(f"El Banco Central respondió HTTP {error.code}") from None
                time.sleep(2**attempt)
            except URLError:
                if attempt >= self.config.max_retries:
                    raise BcchApiError("No fue posible conectar con el Banco Central") from None
                time.sleep(2**attempt)
        raise BcchApiError("No fue posible completar la consulta al Banco Central")

    def _save(
        self,
        body: bytes,
        status: int,
        destination: Path,
        manifest_path: Path,
        *,
        operation: str,
        frequency: str | None = None,
        series_id: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> BcchDownloadRecord:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)
        record = BcchDownloadRecord(
            source="Banco Central de Chile BDE",
            operation=operation,
            frequency=frequency,
            series_id=series_id,
            start_date=start.isoformat() if start else None,
            end_date=end.isoformat() if end else None,
            downloaded_at_utc=datetime.now(UTC).isoformat(),
            http_status=status,
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            local_path=(
                Path("data") / "raw" / destination.parent.name / destination.name
            ).as_posix(),
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("a", encoding="utf-8", newline="\n") as manifest:
            manifest.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def download_catalog(
        self,
        frequency: str,
        destination: Path,
        manifest_path: Path,
        *,
        overwrite: bool = False,
    ) -> bool:
        frequency = frequency.upper()
        if frequency not in _VALID_FREQUENCIES:
            raise ValueError(f"Frecuencia no admitida: {frequency}")
        if destination.exists() and not overwrite:
            return False
        status, body = self._request({"function": "SearchSeries", "frequency": frequency})
        self._save(
            body,
            status,
            destination,
            manifest_path,
            operation="SearchSeries",
            frequency=frequency,
        )
        return True

    def download_series(
        self,
        series_id: str,
        start: date,
        end: date,
        destination: Path,
        manifest_path: Path,
        *,
        overwrite: bool = False,
    ) -> bool:
        if not _VALID_SERIES_ID.fullmatch(series_id):
            raise ValueError("Código de serie BCCh inválido")
        if start > end:
            raise ValueError("La fecha inicial no puede ser posterior a la final")
        if destination.exists() and not overwrite:
            return False
        status, body = self._request(
            {
                "function": "GetSeries",
                "timeseries": series_id,
                "firstdate": start.isoformat(),
                "lastdate": end.isoformat(),
            }
        )
        self._save(
            body,
            status,
            destination,
            manifest_path,
            operation="GetSeries",
            series_id=series_id,
            start=start,
            end=end,
        )
        return True


def load_catalog(path: Path) -> list[dict]:
    try:
        payload = _load_json_bytes(path.read_bytes())
        series = payload["SeriesInfos"]
    except (FileNotFoundError, BcchApiError, KeyError, TypeError) as error:
        raise BcchApiError(f"Catálogo local inválido: {path.name}") from error
    if not isinstance(series, list):
        raise BcchApiError(f"Catálogo local inválido: {path.name}")
    return series
