"""verify_fix node: gpt-4o-mini checks the fix is valid and addresses the comment."""

from openai import OpenAI
from ..state import CommentFixerState
from ..prompts.verify import build_verify_prompt
from shared.json_utils import parse_json


def verify_fix(state: CommentFixerState) -> dict:
    if not state.get("should_fix") or not state.get("proposed_fix"):
        return {"fix_valid": False, "fix_issues": "no fix to verify"}

    ctx = state.get("code_context", {})
    prompt = build_verify_prompt(
        comment_body=state.get("comment_body", ""),
        proposed_fix_lines=state.get("proposed_fix", []),
        surrounding_function=ctx.get("surrounding_function", ""),
        line_number=state.get("line_number", 1),
    )

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.choices[0].message.content or ""
    result = parse_json(text)

    valid = bool(result and result.get("valid"))
    issues = result.get("issues", "") if result else "parse error"
    print(f"  [verify_fix] valid={valid}" + (f" issues={issues}" if not valid else ""))
    return {"fix_valid": valid, "fix_issues": issues}
