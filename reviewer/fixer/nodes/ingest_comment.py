"""ingest_comment node: parse GitHub event, apply bot-loop guards."""

import os
from ..state import CommentFixerState
from shared.config import BOT_USERNAME, REVIEWAI_MARKER


def ingest_comment(state: CommentFixerState) -> dict:
    comment_user = state.get("comment_user", "")
    comment_body = state.get("comment_body", "")

    # Guard 1: comment is from the bot itself
    if comment_user == BOT_USERNAME:
        print(f"  [ingest_comment] skipping — comment from bot")
        return {"should_fix": False, "skip_reason": "bot_comment"}

    # Guard 2: comment body contains a ReviewAI marker (bot's own output)
    if REVIEWAI_MARKER in comment_body:
        print(f"  [ingest_comment] skipping — ReviewAI marker found in body")
        return {"should_fix": False, "skip_reason": "reviewai_output"}

    # Guard 3: empty comment
    if not comment_body.strip():
        return {"should_fix": False, "skip_reason": "empty_comment"}

    print(f"  [ingest_comment] will fix comment from {comment_user} on {state.get('file_path')}:{state.get('line_number')}")
    return {"should_fix": True}
