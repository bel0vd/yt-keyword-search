"""Debug script: inspect the comments section HTML."""

import asyncio

from playwright.async_api import async_playwright

from scraper.utils import handle_cookie_consent


async def main() -> None:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.youtube.com", wait_until="domcontentloaded")
        await handle_cookie_consent(page)

        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)

        # Scroll to comments.
        for _ in range(5):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        html = await page.evaluate("""
            () => {
                const comments = document.querySelector('#comments');
                if (!comments) return 'NO_COMMENTS_ELEMENT';
                const threads = comments.querySelectorAll('ytd-comment-thread-renderer');
                return {
                    commentsOuter: comments.outerHTML.substring(0, 1500),
                    threadCount: threads.length,
                    firstThread: threads.length > 0 ? threads[0].outerHTML.substring(0, 2000) : 'NO_THREADS',
                };
            }
        """)
        print("THREAD_COUNT:", html.get("threadCount"))
        print("COMMENTS_OUTER:", html.get("commentsOuter"))
        print("FIRST_THREAD:", html.get("firstThread"))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
