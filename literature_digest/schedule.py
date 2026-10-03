"""Calendar scheduling with one actual instant per reader-local calendar day."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def scheduled_instant(config, day):
    if day.weekday() not in config["schedule"]["weekdays"]:
        return None
    zone = ZoneInfo(config["timezone"])
    hour, minute = map(int, config["schedule"]["time"].split(":"))
    wall = datetime.combine(day, time(hour, minute))
    for _ in range(1440):
        candidate = wall.replace(tzinfo=zone, fold=0)
        roundtrip = candidate.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) == wall:
            return candidate  # On an autumn fold, always choose the first occurrence.
        if not config["schedule"]["catch_up"]:
            return None
        wall += timedelta(minutes=1)
        if wall.date() != day:
            return None
    return None


def is_due(config, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(config["timezone"]))
    due = scheduled_instant(config, local.date())
    if due is None:
        return False
    elapsed = (now.astimezone(timezone.utc) - due.astimezone(timezone.utc)).total_seconds()
    return elapsed >= 0 if config["schedule"]["catch_up"] else 0 <= elapsed < 60


def next_run(config, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(config["timezone"]))
    for offset in range(15):
        due = scheduled_instant(config, local.date() + timedelta(days=offset))
        if due is not None and due.astimezone(timezone.utc) > now.astimezone(timezone.utc):
            return due.isoformat()
    raise ValueError("No valid future scheduled day found")
