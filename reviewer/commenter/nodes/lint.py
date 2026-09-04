"""Lint node: run flake8 + bandit on all changed Python files."""

from ..state import CommenterState
from shared.linter import run_flake8, run_bandit


def lint(state: CommenterState) -> dict:
    file_contents = {
        fd["file"]: fd["full_content"]
        for fd in state.get("file_diffs", [])
        if fd["file"].endswith(".py") and fd.get("full_content")
    }

    flake8_findings = run_flake8(file_contents) if file_contents else {}
    bandit_findings = run_bandit(file_contents) if file_contents else {}

    # Merge findings per file
    combined: dict[str, list[str]] = {}
    all_files = set(flake8_findings) | set(bandit_findings)
    for f in all_files:
        combined[f] = flake8_findings.get(f, []) + bandit_findings.get(f, [])

    total = sum(len(v) for v in combined.values())
    print(f"  [lint] {total} finding(s) across {len(combined)} file(s)")
    return {"lint_findings": combined, "status": "linted"}
