"""Prompt builders for the two LLM calls in the pipeline.

- build_review_prompt: claude-opus-4-6 with adaptive thinking
  Diff + full file + related files + lint findings → structured comments
- build_verify_prompt: claude-haiku-4-5
  Single comment + relevant code → verified: true/false
"""


def build_review_prompt(
    file: str,
    patch: str,
    full_content: str,
    related_files: list[dict],
    lint_findings: list[str],
) -> str:
    """Build the Standard reviewer prompt for a single file.

    Incorporates:
    - The diff (what changed)
    - Full file content (Greptile: cross-file context is critical)
    - Files that import/are imported by this file
    - Flake8 findings (CodeRabbit: ground LLM in deterministic facts)
    """

    lint_section = ""
    if lint_findings:
        lint_section = (
            "\n## Linter Findings (flake8 — treat these as confirmed facts)\n"
            + "\n".join(f"  {l}" for l in lint_findings)
            + "\n"
        )

    related_section = ""
    if related_files:
        related_section = "\n## Related Files (import relationships)\n"
        for rf in related_files:
            # Truncate to keep context window reasonable
            snippet = rf["content"][:2000]
            if len(rf["content"]) > 2000:
                snippet += "\n... (truncated)"
            related_section += f"\n### {rf['file']}\n```python\n{snippet}\n```\n"

    # Truncate full_content if very large (> 8000 chars)
    content_display = full_content
    if len(full_content) > 8000:
        content_display = full_content[:8000] + "\n... (truncated — showing first 8000 chars)"

    return f"""You are a senior software engineer doing a careful code review. Your job is to find **real bugs and logic errors only** — not style issues, not nitpicks.

## File Under Review: `{file}`

## Diff (what changed in this PR)
```diff
{patch}
```

## Full File Content (after this PR's changes)
```python
{content_display}
```
{lint_section}{related_section}
## Your Task

Review the diff carefully in the context of the full file. Look specifically for:

- **Bugs**: Code that will throw exceptions, produce wrong results, or fail silently (e.g., KeyError on direct dict access, off-by-one in slice, unhandled None, wrong variable used)
- **Logic errors**: Incorrect conditions, inverted boolean, wrong branching, missing return, mutation of shared state
- **Cross-file breakage**: Does this change break an import or function signature relied on in a related file shown above?

**Do NOT report:**
- Formatting, naming, or style
- Missing docstrings or type hints
- Performance micro-optimizations
- Anything already listed in the Linter Findings above

For each issue, be specific: name the variable, function, or line. Explain exactly what goes wrong and when.

**Confidence scale:** 5 = certain this is a bug, 1 = uncertain / depends on runtime context.
Only include comments with confidence ≥ 3.

Output **only** valid JSON in this exact format — no markdown fences, no explanation:
{{
  "comments": [
    {{
      "file": "{file}",
      "line": <integer — line number in the FULL FILE above>,
      "category": "bug" | "logic",
      "comment": "<specific, actionable description>",
      "confidence": <3 | 4 | 5>
    }}
  ]
}}

If you find no real bugs or logic errors, output: {{"comments": []}}"""


def build_verify_prompt(
    file: str,
    full_content: str,
    line: int,
    category: str,
    comment: str,
) -> str:
    """Build the skeptical verification prompt for a single comment.

    claude-haiku-4-5 reads the exact code at the flagged line and
    answers: does this comment describe a real bug visible in the code?

    Inspired by uReview's two-model grading and CodeRabbit's judge gate.
    """

    # Extract ±8 lines around the flagged line for tight context
    lines = full_content.splitlines()
    start = max(0, line - 9)
    end = min(len(lines), line + 8)
    numbered = "\n".join(
        f"{'→ ' if i + 1 == line else '  '}{i + 1:4d}: {l}"
        for i, l in enumerate(lines[start:end], start=start)
    )

    return f"""You are a skeptical code reviewer verifying a bug report before it is shown to a developer.

## Bug Report
- File: `{file}`
- Line: {line}
- Category: {category}
- Claim: {comment}

## Relevant Code (arrow → marks the flagged line)
```python
{numbered}
```

## Verification Task

Read the code carefully. Answer YES (verified=true) only if ALL of these hold:
1. The specific issue described in the claim is **clearly visible** in the code shown
2. It would **actually cause incorrect behavior** at runtime (exception, wrong result, silent failure)
3. The code does **not** already handle the edge case the claim describes

Answer NO (verified=false) if:
- The claim requires assumptions not visible in the code
- The code already handles the case correctly
- The issue is a style concern, not a real functional bug
- The claim is too vague to verify

Output **only** valid JSON — no markdown, no explanation:
{{"verified": true | false, "reason": "<one sentence>"}}"""
