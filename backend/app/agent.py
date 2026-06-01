from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from .browser_tools import browser_open_enabled, browser_open_text, should_try_browser_open
from .llm import LLMExtractor
from .llm_brain import LLMAgentBrain
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

FALLBACK_PURPOSE_TERMS = {
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
        self.query_plan = None
        self.candidate_counter = 0
        self.opened_candidate_ids = set()
        self.accepted_candidate_ids = set()
        self.rejected_candidate_ids = set()
        self.candidate_statuses = {}

    def build_fallback_queries(self) -> List[str]:
        base_terms = self.context.interests or ["clubs", "communities", "activities"]
        purpose_terms = []
        for focus in self.context.focus:
            purpose_terms.extend(FALLBACK_PURPOSE_TERMS.get(focus, []))

        if not purpose_terms:
            purpose_terms = FALLBACK_PURPOSE_TERMS["make_friends"][:2]

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

    async def build_query_plan(self) -> List[Dict[str, Any]]:
        fallback_queries = self.build_fallback_queries()
        brain = LLMAgentBrain()
        plan = await brain.plan_queries(self.llm_context(), fallback_queries)
        self.query_plan = plan
        for entry in plan:
            self.events.append({
                "query": entry["query"],
                "status": "planned_query",
                "reason": entry.get("reason"),
                "metadata": {"intent": entry.get("intent"), "llm_enabled": brain.enabled},
            })
        return plan

    def build_queries(self) -> List[str]:
        if self.query_plan:
            return [entry["query"] for entry in self.query_plan]
        return self.build_fallback_queries()

    async def build_source_urls(self) -> List[Dict[str, str]]:
        searches = []
        query_plan = self.query_plan or await self.build_query_plan()
        for entry in query_plan:
            query = entry["query"]
            for source_name in self.context.enabled_sources:
                scraper = SOURCE_SCRAPERS.get(source_name)
                if not scraper:
                    continue
                searches.extend(scraper.build_searches(query, self.context.location_name, self.context.location_code))

        return [{"source": search.source, "query": search.query, "url": search.url, "search": search} for search in searches]

    async def run(self) -> List[Dict[str, Any]]:
        brain = LLMAgentBrain()
        if brain.enabled:
            candidates = await self.run_agentic_search(brain)
        else:
            candidates = await self.run_fixed_search()

        return await self.finalize_candidates(candidates)

    async def run_fixed_search(self) -> List[Dict[str, Any]]:
        candidates = []
        source_urls = await self.build_source_urls()
        per_run_limit = 70 if self.context.discovery_mode == "wide" else 45

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "XCursionStudiosBot/0.1 (+local prototype)"},
        ) as client:
            for source in source_urls[:per_run_limit]:
                scraped = await self.scrape_source(client, source)
                candidates.extend(scraped)

        return candidates

    async def run_agentic_search(self, brain: LLMAgentBrain) -> List[Dict[str, Any]]:
        candidates = []
        query_plan = self.query_plan or await self.build_query_plan()
        searched_pairs = set()
        observations = []
        max_tool_calls = self.tool_budget()

        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "XCursionStudiosBot/0.1 (+local prototype)"},
        ) as client:
            for step in range(max_tool_calls):
                action = await brain.choose_action(
                    self.llm_context(),
                    self.agent_state(candidates, observations, searched_pairs, step, max_tool_calls),
                    self.available_sources(),
                    query_plan,
                )
                if action["action"] == "open_result":
                    opened = await self.open_result(client, candidates, action, step + 1)
                    observations.append({
                        "step": step + 1,
                        "tool": "open_result",
                        "candidate_id": action.get("candidate_id"),
                        "opened": opened,
                    })
                    continue

                if action["action"] in {"accept_candidate", "reject_candidate"}:
                    decided = self.apply_candidate_decision(candidates, action, step + 1)
                    observations.append({
                        "step": step + 1,
                        "tool": action["action"],
                        "candidate_id": action.get("candidate_id"),
                        "decided": decided,
                    })
                    if len(self.accepted_candidate_ids) >= self.context.max_finds:
                        self.events.append({
                            "status": "agent_stop",
                            "reason": "Accepted enough candidates for this run.",
                            "metadata": {"step": step + 1, "accepted_count": len(self.accepted_candidate_ids)},
                        })
                        break
                    continue

                if action["action"] != "search_source":
                    self.events.append({
                        "status": "agent_stop",
                        "reason": action.get("reason"),
                        "metadata": {"step": step, "candidate_count": len(candidates)},
                    })
                    break

                pair = (action["source"], action["query"].lower())
                if pair in searched_pairs:
                    fallback = self.next_unsearched_action(query_plan, searched_pairs)
                    if not fallback:
                        self.events.append({
                            "status": "agent_stop",
                            "reason": "No unsearched source/query pairs remain.",
                            "metadata": {"step": step, "candidate_count": len(candidates)},
                        })
                        break
                    action = fallback
                    pair = (action["source"], action["query"].lower())

                searched_pairs.add(pair)
                self.events.append({
                    "source": action["source"],
                    "query": action["query"],
                    "status": "agent_action",
                    "reason": action.get("reason"),
                    "metadata": {"step": step + 1, "tool": "search_source"},
                })
                search_items = self.source_searches(action["source"], action["query"])
                before_count = len(candidates)
                for source in search_items:
                    scraped = await self.scrape_source(client, source)
                    self.assign_candidate_ids(scraped)
                    candidates.extend(scraped)
                found_count = len(candidates) - before_count
                observations.append({
                    "step": step + 1,
                    "source": action["source"],
                    "query": action["query"],
                    "found": found_count,
                })
                if len(candidates) >= self.context.max_finds * 6 and step >= 4:
                    self.events.append({
                        "status": "agent_stop",
                        "reason": "Candidate budget reached; moving to extraction and ranking.",
                        "metadata": {"step": step + 1, "candidate_count": len(candidates)},
                    })
                    break

        return candidates

    def apply_candidate_decision(self, candidates: List[Dict[str, Any]], action: Dict[str, Any], step: int) -> bool:
        candidate = self.find_candidate(candidates, action.get("candidate_id"), action.get("url"))
        if not candidate:
            self.events.append({
                "status": "decision_error",
                "reason": "Agent tried to decide on a candidate that is no longer available.",
                "url": action.get("url"),
                "metadata": {"step": step, "candidate_id": action.get("candidate_id"), "action": action.get("action")},
            })
            return False

        candidate_id = candidate.get("_agent_id")
        decision = "accepted" if action["action"] == "accept_candidate" else "rejected"
        if candidate_id in self.accepted_candidate_ids or candidate_id in self.rejected_candidate_ids:
            self.events.append({
                "source": candidate.get("source"),
                "status": "decision_skipped",
                "reason": "Candidate already has an agent decision.",
                "item_title": candidate.get("title"),
                "item_link": candidate.get("link"),
                "metadata": {"step": step, "candidate_id": candidate_id, "decision": self.candidate_statuses.get(candidate_id)},
            })
            return False

        metadata = candidate.get("metadata") or {}
        metadata["agent_decision"] = decision
        metadata["agent_decision_reason"] = action.get("reason")
        candidate["metadata"] = metadata
        self.candidate_statuses[candidate_id] = decision
        if decision == "accepted":
            self.accepted_candidate_ids.add(candidate_id)
            candidate["score"] = max(float(candidate.get("score") or 0), 9.0)
        else:
            self.rejected_candidate_ids.add(candidate_id)
            candidate["score"] = 0

        self.events.append({
            "source": candidate.get("source"),
            "query": candidate.get("tags"),
            "url": candidate.get("link"),
            "status": f"candidate_{decision}",
            "reason": action.get("reason"),
            "item_title": candidate.get("title"),
            "item_link": candidate.get("link"),
            "score": candidate.get("score", 0),
            "metadata": {"step": step, "candidate_id": candidate_id},
        })
        return True

    async def open_result(self, client: httpx.AsyncClient, candidates: List[Dict[str, Any]], action: Dict[str, Any], step: int) -> bool:
        candidate = self.find_candidate(candidates, action.get("candidate_id"), action.get("url"))
        if not candidate:
            self.events.append({
                "status": "open_error",
                "reason": "Agent tried to open a candidate that is no longer available.",
                "url": action.get("url"),
                "metadata": {"step": step, "candidate_id": action.get("candidate_id")},
            })
            return False

        candidate_id = candidate.get("_agent_id")
        if candidate_id in self.opened_candidate_ids:
            self.events.append({
                "source": candidate.get("source"),
                "status": "open_skipped",
                "reason": "Candidate already opened during this run.",
                "item_title": candidate.get("title"),
                "item_link": candidate.get("link"),
                "metadata": {"step": step, "candidate_id": candidate_id},
            })
            return False

        url = candidate.get("link")
        self.events.append({
            "source": candidate.get("source"),
            "query": candidate.get("tags"),
            "url": url,
            "status": "agent_action",
            "reason": action.get("reason"),
            "item_title": candidate.get("title"),
            "item_link": url,
            "metadata": {"step": step, "tool": "open_result", "candidate_id": candidate_id},
        })
        try:
            response = await client.get(url)
            response.raise_for_status()
            page_text = extract_page_text(response.text)
        except Exception as exc:
            self.events.append({
                "source": candidate.get("source"),
                "query": candidate.get("tags"),
                "url": url,
                "status": "open_error",
                "reason": str(exc)[:240],
                "item_title": candidate.get("title"),
                "item_link": url,
                "metadata": {"step": step, "candidate_id": candidate_id},
            })
            self.opened_candidate_ids.add(candidate_id)
            return False

        if browser_open_enabled() and should_try_browser_open(page_text):
            try:
                browser_result = await browser_open_text(url)
                browser_text = browser_result.get("text") or ""
                if len(browser_text) > len(page_text):
                    page_text = browser_text
                    url = browser_result.get("url") or url
                self.events.append({
                    "source": candidate.get("source"),
                    "query": candidate.get("tags"),
                    "url": url,
                    "status": "browser_opened_result",
                    "reason": f"Browser fallback captured {len(browser_text)} visible text characters.",
                    "item_title": candidate.get("title"),
                    "item_link": candidate.get("link"),
                    "metadata": {"step": step, "candidate_id": candidate_id, "page_chars": len(browser_text)},
                })
            except Exception as exc:
                self.events.append({
                    "source": candidate.get("source"),
                    "query": candidate.get("tags"),
                    "url": url,
                    "status": "browser_open_error",
                    "reason": str(exc)[:240],
                    "item_title": candidate.get("title"),
                    "item_link": candidate.get("link"),
                    "metadata": {"step": step, "candidate_id": candidate_id},
                })

        metadata = candidate.get("metadata") or {}
        metadata["opened_url"] = url
        metadata["opened_page_excerpt"] = page_text[:5000]
        metadata["opened_page_chars"] = len(page_text)
        candidate["metadata"] = metadata
        if page_text and not candidate.get("summary"):
            candidate["summary"] = page_text[:420]

        self.opened_candidate_ids.add(candidate_id)
        self.events.append({
            "source": candidate.get("source"),
            "query": candidate.get("tags"),
            "url": url,
            "status": "opened_result",
            "reason": f"Opened result page and captured {len(page_text)} text characters.",
            "item_title": candidate.get("title"),
            "item_link": url,
            "metadata": {"step": step, "candidate_id": candidate_id, "page_chars": len(page_text)},
        })
        return True

    async def finalize_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scored = [self.score_candidate(candidate) for candidate in candidates if self.candidate_status(candidate) != "rejected"]
        scored = await LLMExtractor().refine_candidates(scored, {
            **self.llm_context(),
            "phase": "extract_activity_cards",
        })
        scored = [self.score_candidate(candidate) for candidate in scored]
        scored = await LLMAgentBrain().rank_candidates(scored, self.llm_context(), self.context.max_finds)
        agent_accepted = [candidate for candidate in scored if self.candidate_status(candidate) == "accepted"]
        for candidate in agent_accepted:
            candidate["score"] = max(float(candidate.get("score") or 0), 9.0)
        ranked_pool = [
            candidate
            for candidate in scored
            if candidate["score"] > 0 and self.candidate_status(candidate) not in {"accepted", "rejected"}
        ]
        ranked_pool = sorted(ranked_pool, key=lambda candidate: candidate["score"], reverse=True)

        accepted = dedupe_candidates(agent_accepted + ranked_pool)[: self.context.max_finds]
        accepted_keys = {(item.get("title", "").lower(), item.get("link", "")) for item in accepted}
        for candidate in candidates:
            key = (candidate.get("title", "").lower(), candidate.get("link", ""))
            accepted_candidate = key in accepted_keys
            status = "accepted" if accepted_candidate else "rejected"
            if self.candidate_status(candidate) == "rejected":
                status = "rejected"
            self.events.append({
                "source": candidate.get("source"),
                "query": candidate.get("tags"),
                "url": (candidate.get("metadata") or {}).get("source_url"),
                "status": status,
                "reason": build_acceptance_reason(candidate, accepted_candidate),
                "item_title": candidate.get("title"),
                "item_link": candidate.get("link"),
                "score": candidate.get("score", 0),
                "metadata": candidate.get("metadata") or {},
            })

        return accepted

    def candidate_status(self, candidate: Dict[str, Any]) -> Optional[str]:
        candidate_id = candidate.get("_agent_id") or (candidate.get("metadata") or {}).get("agent_candidate_id")
        return self.candidate_statuses.get(candidate_id)

    def tool_budget(self) -> int:
        if self.context.discovery_mode == "wide":
            return 18
        if self.context.discovery_mode == "precise":
            return 8
        return 12

    def available_sources(self) -> List[str]:
        return [source for source in self.context.enabled_sources if source in SOURCE_SCRAPERS]

    def source_searches(self, source_name: str, query: str) -> List[Dict[str, str]]:
        scraper = SOURCE_SCRAPERS.get(source_name)
        if not scraper:
            return []
        searches = scraper.build_searches(query, self.context.location_name, self.context.location_code)
        return [{"source": search.source, "query": search.query, "url": search.url, "search": search} for search in searches]

    def assign_candidate_ids(self, candidates: List[Dict[str, Any]]):
        for candidate in candidates:
            if candidate.get("_agent_id"):
                continue
            self.candidate_counter += 1
            candidate_id = f"cand-{self.candidate_counter}"
            candidate["_agent_id"] = candidate_id
            metadata = candidate.get("metadata") or {}
            metadata["agent_candidate_id"] = candidate_id
            candidate["metadata"] = metadata
            self.candidate_statuses[candidate_id] = "new"

    def find_candidate(self, candidates: List[Dict[str, Any]], candidate_id: Optional[str], url: Optional[str]):
        for candidate in candidates:
            if candidate_id and candidate.get("_agent_id") == candidate_id:
                return candidate
            if url and candidate.get("link") == url:
                return candidate
        return None

    def next_unsearched_action(self, query_plan: List[Dict[str, Any]], searched_pairs: set) -> Optional[Dict[str, str]]:
        for entry in query_plan:
            query = entry["query"]
            for source in self.available_sources():
                if (source, query.lower()) not in searched_pairs:
                    return {
                        "action": "search_source",
                        "source": source,
                        "query": query,
                        "reason": "Fallback selected the next unsearched planned query.",
                    }
        return None

    def agent_state(self, candidates, observations, searched_pairs, step, max_tool_calls) -> Dict[str, Any]:
        top_candidates = sorted(
            [self.score_candidate(dict(candidate)) for candidate in candidates[-30:]],
            key=lambda candidate: candidate.get("score", 0),
            reverse=True,
        )[:8]
        return {
            "step": step + 1,
            "max_tool_calls": max_tool_calls,
            "candidate_count": len(candidates),
            "accepted_target": self.context.max_finds,
            "searched_pairs": [f"{source}:{query}" for source, query in sorted(searched_pairs)][-24:],
            "opened_candidate_ids": sorted(self.opened_candidate_ids)[-24:],
            "accepted_candidate_ids": sorted(self.accepted_candidate_ids)[-24:],
            "rejected_candidate_ids": sorted(self.rejected_candidate_ids)[-24:],
            "accepted_count": len(self.accepted_candidate_ids),
            "rejected_count": len(self.rejected_candidate_ids),
            "recent_observations": observations[-8:],
            "openable_candidates": [
                {
                    "id": candidate.get("_agent_id"),
                    "title": candidate.get("title"),
                    "source": candidate.get("source"),
                    "url": candidate.get("link"),
                    "summary": candidate.get("summary"),
                    "score": candidate.get("score"),
                }
                for candidate in top_candidates
                if candidate.get("_agent_id") and self.candidate_status(candidate) not in {"accepted", "rejected"}
            ][:8],
            "top_candidate_snapshots": [
                {
                    "title": candidate.get("title"),
                    "source": candidate.get("source"),
                    "tags": candidate.get("tags"),
                    "score": candidate.get("score"),
                }
                for candidate in top_candidates
            ],
        }

    def llm_context(self) -> Dict[str, Any]:
        return {
            "interests": self.context.interests,
            "focus": self.context.focus,
            "settings": self.context.settings,
            "location": self.context.location_name,
            "feedback_profile": self.context.feedback_profile or {},
        }

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
            for term in FALLBACK_PURPOSE_TERMS.get(focus, []):
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

        metadata = candidate.get("metadata") or {}
        if metadata.get("agent_decision") == "accepted":
            score += 5
        elif metadata.get("agent_decision") == "rejected":
            score = 0

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
    if metadata.get("agent_decision_reason"):
        return metadata["agent_decision_reason"]
    if metadata.get("llm_ranking_reason"):
        return metadata["llm_ranking_reason"]
    if metadata.get("llm_reason"):
        return metadata["llm_reason"]
    if accepted:
        return "high enough score after interest, focus, source, and feedback weighting"
    if candidate.get("score", 0) <= 0:
        return "filtered out by low score or quality rules"
    return "not selected because higher-ranked candidates filled the daily limit"


def extract_page_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    return clean_text(main.get_text(" ", strip=True))[:12000]
