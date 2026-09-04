"""resolve_stale node: dismiss previously-posted comments whose issues are fixed."""

import os

from ..state import CommenterState
from shared.github_io import fetch_bot_comments, resolve_comment


def resolve_stale(state: CommenterState) -> dict:
    meta = state["pr_metadata"]
    token = os.environ["GH_TOKEN"]
    current_fingerprints = {c.get("fingerprint") for c in state.get("filtered_comments", []) if c.get("fingerprint")}

    existing = fetch_bot_comments(meta["repo"], meta["pr_number"], token)
    resolved_ids = []

    for bot_comment in existing:
        marker = bot_comment.get("marker")
        if not marker:
            continue
        fingerprint = marker.get("fingerprint")
        if fingerprint and fingerprint not in current_fingerprints:
            # Issue no longer found — it was fixed
            try:
                resolve_comment(meta["repo"], bot_comment["id"], token)
                resolved_ids.append(bot_comment["id"])
                print(f"  [resolve_stale] resolved comment {bot_comment['id']} (fingerprint={fingerprint})")
            except Exception as e:
                print(f"  [resolve_stale] failed to resolve {bot_comment['id']}: {e}")

    # Remove already-posted fingerprints from current comments to avoid double-posting
    existing_fingerprints = {
        bot_comment.get("marker", {}).get("fingerprint")
        for bot_comment in existing
        if bot_comment.get("marker")
    }
    deduplicated = [
        c for c in state.get("filtered_comments", [])
        if c.get("fingerprint") not in existing_fingerprints
    ]

    print(f"  [resolve_stale] {len(resolved_ids)} resolved, {len(state.get('filtered_comments', [])) - len(deduplicated)} already posted")
    return {
        "filtered_comments": deduplicated,
        "resolved_comment_ids": resolved_ids,
        "status": "stale_resolved",
    }
