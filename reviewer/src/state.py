import operator
from typing import Annotated
from typing_extensions import TypedDict


class FastReviewer(TypedDict, total=False):
    pr_metadata: dict                              # {repo, pr_number}
    file_diffs: list                               # [{file, patch, additions, deletions, full_content, related_files}]
    lint_findings: dict                            # {file: [flake8 output lines]}
    raw_comments: Annotated[list, operator.add]    # parallel fan-out accumulator (operator.add merges lists)
    filtered_comments: list                        # after verify → grade_filter → dedup
    dry_run: bool
    status: str
