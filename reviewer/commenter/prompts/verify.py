"""Category-aware verify prompts."""


def build_verify_prompt(
    file: str,
    full_content: str,
    line: int,
    category_tag: str,
    comment: str,
) -> str:
    lines = full_content.splitlines()
    start = max(0, line - 9)
    end = min(len(lines), line + 8)
    numbered = "\n".join(
        f"{'→ ' if i + 1 == line else '  '}{i + 1:4d}: {l}"
        for i, l in enumerate(lines[start:end], start=start)
    )

    category = category_tag.split(":")[0] if ":" in category_tag else category_tag

    # Category-specific verification guidance
    extra_guidance = {
        "security": (
            "For security findings: verify the vulnerable code path actually reaches user-controlled input. "
            "A security finding is only valid if there is a realistic attack vector."
        ),
        "correctness": (
            "For correctness findings: verify the specific failure mode (e.g., KeyError, AttributeError) "
            "would actually occur given realistic runtime inputs."
        ),
        "logic": (
            "For logic findings: trace the condition or branching carefully. "
            "Verify the logic error produces a wrong outcome, not just a code smell."
        ),
        "patterns": (
            "For pattern findings: verify the anti-pattern is actually present and not already mitigated "
            "by a surrounding try/finally or context manager."
        ),
    }.get(category, "")

    return f"""You are a skeptical code reviewer verifying a bug report before it is shown to a developer.

## Bug Report
- File: `{file}`
- Line: {line}
- Category: {category_tag}
- Claim: {comment}

## Relevant Code (→ marks the flagged line)
```python
{numbered}
```

## Verification Task
{extra_guidance}

Answer YES (verified=true) ONLY if ALL hold:
1. The specific issue is clearly visible in the code shown
2. It would actually cause incorrect behavior at runtime
3. The code does not already handle the edge case

Answer NO (verified=false) if:
- The claim requires assumptions not visible in the code
- The code already handles the case
- The issue is style, not functional
- The claim is too vague

Output ONLY valid JSON:
{{"verified": true | false, "reason": "<one sentence>"}}"""
