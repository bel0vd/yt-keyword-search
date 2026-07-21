"""Main orchestration for the YouTube Music Scraper."""

import asyncio
import logging
import random
from collections import OrderedDict
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from scraper.csv_writer import write_csv_report
from scraper.extractor import extract_video_metadata
from scraper.filters import pre_filter_results, post_filter_video
from scraper.logger import setup_logger
from scraper.models import ScraperConfig, SearchResult, Video
from scraper.search import search_keyword, warm_up_homepage
from scraper.utils import (
    async_random_delay,
    extract_video_id,
    get_csv_filename,
    get_search_keywords,
    handle_cookie_consent,
)

logger = logging.getLogger("youtube_music_scraper.main")


BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1920,1080",
]


def _create_browser_context_args(config: ScraperConfig) -> dict:
    """Build context options that look like a normal desktop browsing session."""
    viewport = {
        "width": random.randint(1366, 1920),
        "height": random.randint(768, 1080),
    }
    return {
        "viewport": viewport,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }


async def _create_context(browser: Browser, config: ScraperConfig) -> BrowserContext:
    """Create a new browser context with anti-detection settings."""
    return await browser.new_context(**_create_browser_context_args(config))


async def _maybe_pause(request_counter: int, config: ScraperConfig) -> int:
    """Pause every N requests to avoid YouTube rate limiting.

    Returns the (possibly reset) request counter.
    """
    if request_counter > 0 and request_counter % config.requests_per_pause == 0:
        logger.info(
            "Processed %d requests; pausing for %.0f seconds to avoid rate limiting",
            config.requests_per_pause,
            config.pause_duration,
        )
        await asyncio.sleep(config.pause_duration)
        return 0
    return request_counter


async def _collect_candidates(
    page: Page,
    keywords: list[str],
    config: ScraperConfig,
) -> tuple[OrderedDict[str, SearchResult], int]:
    """Search every keyword and return unique video candidates keyed by video ID.

    The request counter is incremented once per keyword search.
    """
    candidates: OrderedDict[str, SearchResult] = OrderedDict()
    request_counter = 0

    await warm_up_homepage(page, config)

    for keyword in keywords:
        request_counter = await _maybe_pause(request_counter, config)

        try:
            results = await search_keyword(page, keyword, config)
            request_counter += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("Search failed for keyword %r: %s", keyword, exc)
            continue

        if not results:
            logger.info("No candidate results for keyword %r", keyword)
            continue

        filtered = pre_filter_results(results, config)
        logger.info(
            "Keyword %r: %d pre-filtered candidate(s)",
            keyword,
            len(filtered),
        )

        for result in filtered:
            video_id = extract_video_id(result.url)
            if video_id and video_id not in candidates:
                candidates[video_id] = result

        await async_random_delay(
            config.min_delay_between_searches, config.max_delay_between_searches
        )

    return candidates, request_counter


async def _extract_videos_concurrently(
    browser: Browser,
    candidates: OrderedDict[str, SearchResult],
    config: ScraperConfig,
    request_counter: int,
) -> list[Video]:
    """Visit each unique video page and extract detailed metadata.

    Uses a pool of concurrent browser contexts to improve throughput.
    """
    queue: asyncio.Queue[SearchResult] = asyncio.Queue()
    for result in candidates.values():
        await queue.put(result)

    valid_videos: list[Video] = []
    counter_lock = asyncio.Lock()
    local_counter = request_counter

    async def worker() -> None:
        nonlocal local_counter
        context = await _create_context(browser, config)
        page = await context.new_page()

        try:
            # Prime the context by visiting the homepage so cookie consent (if any)
            # is handled before we visit video pages.
            try:
                await page.goto(
                    "https://www.youtube.com",
                    wait_until="domcontentloaded",
                    timeout=config.request_timeout,
                )
                await handle_cookie_consent(page)
                await async_random_delay(1.0, 2.5)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Worker context warm-up failed (non-critical): %s", exc)

            while True:
                try:
                    result = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                async with counter_lock:
                    local_counter = await _maybe_pause(local_counter, config)
                    local_counter += 1

                try:
                    video = await extract_video_metadata(
                        page, result.url, result.source_keyword, config
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Extraction failed for %s: %s", result.url, exc)
                    video = None

                if video is None:
                    logger.debug(
                        "Skipping %s: extraction failed or non-Music category",
                        result.url,
                    )
                    queue.task_done()
                    continue

                if not post_filter_video(video, config):
                    logger.debug(
                        "Skipping %s: failed post-filter (views=%s, duration=%s, hours=%s)",
                        result.url,
                        video.views,
                        video.duration_seconds,
                        video.hours_since_upload,
                    )
                    queue.task_done()
                    continue

                valid_videos.append(video)
                logger.info(
                    "Accepted video: %s | views=%d | hours=%.2f | velocity=%.2f",
                    video.title,
                    video.views,
                    video.hours_since_upload,
                    video.velocity,
                )

                await async_random_delay(
                    config.min_delay_between_videos, config.max_delay_between_videos
                )
                queue.task_done()
        finally:
            await context.close()

    workers = [asyncio.create_task(worker()) for _ in range(config.concurrent_contexts)]
    await asyncio.gather(*workers)

    return valid_videos


async def _scrape(
    keywords: list[str] | None = None,
    config: ScraperConfig | None = None,
) -> tuple[str, int]:
    """Run the full scrape and return the CSV path plus the number of rows."""
    config = config or ScraperConfig()
    keywords = keywords if keywords is not None else get_search_keywords()

    logger.info("Starting YouTube Music scraper with %d keyword(s)", len(keywords))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=BROWSER_ARGS,
        )
        try:
            search_context = await _create_context(browser, config)
            search_page = await search_context.new_page()

            candidates, request_counter = await _collect_candidates(
                search_page, keywords, config
            )
            await search_context.close()

            logger.info(
                "Collected %d unique candidate video(s) across all keywords",
                len(candidates),
            )

            if not candidates:
                logger.warning("No candidate videos found; writing empty CSV")
                filename = get_csv_filename()
                path, count = write_csv_report([], filename)
                return str(path), count

            videos = await _extract_videos_concurrently(
                browser, candidates, config, request_counter
            )

            logger.info("Total valid videos before deduplication: %d", len(videos))

            filename = get_csv_filename()
            path, count = write_csv_report(videos, filename)
            logger.info("CSV written: %s (%d rows)", path, count)
            return str(path), count
        finally:
            await browser.close()


def main() -> None:
    """Entry point for the scraper."""
    setup_logger()
    try:
        csv_path, row_count = asyncio.run(_scrape())
        print(f"\nScrape complete: {csv_path}")
        print(f"Total rows: {row_count}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scraper failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
