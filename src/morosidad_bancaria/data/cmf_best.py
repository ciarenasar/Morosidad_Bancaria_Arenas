"""Cliente mínimo y auditable para APIBEST de la CMF."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from morosidad_bancaria.config import CmfBestConfig

_VALID_TAG = re.compile(r"^[A-Z0-9_]+$")


class BestApiError(RuntimeError):
    """Error seguro del servicio, sin incluir la credencial."""


@dataclass(frozen=True)
class DownloadRecord:
    source: str
    chart_tag: str
    start_date: str
    end_date: str
    endpoint_path: str
    downloaded_at_utc: str
    http_status: int
    content_type: str
    bytes: int
    sha256: str
    local_path: str


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    downloaded: bool
    record: DownloadRecord | None


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def month_end(value: date) -> date:
    return add_months(date(value.year, value.month, 1), 1) - timedelta(days=1)


def iter_month_windows(start: date, end: date, max_months: int = 12):
    """Entrega rangos inclusivos que abarcan como máximo ``max_months`` meses."""
    if start > end:
        raise ValueError("La fecha inicial no puede ser posterior a la final")
    if max_months < 1:
        raise ValueError("max_months debe ser positivo")

    cursor = start
    while cursor <= end:
        last_month = add_months(date(cursor.year, cursor.month, 1), max_months - 1)
        window_end = min(end, month_end(last_month))
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


class BestClient:
    def __init__(self, config: CmfBestConfig, api_key: str):
        if not api_key:
            raise ValueError("api_key no puede estar vacía")
        self.config = config
        self._api_key = api_key

    @staticmethod
    def _validate_tag(chart_tag: str) -> None:
        if not _VALID_TAG.fullmatch(chart_tag):
            raise ValueError("El tag del cuadro contiene caracteres no permitidos")

    def _endpoint_path(self, chart_tag: str, start: date, end: date) -> str:
        self._validate_tag(chart_tag)
        return (
            f"/api/v1/cuadros/data/{chart_tag}/range/"
            f"{start:%Y%m%d}/{end:%Y%m%d}"
        )

    def fetch_range(self, chart_tag: str, start: date, end: date) -> tuple[int, str, bytes, str]:
        endpoint_path = self._endpoint_path(chart_tag, start, end)
        url = f"{self.config.base_url.rstrip('/')}{endpoint_path}"
        request = Request(
            url,
            headers={"Accept": "application/json", "x-api-key": self._api_key},
            method="GET",
        )

        for attempt in range(self.config.max_retries + 1):
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    status = response.status
                try:
                    json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise BestApiError(
                        "APIBEST respondió contenido que no es JSON válido"
                    ) from error
                return status, content_type, body, endpoint_path
            except HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code < 600
                if not retryable or attempt >= self.config.max_retries:
                    raise BestApiError(f"APIBEST respondió HTTP {error.code}") from error
                retry_after = error.headers.get("Retry-After")
                delay = min(float(retry_after), 30.0) if retry_after else 2**attempt
                time.sleep(delay)
            except URLError as error:
                if attempt >= self.config.max_retries:
                    raise BestApiError("No fue posible conectar con APIBEST") from error
                time.sleep(2**attempt)

        raise BestApiError("No fue posible completar la consulta a APIBEST")

    def download_range(
        self,
        chart_tag: str,
        start: date,
        end: date,
        raw_directory: Path,
        manifest_path: Path,
        *,
        overwrite: bool = False,
    ) -> DownloadResult:
        filename = f"cmf_best__{chart_tag.lower()}__{start:%Y%m%d}_{end:%Y%m%d}.json"
        destination = raw_directory / filename
        if destination.exists() and not overwrite:
            return DownloadResult(destination, downloaded=False, record=None)

        status, content_type, body, endpoint_path = self.fetch_range(chart_tag, start, end)
        raw_directory.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(body)
        temporary.replace(destination)

        record = DownloadRecord(
            source="CMF APIBEST",
            chart_tag=chart_tag,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            endpoint_path=endpoint_path,
            downloaded_at_utc=datetime.now(UTC).isoformat(),
            http_status=status,
            content_type=content_type,
            bytes=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            local_path=(Path("data") / "raw" / raw_directory.name / filename).as_posix(),
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("a", encoding="utf-8", newline="\n") as manifest:
            manifest.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")
        return DownloadResult(destination, downloaded=True, record=record)

    def download_history(
        self,
        chart_tag: str,
        start: date,
        end: date,
        raw_directory: Path,
        manifest_path: Path,
        *,
        overwrite: bool = False,
    ) -> list[DownloadResult]:
        windows = list(iter_month_windows(start, end, self.config.max_months_per_request))
        results: list[DownloadResult] = []
        previous_request_at: float | None = None
        for window_start, window_end in windows:
            filename = (
                f"cmf_best__{chart_tag.lower()}__"
                f"{window_start:%Y%m%d}_{window_end:%Y%m%d}.json"
            )
            will_request = overwrite or not (raw_directory / filename).exists()
            if will_request and previous_request_at is not None:
                elapsed = time.monotonic() - previous_request_at
                time.sleep(max(0.0, self.config.min_interval_seconds - elapsed))
            if will_request:
                previous_request_at = time.monotonic()
            results.append(
                self.download_range(
                    chart_tag,
                    window_start,
                    window_end,
                    raw_directory,
                    manifest_path,
                    overwrite=overwrite,
                )
            )
        return results
