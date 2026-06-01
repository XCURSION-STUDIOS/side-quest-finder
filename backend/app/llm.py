import json
from typing import Any, Dict, List

import httpx

from .llm_config import get_llm_config


ACTIVITY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "activity_when": {"type": ["string", "null"]},
        "venue": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "contact": {"type": ["string", "null"]},
        "tags": {"type": "string"},
        "relevance_score": {"type": "number"},
        "accept": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["title", "summary", "activity_when", "venue", "location", "contact", "tags", "relevance_score", "accept", "reason"],
}


class LLMExtractor:
    def __init__(self):
        self.config = get_llm_config()
        self.api_key = self.config.api_key
        self.model = self.config.model
        self.enabled = self.config.enabled

    async def refine_candidates(self, candidates: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.enabled:
            return candidates

        refined = []
        async with httpx.AsyncClient(timeout=35) as client:
            for candidate in candidates[:40]:
                refined.append(await self.refine_candidate(client, candidate, context))
        return refined + candidates[40:]

    async def refine_candidate(self, client: httpx.AsyncClient, candidate: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = {
            "candidate": candidate,
            "user_context": context,
            "instruction": (
                "Extract a clean activity card. If candidate.metadata.opened_page_excerpt exists, use it as "
                "the inspected result page and prefer it over search-result snippets for date, venue, contact, "
                "summary, and quality. Reject navigation pages, cookie pages, ads, logins, stale pages, and vague non-events."
            ),
        }
        try:
            response = await client.post(
                self.config.chat_completions_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You clean and rank activity recommendations for a local discovery agent. Return only schema-valid JSON."},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "activity_card",
                            "strict": True,
                            "schema": ACTIVITY_SCHEMA,
                        },
                    },
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except Exception as exc:
            metadata = candidate.get("metadata") or {}
            metadata["llm_error"] = str(exc)[:200]
            candidate["metadata"] = metadata
            return candidate

        candidate.update({
            "title": data["title"][:180],
            "summary": data["summary"],
            "activity_when": data["activity_when"],
            "venue": data["venue"],
            "location": data["location"] or candidate.get("location"),
            "contact": data["contact"],
            "tags": data["tags"],
            "score": max(float(candidate.get("score") or 0), float(data["relevance_score"])),
        })
        metadata = candidate.get("metadata") or {}
        metadata["llm_accept"] = data["accept"]
        metadata["llm_reason"] = data["reason"]
        candidate["metadata"] = metadata
        if not data["accept"]:
            candidate["score"] = 0
        return candidate
