"""Brave Search API wrapper."""

from typing import List, Dict
import aiohttp
import config

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


async def brave_search(query: str, count: int = 5) -> List[Dict[str, str]]:
    """Perform a web search via Brave Search API."""
    if not config.BRAVE_API_KEY:
        raise ValueError("BRAVE_API_KEY is not set in environment variables.")

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": config.BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": min(count, 20),
        "offset": 0,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(BRAVE_API_URL, headers=headers, params=params) as resp:
            if resp.status == 401:
                raise ValueError("Invalid BRAVE_API_KEY (HTTP 401)")
            resp.raise_for_status()
            data = await resp.json()
            results = data.get("web", {}).get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                }
                for r in results
            ]
