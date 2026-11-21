"""Single source of runtime configuration. Every value can be overridden in .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["extractive", "ollama", "gemini"]
EmbedProvider = Literal["hash", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- generation -------------------------------------------------------
    # "extractive" is an offline, no-LLM baseline: it works with zero setup.
    llm_provider: LLMProvider = "extractive"
    # 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and adds ~2 s per request.
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:e4b"
    # How long Ollama keeps models in (V)RAM after the last request (Ollama's own default is 5m).
    ollama_keep_alive: str = "30m"
    # Load the models when the API/eval starts, so the first question doesn't pay the cold load.
    warm_up: bool = True
    # Gemma 4 "thinks" before answering by default: ~6x more tokens for the same grounded JSON.
    ollama_think: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-4-hydrogen"
    # Gemini 3+/4 thinking level: minimal | low | medium | high | xhigh. "low" keeps grounded JSON fast.
    # Empty = model default (use empty for Gemini 2.5, which takes a budget, not a level).
    # Note: Gemini 4 Neon rejects "minimal" (HTTP 400) and ignores temperature.
    gemini_thinking_level: str = "low"
    # Local calls can be slow on first load; a hung cloud call should fail fast and fall back.
    request_timeout_s: float = 120.0
    gemini_timeout_s: float = 30.0

    # --- fallback chain ---------------------------------------------------
    # Tried in order after LLM_PROVIDER fails (network error, timeout, rate limit, invalid JSON).
    # e.g. LLM_PROVIDER=gemini + this default = gemini -> ollama -> extractive (never fails).
    llm_fallback: str = "ollama,extractive"
    # After a provider fails, skip it for this many seconds so each request doesn't wait out
    # the same timeout again (e.g. venue Wi-Fi drops mid-demo). 0 disables.
    llm_cooldown_s: float = 60.0

    # --- retrieval --------------------------------------------------------
    # "hash" is an offline bag-of-words fallback; switch to "ollama" for real embeddings.
    embed_provider: EmbedProvider = "hash"
    embed_model: str = "embeddinggemma-2:570m"
    memory_path: Path = Path("data/memory.sqlite")
    top_k: int = 5

    # --- grounding --------------------------------------------------------
    min_confidence: float = 0.5

    # --- SentinelDesk -----------------------------------------------------
    # Its own index file, so the scaffold's sample/bench indexes never mix with 22k tickets.
    sentinel_memory_path: Path = Path("data/sentinel.sqlite")
    sentinel_top_k: int = 5
    # Escalation gate thresholds (see sentinel/escalation.py for what each rule does).
    triage_confidence_min: float = 0.65
    retrieval_similarity_min: float = 0.55
    high_priority_alert_probability: float = 0.45
    # Mask emails/phones/IPs/IBANs out of the text sent to any LLM (the console still shows the original).
    mask_pii_in_prompts: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
