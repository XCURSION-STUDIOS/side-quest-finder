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
