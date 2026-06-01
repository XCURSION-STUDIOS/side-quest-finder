import os
from dataclasses import dataclass


OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None
    model: str
    base_url: str
    provider: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def get_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if not provider:
        provider = "gemini" if os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY") else "openai"

    if provider == "gemini":
        api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
    else:
        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")

    base_url = os.getenv("LLM_BASE_URL")
    if not base_url:
        base_url = GEMINI_BASE_URL if provider == "gemini" else OPENAI_BASE_URL

    if provider == "gemini":
        model = os.getenv("LLM_MODEL") or os.getenv("GEMINI_MODEL")
    else:
        model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    if not model:
        model = GEMINI_DEFAULT_MODEL if provider == "gemini" else OPENAI_DEFAULT_MODEL

    return LLMConfig(
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        provider=provider,
    )
