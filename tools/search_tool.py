"""
Web search tool for research/Q&A. Free, no API key needed.
"""
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException


def web_search(query, max_results=5, retries=3):
    """Returns a list of {title, snippet, url} dicts.
    DuckDuckGo rate-limits automated requests fairly aggressively, so this
    retries a couple of times with a short delay before giving up."""
    for attempt in range(retries):
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        {
                            "title": r.get("title", ""),
                            "snippet": r.get("body", ""),
                            "url": r.get("href", ""),
                        }
                    )
            return results
        except RatelimitException:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
        except DDGSException:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            break

    return [
        {
            "title": "Search temporarily unavailable",
            "snippet": "Web search is being rate-limited right now. Try again in a minute.",
            "url": "",
        }
    ]


if __name__ == "__main__":
    for r in web_search("latest AI agent frameworks 2026"):
        print(r["title"], "-", r["url"])
