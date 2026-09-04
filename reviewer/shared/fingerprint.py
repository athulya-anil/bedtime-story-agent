"""Comment fingerprint: stable hash for stale comment resolution."""

import hashlib
import re


def make_fingerprint(file: str, category: str, comment: str) -> str:
    """Return a short hex hash of (file, category, normalized_comment).

    Used to match previously-posted comments against new findings.
    Normalization strips punctuation and lowercases so minor rephrasing
    does not create a new fingerprint.
    """
    normalized = re.sub(r"[^a-z0-9 ]", "", comment.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    raw = f"{file}|{category}|{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_marker(comment_body: str) -> dict | None:
    """Extract the reviewai JSON marker from a comment body.

    Markers look like: <!-- reviewai:finding:{"fingerprint":"abc","tag":"x"} -->
    Returns the parsed dict or None if not found.
    """
    import json
    match = re.search(r"<!-- reviewai:finding:(\{.*?\}) -->", comment_body)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
