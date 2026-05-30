from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from .llm import LLMExtractor
from .source_scrapers import SOURCE_SCRAPERS


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
        self.events = []

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
        searches = []
        for query in self.build_queries():
            for source_name in self.context.enabled_sources:
                scraper = SOURCE_SCRAPERS.get(source_name)
                if not scraper:
                    continue
                searches.extend(scraper.build_searches(query, self.context.location_name, self.context.location_code))

        return [{"source": search.source, "query": search.query, "url": search.url, "search": search} for search in searches]

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
                scraped = await self.scrape_source(client, source)
                candidates.extend(scraped)

        scored = [self.score_candidate(candidate) for candidate in candidates]
        scored = await LLMExtractor().refine_candidates(scored, {
            "interests": self.context.interests,
            "focus": self.context.focus,
            "settings": self.context.settings,
        })
        scored = [self.score_candidate(candidate) for candidate in scored]
        scored = [candidate for candidate in scored if candidate["score"] > 0]
        scored = sorted(scored, key=lambda candidate: candidate["score"], reverse=True)

        accepted = dedupe_candidates(scored)[: self.context.max_finds]
        accepted_keys = {(item.get("title", "").lower(), item.get("link", "")) for item in accepted}
        for candidate in candidates:
            key = (candidate.get("title", "").lower(), candidate.get("link", ""))
            accepted_candidate = key in accepted_keys
            self.events.append({
                "source": candidate.get("source"),
                "query": candidate.get("tags"),
                "url": (candidate.get("metadata") or {}).get("source_url"),
                "status": "accepted" if accepted_candidate else "rejected",
                "reason": build_acceptance_reason(candidate, accepted_candidate),
                "item_title": candidate.get("title"),
                "item_link": candidate.get("link"),
                "score": candidate.get("score", 0),
                "metadata": candidate.get("metadata") or {},
            })

        return accepted

    async def scrape_source(self, client: httpx.AsyncClient, source: Dict[str, str]) -> List[Dict[str, Any]]:
        scraper = SOURCE_SCRAPERS.get(source["source"])
        self.events.append({
            "source": source["source"],
            "query": source["query"],
            "url": source["url"],
            "status": "searched",
            "reason": "source-specific scraper scheduled",
            "metadata": {},
        })
        if not scraper:
            return []
        try:
            results = await scraper.scrape(client, source["search"], self.context.location_name)
            self.events.append({
                "source": source["source"],
                "query": source["query"],
                "url": source["url"],
                "status": "candidates_found",
                "reason": f"{len(results)} raw candidates extracted",
                "metadata": {"count": len(results)},
            })
            return results
        except Exception as exc:
            self.events.append({
                "source": source["source"],
                "query": source["query"],
                "url": source["url"],
                "status": "source_error",
                "reason": str(exc)[:240],
                "metadata": {},
            })
            return [{
                "title": f"{source['source']} search unavailable for {source['query']}",
                "link": source["url"],
                "source": source["source"],
                "summary": str(exc)[:180],
                "tags": source["query"],
                "metadata": {"status": "source_error", "query": source["query"]},
                "score": 0,
            }]

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


def build_acceptance_reason(candidate: Dict[str, Any], accepted: bool) -> str:
    metadata = candidate.get("metadata") or {}
    if metadata.get("llm_reason"):
        return metadata["llm_reason"]
    if accepted:
        return "high enough score after interest, focus, source, and feedback weighting"
    if candidate.get("score", 0) <= 0:
        return "filtered out by low score or quality rules"
    return "not selected because higher-ranked candidates filled the daily limit"
