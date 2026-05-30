from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup


DEFAULT_SETTINGS = {
    "dailySummary": True,
    "maxFinds": 10,
    "locationFocus": "SG",
    "discoveryMode": "balanced",
    "enabledSources": ["meetup", "eventbrite", "reddit", "peatix", "timeout"],
    "searchPosture": "recent_public",
    "qualityFilter": "strict",
    "testingMode": False,
}

COUNTRY_NAMES = {
    "SG": "Singapore",
    "US": "United States",
    "GB": "United Kingdom",
    "MY": "Malaysia",
    "ID": "Indonesia",
    "AU": "Australia",
    "CA": "Canada",
}

PURPOSE_TERMS = {
    "make_friends": ["social", "community", "new friends", "club", "group"],
    "dating": ["singles", "social mixer", "dating", "speed dating"],
    "fitness": ["training", "run", "fitness", "sports", "workout"],
    "use_time": ["workshop", "class", "things to do", "weekend", "activity"],
    "give_back": ["volunteer", "charity", "mutual aid", "community service"],
    "learn": ["class", "course", "workshop", "skill", "beginner"],
}

SOURCE_TEMPLATES = [
    {
        "name": "meetup",
        "url": "https://www.meetup.com/find/?keywords={query}&location={location}",
    },
    {
        "name": "eventbrite",
        "url": "https://www.eventbrite.com/d/{location_slug}/{query_slug}/",
    },
    {
        "name": "reddit",
        "url": "https://www.reddit.com/search/?q={query}%20{location}",
    },
    {
        "name": "peatix",
        "url": "https://peatix.com/search?q={query}&country={country}",
    },
    {
        "name": "timeout",
        "url": "https://www.timeout.com/{location_slug}/search?q={query}",
    },
]


@dataclass
class DiscoveryContext:
    interests: List[str]
    focus: List[str]
    settings: Dict[str, Any]
    feedback_profile: Dict[str, Any] = None

    @property
    def location_code(self) -> str:
        return str(self.settings.get("locationFocus") or "SG").upper()

    @property
    def location_name(self) -> str:
        return COUNTRY_NAMES.get(self.location_code, self.location_code)

    @property
    def max_finds(self) -> int:
        try:
            return max(1, min(int(self.settings.get("maxFinds", 10)), 25))
        except (TypeError, ValueError):
            return 10

    @property
    def discovery_mode(self) -> str:
        return str(self.settings.get("discoveryMode") or "balanced")

    @property
    def enabled_sources(self) -> List[str]:
        sources = self.settings.get("enabledSources") or DEFAULT_SETTINGS["enabledSources"]
        if not isinstance(sources, list):
            return DEFAULT_SETTINGS["enabledSources"]
        return [str(source) for source in sources]

    @property
    def quality_filter(self) -> str:
        return str(self.settings.get("qualityFilter") or "strict")


class DiscoveryAgent:
    def __init__(self, context: DiscoveryContext):
        self.context = context

    def build_queries(self) -> List[str]:
        base_terms = self.context.interests or ["clubs", "communities", "activities"]
        purpose_terms = []
        for focus in self.context.focus:
            purpose_terms.extend(PURPOSE_TERMS.get(focus, []))

        if not purpose_terms:
            purpose_terms = PURPOSE_TERMS["make_friends"][:2]

        queries = []
        for term in base_terms:
            queries.append(term)
            for purpose in purpose_terms[:2]:
                queries.append(f"{term} {purpose}")

        if self.context.discovery_mode == "wide":
            queries.extend(["meetups", "community events", "weekend activities"])
        elif self.context.discovery_mode == "precise":
            queries = queries[: max(4, len(base_terms))]

        return dedupe(queries)[:12]

    def build_source_urls(self) -> List[Dict[str, str]]:
        urls = []
        location = self.context.location_name
        location_slug = slug(location)
        country = self.context.location_code.lower()

        for query in self.build_queries():
            for template in SOURCE_TEMPLATES:
                if template["name"] not in self.context.enabled_sources:
                    continue
                urls.append({
                    "source": template["name"],
                    "query": query,
                    "url": template["url"].format(
                        query=quote_plus(query),
                        query_slug=slug(query),
                        location=quote_plus(location),
                        location_slug=location_slug,
                        country=country,
                    ),
                })

        return urls

    async def run(self) -> List[Dict[str, Any]]:
        candidates = []
        source_urls = self.build_source_urls()
        per_run_limit = 70 if self.context.discovery_mode == "wide" else 45

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "XCursionStudiosBot/0.1 (+local prototype)"},
        ) as client:
            for source in source_urls[:per_run_limit]:
                candidates.extend(await self.scrape_source(client, source))

        scored = [self.score_candidate(candidate) for candidate in candidates]
        scored = [candidate for candidate in scored if candidate["score"] > 0]
        scored = sorted(scored, key=lambda candidate: candidate["score"], reverse=True)

        return dedupe_candidates(scored)[: self.context.max_finds]

    async def scrape_source(self, client: httpx.AsyncClient, source: Dict[str, str]) -> List[Dict[str, Any]]:
        try:
            response = await client.get(source["url"])
            response.raise_for_status()
        except Exception as exc:
            return [{
                "title": f"{source['source']} search unavailable for {source['query']}",
                "link": source["url"],
                "source": source["source"],
                "summary": str(exc)[:180],
                "tags": source["query"],
                "metadata": {"status": "source_error", "query": source["query"]},
                "score": 0,
            }]

        soup = BeautifulSoup(response.text, "lxml")
        results = []
        for anchor in soup.find_all("a")[:80]:
            title = clean_text(anchor.get_text(" ", strip=True))
            href = anchor.get("href")
            if not title or len(title) < 8 or not href:
                continue

            link = urljoin(source["url"], href)
            nearby = clean_text(anchor.parent.get_text(" ", strip=True) if anchor.parent else "")
            results.append({
                "title": title[:180],
                "link": link,
                "source": source["source"],
                "summary": nearby[:320] if nearby and nearby != title else None,
                "tags": source["query"],
                "activity_when": extract_when(nearby),
                "venue": None,
                "location": self.context.location_name,
                "contact": None,
                "metadata": {"query": source["query"], "source_url": source["url"]},
                "score": 0,
            })

        return results

    def score_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        text = " ".join(filter(None, [
            candidate.get("title"),
            candidate.get("summary"),
            candidate.get("tags"),
            candidate.get("source"),
        ])).lower()

        score = 0.2
        for interest in self.context.interests:
            if interest.lower() in text:
                score += 2.5

        for focus in self.context.focus:
            for term in PURPOSE_TERMS.get(focus, []):
                if term.lower() in text:
                    score += 1.0

        if self.context.location_name.lower() in text:
            score += 0.7
        if candidate.get("activity_when"):
            score += 0.7
        if any(word in text for word in ["event", "club", "meetup", "workshop", "class", "volunteer"]):
            score += 0.8

        feedback_profile = self.context.feedback_profile or {}
        source_weights = feedback_profile.get("source_weights", {})
        term_weights = feedback_profile.get("term_weights", {})
        score += float(source_weights.get(candidate.get("source"), 0))
        for term, weight in term_weights.items():
            if term and term in text:
                score += float(weight)

        bad_terms = ["cookie", "privacy policy", "log in", "sign up", "advertise"]
        if self.context.quality_filter == "strict":
            bad_terms.extend(["subscribe", "terms", "404", "all rights reserved"])
        if any(bad in text for bad in bad_terms):
            score -= 2.5

        candidate["score"] = round(max(score, 0), 2)
        return candidate


def clean_text(value: Optional[str]) -> str:
    return " ".join((value or "").split())


def slug(value: str) -> str:
    return quote_plus(value.strip().lower().replace(" ", "-"))


def dedupe(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for candidate in candidates:
        key = (candidate.get("title", "").lower(), candidate.get("link", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def extract_when(text: Optional[str]) -> Optional[str]:
    text = clean_text(text)
    if not text:
        return None

    markers = ["today", "tomorrow", "sat", "sun", "mon", "tue", "wed", "thu", "fri", "2026"]
    lowered = text.lower()
    if not any(marker in lowered for marker in markers):
        return None

    return text[:120]
