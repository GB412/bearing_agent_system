"""DeepSeek Chat Completions setup for a non-thinking tool-calling agent."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def make_deepseek_model(
    model_name: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    """Use an explicit non-thinking mode while Tool Calling is being validated.

    DeepSeek thinking+tools requires reasoning_content to be replayed exactly;
    PR-02's LangGraph adapter does not claim that support until live-tested.
    """
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for real DeepSeek API tests")
    thinking = os.environ.get("DEEPSEEK_THINKING", "disabled").lower()
    if thinking != "disabled":
        raise ValueError(
            "PR-02 supports DEEPSEEK_THINKING=disabled only. "
            "Thinking tool calls need separate reasoning_content replay validation."
        )
    model = model_name or os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=url,
        temperature=0,
        timeout=45,
        max_retries=0,  # Do not auto-replay a possibly successful tool write.
        extra_body={"thinking": {"type": "disabled"}},
    )
