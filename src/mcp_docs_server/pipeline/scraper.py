"""Documentation scraper - second stage of the retrieval pipeline.

Uses Crawl4AI to fetch and extract documentation content from a URL.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from ..config import settings
logger = logging.getLogger(__name__)


class ScraperError(RuntimeError):
	"""Raised when scraping fails or returns unusable content."""


class Crawl4AIScraper:
	"""Async Crawl4AI wrapper for fetching documentation pages."""

	def __init__(self) -> None:
		self.browser_config = BrowserConfig(
			headless=True,
			verbose=False,
		)
		self.run_config = CrawlerRunConfig(
			cache_mode=CacheMode.BYPASS,
			page_timeout=settings.scraper_timeout_ms,
		)

	async def scrape(self, url: str) -> str:
		"""Scrape a URL and return markdown text.

		Args:
			url: Fully qualified URL for a documentation page.

		Returns:
			Extracted markdown text.
		"""
		self._validate_url(url)

		logger.info("Scraping URL with Crawl4AI: %s", url)

		async with AsyncWebCrawler(config=self.browser_config) as crawler:
			result = await crawler.arun(url=url, config=self.run_config)

		if not getattr(result, "success", False):
			error_message = getattr(result, "error_message", None) or "unknown crawler error"
			raise ScraperError(f"Crawl4AI failed for {url}: {error_message}")

		markdown_text = self._extract_markdown_text(result)
		if not markdown_text:
			raise ScraperError(f"Crawl4AI returned empty content for {url}")

		if settings.scraper_max_content_chars > 0:
			markdown_text = markdown_text[: settings.scraper_max_content_chars]

		return markdown_text

	def _validate_url(self, url: str) -> None:
		parsed = urlparse(url)
		if parsed.scheme not in {"http", "https"} or not parsed.netloc:
			raise ScraperError(f"Invalid URL: {url}")

	def _extract_markdown_text(self, result: Any) -> str:
		markdown = getattr(result, "markdown", None)

		if isinstance(markdown, str):
			text = markdown
		elif markdown is not None:
			text = getattr(markdown, "raw_markdown", None) or getattr(markdown, "fit_markdown", None)
		else:
			text = None

		if not text:
			extracted_content = getattr(result, "extracted_content", None)
			if isinstance(extracted_content, str):
				text = extracted_content

		return (text or "").strip()


async def scrape_page(url: str) -> dict:
	"""Scrape a docs page and return structured markdown content.

	Args:
		url: The full URL to scrape.

	Returns:
		Dict with `url` and `content`.
	"""
	scraper = Crawl4AIScraper()
	content = await scraper.scrape(url)
	return {
		"url": url,
		"content": content,
	}
