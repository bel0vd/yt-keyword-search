"""Debug script: extract all metadata fields from any video URL."""

import asyncio

from playwright.async_api import async_playwright

from scraper.extractor import (
    _extract_yt_initial_data,
    _extract_yt_initial_player_response,
    _extract_channel_info,
    _extract_comments_from_initial_data,
    _extract_description_from_dom,
    _extract_likes_from_dom,
    _extract_subscriber_count_from_dom,
    _extract_comment_count_from_dom,
    _extract_comments_from_dom,
)
from scraper.utils import handle_cookie_consent


async def main() -> None:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        await handle_cookie_consent(page)

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Scroll to bottom to trigger comments load.
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        pr = await _extract_yt_initial_player_response(page)
        initial_data = await _extract_yt_initial_data(page)

        print("TITLE:", pr.get("videoDetails", {}).get("title") if pr else None)
        print(
            "CATEGORY:",
            pr.get("microformat", {})
            .get("playerMicroformatRenderer", {})
            .get("category")
            if pr
            else None,
        )
        print("VIEWS:", pr.get("videoDetails", {}).get("viewCount") if pr else None)
        print("CHANNEL_INFO:", _extract_channel_info(pr) if pr else None)
        print(
            "DESCRIPTION_JSON:",
            pr.get("microformat", {})
            .get("playerMicroformatRenderer", {})
            .get("description", {})
            .get("simpleText")[:200]
            if pr
            else None,
        )
        print("DESCRIPTION_DOM:", (await _extract_description_from_dom(page))[:200])
        print("LIKES:", await _extract_likes_from_dom(page))
        print("SUBSCRIBERS:", await _extract_subscriber_count_from_dom(page))
        print(
            "COMMENTS_INITIAL:",
            _extract_comments_from_initial_data(initial_data, 5)
            if initial_data
            else None,
        )
        comments_dom, enabled = await _extract_comments_from_dom(page, 5)
        print("COMMENTS_DOM:", comments_dom)
        print("COMMENTS_ENABLED:", enabled)
        print("COMMENT_COUNT_DOM:", await _extract_comment_count_from_dom(page))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
