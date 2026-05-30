import json
import os
from typing import Any, Dict, List

import httpx


QUERY_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string"},
                    "intent": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["query", "intent", "reason"],
            },
        },
    },
    "required": ["queries"],
}

RANKING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "accept": {"type": "boolean"},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "accept", "score", "reason"],
            },
        },
    },
    "required": ["decisions"],
}

ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["search_source", "open_result", "stop"]},
        "source": {"type": ["string", "null"]},
        "query": {"type": ["string", "null"]},
        "candidate_id": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["action", "source", "query", "candidate_id", "url", "reason"],
}


class LLMAgentBrain:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.enabled = bool(self.api_key)

    async def plan_queries(self, context: Dict[str, Any], fallback_queries: List[str]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return fallback_plan(fallback_queries, "deterministic fallback query")

        prompt = {
            "user_context": context,
            "fallback_queries": fallback_queries,
            "instruction": (
                "Create search queries for a hobby/community discovery agent. The user wants real activities, "
                "clubs, classes, communities, volunteering, sports, social groups, faith groups, or events. "
                "Use natural terms that event sites, Reddit posts, and organiser pages are likely to contain. "
                "Make the plan personal to the user's interests, goals, location, and past feedback."
            ),
        }
        try:
            data = await self.request_schema(
                name="query_plan",
                schema=QUERY_PLAN_SCHEMA,
                system_prompt="You plan searches for a personalised local discovery agent. Return only valid JSON.",
                prompt=prompt,
            )
        except Exception:
            return fallback_plan(fallback_queries, "LLM query planning unavailable")

        planned = []
        for item in data.get("queries", []):
            query = " ".join(str(item.get("query") or "").split())
            if not query:
                continue
            planned.append({
                "query": query[:140],
                "intent": str(item.get("intent") or "discovery")[:120],
                "reason": str(item.get("reason") or "LLM planned query")[:240],
            })
        return planned[:16] or fallback_plan(fallback_queries, "LLM returned no usable queries")

    async def rank_candidates(self, candidates: List[Dict[str, Any]], context: Dict[str, Any], max_items: int) -> List[Dict[str, Any]]:
        if not self.enabled or not candidates:
            return candidates

        ranked_candidates = candidates[:70]
        payload = []
        for index, candidate in enumerate(ranked_candidates):
            candidate["_rank_id"] = f"c{index}"
            payload.append({
                "id": candidate["_rank_id"],
                "title": candidate.get("title"),
                "source": candidate.get("source"),
                "summary": candidate.get("summary"),
                "when": candidate.get("activity_when"),
                "location": candidate.get("location"),
                "tags": candidate.get("tags"),
                "score": candidate.get("score"),
            })

        prompt = {
            "user_context": context,
            "max_items": max_items,
            "candidates": payload,
            "instruction": (
                "Judge these candidates comparatively for this specific user. Accept only likely real, useful "
                "activities or communities. Penalise weak matches, generic pages, stale pages, login walls, "
                "spam, and items that do not support the user's purpose."
            ),
        }
        try:
            data = await self.request_schema(
                name="candidate_ranking",
                schema=RANKING_SCHEMA,
                system_prompt="You rank local activity recommendations for personal fit. Return only valid JSON.",
                prompt=prompt,
            )
        except Exception as exc:
            for candidate in candidates:
                metadata = candidate.get("metadata") or {}
                metadata["llm_ranking_error"] = str(exc)[:200]
                candidate["metadata"] = metadata
            return candidates

        decisions = {item.get("id"): item for item in data.get("decisions", [])}
        for candidate in ranked_candidates:
            decision = decisions.get(candidate.get("_rank_id"))
            if not decision:
                continue
            metadata = candidate.get("metadata") or {}
            metadata["llm_rank_accept"] = bool(decision["accept"])
            metadata["llm_ranking_reason"] = str(decision["reason"])[:260]
            candidate["metadata"] = metadata
            candidate["score"] = max(float(candidate.get("score") or 0), float(decision["score"]))
            if not decision["accept"]:
                candidate["score"] = 0
        return candidates

    async def choose_action(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any],
        enabled_sources: List[str],
        query_plan: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"action": "stop", "source": None, "query": None, "candidate_id": None, "url": None, "reason": "LLM action loop unavailable"}

        prompt = {
            "user_context": context,
            "state": state,
            "enabled_sources": enabled_sources,
            "query_plan": query_plan,
            "instruction": (
                "Choose exactly one next action for the discovery agent. Use search_source when another "
                "targeted search is likely to improve the result pool. Use open_result when an unopened "
                "candidate looks promising and inspecting the page could confirm date, venue, contact, or "
                "quality. Use stop when enough promising candidates have been inspected/found, the budget is "
                "nearly spent, or remaining actions look repetitive. Avoid repeating searched_pairs and avoid "
                "opening candidate ids listed in opened_candidate_ids."
            ),
        }
        try:
            data = await self.request_schema(
                name="agent_action",
                schema=ACTION_SCHEMA,
                system_prompt="You control one step of a local discovery agent. Return only valid JSON.",
                prompt=prompt,
            )
        except Exception as exc:
            return {"action": "stop", "source": None, "query": None, "candidate_id": None, "url": None, "reason": f"LLM action choice failed: {str(exc)[:160]}"}

        action = data.get("action")
        source = data.get("source")
        query = data.get("query")
        candidate_id = data.get("candidate_id")
        url = data.get("url")
        if action == "open_result":
            if not candidate_id and not url:
                return {"action": "stop", "source": None, "query": None, "candidate_id": None, "url": None, "reason": "LLM chose open_result without a candidate"}
            return {
                "action": "open_result",
                "source": None,
                "query": None,
                "candidate_id": str(candidate_id) if candidate_id else None,
                "url": str(url) if url else None,
                "reason": str(data.get("reason") or "LLM selected a result to inspect")[:240],
            }
        if action != "search_source":
            return {"action": "stop", "source": None, "query": None, "candidate_id": None, "url": None, "reason": data.get("reason") or "LLM chose to stop"}
        if source not in enabled_sources or not query:
            return {"action": "stop", "source": None, "query": None, "candidate_id": None, "url": None, "reason": "LLM chose an unavailable source or empty query"}
        return {
            "action": "search_source",
            "source": str(source),
            "query": " ".join(str(query).split())[:140],
            "candidate_id": None,
            "url": None,
            "reason": str(data.get("reason") or "LLM selected next source/query")[:240],
        }

    async def request_schema(self, name: str, schema: Dict[str, Any], system_prompt: str, prompt: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": name,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                },
            )
            response.raise_for_status()
            return json.loads(response.json()["choices"][0]["message"]["content"])


def fallback_plan(queries: List[str], reason: str) -> List[Dict[str, Any]]:
    return [
        {"query": query, "intent": "fallback", "reason": reason}
        for query in queries
    ]
