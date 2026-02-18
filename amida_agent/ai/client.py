"""Anthropic Claude API wrapper."""

import logging

import anthropic

from amida_agent.config import settings

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def generate(
    system: str,
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Send a prompt to Claude and return the text response."""
    client = get_client()
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
