from dataclasses import dataclass
import os
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class SourceSearch:
    source: str
    query: str
    url: str


class SourceScraper:
    name = "generic"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        raise NotImplementedError

    async def scrape(self, client: httpx.AsyncClient, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        response = await client.get(search.url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return self.extract(soup, search, location_name)

    def extract(self, soup: BeautifulSoup, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        results = []
        for anchor in soup.find_all("a")[:100]:
            title = clean_text(anchor.get_text(" ", strip=True))
            href = anchor.get("href")
            if not title or len(title) < 8 or not href:
                continue
            link = urljoin(search.url, href)
            nearby = clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else "")
            results.append(candidate(
                title=title,
                link=link,
                source=search.source,
                query=search.query,
                summary=nearby if nearby != title else None,
                location=location_name,
                source_url=search.url,
            ))
        return results


class MeetupScraper(SourceScraper):
    name = "meetup"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        return [SourceSearch(
            source=self.name,
            query=query,
            url=f"https://www.meetup.com/find/?keywords={quote_plus(query)}&location={quote_plus(location_name)}",
        )]

    def extract(self, soup: BeautifulSoup, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        anchors = soup.select("a[href*='/events/'], a[href*='/find/'], a[href*='meetup.com']")
        return extract_from_anchors(anchors, search, location_name)


class EventbriteScraper(SourceScraper):
    name = "eventbrite"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        return [SourceSearch(
            source=self.name,
            query=query,
            url=f"https://www.eventbrite.com/d/{slug(location_name)}/{slug(query)}/",
        )]

    async def scrape(self, client: httpx.AsyncClient, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        token = os.getenv("EVENTBRITE_TOKEN")
        if not token:
            return await super().scrape(client, search, location_name)

        response = await client.get(
            "https://www.eventbriteapi.com/v3/events/search/",
            params={"q": search.query, "location.address": location_name, "sort_by": "date"},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        events = response.json().get("events", [])
        return [
            candidate(
                title=(event.get("name") or {}).get("text") or "Untitled Eventbrite event",
                link=(event.get("url") or search.url),
                source=search.source,
                query=search.query,
                summary=(event.get("description") or {}).get("text") or "",
                location=location_name,
                source_url=search.url,
                activity_when=((event.get("start") or {}).get("local")),
                venue=None,
                extractor="eventbrite_api",
            )
            for event in events[:20]
        ]

    def extract(self, soup: BeautifulSoup, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        anchors = soup.select("a[href*='/e/'], a[href*='eventbrite']")
        return extract_from_anchors(anchors, search, location_name)


class RedditScraper(SourceScraper):
    name = "reddit"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        searches = [
            f"{query} {location_name} meetup club community",
            f"{query} events friends activities {location_name}",
        ]
        if location_code.upper() == "SG":
            searches.append(f"subreddit:singapore {query} meetup club")

        return [SourceSearch(source=self.name, query=query, url=reddit_search_url(value)) for value in searches]

    async def scrape(self, client: httpx.AsyncClient, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        token = await reddit_access_token(client)
        if token:
            response = await client.get(
                "https://oauth.reddit.com/search",
                params={"q": reddit_query_from_url(search.url), "sort": "new", "limit": 25},
                headers=reddit_headers(token),
            )
            response.raise_for_status()
            return reddit_json_candidates(response.json(), search, location_name, "reddit_oauth")

        try:
            response = await client.get(search.url, headers=reddit_headers())
            response.raise_for_status()
            return reddit_json_candidates(response.json(), search, location_name, "reddit_json")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise

        response = await client.get(reddit_old_search_url(reddit_query_from_url(search.url)), headers=reddit_headers())
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        return self.extract(soup, SourceSearch(search.source, search.query, response.url.human_repr()), location_name)

    def extract(self, soup: BeautifulSoup, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        anchors = soup.select("a[href*='/comments/'], a[href*='/r/']")
        return extract_from_anchors(anchors, search, location_name)


class PeatixScraper(SourceScraper):
    name = "peatix"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        return [SourceSearch(
            source=self.name,
            query=query,
            url=f"https://peatix.com/search?q={quote_plus(query)}&country={location_code.lower()}",
        )]

    def extract(self, soup: BeautifulSoup, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
        anchors = soup.select("a[href*='event'], a[href*='peatix']")
        return extract_from_anchors(anchors, search, location_name)


class TimeoutScraper(SourceScraper):
    name = "timeout"

    def build_searches(self, query: str, location_name: str, location_code: str) -> List[SourceSearch]:
        return [SourceSearch(
            source=self.name,
            query=query,
            url=f"https://www.timeout.com/{slug(location_name)}/search?q={quote_plus(query)}",
        )]


SOURCE_SCRAPERS = {
    scraper.name: scraper
    for scraper in [MeetupScraper(), EventbriteScraper(), RedditScraper(), PeatixScraper(), TimeoutScraper()]
}


def extract_from_anchors(anchors, search: SourceSearch, location_name: str) -> List[Dict[str, Any]]:
    results = []
    for anchor in anchors[:80]:
        title = clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href")
        if not title or len(title) < 8 or not href:
            continue
        link = urljoin(search.url, href)
        nearby = clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else "")
        results.append(candidate(
            title=title,
            link=link,
            source=search.source,
            query=search.query,
            summary=nearby if nearby and nearby != title else None,
            location=location_name,
            source_url=search.url,
        ))
    return results


def candidate(
    title: str,
    link: str,
    source: str,
    query: str,
    summary: str,
    location: str,
    source_url: str,
    activity_when=None,
    venue=None,
    extractor=None,
):
    return {
        "title": title[:180],
        "link": link,
        "source": source,
        "summary": (summary or "")[:420] or None,
        "tags": query,
        "activity_when": activity_when or extract_when(summary),
        "venue": venue,
        "location": location,
        "contact": None,
        "metadata": {"query": query, "source_url": source_url, "extractor": extractor or source},
        "score": 0,
    }


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def slug(value: str) -> str:
    return quote_plus(value.strip().lower().replace(" ", "-"))


def reddit_search_url(query: str) -> str:
    return f"https://www.reddit.com/search.json?q={quote_plus(query)}&sort=new&limit=25"


def reddit_old_search_url(query: str) -> str:
    return f"https://old.reddit.com/search?q={quote_plus(query)}&sort=new"


def reddit_query_from_url(url: str) -> str:
    return parse_qs(urlparse(url).query).get("q", [""])[0]


def reddit_headers(token: str = None) -> Dict[str, str]:
    headers = {
        "User-Agent": os.getenv("REDDIT_USER_AGENT", "SideQuestFinder/0.1 by XCursionStudios"),
        "Accept": "application/json,text/html",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def reddit_access_token(client: httpx.AsyncClient) -> str:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return ""

    response = await client.post(
        "https://www.reddit.com/api/v1/access_token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers=reddit_headers(),
    )
    response.raise_for_status()
    return response.json().get("access_token") or ""


def reddit_json_candidates(data: Dict[str, Any], search: SourceSearch, location_name: str, extractor: str) -> List[Dict[str, Any]]:
    children = data.get("data", {}).get("children", [])
    results = []
    for child in children[:25]:
        post = child.get("data") or {}
        title = clean_text(post.get("title"))
        if not title or post.get("stickied"):
            continue
        summary = clean_text(" ".join(filter(None, [
            post.get("selftext"),
            post.get("subreddit_name_prefixed"),
            f"{post.get('num_comments') or 0} comments",
        ])))
        permalink = post.get("permalink") or ""
        if not permalink:
            continue
        results.append(candidate(
            title=title,
            link=urljoin("https://www.reddit.com", permalink),
            source=search.source,
            query=search.query,
            summary=summary,
            location=location_name,
            source_url=search.url,
            activity_when=None,
            venue=None,
            extractor=extractor,
        ))
    return results


def extract_when(text: str):
    text = clean_text(text)
    markers = ["today", "tomorrow", "sat", "sun", "mon", "tue", "wed", "thu", "fri", "2026"]
    if text and any(marker in text.lower() for marker in markers):
        return text[:120]
    return None
