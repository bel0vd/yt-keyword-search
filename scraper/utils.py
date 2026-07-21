"""Utility helpers for the YouTube Music scraper."""

import asyncio
import logging
import random
import re
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import TimeoutError as PlaywrightTimeout

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("youtube_music_scraper.utils")


# Keywords that are obviously music-related and do NOT need "music" appended.
OBVIOUSLY_MUSIC_KEYWORDS = {
    "remix",
    "mashup",
    "edit",
    "acapella",
    "accapella",
    "vocals only",
    "instrumental",
    "type beat",
    "sped up",
    "spedup",
    "sped uup",
    "spdup",
    "spd up",
    "slowed",
    "slwed",
    "slowed + reverb",
    "rvrb",
    "suno",
    "suno ai",
    "udio",
    "ai song",
    "ai cover",
}

# YouTube search parameter for "Upload date: Today".
UPLOAD_TODAY_SP_PARAM = "EgQIARgB"


# The full keyword list as provided in the requirements.
RAW_KEYWORDS = [
    "Sped Up",
    "spedup",
    "sped uup",
    "spdup",
    "spd up",
    "Slowed",
    "slwed",
    "slowed + reverb",
    "rvrb",
    "Remix",
    "Mashup",
    "Edit",
    "Acapella",
    "accapella",
    "vocals only",
    "Instrumental",
    "Type Beat",
    "WIP",
    "Teaser",
    "Snippet",
    "Leak",
    "Unreleased",
    "Leaked",
    "Hardtekk",
    "hardtek",
    "tekk",
    "Jersey Club",
    "Krushclub",
    "Mylancore",
    "Speed Garage",
    "UKG",
    "Amapiano",
    "Hyperpop",
    "Sigmacore",
    "Bitpop",
    "Glitchcore",
    "Breakcore",
    "Hoodtrap",
    "Soul Jazz",
    "Hardstyle",
    "Jumpstyle",
    "BP",
    "The Dark Triad",
    "BP Edit",
    "Suno",
    "Suno AI",
    "Udio",
    "AI Song",
    "AI Cover",
    "Brainrot",
    "Skibidi",
    "Sigma",
]


def normalize_keyword(keyword: str) -> str:
    """Return the keyword, appending 'music' if it is not obviously music-related."""
    lower = keyword.strip().lower()
    if lower in OBVIOUSLY_MUSIC_KEYWORDS:
        return keyword.strip()
    return f"{keyword.strip()} music"


def get_search_keywords() -> list[str]:
    """Return the full keyword list with automatic 'music' normalization applied."""
    return [normalize_keyword(k) for k in RAW_KEYWORDS]


def build_search_url(keyword: str) -> str:
    """Build a YouTube search URL with the 'Upload date: Today' filter applied."""
    encoded = urllib.parse.quote_plus(keyword)
    return f"https://www.youtube.com/results?search_query={encoded}&sp={UPLOAD_TODAY_SP_PARAM}"


def extract_video_id(url: str) -> str | None:
    """Extract the 11-character YouTube video ID from a URL."""
    patterns = [
        r"(?:v=|/shorts/|/embed/|/live/|/watch\?v=)([A-Za-z0-9_-]{11})",
        r"^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_shorts_url(url: str) -> bool:
    """Return True if the URL points to a YouTube Shorts video."""
    return "/shorts/" in url.lower()


def is_video_url(url: str) -> bool:
    """Return True if the URL contains a YouTube video ID."""
    return extract_video_id(url) is not None


def clean_text(text: str | None) -> str:
    """Normalize whitespace and strip a text fragment."""
    if not text:
        return ""
    return " ".join(text.split())


def truncate_text(text: str, max_length: int = 300) -> str:
    """Return a text snippet truncated to max_length characters."""
    text = clean_text(text)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def random_delay(min_seconds: float, max_seconds: float) -> None:
    """Block for a random duration between min_seconds and max_seconds."""
    sleep_time = random.uniform(min_seconds, max_seconds)
    asyncio.run(asyncio.sleep(sleep_time))


async def async_random_delay(min_seconds: float, max_seconds: float) -> None:
    """Asynchronously sleep for a random duration between min_seconds and max_seconds."""
    sleep_time = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(sleep_time)


def ensure_csv_dir(filename: str) -> Path:
    """Create the parent directory for the CSV file if it does not exist."""
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_csv_filename() -> str:
    """Generate the default CSV filename: youtube_music_scrape_YYYYMMDD_HHMMSS.csv."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"youtube_music_scrape_{timestamp}.csv"


async def handle_cookie_consent(page: "Page", timeout: int = 5000) -> None:
    """Dismiss YouTube cookie consent if it appears.

    Prefers "Reject all" / "Decline" to minimize tracking, falling back to
    "Accept all" if necessary.
    """
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        for label_substring in [
            "Reject all",
            "Decline optional",
            "Manage options",
            "Accept all",
            "I agree",
        ]:
            locator = page.get_by_role("button", name=label_substring, exact=False)
            if await locator.count() > 0:
                await locator.first.click(timeout=timeout)
                logger.debug("Clicked cookie consent button: %s", label_substring)
                await page.wait_for_load_state("networkidle", timeout=10000)
                return
    except PlaywrightTimeout:
        logger.debug("No cookie consent dialog appeared")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cookie consent handling encountered an error: %s", exc)
