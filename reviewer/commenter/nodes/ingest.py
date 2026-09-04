"""Ingest node: fetch PR diff, full file content, related files."""

import os
from ..state import CommenterState
from shared.github_io import fetch_pr_diff, find_related_files


def ingest(state: CommenterState) -> dict:
    meta = state["pr_metadata"]
    token = os.environ["GH_TOKEN"]

    file_diffs, extra = fetch_pr_diff(meta["repo"], meta["pr_number"], token)

    # Update pr_metadata with PR title/body fetched from GitHub
    updated_meta = {**meta, **extra}

    # Build content map for cross-file relationship lookup
    all_content = {fd["file"]: fd["full_content"] for fd in file_diffs}

    for fd in file_diffs:
        fd["related_files"] = find_related_files(fd["file"], all_content)

    print(f"  [ingest] {len(file_diffs)} reviewable file(s)")
    return {"file_diffs": file_diffs, "pr_metadata": updated_meta, "status": "ingested"}
