"""post_summary node: post PR-level summary comment."""

import os

from ..state import CommenterState, PRSummary
from shared.github_io import fetch_bot_summary_comment, post_summary_comment


def post_summary(state: CommenterState) -> dict:
    comments = state.get("filtered_comments", [])
    resolved_ids = state.get("resolved_comment_ids", [])
    meta = state["pr_metadata"]
    dry_run = state.get("dry_run", True)
    token = os.environ["GH_TOKEN"]

    summary = _compute_summary(comments, resolved_ids, state)
    body = _format_summary(summary, meta)

    print(f"\n{'=' * 60}")
    print(f"ReviewAI — {meta.get('repo')} PR #{meta.get('pr_number')}")
    print(f"Score: {summary['overall_score']}/5 | Comments: {len(comments)} | Resolved: {len(resolved_ids)}")
    print(f"{'=' * 60}")
    for c in comments:
        print(f"  [{c.get('category_tag')}] conf={c.get('confidence')} {c['file']}:{c.get('line')} — {c['comment'][:80]}")

    if not dry_run:
        previous_id = fetch_bot_summary_comment(meta["repo"], meta["pr_number"], token)
        post_summary_comment(meta["repo"], meta["pr_number"], token, body, previous_id)

    return {"pr_summary": summary, "status": "done"}


def _compute_summary(comments: list, resolved_ids: list, state: dict) -> PRSummary:
    if not comments:
        score = 5
    else:
        max_conf = max(c.get("confidence", 0) for c in comments)
        critical_count = sum(1 for c in comments if c.get("confidence") == 5)
        security_count = sum(1 for c in comments if "security" in c.get("category_tag", ""))

        if security_count > 0 or critical_count > 2:
            score = 1
        elif critical_count > 0 or max_conf == 5:
            score = 2
        elif max_conf >= 4:
            score = 3
        elif max_conf >= 3:
            score = 4
        else:
            score = 5

    counts: dict[str, int] = {}
    for c in comments:
        cat = c.get("category_tag", "unknown").split(":")[0]
        counts[cat] = counts.get(cat, 0) + 1

    critical = [c for c in comments if c.get("confidence") == 5]

    return PRSummary(
        overall_score=score,
        counts_by_category=counts,
        critical_issues=critical,
        resolved_count=len(resolved_ids),
        total_files_reviewed=len(state.get("file_diffs", [])),
    )


def _format_summary(summary: PRSummary, meta: dict) -> str:
    score = summary["overall_score"]
    score_emoji = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "✅"}.get(score, "⚪")

    lines = [
        f"## ReviewAI Summary — PR #{meta.get('pr_number')}",
        "",
        f"**Overall confidence score: {score_emoji} {score}/5**",
        "",
    ]

    if summary["counts_by_category"]:
        lines += ["| Category | Count |", "|---|---|"]
        for cat, count in sorted(summary["counts_by_category"].items()):
            lines.append(f"| {cat} | {count} |")
        lines.append("")

    if summary["critical_issues"]:
        lines.append("### Critical Issues (confidence 5/5)")
        for c in summary["critical_issues"]:
            lines.append(f"- `{c['file']}:{c.get('line')}` — {c['comment'][:100]}")
        lines.append("")

    if summary["resolved_count"]:
        lines.append(f"### Resolved from previous run")
        lines.append(f"- {summary['resolved_count']} issue(s) resolved ✓")
        lines.append("")

    lines.append(
        f"_Reviewed {summary['total_files_reviewed']} file(s) · "
        f"claude-sonnet-4-6 + claude-haiku-4-5 · ReviewAI_"
    )

    return "\n".join(lines)
