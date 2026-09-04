"""GitHub API wrapper: fetch PR diffs + file content, post inline comments."""

import os
from github import Github


def fetch_pr_diff(repo_name: str, pr_number: int, token: str) -> list[dict]:
    """Fetch PR file patches + full content of each changed file.

    Returns a list of dicts:
      {file, patch, additions, deletions, status, full_content, related_files}
    related_files is populated separately by find_related_files().
    """
    g = Github(token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    file_diffs = []
    for f in pr.get_files():
        if f.patch is None:
            # Binary file or rename-only — skip, no text to review
            continue

        # Fetch the full file content at the head commit
        full_content = ""
        try:
            contents = repo.get_contents(f.filename, ref=pr.head.sha)
            full_content = contents.decoded_content.decode("utf-8", errors="replace")
        except Exception:
            pass  # Deleted or inaccessible file — leave empty

        file_diffs.append({
            "file": f.filename,
            "patch": f.patch or "",
            "additions": f.additions,
            "deletions": f.deletions,
            "status": f.status,           # added | modified | removed | renamed
            "full_content": full_content,
            "related_files": [],           # populated by ingest node
        })

    return file_diffs


def find_related_files(file_path: str, all_content: dict[str, str]) -> list[dict]:
    """Return up to 3 files that import or are imported by file_path.

    Uses a simple string-search heuristic — good enough for Python files
    in a small repo without running a full AST parser.
    """
    base = os.path.basename(file_path).replace(".py", "")
    related = []

    for path, content in all_content.items():
        if path == file_path or not content:
            continue
        if f"import {base}" in content or f"from {base}" in content:
            related.append({"file": path, "content": content})

    # Cap at 3 to keep context size manageable
    return related[:3]


def post_inline_comment(
    repo_name: str,
    pr_number: int,
    token: str,
    commit_sha: str,
    path: str,
    line: int,
    body: str,
) -> None:
    """Post an inline review comment on a PR.

    Built for v2 — not called in v1 dry-run mode.
    """
    g = Github(token)
try:
    commit = repo.get_commit(commit_sha)
    pr.create_review_comment(body=body, commit=commit, path=path, line=line)
except Exception as e:
    raise RuntimeError(f"Failed to post comment for {commit_sha} on {path}:{line}") from e
    pr = repo.get_pull(pr_number)
    commit = repo.get_commit(commit_sha)
    pr.create_review_comment(body=body, commit=commit, path=path, line=line)
