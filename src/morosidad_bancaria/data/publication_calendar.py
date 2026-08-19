"""Calendario histórico de publicación construido desde comunicados oficiales."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from calendar import monthrange
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from morosidad_bancaria.config import PublicationCalendarConfig

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_ABBREVIATED_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_BANK_PERFORMANCE = re.compile(
    r"desempeño.*(?:bancos|sistema bancario)", re.IGNORECASE
)


class PublicationCalendarError(RuntimeError):
    """Indica evidencia ausente, ambigua o contradictoria."""


@dataclass(frozen=True)
class PageRecord:
    text: str
    title: str
    href: str


@dataclass(frozen=True)
class PublicationEntry:
    observation_date: date
    forecast_issue_date: date
    source_agency: str
    source_url: str
    source_title: str


@dataclass(frozen=True)
class CalendarCoverage:
    first_observation: str
    last_observation: str
    target_months: int
    calendar_months: int
    matched_months: int
    missing_months: list[str]
    extra_months: list[str]
    minimum_days_after_month_end: int
    maximum_days_after_month_end: int


class _ContainerParser(HTMLParser):
    def __init__(self, container_tag: str, heading_tags: set[str]):
        super().__init__(convert_charrefs=True)
        self.container_tag = container_tag
        self.heading_tags = heading_tags
        self.records: list[PageRecord] = []
        self._depth = 0
        self._text: list[str] = []
        self._heading_depth = 0
        self._title: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs):
        if tag == self.container_tag:
            if self._depth == 0:
                self._text = []
                self._title = []
                self._href = ""
            self._depth += 1
        if self._depth and tag in self.heading_tags:
            self._heading_depth += 1
        if self._depth and self._heading_depth and tag == "a" and not self._href:
            self._href = dict(attrs).get("href", "")

    def handle_endtag(self, tag: str):
        if self._depth and tag in self.heading_tags and self._heading_depth:
            self._heading_depth -= 1
        if tag == self.container_tag and self._depth:
            self._depth -= 1
            if self._depth == 0:
                self.records.append(
                    PageRecord(
                        text=_normalize(" ".join(self._text)),
                        title=_normalize(" ".join(self._title)),
                        href=self._href,
                    )
                )

    def handle_data(self, data: str):
        if self._depth:
            self._text.append(data)
            if self._heading_depth:
                self._title.append(data)


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8", "windows-1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise PublicationCalendarError("No fue posible decodificar una página oficial")


def _parse_observation_date(title: str) -> date | None:
    normalized = title.casefold()
    semester = re.search(r"primer semestre de\s+(\d{4})", normalized)
    if semester:
        return date(int(semester.group(1)), 6, 1)
    for month_name, month_number in _MONTHS.items():
        match = re.search(rf"\b{month_name}(?:\s+de)?\s+(\d{{4}})\b", normalized)
        if match:
            return date(int(match.group(1)), month_number, 1)
    return None


def _parse_cmf_publication_date(text: str) -> date | None:
    match = re.match(r"(\d{1,2})\s+([a-z]{3})\s+(\d{4})\b", text.casefold())
    if not match or match.group(2) not in _ABBREVIATED_MONTHS:
        return None
    return date(int(match.group(3)), _ABBREVIATED_MONTHS[match.group(2)], int(match.group(1)))


def _parse_sbif_publication_date(text: str) -> date | None:
    match = re.match(r"(\d{2})/(\d{2})/(\d{4})\b", text)
    if not match:
        return None
    return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))


def _entries_from_records(
    records: list[PageRecord],
    *,
    agency: str,
    base_url: str,
    date_parser,
) -> list[PublicationEntry]:
    entries: list[PublicationEntry] = []
    for record in records:
        if not _BANK_PERFORMANCE.search(record.title):
            continue
        observation_date = _parse_observation_date(record.title)
        publication_date = date_parser(record.text)
        if observation_date is None or publication_date is None:
            continue
        entries.append(
            PublicationEntry(
                observation_date=observation_date,
                forecast_issue_date=publication_date,
                source_agency=agency,
                source_url=urljoin(base_url, record.href),
                source_title=record.title,
            )
        )
    return entries


def parse_cmf_press(content: bytes, source_url: str) -> list[PublicationEntry]:
    parser = _ContainerParser("article", {"h2", "h3"})
    parser.feed(_decode_html(content))
    return _entries_from_records(
        parser.records,
        agency="CMF",
        base_url=source_url,
        date_parser=_parse_cmf_publication_date,
    )


def parse_sbif_archive(content: bytes, source_url: str) -> list[PublicationEntry]:
    parser = _ContainerParser("tr", {"h2"})
    parser.feed(_decode_html(content))
    return _entries_from_records(
        parser.records,
        agency="SBIF",
        base_url=source_url,
        date_parser=_parse_sbif_publication_date,
    )


def _download_page(url: str, destination: Path, timeout: int, overwrite: bool) -> bool:
    if destination.exists() and not overwrite:
        return False
    request = Request(url, headers={"User-Agent": "morosidad-bancaria-research/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as error:
        raise PublicationCalendarError(f"La fuente oficial respondió HTTP {error.code}") from None
    except URLError:
        raise PublicationCalendarError("No fue posible conectar con la fuente oficial") from None
    if status != 200 or b"<html" not in content[:2000].lower():
        raise PublicationCalendarError("La fuente oficial no devolvió una página HTML válida")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)
    metadata = {
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
        "source_url": url,
        "http_status": status,
        "content_type": content_type,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    destination.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def download_calendar_sources(
    config: PublicationCalendarConfig, raw_directory: Path, *, overwrite: bool = False
) -> dict[str, bool]:
    return {
        "cmf_press": _download_page(
            config.cmf_press_url,
            raw_directory / "cmf_press.html",
            config.timeout_seconds,
            overwrite,
        ),
        "sbif_archive": _download_page(
            config.sbif_archive_url,
            raw_directory / "sbif_archive.html",
            config.timeout_seconds,
            overwrite,
        ),
    }


def combine_entries(entries: list[PublicationEntry]) -> dict[date, PublicationEntry]:
    combined: dict[date, PublicationEntry] = {}
    for entry in sorted(entries, key=lambda item: (item.observation_date, item.source_agency)):
        existing = combined.get(entry.observation_date)
        if existing and existing.forecast_issue_date != entry.forecast_issue_date:
            raise PublicationCalendarError(
                f"Fechas de publicación contradictorias para {entry.observation_date.isoformat()}"
            )
        combined.setdefault(entry.observation_date, entry)
    return combined


def write_calendar(entries: dict[date, PublicationEntry], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "observation_date",
                "forecast_issue_date",
                "source_agency",
                "source_url",
                "source_title",
            ],
        )
        writer.writeheader()
        for observation_date in sorted(entries):
            entry = entries[observation_date]
            writer.writerow(
                {
                    **asdict(entry),
                    "observation_date": entry.observation_date.isoformat(),
                    "forecast_issue_date": entry.forecast_issue_date.isoformat(),
                }
            )
    temporary.replace(destination)


def audit_calendar(
    entries: dict[date, PublicationEntry], target_dates: list[date]
) -> CalendarCoverage:
    target = set(target_dates)
    calendar = set(entries)
    matched = target & calendar
    if not target:
        raise PublicationCalendarError("No hay fechas objetivo para auditar")
    lags = []
    for item in matched:
        observation_month_end = date(item.year, item.month, monthrange(item.year, item.month)[1])
        lags.append((entries[item].forecast_issue_date - observation_month_end).days)
    return CalendarCoverage(
        first_observation=min(target).isoformat(),
        last_observation=max(target).isoformat(),
        target_months=len(target),
        calendar_months=len(calendar),
        matched_months=len(matched),
        missing_months=[item.isoformat() for item in sorted(target - calendar)],
        extra_months=[item.isoformat() for item in sorted(calendar - target)],
        minimum_days_after_month_end=min(lags) if lags else 0,
        maximum_days_after_month_end=max(lags) if lags else 0,
    )
