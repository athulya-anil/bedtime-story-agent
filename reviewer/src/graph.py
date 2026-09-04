"""LangGraph graph definition for the AI code reviewer.

Pipeline:
  START → ingest → lint → [Send × N files] → execute_review → verify → grade_filter → dedup → post_or_log → END

The Send fan-out at the lint→execute_review boundary runs one execute_review
instance per changed file in parallel. All results are merged into raw_comments
via the operator.add reducer defined in FastReviewer. After all parallel
instances complete, verify runs once with the full accumulated list.

Architecture mirrors Uber uReview's LangGraph design, with additions
from Greptile (full-file context) and CodeRabbit (lint + verify judge).
"""

from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send

from .state import FastReviewer
from .nodes import (
    ingest,
    lint,
    execute_review,
    verify,
    grade_filter,
    dedup,
    post_or_log,
)


def _route_to_review(state: FastReviewer):
    """Fan out to execute_review for each file, or short-circuit to post_or_log.

    Returns a list of Send objects (parallel fan-out) when there are files
    to review, or the string "post_or_log" when the PR has no reviewable files.
    """
    file_diffs = state.get("file_diffs", [])

    if not file_diffs:
        return "post_or_log"

    return [
        Send(
            "execute_review",
            {
                "file_diff": fd,
                "pr_metadata": state.get("pr_metadata", {}),
                "lint_findings": state.get("lint_findings", {}),
                "dry_run": state.get("dry_run", True),
            },
        )
        for fd in file_diffs
    ]


def build_graph() -> StateGraph:
    builder = StateGraph(FastReviewer)

    # Register nodes
    builder.add_node("ingest", ingest)
    builder.add_node("lint", lint)
    builder.add_node("execute_review", execute_review)
    builder.add_node("verify", verify)
    builder.add_node("grade_filter", grade_filter)
    builder.add_node("dedup", dedup)
    builder.add_node("post_or_log", post_or_log)

    # Linear edges
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "lint")

    # Fan-out: lint → [execute_review × N] or → post_or_log (if no files)
    builder.add_conditional_edges(
        "lint",
        _route_to_review,
        ["execute_review", "post_or_log"],
    )

    # Fan-in: all parallel execute_review instances converge at verify
    builder.add_edge("execute_review", "verify")

    # Sequential tail
    builder.add_edge("verify", "grade_filter")
    builder.add_edge("grade_filter", "dedup")
    builder.add_edge("dedup", "post_or_log")
    builder.add_edge("post_or_log", END)

    return builder.compile()


# Module-level graph instance — imported by entry.py
graph = build_graph()
