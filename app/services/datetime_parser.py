from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import dateparser

from app.config import cfg

# German month names for deterministic locale-independent output
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


def format_datetime(dt: datetime) -> str:
    """Format a datetime as a short German-locale string (e.g. '11. Apr., 12:00')."""
    hour = dt.hour
    minute = dt.minute
    return f"{dt.day}. {_GERMAN_MONTHS[dt.month - 1]}, {hour:02d}:{minute:02d}"


def format_date_long(d: str | None) -> str:
    """Format an ISO date string as a long German weekday+date (e.g. 'Freitag, 11. Apr.')."""
    parsed = date.fromisoformat(d) if d else None
    if parsed is None:
        return ""
    weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return f"{weekdays[parsed.weekday()]}, {parsed.day}. {_GERMAN_MONTHS[parsed.month - 1]}"


_KNOWN_TIME_RANGES: dict[str, tuple[str, str]] = {
    "ganztags": ("00:00", "23:59"),
    "ganztägig": ("00:00", "23:59"),
    "vormittags": ("08:00", "12:00"),
    "abends": ("18:00", "22:00"),
    "nachmittags": ("15:00", "18:00"),
    "ab mittag": ("12:00", "18:00"),
    "-": ("00:00", "23:59"),
    "": ("00:00", "23:59"),
}


def _parse_time_range(time_str: str, event_date: date | str) -> tuple[str, str, date | str]:
    """Extract start/end time strings and (possibly updated) date from time_str."""
    lower = time_str.lower()

    if known := _KNOWN_TIME_RANGES.get(lower):
        return (*known, event_date)

    if "-" in time_str:
        parts = time_str.split("-", maxsplit=1)
        start_str = parts[0].strip().replace(" Uhr", "")
        end_part = parts[1].strip().replace(" Uhr", "")
        if "??" in end_part:
            return (start_str, "23:59", event_date)
        return (start_str, end_part, event_date)

    return _parse_with_dateparser(time_str, event_date)


def _parse_with_dateparser(time_str: str, event_date: date | str) -> tuple[str, str, date | str]:
    """Use dateparser to interpret a free-form time string."""
    parsed = dateparser.parse(
        time_str.strip(),
        languages=["de"],
        settings={
            "TIMEZONE": cfg.TZ,
            "RELATIVE_BASE": datetime.strptime(f"{event_date} 00:00", "%Y-%m-%d %H:%M").replace(
                tzinfo=ZoneInfo(cfg.TZ)
            ),
        },
    )
    try:
        start_str = parsed.strftime("%H:%M") if parsed else time_str.replace(" Uhr", "").strip()
        end_str = (
            datetime.strptime(start_str, "%H:%M").replace(tzinfo=ZoneInfo(cfg.TZ)) + timedelta(hours=2)
        ).strftime(
            "%H:%M",
        )
        if parsed:
            event_date = parsed.date()
    except (ValueError, AttributeError):
        return ("00:00", "23:59", event_date)
    return (start_str, end_str, event_date)


def parse_event_times(date: date | str, time_str: str) -> tuple[datetime, datetime]:
    """Parse a German time-range string into start and end datetimes."""
    start_str, end_str, date = _parse_time_range(time_str, date)

    try:
        start_time = datetime.strptime(f"{date} {start_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(cfg.TZ))
        end_time = datetime.strptime(f"{date} {end_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(cfg.TZ))

        if start_time > end_time:
            end_time += timedelta(days=1)

        return (start_time, end_time)
    except ValueError:
        # fallback to all-day
        fallback_start = datetime.strptime(f"{date} 00:00", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(cfg.TZ))
        fallback_end = datetime.strptime(f"{date} 23:59", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(cfg.TZ))
        return (fallback_start, fallback_end)
