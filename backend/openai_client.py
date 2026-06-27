"""OpenAI API client helpers for game agents and reports."""
from __future__ import annotations

import logging

from .config import OPENAI_API_KEY, OPENAI_FAST_MODEL, OPENAI_MODEL

LOG = logging.getLogger(__name__)


class OpenAIConfigError(RuntimeError):
    """Raised when OpenAI API is not configured for live generation."""


def is_openai_configured(fast: bool = False) -> bool:
    model = OPENAI_FAST_MODEL if fast else OPENAI_MODEL
    return bool(OPENAI_API_KEY and model)


def generate_text(
    *,
    system: str,
    user: str,
    fast: bool = False,
    max_output_tokens: int = 1200,
) -> str:
    """Generate text using OpenAI Responses API.

    The OpenAI package is imported lazily so local/demo environments without the
    dependency can still run rule-based fallback flows.
    """
    model = OPENAI_FAST_MODEL if fast else OPENAI_MODEL
    if not OPENAI_API_KEY or not model:
        raise OpenAIConfigError("OpenAI API key or model is not configured.")

    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise OpenAIConfigError("OpenAI Python SDK is not installed.") from exc

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model=model,
        instructions=system,
        input=user,
        max_output_tokens=max_output_tokens,
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        LOG.warning("OpenAI response did not include output_text")
    return text


def generate_vision_text(
    *,
    system: str,
    prompt: str,
    image_data_url: str,
    max_output_tokens: int = 1200,
) -> str:
    """Generate text from an image using OpenAI Responses API."""
    if not OPENAI_API_KEY or not OPENAI_MODEL:
        raise OpenAIConfigError("OpenAI API key or model is not configured.")

    try:
        from openai import OpenAI
    except Exception as exc:  # pragma: no cover - depends on optional env
        raise OpenAIConfigError("OpenAI Python SDK is not installed.") from exc

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=system,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
        max_output_tokens=max_output_tokens,
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        LOG.warning("OpenAI vision response did not include output_text")
    return text
