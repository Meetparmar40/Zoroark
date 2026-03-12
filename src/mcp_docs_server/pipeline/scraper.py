"""Page scraper — fetches a URL and returns its content as markdown via crawl4ai.

Uses the HTTP-only strategy (AsyncHTTPCrawlerStrategy + HTTPCrawlerConfig) so
**no browser or Playwright installation is needed**.
"""

import asyncio
import logging

from crawl4ai import (
    AsyncWebCrawler,
    CacheMode,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
    HTTPCrawlerConfig,
)
from crawl4ai.async_crawler_strategy import AsyncHTTPCrawlerStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared configuration (module-level, created once)
# ---------------------------------------------------------------------------
_http_config = HTTPCrawlerConfig(
    method="GET",
    headers={
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    follow_redirects=True,
    verify_ssl=True,
)

_http_strategy = AsyncHTTPCrawlerStrategy(browser_config=_http_config)


# ---------------------------------------------------------------------------
# Async public API
# ---------------------------------------------------------------------------
async def scrape_page(url: str, max_length: int = 50_000) -> dict:
    """Scrape *url* and return ``{"url": ..., "content": ...}``.

    Args:
        url: Full URL to scrape.
        max_length: Truncate markdown content beyond this many characters.

    Returns:
        Dict with ``url`` and ``content`` (markdown text).
        On failure the ``content`` key is empty and an ``error`` key is added.
    """
    try:
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            markdown_generator=DefaultMarkdownGenerator(),
            verbose=False,
        )

        async with AsyncWebCrawler(
            crawler_strategy=_http_strategy,
        ) as crawler:
            result = await crawler.arun(url=url, config=run_config)

        if not result.success:
            logger.warning("Scrape failed for %s: %s", url, result.error_message)
            return {
                "url": url,
                "content": "",
                "error": result.error_message or "unknown",
            }

        # Prefer fit_markdown (cleaned) > markdown > cleaned_html
        content = (
            getattr(result, "fit_markdown", None)
            or getattr(result, "markdown", None)
            or result.cleaned_html
            or ""
        )

        if max_length and len(content) > max_length:
            content = content[:max_length] + "\n\n... [truncated]"

        return {"url": url, "content": content}

    except Exception as e:
        logger.error("Scrape exception for %s: %s", url, e)
        return {"url": url, "content": "", "error": str(e)}


# ---------------------------------------------------------------------------
# Sync wrapper (safe to call from non-async contexts like Streamlit)
# ---------------------------------------------------------------------------
def scrape_page_sync(url: str, max_length: int = 50_000) -> dict:
    """Synchronous wrapper around :func:`scrape_page`.

    Works in Streamlit and other sync environments without subprocess
    spawning because the HTTP strategy does not rely on Playwright.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop (e.g. Jupyter / Streamlit).
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, scrape_page(url, max_length)).result(timeout=120)

        return asyncio.run(scrape_page(url, max_length))

    except Exception as e:
        logger.error("scrape_page_sync error for %s: %s", url, e)
        return {"url": url, "content": "", "error": str(e)}
