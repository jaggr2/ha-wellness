"""Groq vision (llama-vision) meal analysis client — OpenAI-compatible API.

Pure helpers (prompt building, response parsing) are unit-testable; the
network call uses aiohttp against Groq's OpenAI-compatible chat completions
endpoint with a base64 image_url content block.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_PROMPT = (
    "You analyze a meal photo for a food journal. "
    "Return ONLY valid JSON (no markdown fences), exactly this schema:\n"
    '{"food":[{"item":"name","amount":<number>,"amount_unit":"g",'
    '"confidence":<0-1>}],'
    '"beverages":[{"item":"name","amount":<number>,"amount_unit":"ml",'
    '"confidence":<0-1>}],'
    '"estimated_kcal_total":<number>,'
    '"estimated_kcal_per_item":[{"item":"name","kcal":<number>}],'
    '"notes":"short observation"}\n'
    "If nothing is visible, return the schema with empty lists and 0 kcal."
)


def _strip_code_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def parse_analysis(text: str) -> dict[str, Any]:
    """Parse the model's reply into the meal-analysis schema (best effort)."""
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        # try to salvage the first {...} block
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {"error": "unparseable", "raw": text[:500]}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"error": "unparseable", "raw": text[:500]}

    normalized: dict[str, Any] = {
        "food": [],
        "beverages": [],
        "estimated_kcal_total": 0,
        "estimated_kcal_per_item": [],
        "notes": "",
    }
    for item in data.get("food") or []:
        if isinstance(item, dict):
            normalized["food"].append(
                {
                    "item": str(item.get("item", "")),
                    "amount": _num(item.get("amount")),
                    "amount_unit": str(item.get("amount_unit", "g")),
                    "confidence": _num(item.get("confidence"), 0.0),
                }
            )
    for item in data.get("beverages") or []:
        if isinstance(item, dict):
            normalized["beverages"].append(
                {
                    "item": str(item.get("item", "")),
                    "amount": _num(item.get("amount")),
                    "amount_unit": str(item.get("amount_unit", "ml")),
                    "confidence": _num(item.get("confidence"), 0.0),
                }
            )
    normalized["estimated_kcal_total"] = max(0.0, _num(data.get("estimated_kcal_total")))
    for item in data.get("estimated_kcal_per_item") or []:
        if isinstance(item, dict):
            normalized["estimated_kcal_per_item"].append(
                {"item": str(item.get("item", "")), "kcal": max(0.0, _num(item.get("kcal")))}
            )
    normalized["notes"] = str(data.get("notes", ""))[:300]
    return normalized


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def image_url_data(photo_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Base64 data URL for the image_url content block."""
    b64 = base64.b64encode(photo_bytes).decode()
    return f"data:{content_type};base64,{b64}"


async def analyze_photo(
    session: Any,
    api_key: str,
    model: str,
    photo_bytes: bytes,
    prompt: str = DEFAULT_PROMPT,
    content_type: str = "image/jpeg",
    max_tokens: int = 800,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Send the photo to Groq and return the parsed meal analysis."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url_data(photo_bytes, content_type)
                        },
                    },
                ],
            }
        ],
    }
    async with session.post(
        GROQ_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    ) as response:
        if response.status != 200:
            body = (await response.text())[:500]
            raise RuntimeError(f"Groq API HTTP {response.status}: {body}")
        data = await response.json()
    content = data["choices"][0]["message"]["content"]
    return parse_analysis(content)
