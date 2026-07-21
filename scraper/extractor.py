"""Video page metadata extraction."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from scraper.models import Video, ScraperConfig
from scraper.parser import (
    parse_duration,
    parse_iso_date,
    hours_since,
    parse_likes,
    parse_comment_count,
    parse_subscribers,
)
from scraper.utils import (
    async_random_delay,
    clean_text,
    extract_video_id,
    truncate_text,
)

logger = logging.getLogger("youtube_music_scraper.extractor")


def _extract_json_from_page(html: str, var_name: str) -> dict[str, Any] | None:
    """Parse a JSON blob assigned to a window variable such as ytInitialPlayerResponse."""
    if not html:
        return None

    prefix = f"var {var_name} = "
    start = html.find(prefix)
    if start == -1:
        # Fallback: try assignment without "var".
        prefix = f"{var_name} = "
        start = html.find(prefix)
    if start == -1:
        return None

    json_start = start + len(prefix)
    if html[json_start] != "{":
        return None

    # Find the matching closing brace by counting braces, ignoring braces inside strings.
    brace_count = 0
    in_string = False
    escape_next = False
    end = json_start
    for i in range(json_start, len(html)):
        char = html[i]
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break

    json_str = html[json_start:end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        logger.debug("Failed to parse %s: %s", var_name, exc)
        return None


def _get_nested(
    data: dict[str, Any] | list[Any], *keys: str | int, default: Any = None
) -> Any:
    """Safely traverse nested dictionaries and lists."""
    current: Any = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif (
            isinstance(current, list)
            and isinstance(key, int)
            and 0 <= key < len(current)
        ):
            current = current[key]
        else:
            return default
    return current


async def _extract_yt_initial_player_response(page: Page) -> dict[str, Any] | None:
    """Extract ytInitialPlayerResponse from the page source or JS variable."""
    try:
        html = await page.content()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not get page content: %s", exc)
        return None

    return _extract_json_from_page(html, "ytInitialPlayerResponse")


async def _extract_yt_initial_data(page: Page) -> dict[str, Any] | None:
    """Extract ytInitialData from the page source."""
    try:
        html = await page.content()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not get page content: %s", exc)
        return None

    return _extract_json_from_page(html, "ytInitialData")


def _extract_category(player_response: dict[str, Any]) -> str | None:
    """Return the YouTube category from ytInitialPlayerResponse."""
    category = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "category",
    )
    if category:
        return str(category)

    # Fallback to meta tag if the JSON path is missing.
    return None


def _extract_title(player_response: dict[str, Any]) -> str:
    """Return the video title from ytInitialPlayerResponse."""
    title = _get_nested(player_response, "videoDetails", "title")
    return clean_text(title) if title else ""


def _extract_views(player_response: dict[str, Any]) -> int:
    """Return the view count as an integer from ytInitialPlayerResponse."""
    view_count = _get_nested(player_response, "videoDetails", "viewCount")
    if view_count:
        try:
            return int(view_count)
        except (ValueError, TypeError):
            pass
    return 0


def _extract_duration_seconds(player_response: dict[str, Any]) -> int:
    """Return the video duration in seconds from ytInitialPlayerResponse."""
    length_seconds = _get_nested(player_response, "videoDetails", "lengthSeconds")
    if length_seconds:
        try:
            return int(length_seconds)
        except (ValueError, TypeError):
            pass

    # Fallback to the microformat duration.
    duration_iso = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "lengthSeconds",
    )
    if duration_iso:
        try:
            return int(duration_iso)
        except (ValueError, TypeError):
            pass
    return 0


def _extract_channel_info(player_response: dict[str, Any]) -> tuple[str, str]:
    """Return (channel_name, channel_url) from ytInitialPlayerResponse."""
    channel_name = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "ownerChannelName",
    )
    channel_id = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "externalChannelId",
    )

    name = clean_text(channel_name) if channel_name else ""
    if channel_id:
        url = f"https://www.youtube.com/channel/{channel_id}"
    else:
        url = ""
    return name, url


def _extract_release_date(player_response: dict[str, Any]) -> str:
    """Return the video release/publish date as an ISO date string."""
    publish_date = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "publishDate",
    )
    if publish_date:
        return str(publish_date)

    upload_date = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "uploadDate",
    )
    if upload_date:
        return str(upload_date)

    return ""


def _extract_description_from_player_response(player_response: dict[str, Any]) -> str:
    """Return the video description from ytInitialPlayerResponse."""
    desc = _get_nested(
        player_response,
        "microformat",
        "playerMicroformatRenderer",
        "description",
        "simpleText",
    )
    if desc:
        return clean_text(desc)

    desc = _get_nested(
        player_response,
        "videoDetails",
        "shortDescription",
    )
    if desc:
        return clean_text(desc)

    return ""


async def _extract_likes_from_dom(page: Page) -> int | None:
    """Extract the like count from the DOM with multiple fallback selectors.

    YouTube frequently redesigns the like button, so this function tries many
    known selectors and also uses JavaScript to inspect the page directly.
    """
    # 1. CSS selector fallbacks.
    selectors = [
        "#top-level-buttons-computed ytd-like-button-view-model button",
        "#top-level-buttons-computed segmented-like-dislike-button-view-model button",
        "#top-level-buttons-computed yt-button-view-model button",
        "#segmented-like-button button",
        "#like-button button",
        "#menu ytd-toggle-button-renderer:first-child button",
        "ytd-toggle-button-renderer .yt-spec-touch-feedback-shape",
        "button[aria-label*='likes']",
        "button[aria-label*='Like']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            text = await locator.text_content()
            if text:
                text = clean_text(text)
                parsed = parse_likes(text)
                if parsed is not None:
                    return parsed

            aria_label = await locator.get_attribute("aria-label")
            if aria_label:
                aria_label = clean_text(aria_label)
                # Try extracting the number that appears before "likes".
                match = re.search(
                    r"([\d.,]+\s*[KMB]?)\s+likes", aria_label, re.IGNORECASE
                )
                if match:
                    parsed = parse_likes(match.group(1))
                    if parsed is not None:
                        return parsed
                # Some buttons only have a number as text in the aria-label.
                parsed = parse_likes(aria_label)
                if parsed is not None:
                    return parsed
        except Exception as exc:  # noqa: BLE001
            logger.debug("Like extraction failed for selector %s: %s", selector, exc)
            continue

    # 2. JavaScript traversal fallback.
    try:
        like_text = await page.evaluate("""
            () => {
                const candidates = [
                    document.querySelector('#top-level-buttons-computed ytd-like-button-view-model button'),
                    document.querySelector('#top-level-buttons-computed segmented-like-dislike-button-view-model button'),
                    document.querySelector('#like-button button'),
                    document.querySelector('button[aria-label*="likes"]'),
                    document.querySelector('button[aria-label*="Like"]'),
                ];
                for (const btn of candidates) {
                    if (!btn) continue;
                    const text = (btn.textContent || '').trim();
                    const label = (btn.getAttribute('aria-label') || '').trim();
                    if (text && /^[\d.,]+\s*[KMB]?$/i.test(text)) return text;
                    if (label) return label;
                }
                return '';
            }
        """)
        if like_text:
            like_text = clean_text(like_text)
            match = re.search(r"([\d.,]+\s*[KMB]?)\s+likes", like_text, re.IGNORECASE)
            if match:
                parsed = parse_likes(match.group(1))
                if parsed is not None:
                    return parsed
            parsed = parse_likes(like_text)
            if parsed is not None:
                return parsed
    except Exception as exc:  # noqa: BLE001
        logger.debug("Like extraction via JS failed: %s", exc)

    return None


async def _extract_subscriber_count_from_dom(page: Page) -> int | None:
    """Extract subscriber count from the channel owner area."""
    selectors = [
        "#owner-sub-count",
        "#subscribe-button ~ #owner-sub-count",
        "[id*='owner-sub-count']",
        "#channel-name + #owner-sub-count",
        "#inner-header-container #owner-sub-count",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            text = await locator.text_content()
            if text:
                parsed = parse_subscribers(clean_text(text))
                if parsed is not None:
                    return parsed
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Subscriber extraction failed for selector %s: %s", selector, exc
            )
            continue

    return None


async def _extract_description_from_dom(page: Page) -> str:
    """Extract description from the DOM as a fallback."""
    selectors = [
        "#description-inline-expander",
        "#description .ytd-text-inline-expander",
        "#description-text",
        "yt-formatted-string#description",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            text = await locator.text_content()
            if text:
                return clean_text(text)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Description extraction failed for selector %s: %s", selector, exc
            )
            continue

    return ""


def _extract_comments_from_initial_data(
    initial_data: dict[str, Any], max_count: int
) -> list[str]:
    """Extract the first N comments from ytInitialData."""
    comments: list[str] = []

    contents = _get_nested(
        initial_data,
        "contents",
        "twoColumnWatchNextResults",
        "results",
        "results",
        "contents",
    )

    if not isinstance(contents, list):
        return comments

    for section in contents:
        item_section = _get_nested(section, "itemSectionRenderer")
        if not isinstance(item_section, dict):
            continue

        items = item_section.get("contents", [])
        if not isinstance(items, list):
            continue

        for item in items:
            comment_renderer = _get_nested(
                item, "commentThreadRenderer", "comment", "commentRenderer"
            )
            if not isinstance(comment_renderer, dict):
                continue

            text_runs = _get_nested(
                comment_renderer,
                "contentText",
                "runs",
                default=[],
            )
            if isinstance(text_runs, list):
                text = "".join(run.get("text", "") for run in text_runs)
                text = clean_text(text)
                if text:
                    comments.append(text)
                    if len(comments) >= max_count:
                        return comments

    return comments


async def _scroll_comments_into_view(page: Page) -> None:
    """Scroll the comments section into view to trigger lazy loading."""
    try:
        await page.locator("#comments").first.scroll_into_view_if_needed(timeout=5000)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not scroll comments into view: %s", exc)


async def _extract_comments_from_dom(
    page: Page, max_count: int
) -> tuple[list[str], bool]:
    """Extract comments from the DOM after scrolling.

    Returns (comments, comments_enabled).
    """
    comments: list[str] = []
    comments_enabled = True

    try:
        # Wait for the comments section to appear in the DOM.
        try:
            await page.wait_for_selector("#comments", timeout=8000)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Comments section did not appear: %s", exc)
            return comments, comments_enabled

        await _scroll_comments_into_view(page)
        await async_random_delay(1.5, 3.0)

        # Check for disabled comments.
        disabled_texts = ["Comments are turned off", "Comments turned off"]
        page_text = await page.locator("#comments").text_content()
        if page_text and any(d in page_text for d in disabled_texts):
            comments_enabled = False
            return comments, comments_enabled

        # Wait for comment thread renderers to load (they appear after a network request).
        try:
            await page.wait_for_selector("ytd-comment-thread-renderer", timeout=8000)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Comment threads did not load: %s", exc)

        # JavaScript traversal to extract comment text robustly.
        extracted = await page.evaluate(
            """
            (maxCount) => {
                const results = [];
                const threads = document.querySelectorAll('ytd-comment-thread-renderer');
                for (const thread of threads) {
                    if (results.length >= maxCount) break;
                    const renderer = thread.querySelector('ytd-comment-renderer');
                    if (!renderer) continue;
                    const textEl = renderer.querySelector('#content-text, #comment-content, span.yt-formatted-string');
                    if (textEl) {
                        const text = textEl.textContent || '';
                        if (text.trim()) results.push(text.trim());
                    }
                }
                return results;
            }
            """,
            max_count,
        )

        if isinstance(extracted, list):
            for text in extracted:
                text = clean_text(text)
                if text:
                    comments.append(text)

    except Exception as exc:  # noqa: BLE001
        logger.debug("Comments extraction failed: %s", exc)

    return comments, comments_enabled


async def _extract_comment_count_from_dom(page: Page) -> int | None:
    """Extract the comment count from the DOM header above the comments section."""
    selectors = [
        "ytd-comments-header-renderer #count",
        "#comments #count .yt-formatted-string",
        "#comments #count",
        "h2#count",
        "#comments h2",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() == 0:
                continue
            text = await locator.text_content()
            if text:
                text = clean_text(text)
                # Extract the leading number before the word "Comments".
                match = re.search(r"([\d.,]+\s*[KMB]?)\s*Comments", text, re.IGNORECASE)
                if match:
                    parsed = parse_comment_count(match.group(1))
                    if parsed is not None:
                        return parsed
                # Try plain number if the label is not present.
                parsed = parse_comment_count(text)
                if parsed is not None:
                    return parsed
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Comment count extraction failed for selector %s: %s", selector, exc
            )
            continue

    return None


def _extract_comment_count_from_initial_data(
    initial_data: dict[str, Any] | None,
) -> int | None:
    """Extract the comment count from ytInitialData engagement panels."""
    if not initial_data:
        return None

    engagement_panels = _get_nested(initial_data, "engagementPanels", default=[])
    if not isinstance(engagement_panels, list):
        return None

    for panel in engagement_panels:
        content = _get_nested(
            panel, "engagementPanelSectionListRenderer", "content", default={}
        )
        section = _get_nested(content, "sectionListRenderer", "contents", default=[])
        if not isinstance(section, list):
            continue

        for item in section:
            count = _get_nested(
                item,
                "itemSectionRenderer",
                "contents",
                0,
                "commentsHeaderRenderer",
                "countText",
                "runs",
                0,
                "text",
            )
            if count:
                parsed = parse_comment_count(str(count))
                if parsed is not None:
                    return parsed

    return None


def _is_topic_channel(channel_name: str) -> bool:
    """Return True if the channel looks like an auto-generated topic channel."""
    if not channel_name:
        return False
    return channel_name.strip().endswith(" - Topic")


async def extract_video_metadata(
    page: Page, video_url: str, source_keyword: str, config: ScraperConfig
) -> Video | None:
    """Extract full metadata from a single video page.

    Returns None if the video is not a valid candidate (e.g. category missing,
    page load failed).
    """
    logger.info("Extracting metadata for %s", video_url)

    try:
        await page.goto(
            video_url, wait_until="domcontentloaded", timeout=config.request_timeout
        )
        await page.wait_for_selector(
            "h1.ytd-watch-metadata, #title h1, ytd-watch-metadata", timeout=15000
        )
    except PlaywrightTimeout:
        logger.warning("Timeout while loading video page: %s", video_url)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load video page %s: %s", video_url, exc)
        return None

    player_response = await _extract_yt_initial_player_response(page)
    if not player_response:
        logger.warning("Could not extract ytInitialPlayerResponse for %s", video_url)
        return None

    category = _extract_category(player_response)
    if category not in {"Music"}:
        logger.debug("Rejecting %s: category is %r", video_url, category)
        return None

    title = _extract_title(player_response)
    views = _extract_views(player_response)
    duration_seconds = _extract_duration_seconds(player_response)
    channel_name, channel_url = _extract_channel_info(player_response)
    release_date = _extract_release_date(player_response)

    # Description fallback to DOM if JSON description is empty.
    description = _extract_description_from_player_response(player_response)
    if not description:
        description = await _extract_description_from_dom(page)

    # Likes from DOM (best effort).
    likes = await _extract_likes_from_dom(page)

    # Subscriber count from DOM.
    subscriber_count = await _extract_subscriber_count_from_dom(page)

    # Comments: first try initial data, then DOM.
    initial_data = await _extract_yt_initial_data(page)
    comments: list[str] = []
    comments_enabled = True

    if initial_data:
        comments = _extract_comments_from_initial_data(
            initial_data, config.max_comments
        )

    if not comments:
        comments, comments_enabled = await _extract_comments_from_dom(
            page, config.max_comments
        )

    # Comment count: try initial data first, then DOM.
    resolved_count = _extract_comment_count_from_initial_data(initial_data)
    if resolved_count is None:
        resolved_count = await _extract_comment_count_from_dom(page)
    if resolved_count is None:
        resolved_count = len(comments)

    # Upload hours calculation.
    publish_dt = parse_iso_date(release_date)
    hours_since_upload = 0.0
    if publish_dt:
        hours_since_upload = hours_since(publish_dt)
    else:
        logger.warning("Could not parse release date for %s", video_url)

    # Velocity.
    velocity = round(views / hours_since_upload, 2) if hours_since_upload > 0 else 0.0

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    video = Video(
        title=title,
        url=video_url,
        channel_name=channel_name,
        channel_url=channel_url,
        subscriber_count=subscriber_count,
        duration_seconds=duration_seconds,
        description_snippet=truncate_text(description, 300),
        views=views,
        original_view_text=f"{views} views",
        likes=likes,
        comment_count=resolved_count,
        comments_enabled=comments_enabled,
        top_comments=comments,
        matched_keywords=[source_keyword],
        source_keyword=source_keyword,
        release_date=release_date,
        scraped_at=scraped_at,
        hours_since_upload=hours_since_upload,
        velocity=velocity,
        is_topic_channel=_is_topic_channel(channel_name),
    )

    logger.debug(
        "Extracted video: %s | views=%d | hours=%.2f", title, views, hours_since_upload
    )
    return video
