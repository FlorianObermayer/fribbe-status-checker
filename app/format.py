"""Human-readable formatting helpers."""


def seconds_to_human(seconds: int) -> str:
    """Convert a duration in seconds to a concise German-language string.

    Examples:
        >>> seconds_to_human(3600)
        '1 Stunde'
        >>> seconds_to_human(86400)
        '1 Tag'
        >>> seconds_to_human(604800)
        '7 Tage'
        >>> seconds_to_human(90061)
        '1 Tag, 1 Stunde, 1 Minute, 1 Sekunde'

    """
    if seconds < 0:
        msg = "seconds must be non-negative"
        raise ValueError(msg)

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} {'Tag' if days == 1 else 'Tage'}")
    if hours:
        parts.append(f"{hours} {'Stunde' if hours == 1 else 'Stunden'}")
    if minutes:
        parts.append(f"{minutes} {'Minute' if minutes == 1 else 'Minuten'}")
    if secs or not parts:
        parts.append(f"{secs} {'Sekunde' if secs == 1 else 'Sekunden'}")

    return ", ".join(parts)
