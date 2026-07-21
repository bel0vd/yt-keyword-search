"""Smoke test: run the scraper with a tiny keyword set to verify the pipeline."""

import asyncio

from scraper.main import _scrape
from scraper.models import ScraperConfig


async def main() -> None:
    config = ScraperConfig(
        min_views=10,
        min_hours_since_upload=0.0,
        max_hours_since_upload=48.0,
        max_scrolls_per_search=2,
        concurrent_contexts=1,
        min_delay_between_searches=1.0,
        max_delay_between_searches=2.0,
        min_delay_between_videos=2.0,
        max_delay_between_videos=4.0,
    )
    path, count = await _scrape(
        keywords=["Remix", "Type Beat"],
        config=config,
    )
    print(f"Smoke test complete: {path} ({count} rows)")


if __name__ == "__main__":
    asyncio.run(main())
