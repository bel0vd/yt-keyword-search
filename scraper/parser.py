"""Parsing helpers for YouTube display text."""

import re
from datetime import datetime, timezone
from typing import Callable


NumberParser = Callable[[str], int | None]


def _normalize_number(text: str) -> int | None:
    """Convert YouTube-style compact numbers into an integer.

    Examples:
        "1.2K" -> 1200
        "3.5M" -> 3500000
        "500" -> 500
        "1.2B" -> 1200000000
    """
    text = text.strip().replace(",", "").replace(" ", "").lower()
    if not text:
        return None

    match = re.match(r"^(\d+(?:\.\d+)?)\s*([kmb]?)\s*\+?$", text)
    if not match:
        return None

    value_str, suffix = match.groups()
    try:
        value = float(value_str)
    except ValueError:
        return None

    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
    return int(value * multiplier)


def parse_views(text: str) -> int | None:
    """Extract view count from strings like '1.2K views' or '3.5M views'."""
    if not text:
        return None
    text = text.lower()
    # Remove known noise words.
    text = text.replace("views", "").replace("view", "").strip()
    return _normalize_number(text)


def parse_subscribers(text: str) -> int | None:
    """Extract subscriber count from strings like '1.2K subscribers'."""
    if not text:
        return None
    text = text.lower().replace("subscribers", "").replace("subscriber", "").strip()
    return _normalize_number(text)


def parse_likes(text: str) -> int | None:
    """Extract like count from strings like '1.2K' or '3.5M'."""
    if not text:
        return None
    text = text.lower().replace("likes", "").replace("like", "").strip()
    return _normalize_number(text)


def parse_comment_count(text: str) -> int | None:
    """Extract comment count from strings like '1.2K Comments' or 'Comments 1.2K'."""
    if not text:
        return None
    text = text.lower().replace("comments", "").replace("comment", "").strip()
    return _normalize_number(text)


def parse_duration(text: str) -> int | None:
    """Convert a duration string into total seconds.

    Examples:
        "3:45" -> 225
        "1:02:30" -> 3750
        "0:45" -> 45
        "12:34" -> 754
    """
    if not text:
        return None

    parts = text.strip().split(":")
    if not all(part.isdigit() for part in parts):
        return None

    try:
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        pass
    return None


def parse_upload_time(text: str, reference: datetime | None = None) -> float | None:
    """Convert an upload-time text to hours since upload.

    Examples:
        "35 minutes ago" -> 0.58
        "5 hours ago" -> 5.0
        "1 day ago" -> 24.0
        "Streamed 5 hours ago" -> 5.0
        "Premiered 5 hours ago" -> 5.0
    """
    if not text:
        return None

    reference = reference or datetime.now(timezone.utc)
    text = text.lower().strip()

    # Remove prefixes like "streamed", "premiered", "uploaded".
    text = re.sub(r"^(?:streamed|premiered|uploaded|published|started)\s+", "", text)

    # Handle "X minutes/hours/days ago".
    match = re.match(
        r"^(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago$",
        text,
    )
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        if unit in ("second", "seconds"):
            hours = value / 3600.0
        elif unit in ("minute", "minutes"):
            hours = value / 60.0
        elif unit in ("hour", "hours"):
            hours = float(value)
        elif unit in ("day", "days"):
            hours = value * 24.0
        elif unit in ("week", "weeks"):
            hours = value * 24.0 * 7
        elif unit in ("month", "months"):
            hours = value * 24.0 * 30
        elif unit in ("year", "years"):
            hours = value * 24.0 * 365
        else:
            return None
        return round(hours, 2)

    # Handle "just now" / "moments ago".
    if text in ("just now", "moments ago", "a moment ago"):
        return 0.0

    return None


def parse_iso_date(text: str) -> datetime | None:
    """Parse an ISO-8601 date string to a timezone-aware datetime."""
    if not text:
        return None
    text = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def hours_since(reference: datetime, now: datetime | None = None) -> float:
    """Return hours elapsed between reference and now, rounded to two decimals."""
    now = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    delta = now - reference
    return round(delta.total_seconds() / 3600.0, 2)
