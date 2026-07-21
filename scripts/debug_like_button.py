"""Debug script: dump the like button HTML structure."""

import asyncio

from playwright.async_api import async_playwright

from scraper.utils import handle_cookie_consent


async def main() -> None:
    url = "https://www.youtube.com/watch?v=-LIgFRYvMKg"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        await handle_cookie_consent(page)

        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)

        html = await page.evaluate("""
            () => {
                const areas = [
                    '#top-level-buttons-computed',
                    '#segmented-like-button',
                    '#like-button',
                    '#menu',
                ];
                const out = {};
                for (const sel of areas) {
                    const el = document.querySelector(sel);
                    if (el) out[sel] = el.outerHTML.substring(0, 2000);
                }
                return out;
            }
        """)

        for sel, content in html.items():
            print(f"\n=== {sel} ===")
            print(content)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
