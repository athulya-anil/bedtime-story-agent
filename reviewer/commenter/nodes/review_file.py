"""review_file node: fan-out target, runs 3 specialized assistants in parallel."""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic

from ..state import Comment
from ..prompts.standard import build_standard_prompt
from ..prompts.best_practices import build_best_practices_prompt
from ..prompts.security import build_security_prompt
from shared.config import REVIEW_SEMAPHORE_SIZE
from shared.json_utils import parse_json
from shared.fingerprint import make_fingerprint

_SEMAPHORE = threading.BoundedSemaphore(REVIEW_SEMAPHORE_SIZE)

ASSISTANTS = {
    "standard": build_standard_prompt,
    "best_practices": build_best_practices_prompt,
    "security": build_security_prompt,
}


def review_file(state: dict) -> dict:
    """Review a single file using 3 specialized assistants in parallel.

    Receives partial state from LangGraph Send:
      file_diff, pr_metadata, lint_findings, dry_run
    """
    file_diff = state["file_diff"]
    pr_meta = state.get("pr_metadata", {})
    lint_findings = state.get("lint_findings", {})
    file_lint = lint_findings.get(file_diff["file"], [])

    all_comments: list[Comment] = []
    lock = threading.Lock()

    def _run_assistant(name: str, prompt_fn) -> None:
        prompt = prompt_fn(
            file=file_diff["file"],
            patch=file_diff.get("patch", ""),
            full_content=file_diff.get("full_content", ""),
            related_files=file_diff.get("related_files", []),
            lint_findings=file_lint,
            pr_title=pr_meta.get("pr_title", ""),
            pr_body=pr_meta.get("pr_body", ""),
        )

        with _SEMAPHORE:
            client = Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        data = parse_json(text)
        if not data or "comments" not in data:
            return

        comments = _parse_comments(data["comments"], file_diff["file"], name)
        with lock:
            all_comments.extend(comments)
        print(f"    [{name}] {file_diff['file']} → {len(comments)} comment(s)")

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_run_assistant, name, fn) for name, fn in ASSISTANTS.items()]
        for f in as_completed(futures):
            exc = f.exception()
            if exc:
                print(f"  [review_file] assistant error: {exc}")

    print(f"  [review_file] {file_diff['file']} → {len(all_comments)} total raw comment(s)")
    return {"raw_comments": all_comments}


def _parse_comments(raw: list, file: str, assistant: str) -> list[Comment]:
    comments = []
    for c in raw:
        if not isinstance(c, dict) or not c.get("comment"):
            continue
        try:
            comment_text = str(c.get("comment", ""))
            category = str(c.get("category", "correctness")).lower()
            fingerprint = make_fingerprint(file, category, comment_text)
            comments.append(Comment(
                file=str(c.get("file", file)),
                line=max(1, int(c.get("line", 1))),
                category=category,
                subcategory=str(c.get("subcategory", "other")).lower(),
                category_tag=f"{category}:{c.get('subcategory', 'other')}".lower(),
                comment=comment_text,
                suggestion_lines=c.get("suggestion_lines", []) or [],
                suggestion_start_line=c.get("suggestion_start_line"),
                confidence=max(1, min(5, int(c.get("confidence", 3)))),
                assistant=assistant,
                verified=False,
                verify_reason="",
                fingerprint=fingerprint,
            ))
        except (TypeError, ValueError):
            continue
    return comments
