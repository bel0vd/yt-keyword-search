"""Debug script: inspect YouTube search results extraction."""

import asyncio
from playwright.async_api import async_playwright

from scraper.search import search_keyword
from scraper.utils import build_search_url, handle_cookie_consent
from scraper.models import ScraperConfig
from scraper.filters import pre_filter_results


async def main() -> None:
    config = ScraperConfig(max_scrolls_per_search=1)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        url = build_search_url("Remix")
        print("Navigating to:", url)
        await page.goto(url, wait_until="domcontentloaded")
        await handle_cookie_consent(page)

        # Count renderers.
        count = await page.locator("ytd-video-renderer").count()
        print(f"Found {count} ytd-video-renderer elements")

        results = await search_keyword(page, "Remix", config)
        print(f"\nExtracted {len(results)} SearchResult objects")
        for r in results[:10]:
            print(
                repr(
                    {
                        "title": r.title[:60],
                        "url": r.url,
                        "views_text": r.views_text,
                        "upload_time_text": r.upload_time_text,
                        "duration_text": r.duration_text,
                        "is_short": r.is_short,
                        "is_live": r.is_live,
                        "is_premiere": r.is_premiere,
                    }
                )
            )

        filtered = pre_filter_results(results, config)
        print(f"\nPre-filtered: {len(filtered)} results")
        for r in filtered[:5]:
            print(
                repr(
                    {
                        "title": r.title[:60],
                        "url": r.url,
                        "views_text": r.views_text,
                        "upload_time_text": r.upload_time_text,
                        "duration_text": r.duration_text,
                    }
                )
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
