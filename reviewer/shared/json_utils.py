"""JSON parsing helpers."""

import json


def parse_json(text: str) -> dict | list | None:
    """Parse JSON, stripping markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if len(lines) > 2 else lines[1:]
        text = "\n".join(inner)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
