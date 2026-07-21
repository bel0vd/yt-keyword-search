"""YouTube search results page scraping."""

import asyncio
import logging
import re
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from scraper.models import SearchResult, ScraperConfig
from scraper.utils import (
    async_random_delay,
    build_search_url,
    clean_text,
    extract_video_id,
    handle_cookie_consent,
)

logger = logging.getLogger("youtube_music_scraper.search")


# JavaScript function injected into the page to extract raw result data without
# relying on brittle CSS-only selectors.
_EXTRACT_RESULTS_JS = """
() => {
  const results = [];
  const renderers = document.querySelectorAll('ytd-video-renderer');
  renderers.forEach(renderer => {
    const titleEl = renderer.querySelector('#video-title');
    const title = titleEl ? (titleEl.textContent || titleEl.getAttribute('title') || '').trim() : '';
    const url = titleEl ? titleEl.href : '';

    const channelEl = renderer.querySelector('#channel-info #channel-name a, #channel-name a, #channel-thumbnail + #channel-info a');
    const channelName = channelEl ? (channelEl.textContent || '').trim() : '';
    const channelUrl = channelEl ? channelEl.href : '';

    const metadataLine = renderer.querySelector('#metadata-line');
    const metaSpans = metadataLine ? Array.from(metadataLine.querySelectorAll('span')) : [];
    const metaTexts = metaSpans.map(s => s.textContent.trim()).filter(Boolean);

    // Views and upload time are the first two metadata spans on English YouTube.
    const viewsText = metaTexts[0] || '';
    const uploadTimeText = metaTexts[1] || '';

    // Duration detection.
    const durationOverlay = renderer.querySelector('ytd-thumbnail-overlay-time-status-renderer');
    const overlayText = durationOverlay ? (durationOverlay.textContent || '').trim() : '';
    const overlayStyle = durationOverlay ? durationOverlay.getAttribute('overlay-style') || '' : '';
    const overlayAriaLabel = durationOverlay ? (durationOverlay.getAttribute('aria-label') || '') : '';

    // Thumbnail aria-label often contains duration as text.
    const thumb = renderer.querySelector('#thumbnail a');
    const ariaLabel = thumb ? (thumb.getAttribute('aria-label') || '') : '';

    // Shorts badge detection.
    const badges = Array.from(renderer.querySelectorAll('span, yt-icon')).map(el => (el.textContent || '').trim()).filter(Boolean);
    const hasShortsBadge = badges.some(t => /Shorts/i.test(t));

    const isShort = /\\/shorts\\//i.test(url) || hasShortsBadge;
    const isLive = overlayStyle.toUpperCase() === 'LIVE' || /\\bLIVE\\b/i.test(overlayText);
    const isPremiere = overlayStyle.toUpperCase() === 'PREMIERE' || /\\bPREMIERE\\b|\\bUpcoming\\b/i.test(overlayText);

    results.push({
      title,
      url,
      channelName,
      channelUrl,
      viewsText,
      uploadTimeText,
      durationText: overlayText,
      overlayAriaLabel,
      ariaLabel,
      isShort,
      isLive,
      isPremiere,
    });
  });
  return results;
}
"""


def _extract_duration_from_aria_label(aria_label: str) -> str:
    """Try to recover a duration string from the thumbnail aria-label.

    Example aria-label: "Song Title by Artist 3 minutes, 45 seconds 12345 views"
    Returns "3:45" if parsed.
    """
    if not aria_label:
        return ""

    match = re.search(
        r"(\d+)\s+minutes?,\s+(\d+)\s+seconds?",
        aria_label,
    )
    if match:
        return f"{match.group(1)}:{int(match.group(2)):02d}"

    match = re.search(
        r"(\d+)\s+hours?,\s+(\d+)\s+minutes?,\s+(\d+)\s+seconds?",
        aria_label,
    )
    if match:
        return f"{match.group(1)}:{int(match.group(2)):02d}:{int(match.group(3)):02d}"

    return ""


def _clean_video_url(url: str) -> str:
    """Normalize a YouTube result URL to a plain watch URL."""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def _clean_duration_text(text: str) -> str:
    """Extract the first valid duration token from the overlay text.

    YouTube sometimes duplicates the duration in the overlay for accessibility,
    e.g. "3:32 3:32". This function returns the first occurrence.
    """
    if not text:
        return ""
    # Find all substrings that look like a duration.
    matches = re.findall(r"\d+:\d+(?::\d+)?", text)
    if matches:
        return matches[0]
    return text


def _parse_search_result(
    raw: dict[str, Any], source_keyword: str
) -> SearchResult | None:
    """Convert a raw JS extraction result into a SearchResult model."""
    title = clean_text(raw.get("title", ""))
    url = clean_text(raw.get("url", ""))

    if not title or not url:
        return None

    video_id = extract_video_id(url)
    if not video_id:
        return None

    url = _clean_video_url(url)

    duration_text = _clean_duration_text(clean_text(raw.get("durationText", "")))
    if not duration_text:
        duration_text = _clean_duration_text(
            clean_text(raw.get("overlayAriaLabel", ""))
        )
    if not duration_text and raw.get("ariaLabel"):
        duration_text = _extract_duration_from_aria_label(raw.get("ariaLabel", ""))

    views_text = clean_text(raw.get("viewsText", ""))
    upload_time_text = clean_text(raw.get("uploadTimeText", ""))

    is_premiere = bool(raw.get("isPremiere", False))
    if not is_premiere:
        is_premiere = (
            re.search(r"premiere|premieres|upcoming", views_text, re.IGNORECASE)
            is not None
        )

    return SearchResult(
        title=title,
        url=url,
        channel_name=clean_text(raw.get("channelName", "")),
        channel_url=clean_text(raw.get("channelUrl", "")),
        views_text=views_text,
        upload_time_text=upload_time_text,
        duration_text=duration_text,
        is_short=bool(raw.get("isShort", False)),
        is_live=bool(raw.get("isLive", False)),
        is_premiere=is_premiere,
        source_keyword=source_keyword,
    )


async def _scroll_results(page: Page, config: ScraperConfig) -> None:
    """Scroll the search results page to load more content.

    Stops early if no new results are loaded for a configured number of attempts.
    """
    previous_count = 0
    stall_count = 0

    for _ in range(config.max_scrolls_per_search):
        # Scroll to the bottom of the page.
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await async_random_delay(
            config.min_delay_between_scrolls, config.max_delay_between_scrolls
        )

        # Count current video renderers.
        try:
            current_count = await page.locator("ytd-video-renderer").count()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not count video renderers while scrolling: %s", exc)
            continue

        if current_count > previous_count:
            previous_count = current_count
            stall_count = 0
            logger.debug(
                "Loaded more results; total video renderers: %d", current_count
            )
        else:
            stall_count += 1
            logger.debug("No new results loaded; stall count: %d", stall_count)
            if stall_count >= config.scrolls_after_stall:
                logger.debug("Results stopped loading; ending scroll early")
                break


async def search_keyword(
    page: Page, keyword: str, config: ScraperConfig
) -> list[SearchResult]:
    """Search YouTube for a keyword and return candidate SearchResult objects.

    Applies the 'Upload date: Today' filter via URL parameter, handles cookie
    consent, scrolls the results page, and extracts metadata.
    """
    url = build_search_url(keyword)
    logger.info("Searching YouTube for keyword: %r", keyword)

    try:
        await page.goto(
            url, wait_until="domcontentloaded", timeout=config.request_timeout
        )
        await handle_cookie_consent(page)
        await page.wait_for_selector("ytd-video-renderer", timeout=15000)
    except PlaywrightTimeout:
        logger.warning("Timeout while loading search results for %r", keyword)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load search results for %r: %s", keyword, exc)
        return []

    await _scroll_results(page, config)

    try:
        raw_results = await page.evaluate(_EXTRACT_RESULTS_JS)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to extract search results for %r: %s", keyword, exc)
        return []

    results: list[SearchResult] = []
    for raw in raw_results:
        result = _parse_search_result(raw, source_keyword=keyword)
        if result:
            results.append(result)

    logger.info(
        "Keyword %r returned %d candidate video(s)",
        keyword,
        len(results),
    )
    return results


async def warm_up_homepage(page: Page, config: ScraperConfig) -> None:
    """Visit the YouTube homepage briefly to warm up the session.

    This makes subsequent searches look more like a real browsing session.
    """
    try:
        await page.goto(
            "https://www.youtube.com",
            wait_until="domcontentloaded",
            timeout=config.request_timeout,
        )
        await handle_cookie_consent(page)
        await async_random_delay(2.0, 4.0)
        logger.debug("Warmed up YouTube homepage")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Homepage warm-up failed (non-critical): %s", exc)
