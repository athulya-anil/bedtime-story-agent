"""Fix generation prompt."""


def build_generate_prompt(
    comment_body: str,
    file_path: str,
    line_number: int,
    surrounding_function: str,
    imports_block: str,
    diff_hunk: str,
    line_content: str,
    lines_before: str,
    lines_after: str,
) -> str:
    return f"""You are a senior engineer implementing a precise code fix based on a reviewer's comment.

## Reviewer Comment
{comment_body}

## File: {file_path}, Line: {line_number}

## Imports (top of file)
```python
{imports_block}
```

## Surrounding Function/Context
```python
{surrounding_function}
```

## Diff Hunk (what changed in this PR)
```diff
{diff_hunk}
```

## Lines Around the Issue
```python
{lines_before}
→ {line_content}
{lines_after}
```

## Your Task

Produce a fix for line {line_number} that addresses EXACTLY what the reviewer describes.

Requirements:
- Fix ONLY what the comment describes — minimal change
- The fix must be syntactically valid Python
- suggestion_lines must be the exact replacement for line {line_number} (and nearby lines if needed)
- If the fix requires changing more than one line, include all replacement lines in suggestion_lines
- If the fix cannot be expressed as a line replacement, set suggestion_lines to []

Output ONLY valid JSON:
{{
  "suggestion_lines": ["<replacement line 1>", "<replacement line 2>"],
  "fix_explanation": "<one sentence: what the fix does and why>",
  "suggestion_start_line": <line number where replacement starts, or null if single line>
}}"""
