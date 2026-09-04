"""State schema for the Fixer LangGraph pipeline."""

from typing import Optional
from typing_extensions import TypedDict


class CodeContext(TypedDict, total=False):
    full_file: str
    surrounding_function: str
    imports_block: str
    diff_hunk: str
    line_content: str
    lines_before: str
    lines_after: str


class CommentFixerState(TypedDict, total=False):
    repo: str
    pr_number: int
    comment_id: int
    comment_body: str
    comment_user: str
    file_path: str
    line_number: int
    commit_sha: str

    should_fix: bool
    skip_reason: Optional[str]

    code_context: CodeContext

    proposed_fix: list[str]
    fix_explanation: str

    fix_valid: bool
    fix_issues: str

    posted_reply_id: Optional[int]
    status: str
