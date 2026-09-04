"""Fix verification prompt."""


def build_verify_prompt(
    comment_body: str,
    proposed_fix_lines: list[str],
    surrounding_function: str,
    line_number: int,
) -> str:
    fix_text = "\n".join(proposed_fix_lines)
    return f"""You are verifying a proposed code fix before it is shown to a developer.

## Original Comment
{comment_body}

## Proposed Fix (replacement for line {line_number})
```python
{fix_text}
```

## Surrounding Context
```python
{surrounding_function}
```

Answer YES (valid=true) ONLY if ALL hold:
1. The fix is syntactically valid Python
2. The fix directly addresses what the reviewer described
3. The fix does not introduce obvious new bugs

Answer NO (valid=false) if:
- The fix has syntax errors
- The fix does not address the comment
- The fix introduces new problems
- The fix is empty or meaningless

Output ONLY valid JSON:
{{"valid": true | false, "issues": "<empty string if valid, or description of problems>"}}"""
