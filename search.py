"""Brave Search API wrapper."""

from typing import List, Dict
import aiohttp
import config

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"

# Simple keyword triggers for auto-search (Japanese + English)
SEARCH_TRIGGERS = [
    "調べて", "検索して", "調査して", "詳しく", "確認して",
    "search", "look up", "find", "調べろ", "検索しろ",
    "what is", "who is", "how to", "latest", "recent",
]


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


def format_results(results: List[Dict[str, str]]) -> str:
    """Format search results into a markdown block for prompts."""
    if not results:
        return "[Web検索結果]\n（検索結果はありませんでした）"

    lines = ["[Web検索結果]"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        if r["description"]:
            lines.append(f"   概要: {r['description']}")
        lines.append("")
    return "\n".join(lines)


def should_search(text: str) -> bool:
    """Check if the user message contains search triggers."""
    lower = text.lower()
    return any(trigger in lower for trigger in SEARCH_TRIGGERS)


def build_search_prompt(original_prompt: str, results: List[Dict[str, str]]) -> str:
    """Append search results to the original prompt."""
    search_block = format_results(results)
    return (
        f"{original_prompt}\n\n"
        f"{search_block}\n"
        f"上記のWeb検索結果を参考にして回答してください。"
        f"検索結果に基づかない推測は避け、確実な情報のみを述べてください。"
    )
