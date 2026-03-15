import os

os.environ["FASTMCP_LOG_LEVEL"] = "ERROR"
os.environ["PYTHONUTF8"] = "1"

"""MCP Documentation Server — exposes resolve_docs and scrape_page tools."""

from typing import Optional
from fastmcp import FastMCP

try:
    from .pipeline.resolver import URLResolver
    from .pipeline.scraper import scrape_page as _scrape_page
except ImportError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from mcp_docs_server.pipeline.resolver import URLResolver
    from mcp_docs_server.pipeline.scraper import scrape_page as _scrape_page

mcp = FastMCP("docs-server")

@mcp.tool()
async def resolve_docs(
    package_name: str,
    keywords: Optional[list[str]] = None,
    version: Optional[str] = None,
) -> list[dict]:
    """Find documentation URLs for a package.

    Returns up to 5 URLs from DuckDuckGo search (in order) plus the official
    npm/PyPI link if it is not already in the list.  Pick the most relevant URL
    from the results and pass it to the `scrape_page` tool to read the content.

    Args:
        package_name: Exact package name as on npm or PyPI (e.g. "react", "fastapi").
        keywords: 2-5 specific technical terms from the user question
                  (e.g. ["useEffect", "cleanup", "unmount"]).
        version: Optional version string (e.g. "18", "4.0"). Omit if irrelevant.

    Returns:
        A list of dicts, each with `url`, `source`, and `package_name`.
    """
    async with URLResolver() as resolver:
        results = await resolver.resolve(
            package_name, keywords=keywords, version=version
        )
    return [r.model_dump() for r in results]


@mcp.tool()
async def scrape_page(url: str) -> dict:
    """Scrape a documentation page and return its content as markdown.

    Use this after `resolve_docs` to fetch the actual content of a chosen URL.

    Args:
        url: The full URL to scrape (typically from `resolve_docs` results).

    Returns:
        A dict with `url` and `content` (markdown text of the page).
    """
    return await _scrape_page(url)


import sys
# Proxy sys.stdout to sys.stderr to stop Crawl4AI and other libs from corrupting JSON-RPC,
# but keep sys.stdout.buffer pointing to the real stdout so FastMCP can communicate.
class StdoutProxy:
    def __init__(self, original, target):
        self.original = original
        self.target = target
        self.buffer = original.buffer
    def write(self, s):
        return self.target.write(s)
    def flush(self):
        self.target.flush()
        self.original.flush()
    def __getattr__(self, attr):
        return getattr(self.original, attr)
        
sys.stdout = StdoutProxy(sys.stdout, sys.stderr)

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "http":
        port = int(os.getenv("MCP_PORT", "8000"))
        mcp.run(transport="http", port=port)
    else:
        mcp.run(transport="stdio")