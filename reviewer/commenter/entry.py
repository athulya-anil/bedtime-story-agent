"""Commenter entrypoint."""

import os
import sys


def main() -> dict:
    repo = os.environ.get("REPO", "").strip()
    pr_number_raw = os.environ.get("PR_NUMBER", "").strip()
    commit_sha = os.environ.get("COMMIT_SHA", "").strip()
    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"

    if not repo:
        print("ERROR: REPO env var required", file=sys.stderr)
        sys.exit(1)
    if not pr_number_raw:
        print("ERROR: PR_NUMBER env var required", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("GH_TOKEN"):
        print("ERROR: GH_TOKEN env var required", file=sys.stderr)
        sys.exit(1)
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    try:
        pr_number = int(pr_number_raw)
    except ValueError:
        print(f"ERROR: PR_NUMBER must be integer, got: {pr_number_raw!r}", file=sys.stderr)
        sys.exit(1)

    from .graph import graph

    initial_state = {
        "pr_metadata": {
            "repo": repo,
            "pr_number": pr_number,
            "commit_sha": commit_sha,
        },
        "dry_run": dry_run,
        "raw_comments": [],
        "filtered_comments": [],
        "resolved_comment_ids": [],
        "posted_comment_ids": [],
    }

    print(f"ReviewAI Commenter")
    print(f"  Repo:      {repo}")
    print(f"  PR:        #{pr_number}")
    print(f"  Commit:    {commit_sha[:8] if commit_sha else 'unknown'}")
    print(f"  Dry-run:   {dry_run}")
    print()

    result = graph.invoke(initial_state)
    print(f"\nDone. Status: {result.get('status')}")
    return result


if __name__ == "__main__":
    main()
