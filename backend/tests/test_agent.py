import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agent import (
    DEFAULT_SETTINGS,
    DiscoveryAgent,
    DiscoveryContext,
    extract_page_text,
)
from backend.app.browser_tools import browser_open_enabled, should_try_browser_open
from backend.app.llm_brain import ACTION_SCHEMA


LLM_ENV_KEYS = [
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
]


def make_agent(max_finds=3):
    settings = {**DEFAULT_SETTINGS, "maxFinds": max_finds}
    return DiscoveryAgent(DiscoveryContext(
        interests=["climbing"],
        focus=["make_friends"],
        settings=settings,
        feedback_profile={},
    ))


def make_agent_with_feedback(feedback_profile, max_finds=3):
    settings = {**DEFAULT_SETTINGS, "maxFinds": max_finds}
    return DiscoveryAgent(DiscoveryContext(
        interests=["climbing"],
        focus=["make_friends"],
        settings=settings,
        feedback_profile=feedback_profile,
    ))


def make_candidate(title, link, score=0):
    return {
        "title": title,
        "link": link,
        "source": "meetup",
        "summary": "A social climbing event in Singapore",
        "tags": "climbing social",
        "location": "Singapore",
        "metadata": {"source_url": "https://example.test/search"},
        "score": score,
    }


class AgentCoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_llm_env = {key: os.environ.get(key) for key in LLM_ENV_KEYS}
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)
            if self.previous_llm_env[key] is not None:
                os.environ[key] = self.previous_llm_env[key]

    def test_fallback_queries_include_interest_and_focus_terms(self):
        agent = make_agent()

        queries = agent.build_fallback_queries()

        self.assertIn("climbing", queries)
        self.assertIn("climbing social", queries)
        self.assertIn("climbing community", queries)

    def test_candidate_ids_and_accept_reject_decisions_are_tracked(self):
        agent = make_agent()
        candidates = [
            make_candidate("Good climbing night", "https://example.test/good"),
            make_candidate("Bad login page", "https://example.test/bad"),
        ]

        agent.assign_candidate_ids(candidates)
        accepted = agent.apply_candidate_decision(candidates, {
            "action": "accept_candidate",
            "candidate_id": "cand-1",
            "url": None,
            "reason": "Strong fit for making friends through climbing.",
        }, step=1)
        rejected = agent.apply_candidate_decision(candidates, {
            "action": "reject_candidate",
            "candidate_id": "cand-2",
            "url": None,
            "reason": "Looks like a login wall, not an activity.",
        }, step=2)

        self.assertTrue(accepted)
        self.assertTrue(rejected)
        self.assertEqual(agent.candidate_status(candidates[0]), "accepted")
        self.assertEqual(agent.candidate_status(candidates[1]), "rejected")
        self.assertIn("cand-1", agent.accepted_candidate_ids)
        self.assertIn("cand-2", agent.rejected_candidate_ids)
        self.assertEqual(candidates[0]["metadata"]["agent_decision"], "accepted")
        self.assertEqual(candidates[1]["metadata"]["agent_decision"], "rejected")

    async def test_finalize_prioritizes_agent_accepts_and_excludes_agent_rejects(self):
        agent = make_agent(max_finds=2)
        candidates = [
            make_candidate("Accepted climbing social", "https://example.test/accepted", score=0),
            make_candidate("Rejected climbing social", "https://example.test/rejected", score=100),
            make_candidate("Unreviewed climbing social", "https://example.test/unreviewed", score=4),
        ]
        agent.assign_candidate_ids(candidates)
        agent.apply_candidate_decision(candidates, {
            "action": "accept_candidate",
            "candidate_id": "cand-1",
            "url": None,
            "reason": "Agent explicitly accepted this.",
        }, step=1)
        agent.apply_candidate_decision(candidates, {
            "action": "reject_candidate",
            "candidate_id": "cand-2",
            "url": None,
            "reason": "Agent explicitly rejected this.",
        }, step=2)

        results = await agent.finalize_candidates(candidates)
        links = [item["link"] for item in results]

        self.assertIn("https://example.test/accepted", links)
        self.assertNotIn("https://example.test/rejected", links)
        self.assertLessEqual(len(results), 2)

    async def test_finalize_excludes_previously_seen_items(self):
        agent = make_agent_with_feedback({
            "seen_links": ["https://example.test/seen"],
            "seen_titles": ["seen climbing social"],
        })
        candidates = [
            make_candidate("Seen climbing social", "https://example.test/seen", score=99),
            make_candidate("Fresh climbing social", "https://example.test/fresh", score=4),
        ]
        agent.assign_candidate_ids(candidates)

        results = await agent.finalize_candidates(candidates)
        links = [item["link"] for item in results]

        self.assertNotIn("https://example.test/seen", links)
        self.assertIn("https://example.test/fresh", links)
        self.assertTrue(candidates[0]["metadata"]["seen_before"])

    def test_extract_page_text_removes_noise_and_keeps_main_content(self):
        html = """
        <html>
          <body>
            <script>bad()</script>
            <style>.hidden{}</style>
            <main>
              <h1>Friday climbing meetup</h1>
              <p>June 12, 7:00 PM at Kallang.</p>
            </main>
          </body>
        </html>
        """

        text = extract_page_text(html)

        self.assertIn("Friday climbing meetup", text)
        self.assertIn("June 12, 7:00 PM", text)
        self.assertNotIn("bad()", text)
        self.assertNotIn(".hidden", text)

    def test_action_schema_exposes_agentic_candidate_tools(self):
        actions = ACTION_SCHEMA["properties"]["action"]["enum"]

        self.assertIn("search_source", actions)
        self.assertIn("open_result", actions)
        self.assertIn("accept_candidate", actions)
        self.assertIn("reject_candidate", actions)
        self.assertIn("stop", actions)

    def test_next_unsearched_action_prefers_new_source_for_diversity(self):
        agent = make_agent()
        query_plan = [{"query": "social events", "intent": "social", "reason": "test"}]
        searched_pairs = {("meetup", "social events")}

        action = agent.next_unsearched_action(query_plan, searched_pairs, prefer_new_source={"meetup"})

        self.assertEqual(action["action"], "search_source")
        self.assertNotEqual(action["source"], "meetup")
        self.assertEqual(action["query"], "social events")

    async def test_scrape_source_errors_are_not_returned_as_candidates(self):
        agent = make_agent()
        search = {
            "source": "reddit",
            "query": "social events",
            "url": "https://example.test/reddit",
            "search": object(),
        }
        failing_scraper = AsyncMock()
        failing_scraper.scrape.side_effect = RuntimeError("blocked by source")

        with patch("backend.app.agent.SOURCE_SCRAPERS", {"reddit": failing_scraper}):
            results = await agent.scrape_source(AsyncMock(), search)

        self.assertEqual(results, [])
        self.assertEqual(agent.events[-1]["status"], "source_error")
        self.assertIn("blocked by source", agent.events[-1]["reason"])

    def test_browser_open_is_feature_flagged_and_only_for_weak_pages(self):
        os.environ.pop("XC_BROWSER_OPEN", None)
        self.assertFalse(browser_open_enabled())

        os.environ["XC_BROWSER_OPEN"] = "1"
        self.assertTrue(browser_open_enabled())
        self.assertTrue(should_try_browser_open("Enable JavaScript to continue"))
        self.assertTrue(should_try_browser_open("short page"))
        self.assertFalse(should_try_browser_open(" ".join(["detailed"] * 1000)))


if __name__ == "__main__":
    unittest.main()
