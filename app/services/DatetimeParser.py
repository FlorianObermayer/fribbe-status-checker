from datetime import date, datetime, timedelta

import dateparser


def parse_event_times(date: date | str, time_str: str) -> tuple[datetime, datetime]:
    # Parse time
    if "-" in time_str:
        # e.g. "12:00 - 16:00", "16:30 - 18:30"
        start_str, end_str = [
            t.strip().replace(" Uhr", "") for t in time_str.split("-")
        ]
    elif time_str.lower() in ["ganztags", "ganztägig"]:
        start_str, end_str = "00:00", "23:59"
    elif time_str.lower() in ["vormittags"]:
        start_str, end_str = "08:00", "12:00"
    elif time_str.lower() in ["abends"]:
        start_str, end_str = "18:00", "22:00"
    elif time_str.lower() in ["nachmittags"]:
        start_str, end_str = "15:00", "18:00"
    elif time_str.lower() in ["ab mittag"]:
        start_str, end_str = "12:00", "18:00"
    elif "??" in time_str:
        # e.g. "13:00 - ?? Uhr"
        start_str, end_str = (
            time_str.split("-")[0].strip().replace(" Uhr", ""),
            "23:59",
        )
    elif time_str.lower() in ["-", ""]:
        start_str, end_str = "00:00", "23:59"
    else:
        parsed = dateparser.parse(
            time_str.strip(),
            languages=["de"],
            settings={
                "TIMEZONE": "Europe/Berlin",
                "RELATIVE_BASE": datetime.strptime(f"{date} 00:00","%Y-%m-%d %H:%M")
            },
        )
        try:
            start_str = (
                parsed.strftime("%H:%M")
                if parsed
                else time_str.replace(" Uhr", "").strip()
            )
            end_str = (
                datetime.strptime(start_str, "%H:%M") + timedelta(hours=2)
            ).strftime("%H:%M")

            if(parsed):
                date = parsed.date()
        except:
            start_str, end_str = "00:00", "23:59"

    start_time: datetime | None = None
    end_time: datetime | None = None
    # Parse datetime
    try:
        start_time = datetime.strptime(f"{date} {start_str}", "%Y-%m-%d %H:%M")
        end_time = datetime.strptime(f"{date} {end_str}", "%Y-%m-%d %H:%M")

        if start_time > end_time:
            end_time += timedelta(days=1)

        return (start_time, end_time)
    except Exception:
        # fallback to all-day
        start_time = start_time or datetime.strptime(f"{date} 00:00", "%Y-%m-%d %H:%M")
        end_time = end_time or datetime.strptime(f"{date} 23:59", "%Y-%m-%d %H:%M")
        return (start_time, end_time)
