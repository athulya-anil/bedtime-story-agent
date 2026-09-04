"""Best Practices Assistant prompt: patterns that cause bugs over time."""


def build_best_practices_prompt(
    file: str,
    patch: str,
    full_content: str,
    related_files: list[dict],
    lint_findings: list[str],
    pr_title: str = "",
    pr_body: str = "",
) -> str:
    lint_section = ""
    if lint_findings:
        lint_section = (
            "\n## Linter Findings (already confirmed — do not rephrase these)\n"
            + "\n".join(f"  {l}" for l in lint_findings)
            + "\n"
        )

    if len(full_content) <= 8000:
        content_display = full_content
    elif len(full_content) <= 32000:
        content_display = full_content[:32000] + "\n... (truncated)"
    else:
        content_display = full_content[:8000] + "\n... (large file — showing first 8000 chars)"

    pr_context = ""
    if pr_title:
        pr_context = f"\n## PR Context\nTitle: {pr_title}\n"

    return f"""You are a Python architect reviewing code for patterns that cause bugs over time.
Your ONLY job is to find structural anti-patterns: resource leaks, exception misuse, API abuse.
{pr_context}
## File: `{file}`

## Diff (what changed)
```diff
{patch}
```

## Full File Content
```python
{content_display}
```
{lint_section}
## What to look for (patterns ONLY):
- Exception swallowed silently (except Exception: pass)
- Bare except: catching BaseException including KeyboardInterrupt
- File/connection/socket not closed (missing context manager / with statement)
- Thread started without .join() or exception propagation mechanism
- assert used for runtime input validation (stripped in -O mode)
- Function returns None implicitly when callers expect a value
- str(e) instead of repr(e) in error logging (loses traceback info)
- Mutable default argument causing shared state across calls
- String concatenation to build SQL/shell commands (flag as pattern, not security issue)

## DO NOT report:
- Naming conventions, code style, formatting, whitespace
- Missing docstrings or type hints
- Import ordering
- Security vulnerabilities (handled by Security reviewer)
- Runtime correctness bugs (handled by Standard reviewer)
- Performance issues

## Output format
For each issue, produce a suggestion_lines fix where possible.

Output ONLY valid JSON:
{{
  "comments": [
    {{
      "file": "{file}",
      "line": <integer>,
      "category": "patterns" | "conventions",
      "subcategory": "swallowed-exception" | "bare-except" | "resource-leak" | "unjoined-thread" | "assert-validation" | "implicit-none-return" | "poor-error-logging" | "string-concat-command" | "other",
      "comment": "<specific description>",
      "suggestion_lines": ["<replacement line>"],
      "confidence": <3 | 4 | 5>
    }}
  ]
}}

Only include comments with confidence >= 4 (higher bar — this assistant produces most noise).
If no issues found: {{"comments": []}}"""
