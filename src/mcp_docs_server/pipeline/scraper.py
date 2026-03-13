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

FALLBACK_SELECTORS = [
    "article",
    "main",
    '[role="main"]',
    ".content",
    ".docs-content",
    ".documentation",
    ".markdown-body",
    "#content",
    "#main",
]

MIN_CONTENT_LENGTH = 200

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
        async with AsyncWebCrawler(
            crawler_strategy=_http_strategy,
        ) as crawler:
            result = None

            for selector in FALLBACK_SELECTORS:
                run_config = CrawlerRunConfig(
                    css_selector=selector,
                    cache_mode=CacheMode.BYPASS,
                    markdown_generator=DefaultMarkdownGenerator(),
                    verbose=False,
                )
                candidate = await crawler.arun(url=url, config=run_config)
                candidate_content = (
                    getattr(candidate, "fit_markdown", None)
                    or getattr(candidate, "markdown", None)
                    or candidate.cleaned_html
                    or ""
                )
                if candidate.success and len(candidate_content.strip()) >= MIN_CONTENT_LENGTH:
                    result = candidate
                    break

            if result is None:
                run_config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    markdown_generator=DefaultMarkdownGenerator(),
                    verbose=False,
                )
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



