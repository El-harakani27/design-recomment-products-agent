"""Chat models for the agents.

Both Hugging Face and OpenRouter expose an OpenAI-compatible endpoint, so one
client covers both and switching provider is a base-URL change. Set
`LLM_PROVIDER=huggingface` (default) or `openrouter` in .env.

Model ids differ between the two - the same model is `google/gemma-4-26B-A4B-it`
on HF and `google/gemma-4-26b-a4b-it:free` on OpenRouter - so they are listed per
provider below rather than assumed interchangeable.
"""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

PROVIDERS = {
    "huggingface": {
        "base_url": "https://router.huggingface.co/v1",
        "key_env": "HF_TOKEN",
        "orchestrator": "deepseek/deepseek-v4-flash",
        "analyzer": "google/gemma-4-26B-A4B-it",
        "searcher": "deepseek-ai/DeepSeek-V4-Flash",
        "judge": "deepseek-ai/DeepSeek-V4-Flash",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "orchestrator": "deepseek/deepseek-v4-flash",
        "analyzer": "google/gemma-4-26b-a4b-it:free",
        "searcher": "deepseek/deepseek-v4-flash",
        "judge": "deepseek/deepseek-v4-flash",
    },
}

PROVIDER = os.getenv("LLM_PROVIDER", "huggingface").lower()

# No max_tokens is set anywhere: the analyzer model reasons before it answers and
# the reasoning is billed against the same budget, so a ceiling that looks
# generous still truncates mid-thought and returns `content: None` with no error.
# The provider default is the model's own limit, which is what we want.


def _config() -> dict[str, str]:
    if PROVIDER not in PROVIDERS:
        raise ValueError(f"unknown LLM_PROVIDER {PROVIDER!r}; expected {sorted(PROVIDERS)}")
    return PROVIDERS[PROVIDER]


def chat(role: str, **overrides) -> ChatOpenAI:
    """Chat model for a pipeline role: orchestrator, analyzer, searcher or judge."""
    cfg = _config()
    if role not in cfg:
        raise ValueError(f"unknown role {role!r}")
    key = os.getenv(cfg["key_env"])
    if not key:
        raise RuntimeError(f"{cfg['key_env']} is not set (LLM_PROVIDER={PROVIDER})")

    params = {
        "model": cfg[role],
        "base_url": cfg["base_url"],
        "api_key": key,
        "temperature": 0.3,
        "timeout": 120,
        "max_retries": 4,
    }
    params.update(overrides)
    return ChatOpenAI(**params)


def image_data_uri(path: str | Path) -> str:
    """Encode a local image as a data URI.

    Inference providers fetch remote URLs server-side and are frequently blocked
    by the host (Wikimedia returns 403, for one), so uploaded bytes are sent
    inline rather than by link.
    """
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


if __name__ == "__main__":
    cfg = _config()
    print(f"provider: {PROVIDER}  ({cfg['base_url']})")
    for role in ("orchestrator", "analyzer", "searcher", "judge"):
        try:
            reply = chat(role).invoke("Reply with one word: OK")
            status = repr((reply.content or "").strip()) or "EMPTY"
        except Exception as exc:  # noqa: BLE001 - a smoke test, report and continue
            status = f"FAILED {type(exc).__name__}: {str(exc)[:70]}"
        print(f"  {role:13} {cfg[role]:32} {status}")
