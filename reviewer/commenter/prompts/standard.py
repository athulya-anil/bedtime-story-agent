"""Standard Assistant prompt: bugs, logic flaws, incorrect exception handling."""


def build_standard_prompt(
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
            "\n## Linter Findings (flake8 + bandit — treat as confirmed facts)\n"
            + "\n".join(f"  {l}" for l in lint_findings)
            + "\n"
        )

    related_section = ""
    if related_files:
        related_section = "\n## Related Files (import relationships)\n"
        for rf in related_files:
            snippet = rf["content"][:2000]
            if len(rf["content"]) > 2000:
                snippet += "\n... (truncated)"
            related_section += f"\n### {rf['file']}\n```python\n{snippet}\n```\n"

    # Tiered context strategy
    if len(full_content) <= 8000:
        content_display = full_content
    elif len(full_content) <= 32000:
        content_display = full_content[:32000] + "\n... (truncated)"
    else:
        content_display = full_content[:8000] + "\n... (large file — showing first 8000 chars)"

    pr_context = ""
    if pr_title:
        pr_context = f"\n## PR Context\nTitle: {pr_title}\n"
        if pr_body:
            pr_context += f"Description: {pr_body[:500]}\n"

    return f"""You are a defensive software engineer reviewing code for RUNTIME FAILURES ONLY.
Your ONLY job is to find bugs that will cause exceptions, wrong results, or silent failures.
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
{lint_section}{related_section}
## What to look for (correctness and logic ONLY):
- KeyError / IndexError from unguarded dict/list access
- AttributeError from accessing attributes on possibly-None objects
- Off-by-one errors in slice/range
- Wrong variable used in a loop or assignment
- Missing return in a function that callers depend on for a value
- Inverted boolean conditions (if not x when if x is correct)
- Mutable default argument shared across calls (def f(lst=[]))
- Uncaught exceptions in critical code paths
- Wrong comparison (= vs ==, is vs ==)
- Coroutine called without await

## DO NOT report (these are handled by other reviewers):
- Code style, naming conventions, formatting
- Missing docstrings or type hints
- Performance issues
- Security vulnerabilities
- Design patterns or architectural concerns
- Anything already listed in Linter Findings

## Output format
For each issue, produce a concrete code fix in suggestion_lines.
suggestion_lines must be the exact replacement lines for the flagged line(s).
If the fix cannot be expressed as a line replacement, set suggestion_lines to [].

Output ONLY valid JSON — no markdown fences, no preamble:
{{
  "comments": [
    {{
      "file": "{file}",
      "line": <integer — line number in the full file above>,
      "category": "correctness" | "logic",
      "subcategory": "null-check" | "key-error" | "off-by-one" | "wrong-variable" | "missing-return" | "inverted-condition" | "shared-mutable" | "uncaught-exception" | "wrong-comparison" | "missing-await" | "other",
      "comment": "<specific, actionable description — name the variable/function/line>",
      "suggestion_lines": ["<replacement line 1>", "<replacement line 2>"],
      "confidence": <3 | 4 | 5>
    }}
  ]
}}

Only include comments with confidence >= 3. If no real bugs found: {{"comments": []}}"""
