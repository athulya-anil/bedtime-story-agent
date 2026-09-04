"""GitHub API wrapper: fetch, post, resolve comments."""

import json
import os
from github import Github

from .config import BOT_USERNAME, REVIEWAI_MARKER
from .fingerprint import parse_marker


def _get_pr(repo_name: str, pr_number: int, token: str):
    g = Github(token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    return g, repo, pr


def fetch_pr_diff(repo_name: str, pr_number: int, token: str) -> list[dict]:
    """Fetch PR file patches + full content at head SHA."""
    _, repo, pr = _get_pr(repo_name, pr_number, token)
    pr_meta_extra = {
        "pr_title": pr.title,
        "pr_body": pr.body or "",
        "head_sha": pr.head.sha,
    }

    file_diffs = []
    for f in pr.get_files():
        if f.patch is None:
            continue
        # Skip non-reviewable files
        if _should_skip_file(f.filename):
            continue

        full_content = ""
        try:
            contents = repo.get_contents(f.filename, ref=pr.head.sha)
            full_content = contents.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            pass

        file_diffs.append({
            "file": f.filename,
            "patch": f.patch or "",
            "additions": f.additions,
            "deletions": f.deletions,
            "status": f.status,
            "full_content": full_content,
            "related_files": [],
        })

    # Prioritize modified files (regressions) over added files (new code), then by additions
    from .config import MAX_FILES_PER_PR
    STATUS_PRIORITY = {"modified": 0, "renamed": 1, "added": 2, "removed": 3}
    file_diffs.sort(key=lambda x: (STATUS_PRIORITY.get(x["status"], 9), -x["additions"]))
    file_diffs = file_diffs[:MAX_FILES_PER_PR]

    return file_diffs, pr_meta_extra


def _should_skip_file(filename: str) -> bool:
    skip_patterns = [
        "_pb2.py", "_pb2_grpc.py", ".min.js", ".min.css",
        "migrations/", "generated/", "vendor/", "dist/",
    ]
    skip_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
                       ".pdf", ".zip", ".tar", ".gz", ".whl", ".lock"}
    ext = os.path.splitext(filename)[1].lower()
    if ext in skip_extensions:
        return True
    return any(p in filename for p in skip_patterns)


def find_related_files(file_path: str, all_content: dict[str, str]) -> list[dict]:
    """Return up to 3 files that import or are imported by file_path."""
    base = os.path.basename(file_path).replace(".py", "")
    related = []
    for path, content in all_content.items():
        if path == file_path or not content:
            continue
        if f"import {base}" in content or f"from {base}" in content:
            related.append({"file": path, "content": content})
    return related[:3]


def get_diff_valid_lines(patch: str) -> set[int]:
    """Parse a diff patch and return the set of line numbers that appear in the diff.

    Only lines in the diff hunk can receive inline GitHub review comments.
    """
    valid_lines = set()
    current_line = 0
    for line in patch.splitlines():
        if line.startswith("@@"):
            # e.g. @@ -10,6 +10,8 @@
            import re
            m = re.search(r"\+(\d+)", line)
            if m:
                current_line = int(m.group(1)) - 1
        elif line.startswith("-"):
            pass  # removed line — not in new file
        elif line.startswith("+"):
            current_line += 1
            valid_lines.add(current_line)
        else:
            current_line += 1
    return valid_lines


def fetch_bot_comments(repo_name: str, pr_number: int, token: str) -> list[dict]:
    """Fetch all existing inline review comments posted by the bot on this PR."""
    _, _, pr = _get_pr(repo_name, pr_number, token)
    bot_comments = []
    for c in pr.get_review_comments():
        if c.user.login == BOT_USERNAME or REVIEWAI_MARKER in (c.body or ""):
            marker = parse_marker(c.body or "")
            bot_comments.append({
                "id": c.id,
                "body": c.body,
                "file": c.path,
                "line": c.line or c.position,
                "marker": marker,
            })
    return bot_comments


def fetch_bot_summary_comment(repo_name: str, pr_number: int, token: str) -> int | None:
    """Return the issue comment ID of the bot's previous summary, if any."""
    _, _, pr = _get_pr(repo_name, pr_number, token)
    for c in pr.get_issue_comments():
        if c.user.login == BOT_USERNAME and "## ReviewAI Summary" in (c.body or ""):
            return c.id
    return None


def resolve_comment(repo_name: str, comment_id: int, token: str) -> None:
    """Post a resolution reply on a review comment thread."""
    g = Github(token)
    repo = g.get_repo(repo_name)
    # We reply to the comment to signal resolution — GitHub doesn't have a
    # direct "resolve thread" API for review comments outside of GraphQL
    comment = repo.get_pull(1).get_review_comment(comment_id)  # placeholder
    # Actual resolution: delete the comment or post reply
    try:
        comment.delete()
    except Exception:
        pass


def post_inline_comment(
    repo_name: str,
    pr_number: int,
    token: str,
    commit_sha: str,
    path: str,
    line: int,
    body: str,
    start_line: int | None = None,
) -> int | None:
    """Post an inline review comment. Returns the comment ID or None on failure."""
    _, repo, pr = _get_pr(repo_name, pr_number, token)
    commit = repo.get_commit(commit_sha)
    try:
        kwargs = dict(body=body, commit=commit, path=path, line=line, side="RIGHT")
        if start_line and start_line != line:
            kwargs["start_line"] = start_line
            kwargs["start_side"] = "RIGHT"
        c = pr.create_review_comment(**kwargs)
        return c.id
    except Exception as e:
        print(f"  [post_inline_comment] failed for {path}:{line} — {e}")
        # Fallback: post as issue comment
        try:
            pr.create_issue_comment(f"**[ReviewAI]** `{path}:{line}`\n\n{body}")
        except Exception:
            pass
        return None


def post_summary_comment(
    repo_name: str,
    pr_number: int,
    token: str,
    body: str,
    previous_comment_id: int | None = None,
) -> None:
    """Post (or replace) the PR-level summary comment."""
    _, _, pr = _get_pr(repo_name, pr_number, token)
    if previous_comment_id:
        try:
            for c in pr.get_issue_comments():
                if c.id == previous_comment_id:
                    c.delete()
                    break
        except Exception:
            pass
    pr.create_issue_comment(body)


def post_suggestion_reply(
    repo_name: str,
    pr_number: int,
    token: str,
    commit_sha: str,
    path: str,
    line: int,
    in_reply_to: int,
    body: str,
) -> int | None:
    """Post a suggestion reply on an existing review comment thread."""
    _, repo, pr = _get_pr(repo_name, pr_number, token)
    commit = repo.get_commit(commit_sha)
    try:
        c = pr.create_review_comment(
            body=body,
            commit=commit,
            path=path,
            line=line,
            side="RIGHT",
            in_reply_to=in_reply_to,
        )
        return c.id
    except Exception as e:
        print(f"  [post_suggestion_reply] failed — {e}")
        return None
