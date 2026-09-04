"""5x Re-run Evaluator entrypoint.

Runs the Commenter pipeline 5 times on the final merged commit and checks
which previously-posted comments were addressed (i.e., not reproduced).
Logs address_rate to LangSmith as feedback on the original traces.
"""

import os
import sys
import json
from collections import Counter


def main() -> dict:
    repo = os.environ.get("REPO", "").strip()
    pr_number_raw = os.environ.get("PR_NUMBER", "").strip()
    commit_sha = os.environ.get("COMMIT_SHA", "").strip()
    eval_runs = int(os.environ.get("EVAL_RUNS", "5"))

    if not all([repo, pr_number_raw]):
        print("ERROR: REPO and PR_NUMBER required", file=sys.stderr)
        sys.exit(1)

    if not os.environ.get("GH_TOKEN") or not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: GH_TOKEN and OPENAI_API_KEY required", file=sys.stderr)
        sys.exit(1)

    pr_number = int(pr_number_raw)
    token = os.environ["GH_TOKEN"]

    from shared.github_io import fetch_bot_comments
    from commenter.graph import graph as commenter_graph

    print(f"ReviewAI Evaluator")
    print(f"  Repo:  {repo}")
    print(f"  PR:    #{pr_number}")
    print(f"  Runs:  {eval_runs}")
    print()

    # Step 1: Fetch all comments previously posted by the bot on this PR
    original_comments = fetch_bot_comments(repo, pr_number, token)
    if not original_comments:
        print("  No bot comments found on this PR — nothing to evaluate")
        return {"status": "no_comments"}

    print(f"  Found {len(original_comments)} original bot comment(s) to evaluate")

    # Step 2: Run the commenter pipeline eval_runs times
    reproduced_fingerprints: Counter = Counter()

    for run_idx in range(eval_runs):
        print(f"\n  --- Eval run {run_idx + 1}/{eval_runs} ---")
        try:
            result = commenter_graph.invoke({
                "pr_metadata": {
                    "repo": repo,
                    "pr_number": pr_number,
                    "commit_sha": commit_sha,
                },
                "dry_run": True,  # Always dry-run for evaluation
                "raw_comments": [],
                "filtered_comments": [],
                "resolved_comment_ids": [],
                "posted_comment_ids": [],
            })

            run_fingerprints = {
                c.get("fingerprint")
                for c in result.get("filtered_comments", [])
                if c.get("fingerprint")
            }

            for fp in run_fingerprints:
                reproduced_fingerprints[fp] += 1

        except Exception as e:
            print(f"  [evaluator] run {run_idx + 1} failed: {e}")

    # Step 3: Score each original comment
    results = []
    for c in original_comments:
        marker = c.get("marker") or {}
        fingerprint = marker.get("fingerprint")
        if not fingerprint:
            continue

        repro_count = reproduced_fingerprints.get(fingerprint, 0)
        addressed = repro_count == 0  # addressed if not reproduced in ANY run

        results.append({
            "comment_id": c["id"],
            "fingerprint": fingerprint,
            "tag": marker.get("tag", "unknown"),
            "repro_count": repro_count,
            "addressed": addressed,
        })

    addressed_count = sum(1 for r in results if r["addressed"])
    total = len(results)
    address_rate = addressed_count / total if total > 0 else 0.0

    print(f"\n{'=' * 60}")
    print(f"Evaluation Results — PR #{pr_number}")
    print(f"  Address rate: {address_rate:.1%} ({addressed_count}/{total})")
    print(f"  (Uber target: 65%+)")
    print(f"{'=' * 60}")

    for r in results:
        status = "✓ addressed" if r["addressed"] else f"✗ still present (reproduced {r['repro_count']}/{eval_runs})"
        print(f"  [{r['tag']}] {status}")

    # Step 4: Log to LangSmith if available
    _log_to_langsmith(repo, pr_number, address_rate, results)

    # Step 5: Save results
    output = {
        "repo": repo,
        "pr_number": pr_number,
        "eval_runs": eval_runs,
        "total_comments": total,
        "addressed_count": addressed_count,
        "address_rate": address_rate,
        "results": results,
    }

    with open("reviewai_evaluation.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(output) + "\n")

    return {"status": "done", "address_rate": address_rate}


def _log_to_langsmith(repo: str, pr_number: int, address_rate: float, results: list) -> None:
    try:
        from langsmith import Client
        client = Client()
        client.create_feedback(
            run_id=None,  # Project-level feedback
            key="address_rate",
            score=address_rate,
            comment=f"PR #{pr_number} in {repo}: {len(results)} comments evaluated",
        )
        print(f"\n  [evaluator] logged address_rate={address_rate:.1%} to LangSmith")
    except Exception as e:
        print(f"  [evaluator] LangSmith logging skipped: {e}")


if __name__ == "__main__":
    main()
