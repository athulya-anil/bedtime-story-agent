"""post_comments node: post inline GitHub PR comments with suggestion blocks."""

import json
import os

from ..state import CommenterState
from shared.github_io import post_inline_comment, get_diff_valid_lines


def post_comments(state: CommenterState) -> dict:
    comments = state.get("filtered_comments", [])
    meta = state["pr_metadata"]
    dry_run = state.get("dry_run", True)
    token = os.environ["GH_TOKEN"]

    # Build diff-valid line sets per file for GitHub API compliance
    diff_valid: dict[str, set[int]] = {}
    for fd in state.get("file_diffs", []):
        diff_valid[fd["file"]] = get_diff_valid_lines(fd.get("patch", ""))

    posted_ids = []
    for c in comments:
        body = _format_comment(c)

        if dry_run:
            print(f"  [DRY-RUN] {c['file']}:{c.get('line')} [{c.get('category_tag')}] conf={c.get('confidence')}")
            continue

        # Validate line is in diff
        file_valid_lines = diff_valid.get(c["file"], set())
        line = c.get("line", 1)
        start_line = c.get("suggestion_start_line")

        # Remap to nearest valid line if needed
        if line not in file_valid_lines and file_valid_lines:
            nearest = min(file_valid_lines, key=lambda l: abs(l - line))
            if abs(nearest - line) <= 5:
                line = nearest
            else:
                line = None  # will fall back to file-level

        comment_id = post_inline_comment(
            repo_name=meta["repo"],
            pr_number=meta["pr_number"],
            token=token,
            commit_sha=meta["commit_sha"],
            path=c["file"],
            line=line or 1,
            body=body,
            start_line=start_line,
        )
        if comment_id:
            posted_ids.append(comment_id)

    print(f"  [post_comments] {'dry-run' if dry_run else 'posted'} {len(comments)} comment(s)")
    return {"posted_comment_ids": posted_ids, "status": "posted"}


def _format_comment(c: dict) -> str:
    tag = c.get("category_tag", c.get("category", "unknown"))
    conf = c.get("confidence", 0)
    text = c.get("comment", "")
    suggestion = c.get("suggestion_lines", [])
    fingerprint = c.get("fingerprint", "")

    body = (
        f'<!-- reviewai:finding:{{"fingerprint":"{fingerprint}","tag":"{tag}"}} -->\n\n'
        f"**[{tag}]** · confidence {conf}/5\n\n"
        f"{text}\n"
    )

    if suggestion:
        suggestion_text = "\n".join(suggestion)
        body += f"\n```suggestion\n{suggestion_text}\n```\n"

    body += "\n_Reviewed by ReviewAI · [Report false positive](../../issues/new?labels=reviewai:fp&title=False+positive)_"
    return body
