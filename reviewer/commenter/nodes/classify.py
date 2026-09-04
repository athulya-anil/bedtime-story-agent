"""classify_and_threshold node: tag comments and apply confidence thresholds."""

from anthropic import Anthropic

from ..state import CommenterState
from ..prompts.classify import build_classify_prompt
from shared.config import SUPPRESSED_CATEGORIES, CONFIDENCE_THRESHOLDS
from shared.json_utils import parse_json


def classify_and_threshold(state: CommenterState) -> dict:
    raw = state.get("raw_comments", [])
    if not raw:
        return {"filtered_comments": [], "status": "classified"}

    # Step 1: Refine category tags via Haiku
    tagged = _classify_comments(raw)

    # Step 2: Suppress blocked categories
    after_suppress = [
        c for c in tagged
        if _get_coarse_category(c.get("category_tag", "")) not in SUPPRESSED_CATEGORIES
    ]

    # Step 3: Apply per-assistant per-category confidence thresholds
    after_threshold = []
    for c in after_suppress:
        assistant = c.get("assistant", "standard")
        coarse = _get_coarse_category(c.get("category_tag", c.get("category", "")))
        thresholds = CONFIDENCE_THRESHOLDS.get(assistant, {})
        min_conf = thresholds.get(coarse, 3)
        if c.get("confidence", 0) >= min_conf:
            after_threshold.append(c)

    suppressed = len(raw) - len(after_suppress)
    threshold_dropped = len(after_suppress) - len(after_threshold)
    print(f"  [classify] {len(raw)} raw → {suppressed} suppressed → {threshold_dropped} below threshold → {len(after_threshold)} remaining")

    return {"filtered_comments": after_threshold, "status": "classified"}


def _classify_comments(comments: list[dict]) -> list[dict]:
    """Refine category_tag for each comment using Haiku."""
    if not comments:
        return comments

    prompt = build_classify_prompt(comments)
    try:
        client = Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        result = parse_json(text)

        if isinstance(result, list):
            for item in result:
                idx = item.get("index")
                tag = item.get("category_tag", "")
                if isinstance(idx, int) and 0 <= idx < len(comments) and tag:
                    comments[idx] = {**comments[idx], "category_tag": tag}
    except Exception as e:
        print(f"  [classify] Haiku classifier error: {e}")

    return comments


def _get_coarse_category(category_tag: str) -> str:
    return category_tag.split(":")[0] if ":" in category_tag else category_tag
