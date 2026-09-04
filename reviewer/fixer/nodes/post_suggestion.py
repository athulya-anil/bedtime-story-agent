"""post_suggestion node: post suggestion reply on the review comment thread."""

import os
from ..state import CommentFixerState
from shared.github_io import post_suggestion_reply


def post_suggestion(state: CommentFixerState) -> dict:
    if not state.get("should_fix") or not state.get("fix_valid"):
        reason = state.get("skip_reason") or state.get("fix_issues") or "fix invalid"
        print(f"  [post_suggestion] skipping — {reason}")
        return {"status": "skipped"}

    token = os.environ["GH_TOKEN"]
    body = _format_suggestion(state)

    comment_id = post_suggestion_reply(
        repo_name=state["repo"],
        pr_number=state["pr_number"],
        token=token,
        commit_sha=state["commit_sha"],
        path=state["file_path"],
        line=state["line_number"],
        in_reply_to=state["comment_id"],
        body=body,
    )

    print(f"  [post_suggestion] posted reply id={comment_id}")
    return {"posted_reply_id": comment_id, "status": "posted"}


def _format_suggestion(state: CommentFixerState) -> str:
    fix_lines = state.get("proposed_fix", [])
    explanation = state.get("fix_explanation", "")
    suggestion_text = "\n".join(fix_lines)

    body = "<!-- reviewai:fix -->\n\nHere's a suggested fix:\n\n"
    if suggestion_text:
        body += f"```suggestion\n{suggestion_text}\n```\n"
    if explanation:
        body += f"\n_{explanation}_\n"
    body += "\n_Fix by ReviewAI · claude-sonnet-4-6_"
    return body
