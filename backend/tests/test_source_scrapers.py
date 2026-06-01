import unittest
import os
from unittest.mock import AsyncMock

from backend.app.source_scrapers import RedditScraper


class MockResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class SourceScraperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.previous_reddit_env = {
            "REDDIT_CLIENT_ID": os.environ.get("REDDIT_CLIENT_ID"),
            "REDDIT_CLIENT_SECRET": os.environ.get("REDDIT_CLIENT_SECRET"),
            "REDDIT_USER_AGENT": os.environ.get("REDDIT_USER_AGENT"),
        }
        for key in self.previous_reddit_env:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.previous_reddit_env.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value

    def test_reddit_builds_json_search_urls(self):
        scraper = RedditScraper()

        searches = scraper.build_searches("social events", "Singapore", "SG")

        self.assertGreaterEqual(len(searches), 2)
        self.assertTrue(all(search.url.startswith("https://www.reddit.com/search.json?") for search in searches))
        self.assertTrue(all("sort=new" in search.url for search in searches))
        self.assertTrue(any("subreddit%3Asingapore" in search.url for search in searches))

    async def test_reddit_json_results_become_candidates(self):
        scraper = RedditScraper()
        search = scraper.build_searches("board games", "Singapore", "SG")[0]
        client = AsyncMock()
        client.get.return_value = MockResponse({
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Board game meetup this weekend",
                            "selftext": "A casual social night for new people.",
                            "subreddit_name_prefixed": "r/singapore",
                            "permalink": "/r/singapore/comments/abc123/board_game_meetup/",
                            "num_comments": 14,
                            "stickied": False,
                        }
                    }
                ]
            }
        })

        results = await scraper.scrape(client, search, "Singapore")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "reddit")
        self.assertIn("Board game meetup", results[0]["title"])
        self.assertEqual(results[0]["link"], "https://www.reddit.com/r/singapore/comments/abc123/board_game_meetup/")
        self.assertEqual(results[0]["metadata"]["extractor"], "reddit_json")


if __name__ == "__main__":
    unittest.main()
