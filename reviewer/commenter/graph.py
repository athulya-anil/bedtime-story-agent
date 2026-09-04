"""Commenter LangGraph pipeline."""

from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send

from .state import CommenterState
from .nodes.ingest import ingest
from .nodes.lint import lint
from .nodes.review_file import review_file
from .nodes.classify import classify_and_threshold
from .nodes.verify import verify
from .nodes.semantic_dedup import semantic_dedup
from .nodes.resolve_stale import resolve_stale
from .nodes.post_comments import post_comments
from .nodes.post_summary import post_summary


def _route_to_review(state: CommenterState):
    file_diffs = state.get("file_diffs", [])
    if not file_diffs:
        return "post_summary"
    return [
        Send("review_file", {
            "file_diff": fd,
            "pr_metadata": state.get("pr_metadata", {}),
            "lint_findings": state.get("lint_findings", {}),
            "dry_run": state.get("dry_run", True),
        })
        for fd in file_diffs
    ]


def build_graph() -> StateGraph:
    builder = StateGraph(CommenterState)

    builder.add_node("ingest", ingest)
    builder.add_node("lint", lint)
    builder.add_node("review_file", review_file)
    builder.add_node("classify_and_threshold", classify_and_threshold)
    builder.add_node("verify", verify)
    builder.add_node("semantic_dedup", semantic_dedup)
    builder.add_node("resolve_stale", resolve_stale)
    builder.add_node("post_comments", post_comments)
    builder.add_node("post_summary", post_summary)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "lint")
    builder.add_conditional_edges("lint", _route_to_review, ["review_file", "post_summary"])
    builder.add_edge("review_file", "classify_and_threshold")
    builder.add_edge("classify_and_threshold", "verify")
    builder.add_edge("verify", "semantic_dedup")
    builder.add_edge("semantic_dedup", "resolve_stale")
    builder.add_edge("resolve_stale", "post_comments")
    builder.add_edge("post_comments", "post_summary")
    builder.add_edge("post_summary", END)

    return builder.compile()


graph = build_graph()
