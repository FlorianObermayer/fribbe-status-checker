import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from app.config import cfg

_TZ = ZoneInfo(cfg.TZ)

_GERMAN_MONTHS = [
    "Jan.",
    "Feb.",
    "Mär.",
    "Apr.",
    "Mai",
    "Jun.",
    "Jul.",
    "Aug.",
    "Sep.",
    "Okt.",
    "Nov.",
    "Dez.",
]
_WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

_ALL_DAY = ("00:00", "23:59")
_KNOWN_TIME_RANGES: dict[str, tuple[str, str]] = {
    "ganztags": _ALL_DAY,
    "ganztägig": _ALL_DAY,
    "vormittags": ("08:00", "12:00"),
    "nachmittags": ("15:00", "18:00"),
    "abends": ("18:00", "22:00"),
    "ab mittag": ("12:00", "18:00"),
    "-": _ALL_DAY,
    "": _ALL_DAY,
}

# Matches "3" or "3:14" as a standalone token, used to zero-pad + inject ":00"
_TIME_TOKEN_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\b")


def format_datetime(dt: datetime) -> str:
    """Format a datetime as a short German-locale string (e.g. '11. Apr., 12:00')."""
    return f"{dt.day}. {_GERMAN_MONTHS[dt.month - 1]}, {dt.hour:02d}:{dt.minute:02d}"


def format_date_long(d: str | None) -> str:
    """Format an ISO date string as a long German weekday+date (e.g. 'Freitag, 11. Apr.')."""
    if not d:
        return ""
    parsed = date.fromisoformat(d)
    return f"{_WEEKDAYS[parsed.weekday()]}, {parsed.day}. {_GERMAN_MONTHS[parsed.month - 1]}"


def _sanitize_time_str(time_str: str) -> str:
    """Normalize a time string: strip 'Uhr', collapse whitespace, zero-pad hours, and inject ':00' for bare hour mentions.

    Examples: '3:14' -> '03:14', '14 Uhr' -> '14:00',
              '14 Uhr - 16 Uhr' -> '14:00 - 16:00'
    """
    sanitized = time_str.lower().replace("uhr", "").strip()
    sanitized = " ".join(sanitized.split())

    def _pad(match: re.Match) -> str:  # pyright: ignore[reportUnknownParameterType, reportMissingTypeArgument]
        hour, minute = match.groups()  # pyright: ignore[reportUnknownVariableType]
        return f"{int(hour):02d}:{minute or '00'}"  # pyright: ignore[reportUnknownArgumentType]

    return _TIME_TOKEN_RE.sub(_pad, sanitized)  # pyright: ignore[reportUnknownArgumentType]


def _split_range(normalized: str) -> tuple[str, str] | None:
    """Split a sanitized string like '14:00 - 16:00' into (start, end), if possible."""
    if "-" not in normalized:
        return None
    start_part, _, end_part = normalized.partition("-")
    start_part, end_part = start_part.strip(), end_part.strip()
    if not end_part or "??" in end_part:
        end_part = "23:59"
    return (start_part, end_part)


def _parse_time_range(time_str: str, event_date: date | str) -> tuple[str, str, date | str]:
    """Extract start/end time strings and (possibly updated) date from time_str."""
    normalized = _sanitize_time_str(time_str)

    if known := _KNOWN_TIME_RANGES.get(normalized):
        return (*known, event_date)

    if normalized.startswith("ab "):
        return (normalized[3:].strip(), "23:59", event_date)
    if normalized.startswith("bis "):
        return ("00:00", normalized[4:].strip(), event_date)

    if time_range := _split_range(normalized):
        return (*time_range, event_date)

    return _parse_with_dateparser(normalized, event_date)


def _parse_with_dateparser(time_str: str, event_date: date | str) -> tuple[str, str, date | str]:
    """Use dateparser to interpret a free-form single time (no explicit range)."""
    base = datetime.strptime(f"{event_date} 00:00", "%Y-%m-%d %H:%M")  # noqa: DTZ007 - naive on purpose
    parsed = dateparser.parse(
        time_str.strip(),
        languages=["de"],
        settings={
            "TIMEZONE": cfg.TZ,
            "RELATIVE_BASE": base,
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
        },
    )

    if parsed is None:
        return _ALL_DAY[0], _ALL_DAY[1], event_date

    start_str = parsed.strftime("%H:%M")
    end_str = (parsed + timedelta(hours=2)).strftime("%H:%M")
    return start_str, end_str, parsed.date()


def parse_event_times(event_date: date | str, time_str: str) -> tuple[datetime, datetime]:
    """Parse a German time-range string into start and end datetimes."""
    start_str, end_str, resolved_date = _parse_time_range(time_str, event_date)

    try:
        start_time = datetime.strptime(f"{resolved_date} {start_str}", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
        end_time = datetime.strptime(f"{resolved_date} {end_str}", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
    except ValueError:
        start_time = datetime.strptime(f"{resolved_date} 00:00", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
        end_time = datetime.strptime(f"{resolved_date} 23:59", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ)
        return start_time, end_time

    if start_time > end_time:
        end_time += timedelta(days=1)

    return start_time, end_time
