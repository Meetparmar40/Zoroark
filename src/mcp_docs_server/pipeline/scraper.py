"""Documentation scraper - second stage of the retrieval pipeline.

Uses Crawl4AI to fetch and extract documentation content from a URL.
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.extraction_strategy import NoExtractionStrategy

from ..config import settings
logger = logging.getLogger(__name__)


EXCLUDED_TAGS = [
	"header",
	"footer",
	"nav",
	"aside",
	"script",
	"style",
	"noscript",
	"form",
	"button",
	"svg",
	"advertisement",
]

EXCLUDED_SELECTORS = ",".join(
	[
		".sidebar",
		".toc",
		".breadcrumb",
		".pagination",
		".feedback",
		".cookie-banner",
		"[role='banner']",
		"[role='navigation']",
		"[role='complementary']",
		"[data-slot='sidebar']",
		"#table-of-contents",
		"#sidebar-content",
	]
)

NOISE_LINE_PATTERNS = (
	re.compile(r"^copy$", re.IGNORECASE),
	re.compile(r"^edit this page$", re.IGNORECASE),
	re.compile(r"^on this page$", re.IGNORECASE),
	re.compile(r"^table of contents$", re.IGNORECASE),
	re.compile(r"^was this page helpful\??$", re.IGNORECASE),
)



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
			excluded_tags=EXCLUDED_TAGS,
			excluded_selector=EXCLUDED_SELECTORS,
			exclude_external_links=True,
			exclude_social_media_links=True,
			word_count_threshold=10,
			extraction_strategy=NoExtractionStrategy(),
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

		return self._clean_markdown_text(text or "")

	def _clean_markdown_text(self, text: str) -> str:
		cleaned_lines: list[str] = []
		previous_blank = False

		for raw_line in text.splitlines():
			line = raw_line.strip()
			if not line:
				if not previous_blank and cleaned_lines:
					cleaned_lines.append("")
				previous_blank = True
				continue

			if any(pattern.match(line) for pattern in NOISE_LINE_PATTERNS):
				continue

			cleaned_lines.append(line)
			previous_blank = False

		return "\n".join(cleaned_lines).strip()


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
