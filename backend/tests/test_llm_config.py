import os
import unittest

from backend.app.llm_config import (
    GEMINI_BASE_URL,
    GEMINI_DEFAULT_MODEL,
    OPENAI_BASE_URL,
    OPENAI_DEFAULT_MODEL,
    get_llm_config,
)


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


class LLMConfigTests(unittest.TestCase):
    def setUp(self):
        self.previous_env = {key: os.environ.get(key) for key in LLM_ENV_KEYS}
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key in LLM_ENV_KEYS:
            os.environ.pop(key, None)
            if self.previous_env[key] is not None:
                os.environ[key] = self.previous_env[key]

    def test_openai_key_keeps_openai_defaults(self):
        os.environ["OPENAI_API_KEY"] = "openai-test-key"

        config = get_llm_config()

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.api_key, "openai-test-key")
        self.assertEqual(config.model, OPENAI_DEFAULT_MODEL)
        self.assertEqual(config.base_url, OPENAI_BASE_URL)
        self.assertEqual(config.chat_completions_url, f"{OPENAI_BASE_URL}/chat/completions")

    def test_gemini_key_selects_gemini_defaults(self):
        os.environ["GEMINI_API_KEY"] = "gemini-test-key"
        os.environ["OPENAI_MODEL"] = "should-not-win-for-gemini"

        config = get_llm_config()

        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.api_key, "gemini-test-key")
        self.assertEqual(config.model, GEMINI_DEFAULT_MODEL)
        self.assertEqual(config.base_url, GEMINI_BASE_URL)
        self.assertEqual(config.chat_completions_url, f"{GEMINI_BASE_URL}/chat/completions")

    def test_explicit_llm_settings_override_provider_defaults(self):
        os.environ["LLM_PROVIDER"] = "gemini"
        os.environ["LLM_API_KEY"] = "custom-key"
        os.environ["LLM_MODEL"] = "gemini-custom"
        os.environ["LLM_BASE_URL"] = "https://example.test/openai/"
        os.environ["OPENAI_API_KEY"] = "ignored-openai-key"

        config = get_llm_config()

        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.api_key, "custom-key")
        self.assertEqual(config.model, "gemini-custom")
        self.assertEqual(config.base_url, "https://example.test/openai")
        self.assertEqual(config.chat_completions_url, "https://example.test/openai/chat/completions")


if __name__ == "__main__":
    unittest.main()
