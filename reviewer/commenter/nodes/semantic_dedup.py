"""semantic_dedup node: merge overlapping findings."""

from collections import defaultdict

from anthropic import Anthropic

from ..state import CommenterState
from ..prompts.classify import build_dedup_prompt
from shared.json_utils import parse_json

LINE_PROXIMITY = 3
HAIKU_DEDUP_THRESHOLD = 5  # use LLM dedup for files with more than this many comments


def semantic_dedup(state: CommenterState) -> dict:
    comments = state.get("filtered_comments", [])
    if not comments:
        return {"filtered_comments": [], "status": "deduped"}

    by_file: dict[str, list] = defaultdict(list)
    for c in comments:
        by_file[c["file"]].append(c)

    result = []
    for file, file_comments in by_file.items():
        if len(file_comments) <= HAIKU_DEDUP_THRESHOLD:
            result.extend(_proximity_dedup(file_comments))
        else:
            result.extend(_llm_dedup(file, file_comments))

    print(f"  [semantic_dedup] {len(result)}/{len(comments)} comment(s) after dedup")
    return {"filtered_comments": result, "status": "deduped"}


def _proximity_dedup(comments: list) -> list:
    """Keep highest-confidence comment per ±3 line cluster."""
    sorted_comments = sorted(comments, key=lambda c: (-c.get("confidence", 0), c.get("line", 0)))
    kept = []
    for comment in sorted_comments:
        line = comment.get("line", 0)
        is_dup = any(abs(line - k.get("line", 0)) <= LINE_PROXIMITY for k in kept)
        if not is_dup:
            kept.append(comment)
    return kept


def _llm_dedup(file: str, comments: list) -> list:
    """Use Haiku to cluster semantically overlapping comments."""
    prompt = build_dedup_prompt(file, comments)
    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        result = parse_json(text)
        if result and "kept" in result and isinstance(result["kept"], list):
            return result["kept"]
    except Exception as e:
        print(f"  [semantic_dedup] LLM dedup error for {file}: {e}")

    return _proximity_dedup(comments)
