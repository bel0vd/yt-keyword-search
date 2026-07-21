"""Debug script: extract full metadata from a single video URL."""

import asyncio

from playwright.async_api import async_playwright

from scraper.extractor import extract_video_metadata
from scraper.models import ScraperConfig
from scraper.utils import handle_cookie_consent


async def main() -> None:
    config = ScraperConfig()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        await handle_cookie_consent(page)

        # Use one of the Music-category videos surfaced by the "Remix" search.
        video_url = "https://www.youtube.com/watch?v=-LIgFRYvMKg"
        await page.goto(video_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        print("PAGE_TITLE:", await page.title())
        html = await page.content()
        print("HAS ytInitialPlayerResponse:", "ytInitialPlayerResponse" in html)
        print("HAS ytInitialData:", "ytInitialData" in html)

        from scraper.extractor import (
            _extract_yt_initial_player_response,
            _extract_category,
        )

        pr = await _extract_yt_initial_player_response(page)
        print("EXTRACTED_PLAYER_RESPONSE:", pr is not None)
        if pr:
            print("CATEGORY:", _extract_category(pr))
            print("TITLE:", pr.get("videoDetails", {}).get("title"))
            print("VIEWS:", pr.get("videoDetails", {}).get("viewCount"))

        video = await extract_video_metadata(page, video_url, "Remix", config)

        if video:
            print("TITLE:", video.title)
            print("URL:", video.url)
            print("CHANNEL_NAME:", video.channel_name)
            print("CHANNEL_URL:", video.channel_url)
            print("SUBSCRIBER_COUNT:", video.subscriber_count)
            print("VIEWS:", video.views)
            print("LIKES:", video.likes)
            print("DURATION_SECONDS:", video.duration_seconds)
            print("COMMENT_COUNT:", video.comment_count)
            print("COMMENTS_ENABLED:", video.comments_enabled)
            print("TOP_COMMENTS:", video.top_comments)
            print("RELEASE_DATE:", video.release_date)
            print("HOURS_SINCE_UPLOAD:", video.hours_since_upload)
            print("VELOCITY:", video.velocity)
            print("IS_TOPIC_CHANNEL:", video.is_topic_channel)
        else:
            print("Extraction returned None")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
