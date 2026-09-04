"""State schema for the Commenter LangGraph pipeline."""

import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict


class FileDiff(TypedDict, total=False):
    file: str
    patch: str
    additions: int
    deletions: int
    status: str
    full_content: str
    related_files: list[dict]


class Comment(TypedDict, total=False):
    file: str
    line: int
    category: str           # coarse: correctness | logic | security | patterns | conventions
    subcategory: str        # fine: null-check | injection | resource-leak | etc.
    category_tag: str       # "correctness:null-check"
    comment: str
    suggestion_lines: list[str]
    suggestion_start_line: Optional[int]
    confidence: int         # 1-5
    assistant: str          # standard | best_practices | security
    verified: bool
    verify_reason: str
    fingerprint: str


class PRSummary(TypedDict, total=False):
    overall_score: int
    counts_by_category: dict
    critical_issues: list[dict]
    resolved_count: int
    total_files_reviewed: int
    run_url: str


class CommenterState(TypedDict, total=False):
    # Inputs
    pr_metadata: dict       # repo, pr_number, commit_sha, head_branch, pr_title, pr_body
    dry_run: bool

    # Ingested data
    file_diffs: list[FileDiff]
    lint_findings: dict     # {file: [flake8+bandit lines]}

    # Fan-out accumulator — operator.add merges across parallel Send nodes
    raw_comments: Annotated[list[Comment], operator.add]

    # Post-processing
    filtered_comments: list[Comment]
    resolved_comment_ids: list[int]
    posted_comment_ids: list[int]

    # Summary
    pr_summary: PRSummary
    status: str
