"""URL Resolver - First stage of the documentation retrieval pipeline.
Takes a package name and returns documentation URLs via DuckDuckGo search
and npm/PyPI registry lookups.
"""

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse
import httpx
from pydantic import BaseModel
from ..config import settings

logger = logging.getLogger(__name__)


class ResolvedURL(BaseModel):
    """Structured result from URL resolution."""
    
    url: str                    # the docs URL
    source: str                 # "npm", "pypi", "duckduckgo"
    package_name: str           # original package name


class URLResolver:
    """Resolves package names to their official documentation URLs."""
    
    def __init__(self):
        """Initialize the resolver with an HTTP client."""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.resolver_timeout),
            follow_redirects=True
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def resolve(
        self,
        package_name: str,
        keywords: Optional[list[str]] = None,
        version: Optional[str] = None,
    ) -> list[ResolvedURL]:
        """Resolve a package name to its documentation URL.
        
        Args:
            package_name  →  exact package name as on npm or PyPI. e.g. "react", "fastapi"
            keywords      →  list of 2-5 specific technical terms the AI extracted from 
                            the user's question. e.g. ["useEffect", "cleanup", "unmount"]
                            These are focused technical terms, not conversational phrases.
            version       →  optional string. specific version if relevant. e.g. "18", "4.0"
                            None if version doesn't. write 'latest' if Latest version is needed
        
        Returns:
            List of ResolvedURL objects if successful, empty list if all methods failed
        """
        keywords = keywords or []
        logger.info("Resolving URL for package: %s", package_name)

        # 1) DuckDuckGo search — top 5 URLs in the order returned.
        results = await self._try_duckduckgo_search(
            package_name=package_name,
            keywords=keywords,
            version=version,
        )

        # 2) npm / PyPI registry — append official link only if not already present.
        official: Optional[ResolvedURL] = None
        for registry in ["npm", "pypi"]:
            if registry == "npm":
                official, _ = await self._try_npm_candidates(package_name)
            else:
                official, _ = await self._try_pypi_candidates(package_name)

            if official:
                break

        if official:
            existing_urls = {item.url.rstrip("/").lower() for item in results}
            if official.url.rstrip("/").lower() not in existing_urls:
                results.append(official)

        return results

    async def _try_npm_candidates(
        self,
        package_name: str,
    ) -> tuple[Optional[ResolvedURL], Optional[ResolvedURL]]:
        """Resolve npm candidates as (official, fallback).
        
        Args:
            package_name: The package name
        
        Returns:
            Tuple of (official_docs_url, fallback_url)
        """
        try:
            url = f"https://registry.npmjs.org/{package_name}/latest"
            response = await self.client.get(url)
            
            if response.status_code == 404:
                logger.debug(f"Package not found on npm: {package_name}")
                return None, None
            
            response.raise_for_status()
            data = response.json()
            fallback: Optional[ResolvedURL] = None

            homepage = data.get("homepage") if isinstance(data.get("homepage"), str) else None
            repo = data.get("repository", {})
            if isinstance(repo, dict):
                repo_url = repo.get("url", "")
            elif isinstance(repo, str):
                repo_url = repo
            else:
                repo_url = ""
            bugs = data.get("bugs", {})
            bugs_url = bugs.get("url") if isinstance(bugs, dict) else None

            candidates = [
                ("homepage", homepage),
                ("repository", repo_url),
                ("bugs", bugs_url),
            ]

            for field, raw_url in candidates:
                candidate_url = self._normalize_registry_url(raw_url)
                if not candidate_url:
                    continue

                is_github = self._is_github_repo_url(candidate_url)

                # Prefer non-GitHub homepage as official docs.
                if field == "homepage" and not is_github:
                    return (
                        ResolvedURL(
                            url=candidate_url,
                            source="npm",
                            package_name=package_name,
                        ),
                        fallback,
                    )

                # If registry points to GitHub repo, try GitHub Pages as official docs.
                if is_github:
                    github_pages_url = await self._try_github_pages(candidate_url)
                    if github_pages_url:
                        return (
                            ResolvedURL(
                                url=github_pages_url,
                                source="npm",
                                package_name=package_name,
                            ),
                            fallback,
                        )

                # Store first valid registry link as last-resort fallback.
                if not fallback:
                    fallback = ResolvedURL(
                        url=candidate_url,
                        source="npm",
                        package_name=package_name,
                    )

            if not fallback:
                logger.debug(f"No URL found in npm registry for: {package_name}")
                return None, None

            return None, fallback
        
        except httpx.HTTPError as e:
            logger.debug(f"npm API request failed for {package_name}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error querying npm for {package_name}: {e}")
            return None, None

    async def _try_pypi_candidates(
        self,
        package_name: str,
    ) -> tuple[Optional[ResolvedURL], Optional[ResolvedURL]]:
        """Resolve PyPI candidates as (official, fallback).
        
        Args:
            package_name: The package name
        
        Returns:
            Tuple of (official_docs_url, fallback_url)
        """
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            response = await self.client.get(url)
            
            if response.status_code == 404:
                logger.debug(f"Package not found on PyPI: {package_name}")
                return None, None
            
            response.raise_for_status()
            data = response.json()
            
            # Only read data["info"], ignore releases
            info = data.get("info", {})
            project_urls = info.get("project_urls") or {}
            fallback: Optional[ResolvedURL] = None

            candidates = [
                ("Documentation", project_urls.get("Documentation")),
                ("Homepage", project_urls.get("Homepage")),
                ("Source", project_urls.get("Source")),
                ("home_page", info.get("home_page")),
            ]

            for field, raw_url in candidates:
                candidate_url = self._normalize_registry_url(raw_url)
                if not candidate_url:
                    continue

                is_github = self._is_github_repo_url(candidate_url)

                # Prefer explicit docs/homepage URLs from PyPI when not GitHub repo links.
                if field in {"Documentation", "Homepage"} and not is_github:
                    return (
                        ResolvedURL(
                            url=candidate_url,
                            source="pypi",
                            package_name=package_name,
                        ),
                        fallback,
                    )

                # GitHub repo URL may have an official GitHub Pages docs site.
                if is_github:
                    github_pages_url = await self._try_github_pages(candidate_url)
                    if github_pages_url:
                        return (
                            ResolvedURL(
                                url=github_pages_url,
                                source="pypi",
                                package_name=package_name,
                            ),
                            fallback,
                        )

                if not fallback:
                    fallback = ResolvedURL(
                        url=candidate_url,
                        source="pypi",
                        package_name=package_name,
                    )

            if not fallback:
                logger.debug(f"No URL found in PyPI for: {package_name}")
                return None, None

            return None, fallback
        
        except httpx.HTTPError as e:
            logger.debug(f"PyPI API request failed for {package_name}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error querying PyPI for {package_name}: {e}")
            return None, None

    def _normalize_registry_url(self, raw_url: Optional[str]) -> Optional[str]:
        """Normalize URLs returned by package registries."""
        if not raw_url or not isinstance(raw_url, str):
            return None
        return raw_url.strip().replace("git+", "").replace(".git", "")

    def _is_github_repo_url(self, url: str) -> bool:
        """Return True when URL points to a GitHub repository host."""
        host = urlparse(url).netloc.lower()
        return host == "github.com" or host.endswith(".github.com")
    
    async def _try_github_pages(self, github_url: str) -> Optional[str]:
        """Try to find GitHub Pages URL for a repository.
        
        Args:
            github_url: The GitHub repository URL
        
        Returns:
            GitHub Pages URL if it exists, None otherwise
        """
        try:
            # Parse the GitHub URL to extract user and repo
            # Expected format: https://github.com/user/repo
            parsed = urlparse(github_url)
            path_parts = parsed.path.strip("/").split("/")
            
            if len(path_parts) >= 2:
                user = path_parts[0]
                repo = path_parts[1]
                
                # Try GitHub Pages URL: https://user.github.io/repo
                pages_url = f"https://{user}.github.io/{repo}"
                
                # Quick HEAD request to check if it exists
                try:
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(settings.heuristic_timeout)
                    ) as client:
                        response = await client.head(pages_url)
                        if response.status_code in (200, 301, 302):
                            logger.info(f"Found GitHub Pages: {pages_url}")
                            return pages_url
                except httpx.HTTPError:
                    pass
        
        except Exception as e:
            logger.debug(f"Error checking GitHub Pages: {e}")
        
        return None
    
    async def _try_duckduckgo_search(
        self,
        package_name: str,
        keywords: list[str],
        version: Optional[str] = None,
    ) -> list[ResolvedURL]:
        """Search DuckDuckGo and return the top 5 URLs in the order returned."""
        try:
            query_parts = [package_name]
            if version and version.lower() != "latest":
                query_parts.append(version)
            if keywords:
                query_parts.extend(keywords)
            query_parts.extend(["official", "documentation"])
            query = " ".join(query_parts).strip()
            response = await self.client.get(
                "https://html.duckduckgo.com/html/",
                headers={"User-Agent": "Mozilla/5.0"},
                params={"q": query},
            )
            response.raise_for_status()
            html = response.text

            matches = re.findall(
                r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                html,
                flags=re.IGNORECASE | re.DOTALL,
            )

            results: list[ResolvedURL] = []
            seen: set[str] = set()

            for raw_url, _ in matches:
                if len(results) >= 5:
                    break

                url = self._extract_duckduckgo_target_url(raw_url)
                if not url or url in seen:
                    continue
                seen.add(url)

                results.append(ResolvedURL(
                    url=url,
                    source="duckduckgo",
                    package_name=package_name,
                ))

            return results

        except httpx.HTTPError as e:
            logger.error(f"DuckDuckGo request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in DuckDuckGo search: {e}")
            return []

    def _extract_duckduckgo_target_url(self, raw_url: str) -> Optional[str]:
        """Extract the target URL from DuckDuckGo redirect URLs."""
        if not raw_url:
            return None

        if raw_url.startswith("//"):
            raw_url = f"https:{raw_url}"
        elif raw_url.startswith("/"):
            raw_url = f"https://duckduckgo.com{raw_url}"

        parsed = urlparse(raw_url)

        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            query = parse_qs(parsed.query)
            target = query.get("uddg", [None])[0]
            return unquote(target) if target else None

        return raw_url


# Convenience function for one-off resolutions
async def resolve_url(
    package_name: str,
    keywords: Optional[list[str]] = None,
    version: Optional[str] = None,
) -> list[ResolvedURL]:
    """Resolve a package name to documentation URLs.
    
    Convenience function that creates a resolver, resolves the URL,
    and cleans up automatically.
    
    Returns:
        List of ResolvedURL objects (top 5 from DuckDuckGo + npm/PyPI official link if absent)
    """
    async with URLResolver() as resolver:
        return await resolver.resolve(package_name, keywords=keywords, version=version)