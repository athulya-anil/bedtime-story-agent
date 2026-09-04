"""Fixer entrypoint."""

import json
import os
import sys


def main() -> dict:
    repo = os.environ.get("REPO", "").strip()
    pr_number_raw = os.environ.get("PR_NUMBER", "").strip()
    comment_id_raw = os.environ.get("COMMENT_ID", "").strip()
    comment_body = os.environ.get("COMMENT_BODY", "").strip()
    file_path = os.environ.get("COMMENT_PATH", "").strip()
    line_raw = os.environ.get("COMMENT_LINE", "0").strip()
    comment_user = os.environ.get("COMMENT_USER", "").strip()
    commit_sha = os.environ.get("COMMIT_SHA", "").strip()

    if not all([repo, pr_number_raw, comment_id_raw, file_path]):
        print("ERROR: REPO, PR_NUMBER, COMMENT_ID, COMMENT_PATH required", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("GH_TOKEN") or not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: GH_TOKEN and ANTHROPIC_API_KEY required", file=sys.stderr)
        sys.exit(1)

    # comment_body may be JSON-encoded from GitHub Actions toJSON()
    try:
        comment_body = json.loads(comment_body)
    except (json.JSONDecodeError, ValueError):
        pass

    from .graph import graph

    initial_state = {
        "repo": repo,
        "pr_number": int(pr_number_raw),
        "comment_id": int(comment_id_raw),
        "comment_body": str(comment_body),
        "comment_user": comment_user,
        "file_path": file_path,
        "line_number": int(line_raw) if line_raw.isdigit() else 1,
        "commit_sha": commit_sha,
        "should_fix": True,
    }

    print(f"ReviewAI Fixer")
    print(f"  Repo:     {repo}")
    print(f"  PR:       #{pr_number_raw}")
    print(f"  File:     {file_path}:{line_raw}")
    print(f"  Comment:  {str(comment_body)[:80]}...")
    print()

    result = graph.invoke(initial_state)
    print(f"\nDone. Status: {result.get('status')}")
    return result


if __name__ == "__main__":
    main()
