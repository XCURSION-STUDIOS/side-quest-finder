import httpx
from bs4 import BeautifulSoup
from typing import List, Dict

class Scraper:
    """Simple scraper interface. Add more site-specific scrapers here."""
    def __init__(self, seeds: List[str] = None):
        self.seeds = seeds or []

    async def fetch(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.text

    async def scrape(self) -> List[Dict]:
        results = []
        for url in self.seeds:
            try:
                html = await self.fetch(url)
                soup = BeautifulSoup(html, "lxml")
                # Generic extraction: collect link titles
                for a in soup.find_all("a")[:20]:
                    title = (a.get_text() or "").strip()
                    href = a.get("href")
                    if not title:
                        continue
                    results.append({
                        "title": title,
                        "link": href,
                        "source": url,
                        "tags": None,
                        "summary": None,
                    })
            except Exception:
                continue
        return results
