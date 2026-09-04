"""LangGraph node implementations for the AI code reviewer pipeline.

Pipeline:
  ingest → lint → [Send × N] → execute_review → verify → grade_filter → dedup → post_or_log

Key architectural decisions (from research):
- execute_review: claude-opus-4-6 with adaptive thinking (best reasoning for subtle bugs)
- verify: claude-haiku-4-5 (fast, cheap, binary Y/N per comment — uReview + CodeRabbit lesson)
- Semaphores cap concurrency at 8 for both stages
- Full file context in review prompt (Greptile lesson: cross-file bugs need full context)
"""

import json
import os
import threading
import concurrent.futures
from collections import defaultdict
from datetime import datetime, timezone

from anthropic import Anthropic

from .state import FastReviewer
from .github_io import fetch_pr_diff, find_related_files
from .linter import run_flake8
from .prompts import build_review_prompt, build_verify_prompt

# Concurrency caps (uReview: always cap from day 1)
_REVIEW_SEMAPHORE = threading.BoundedSemaphore(8)
_VERIFY_SEMAPHORE = threading.BoundedSemaphore(8)


# ---------------------------------------------------------------------------
# Node 1: ingest
# ---------------------------------------------------------------------------

def ingest(state: FastReviewer) -> dict:
    """Fetch PR diff, full file content, and related files for each changed file."""
    meta = state["pr_metadata"]
    token = os.environ["GH_TOKEN"]

    file_diffs = fetch_pr_diff(meta["repo"], meta["pr_number"], token)

    # Build content map for cross-file relationship lookup (Greptile lesson)
    all_content = {fd["file"]: fd["full_content"] for fd in file_diffs}

    for fd in file_diffs:
        fd["related_files"] = find_related_files(fd["file"], all_content)

    return {"file_diffs": file_diffs, "status": "ingested"}


# ---------------------------------------------------------------------------
# Node 2: lint
# ---------------------------------------------------------------------------

def lint(state: FastReviewer) -> dict:
    """Run flake8 on all changed Python files. (CodeRabbit lesson)"""
    file_contents = {
        fd["file"]: fd["full_content"]
        for fd in state.get("file_diffs", [])
        if fd["file"].endswith(".py") and fd.get("full_content")
    }

    findings = run_flake8(file_contents) if file_contents else {}
    return {"lint_findings": findings, "status": "linted"}


# ---------------------------------------------------------------------------
# Node 3: execute_review  (runs N times in parallel via LangGraph Send)
# ---------------------------------------------------------------------------

def execute_review(state: dict) -> dict:
    """Review a single file. Receives partial state from Send.

    Input keys (from Send dict):
      file_diff, pr_metadata, lint_findings, dry_run

    Returns {"raw_comments": [...]} which is accumulated via operator.add.
    """
    file_diff = state["file_diff"]
    lint_findings = state.get("lint_findings", {})
    file_lint = lint_findings.get(file_diff["file"], [])

    prompt = build_review_prompt(
        file=file_diff["file"],
        patch=file_diff.get("patch", ""),
        full_content=file_diff.get("full_content", ""),
        related_files=file_diff.get("related_files", []),
        lint_findings=file_lint,
    )

    with _REVIEW_SEMAPHORE:
        client = Anthropic()
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

    text = next((b.text for b in response.content if b.type == "text"), "")
    comments = _parse_comments(text, file_diff["file"])

    print(f"  [execute_review] {file_diff['file']} → {len(comments)} raw comment(s)")
    return {"raw_comments": comments}


# ---------------------------------------------------------------------------
# Node 4: verify  (single node, runs concurrent haiku calls internally)
# ---------------------------------------------------------------------------

def verify(state: FastReviewer) -> dict:
    """Skeptical second pass: verify each raw comment with claude-haiku-4-5.

    uReview lesson: self-reported confidence is weaker than independent verification.
    CodeRabbit lesson: a judge model gates every finding before it ships.
    """
    raw = state.get("raw_comments", [])
    if not raw:
        return {"filtered_comments": [], "status": "verified"}

    content_map = {
        fd["file"]: fd.get("full_content", "")
        for fd in state.get("file_diffs", [])
    }

    verified_comments: list[dict] = []
    lock = threading.Lock()

    def _verify_one(comment: dict) -> None:
        full_content = content_map.get(comment["file"], "")
        prompt = build_verify_prompt(
            file=comment["file"],
            full_content=full_content,
            line=comment.get("line", 1),
            category=comment.get("category", "bug"),
            comment=comment.get("comment", ""),
        )

        with _VERIFY_SEMAPHORE:
            client = Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        result = _parse_json(text)

        if result and result.get("verified") is True:
            with lock:
                verified_comments.append({
                    **comment,
                    "verified": True,
                    "verify_reason": result.get("reason", ""),
                })

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_verify_one, c) for c in raw]
        concurrent.futures.wait(futures)

    print(f"  [verify] {len(verified_comments)}/{len(raw)} comment(s) verified")
    return {"filtered_comments": verified_comments, "status": "verified"}


# ---------------------------------------------------------------------------
# Node 5: grade_filter
# ---------------------------------------------------------------------------

def grade_filter(state: FastReviewer) -> dict:
    """Keep only bug/logic categories for v1. (Other categories added in v2+)"""
    allowed = {"bug", "logic"}
    comments = state.get("filtered_comments", [])
    kept = [c for c in comments if c.get("category", "").lower() in allowed]
    print(f"  [grade_filter] {len(kept)}/{len(comments)} comment(s) kept")
    return {"filtered_comments": kept, "status": "filtered"}


# ---------------------------------------------------------------------------
# Node 6: dedup
# ---------------------------------------------------------------------------

def dedup(state: FastReviewer) -> dict:
    """Same-file + adjacent-line (±3) dedup. Keep highest-confidence per cluster.

    uReview + Greptile lesson: dedup before posting to avoid noise.
    """
    comments = state.get("filtered_comments", [])
    by_file: dict[str, list] = defaultdict(list)
    for c in comments:
        by_file[c["file"]].append(c)

    result = []
    for file_comments in by_file.values():
        # Sort: highest confidence first, then by line
        sorted_comments = sorted(
            file_comments,
            key=lambda c: (-c.get("confidence", 0), c.get("line", 0)),
        )
        kept: list[dict] = []
        for comment in sorted_comments:
            line = comment.get("line", 0)
            is_dup = any(abs(line - k.get("line", 0)) <= 3 for k in kept)
            if not is_dup:
                kept.append(comment)
        result.extend(kept)

    print(f"  [dedup] {len(result)}/{len(comments)} comment(s) after dedup")
    return {"filtered_comments": result, "status": "deduped"}


# ---------------------------------------------------------------------------
# Node 7: post_or_log
# ---------------------------------------------------------------------------

def post_or_log(state: FastReviewer) -> dict:
    """v1: write reviewer_feedback.jsonl + stdout.
    v2: also post inline GitHub PR comments when dry_run=False.
    """
    comments = state.get("filtered_comments", [])
    meta = state.get("pr_metadata", {})
    dry_run = state.get("dry_run", True)
    ts = datetime.now(timezone.utc).isoformat()

    print(f"\n{'=' * 60}")
    print(f"AI Review — {meta.get('repo')} PR #{meta.get('pr_number')} [dry_run={dry_run}]")
    print(f"{'=' * 60}")

    log_entries = []
    for c in comments:
        entry = {
            "pr_id": meta.get("pr_number"),
            "repo": meta.get("repo"),
            "file": c.get("file"),
            "line": c.get("line"),
            "category": c.get("category"),
            "comment": c.get("comment"),
            "verified": c.get("verified", False),
            "verify_reason": c.get("verify_reason", ""),
            "confidence": c.get("confidence"),
            "posted": False,
            "dry_run": dry_run,
            "created_at": ts,
        }
        log_entries.append(entry)

        tag = "DRY-RUN" if dry_run else "POSTING"
        print(
            f"[{tag}] {c['file']}:{c.get('line')} [{c['category']}] "
            f"(conf={c.get('confidence')}) {c['comment']}"
        )

    with open("reviewer_feedback.jsonl", "a", encoding="utf-8") as f:
        for entry in log_entries:
            f.write(json.dumps(entry) + "\n")

    if not dry_run:
        # v2: post inline comments via GitHub API
        # token = os.environ.get("GH_TOKEN", "")
        # for c in comments: post_inline_comment(...)
        pass

    print(f"\nTotal: {len(comments)} comment(s) logged → reviewer_feedback.jsonl")
    return {"status": "done"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict | None:
    """Parse JSON, stripping markdown code fences if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove opening fence (```json or ```) and closing fence (```)
        inner = lines[1:-1] if len(lines) > 2 else lines[1:]
        text = "\n".join(inner)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_comments(text: str, file: str) -> list[dict]:
    """Parse model output into validated list of comment dicts."""
    data = _parse_json(text)
    if not data or "comments" not in data:
        return []

    comments = []
    for c in data.get("comments", []):
        if not isinstance(c, dict) or not c.get("comment"):
            continue
        try:
            comments.append({
                "file": str(c.get("file", file)),
                "line": max(1, int(c.get("line", 1))),
                "category": str(c.get("category", "bug")).lower(),
                "comment": str(c.get("comment", "")),
                "confidence": max(1, min(5, int(c.get("confidence", 3)))),
            })
        except (TypeError, ValueError):
            continue

    return comments
