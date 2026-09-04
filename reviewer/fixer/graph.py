"""Fixer LangGraph pipeline."""

from langgraph.graph import StateGraph, START, END

from .state import CommentFixerState
from .nodes.ingest_comment import ingest_comment
from .nodes.fetch_context import fetch_context
from .nodes.generate_fix import generate_fix
from .nodes.verify_fix import verify_fix
from .nodes.post_suggestion import post_suggestion


def _should_continue(state: CommentFixerState) -> str:
    return "fetch_context" if state.get("should_fix") else "post_suggestion"


def build_graph() -> StateGraph:
    builder = StateGraph(CommentFixerState)

    builder.add_node("ingest_comment", ingest_comment)
    builder.add_node("fetch_context", fetch_context)
    builder.add_node("generate_fix", generate_fix)
    builder.add_node("verify_fix", verify_fix)
    builder.add_node("post_suggestion", post_suggestion)

    builder.add_edge(START, "ingest_comment")
    builder.add_conditional_edges("ingest_comment", _should_continue, ["fetch_context", "post_suggestion"])
    builder.add_edge("fetch_context", "generate_fix")
    builder.add_edge("generate_fix", "verify_fix")
    builder.add_edge("verify_fix", "post_suggestion")
    builder.add_edge("post_suggestion", END)

    return builder.compile()


graph = build_graph()
