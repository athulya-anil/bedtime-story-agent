"""generate_fix node: gpt-4o generates a concrete code fix."""

import threading
from openai import OpenAI
from ..state import CommentFixerState
from ..prompts.generate import build_generate_prompt
from shared.json_utils import parse_json
from shared.config import REVIEW_SEMAPHORE_SIZE

_SEMAPHORE = threading.BoundedSemaphore(REVIEW_SEMAPHORE_SIZE)


def generate_fix(state: CommentFixerState) -> dict:
    if not state.get("should_fix"):
        return {}

    ctx = state.get("code_context", {})
    prompt = build_generate_prompt(
        comment_body=state.get("comment_body", ""),
        file_path=state.get("file_path", ""),
        line_number=state.get("line_number", 1),
        surrounding_function=ctx.get("surrounding_function", ""),
        imports_block=ctx.get("imports_block", ""),
        diff_hunk=ctx.get("diff_hunk", ""),
        line_content=ctx.get("line_content", ""),
        lines_before=ctx.get("lines_before", ""),
        lines_after=ctx.get("lines_after", ""),
    )

    with _SEMAPHORE:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

    text = response.choices[0].message.content or ""
    result = parse_json(text)

    if not result or not result.get("suggestion_lines"):
        print(f"  [generate_fix] no suggestion produced")
        return {"should_fix": False, "skip_reason": "no_suggestion_generated"}

    print(f"  [generate_fix] produced {len(result['suggestion_lines'])} suggestion line(s)")
    return {
        "proposed_fix": result["suggestion_lines"],
        "fix_explanation": result.get("fix_explanation", ""),
    }
