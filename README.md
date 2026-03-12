# MCP Docs Server

A documentation retrieval server with URL resolution, scraping, embedding, and caching capabilities.

## Overview

This server provides a pipeline for retrieving and processing documentation for software libraries and packages:

1. **URL Resolver** - Finds official documentation URLs for packages
2. **Scraper** - Fetches and extracts documentation content
3. **Parser** - Processes and structures the content
4. **Embedder** - Creates vector embeddings for semantic search
5. **Retriever** - Searches and retrieves relevant documentation
6. **Cache** - Redis-based caching layer for performance

## Installation

```bash
# Install dependencies
pip install -e .

# Or using uv
uv pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

### Environment Variables

- `BRAVE_API_KEY` - (Optional) API key for Brave Search fallback
- `RESOLVER_TIMEOUT` - Timeout for registry API calls (default: 5 seconds)
- `HEURISTIC_TIMEOUT` - Timeout for heuristic URL checks (default: 3 seconds)
- `REDIS_HOST` - Redis server host (default: localhost)
- `REDIS_PORT` - Redis server port (default: 6379)
- `CACHE_TTL` - Cache time-to-live in seconds (default: 86400)

## Components

### URL Resolver

The URL resolver is the first stage of the pipeline. It takes a package name and returns the official documentation URL.

**Resolution Priority:**

1. **npm Registry API** - For JavaScript/TypeScript packages
2. **PyPI JSON API** - For Python packages
3. **Heuristic Patterns** - Common documentation URL patterns
4. **Brave Search API** - Last resort fallback (requires API key)

**Usage:**

```python
from mcp_docs_server.pipeline.resolver import resolve_url

# Simple usage with convenience function
result = await resolve_url("react", ecosystem="npm")
if result:
    print(f"Docs URL: {result.url}")
    print(f"Source: {result.source}")
    print(f"Confidence: {result.confidence}")

# Using the resolver class for multiple resolutions
from mcp_docs_server.pipeline.resolver import URLResolver

async with URLResolver() as resolver:
    react_docs = await resolver.resolve("react", "npm")
    fastapi_docs = await resolver.resolve("fastapi", "pypi")
    numpy_docs = await resolver.resolve("numpy")  # auto-detect
```

**Return Object:**

```python
class ResolvedURL:
    url: str                # The documentation URL
    source: str             # "npm", "pypi", "heuristic", or "brave"
    confidence: float       # 1.0 (registry) to 0.5 (search)
    is_github: bool         # True if URL is a GitHub repository
    package_name: str       # Original package name
    ecosystem: str          # "npm" or "pypi"
```

**Features:**

- ✓ Async/await support with httpx
- ✓ Concurrent heuristic checking
- ✓ GitHub Pages detection
- ✓ Automatic redirect following
- ✓ Configurable timeouts
- ✓ Comprehensive error handling
- ✓ Logging at all stages

## Testing

Run the example test script:

```bash
python examples/test_resolver.py
```

This will test URL resolution for various popular packages across npm and PyPI.

## Project Structure

```
mcp_docs_server/
├── src/
│   └── mcp_docs_server/
│       ├── __init__.py
│       ├── config.py          # Configuration management
│       ├── main.py            # Main server entry point
│       ├── cache/             # Redis caching layer
│       │   ├── __init__.py
│       │   └── redis_client.py
│       └── pipeline/          # Processing pipeline
│           ├── __init__.py
│           ├── resolver.py    # URL resolution (implemented)
│           ├── scraper.py     # Documentation scraping (TODO)
│           ├── parser.py      # Content parsing (TODO)
│           ├── embedder.py    # Vector embeddings (TODO)
│           └── retriever.py   # Search & retrieval (TODO)
├── examples/
│   └── test_resolver.py       # Resolver test script
├── pyproject.toml
├── .env.example
└── README.md
```

## Dependencies

- **httpx** - Async HTTP client
- **pydantic** - Data validation and settings
- **pydantic-settings** - Environment-based configuration
- **redis** - Caching layer

## Development

### Running Tests

```bash
# Test the resolver
python examples/test_resolver.py
```

### Adding a New Package Ecosystem

To add support for a new package registry (e.g., RubyGems, Go packages):

1. Add a new `_try_<ecosystem>` method in `URLResolver`
2. Add the ecosystem to the resolution priority in `resolve()`
3. Update the `ecosystem` field hints in `ResolvedURL`

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
# Zoroark
