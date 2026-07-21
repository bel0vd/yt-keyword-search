"""Video filtering rules."""

import re
from scraper.models import SearchResult, Video, ScraperConfig
from scraper.parser import parse_views, parse_duration, parse_upload_time


# Title fragments that reject a video regardless of other metadata.
TITLE_BANNED_WORDS = {
    "tutorial",
    "how to",
    "breakdown",
    "making of",
    "fl studio",
    "ableton",
    "vlog",
    "podcast",
    "reaction",
    "review",
    "karaoke",
    "official music video",
    "episode",
    "movie",
    "full movie",
    "gaming",
    "walkthrough",
    "playthrough",
    "stream",
    "live stream",
    "interview",
    "documentary",
    "news",
    "sports",
    "funny",
    "comedy",
    "challenge",
    "guide",
    "tips",
    "course",
    "class",
}


ALLOWED_CATEGORIES = {"Music"}


def title_contains_banned_words(title: str) -> bool:
    """Return True if the title contains any banned word/phrase."""
    lower_title = title.lower()
    for word in TITLE_BANNED_WORDS:
        if word in lower_title:
            return True
    return False


def is_valid_video_type(result: SearchResult) -> bool:
    """Return True for regular videos; reject Shorts, Live Streams, and Premieres."""
    if result.is_short:
        return False
    if result.is_live:
        return False
    if result.is_premiere:
        return False
    return True


def pre_filter_results(
    results: list[SearchResult], config: ScraperConfig
) -> list[SearchResult]:
    """Filter candidates using only search-result-page metadata.

    This keeps the expensive video-page visits to a minimum.
    """
    accepted: list[SearchResult] = []

    for result in results:
        if not is_valid_video_type(result):
            continue
        if title_contains_banned_words(result.title):
            continue

        duration = parse_duration(result.duration_text)
        if duration is None or duration > config.max_duration_seconds:
            continue

        views = parse_views(result.views_text)
        if views is None or views < config.min_views:
            continue

        hours = parse_upload_time(result.upload_time_text)
        if hours is None or not (
            config.min_hours_since_upload <= hours <= config.max_hours_since_upload
        ):
            continue

        accepted.append(result)

    return accepted


def post_filter_video(video: Video, config: ScraperConfig) -> bool:
    """Apply the full filter rules after detailed metadata is extracted.

    Returns True only when every acceptance criterion is met.
    """
    if title_contains_banned_words(video.title):
        return False
    if video.views < config.min_views:
        return False
    if video.duration_seconds > config.max_duration_seconds:
        return False
    if not (
        config.min_hours_since_upload
        <= video.hours_since_upload
        <= config.max_hours_since_upload
    ):
        return False
    return True
