"""CLI + GitHub Actions entrypoint for the AI code reviewer.

Run from the repo root:
    cd reviewer && python -m src.entry

Or via GitHub Actions (see .github/workflows/pr-review.yml).

Required environment variables:
    GH_TOKEN           GitHub personal access token (read: pull_requests, contents)
    ANTHROPIC_API_KEY  Anthropic API key
    REPO               Repository in "owner/name" format (e.g. athulyaanil/bedtime-story-agent)
    PR_NUMBER          Pull request number (integer)

Optional:
    DRY_RUN            "true" (default) or "false". When true, comments are
                       logged to reviewer_feedback.jsonl and stdout only.
                       When false (v2), comments are also posted to the PR.
"""

import os
import sys


def main() -> dict:
    repo = os.environ.get("REPO", "").strip()
    pr_number_raw = os.environ.get("PR_NUMBER", "").strip()
    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"

    # Validate required inputs
    if not repo:
        print("ERROR: REPO env var is required (e.g. 'owner/repo')", file=sys.stderr)
        sys.exit(1)

    if not pr_number_raw:
        print("ERROR: PR_NUMBER env var is required", file=sys.stderr)
        sys.exit(1)

    try:
        pr_number = int(pr_number_raw)
    except ValueError:
        print(f"ERROR: PR_NUMBER must be an integer, got: {pr_number_raw!r}", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("GH_TOKEN"):
        print("ERROR: GH_TOKEN env var is required", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY env var is required", file=sys.stderr)
        sys.exit(1)

    # Import graph here so env vars are validated before Anthropic client init
    from .graph import graph

    initial_state = {
        "pr_metadata": {"repo": repo, "pr_number": pr_number},
        "dry_run": dry_run,
        "raw_comments": [],
        "filtered_comments": [],
    }

    print(f"AI Code Reviewer v1")
    print(f"  Repo:     {repo}")
    print(f"  PR:       #{pr_number}")
    print(f"  Dry-run:  {dry_run}")
    print()

    result = graph.invoke(initial_state)

    print(f"\nDone. Final status: {result.get('status')}")
    return result


if __name__ == "__main__":
    main()
