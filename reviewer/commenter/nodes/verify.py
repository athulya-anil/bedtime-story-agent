"""verify node: gpt-4o-mini grades each comment pass/fail."""

import threading
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from ..state import CommenterState
from ..prompts.verify import build_verify_prompt
from shared.config import VERIFY_SEMAPHORE_SIZE
from shared.json_utils import parse_json

_SEMAPHORE = threading.BoundedSemaphore(VERIFY_SEMAPHORE_SIZE)


def verify(state: CommenterState) -> dict:
    raw = state.get("filtered_comments", [])
    if not raw:
        return {"filtered_comments": [], "status": "verified"}

    content_map = {fd["file"]: fd.get("full_content", "") for fd in state.get("file_diffs", [])}
    verified_comments = []
    lock = threading.Lock()

    def _verify_one(comment: dict) -> None:
        full_content = content_map.get(comment["file"], "")
        prompt = build_verify_prompt(
            file=comment["file"],
            full_content=full_content,
            line=comment.get("line", 1),
            category_tag=comment.get("category_tag", comment.get("category", "correctness")),
            comment=comment.get("comment", ""),
        )

        with _SEMAPHORE:
            client = OpenAI()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

        text = response.choices[0].message.content or ""
        result = parse_json(text)

        if result and result.get("verified") is True:
            with lock:
                verified_comments.append({
                    **comment,
                    "verified": True,
                    "verify_reason": result.get("reason", ""),
                })

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_verify_one, raw))

    print(f"  [verify] {len(verified_comments)}/{len(raw)} comment(s) verified")
    return {"filtered_comments": verified_comments, "status": "verified"}
