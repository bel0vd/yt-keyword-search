"""Debug script: search for Music-category videos and extract full metadata."""

import asyncio

from playwright.async_api import async_playwright

from scraper.extractor import extract_video_metadata
from scraper.filters import pre_filter_results
from scraper.models import ScraperConfig
from scraper.search import search_keyword, warm_up_homepage
from scraper.utils import handle_cookie_consent


async def main() -> None:
    # Relaxed config for debugging.
    config = ScraperConfig(
        min_views=50,
        min_hours_since_upload=0.0,
        max_hours_since_upload=48.0,
        max_scrolls_per_search=2,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await warm_up_homepage(page, config)

        results = await search_keyword(page, "music", config)
        print(f"Search returned {len(results)} results")
        for r in results[:10]:
            print(
                repr(
                    {
                        "title": r.title[:80],
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
        print(f"Pre-filtered with relaxed thresholds: {len(filtered)} results")

        for r in filtered[:3]:
            print("\n--- Extracting ---")
            print(
                repr(
                    {
                        "title": r.title[:80],
                        "url": r.url,
                        "views_text": r.views_text,
                        "upload_time_text": r.upload_time_text,
                        "duration_text": r.duration_text,
                    }
                )
            )

            video = await extract_video_metadata(page, r.url, "music", config)
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
                print("TOP_COMMENTS_COUNT:", len(video.top_comments))
                print("TOP_COMMENTS:", video.top_comments[:3])
                print("RELEASE_DATE:", video.release_date)
                print("HOURS_SINCE_UPLOAD:", video.hours_since_upload)
                print("VELOCITY:", video.velocity)
                print("IS_TOPIC_CHANNEL:", video.is_topic_channel)
            else:
                print("Extraction returned None (likely non-Music category)")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
