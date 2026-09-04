"""fetch_context node: AST-extract surrounding function and imports."""

import ast
import os
from github import Github
from ..state import CommentFixerState, CodeContext


def fetch_context(state: CommentFixerState) -> dict:
    if not state.get("should_fix"):
        return {}

    token = os.environ["GH_TOKEN"]
    g = Github(token)
    repo = g.get_repo(state["repo"])

    # Fetch full file at head commit
    full_file = ""
    try:
        contents = repo.get_contents(state["file_path"], ref=state["commit_sha"])
        full_file = contents.decoded_content.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [fetch_context] failed to fetch file: {e}")
        return {"should_fix": False, "skip_reason": "file_fetch_failed"}

    line_number = state.get("line_number", 1)
    lines = full_file.splitlines()

    # Extract surrounding lines
    before_start = max(0, line_number - 6)
    after_end = min(len(lines), line_number + 5)
    line_content = lines[line_number - 1] if 0 < line_number <= len(lines) else ""
    lines_before = "\n".join(lines[before_start:line_number - 1])
    lines_after = "\n".join(lines[line_number:after_end])

    # Extract imports block (first lines until non-import)
    imports_block = _extract_imports(full_file)

    # AST-extract surrounding function
    surrounding_function = _extract_surrounding_function(full_file, line_number)

    # Get diff hunk from PR
    diff_hunk = _fetch_diff_hunk(repo, state["repo"], state["pr_number"], state["file_path"], token)

    context = CodeContext(
        full_file=full_file,
        surrounding_function=surrounding_function,
        imports_block=imports_block,
        diff_hunk=diff_hunk,
        line_content=line_content,
        lines_before=lines_before,
        lines_after=lines_after,
    )

    return {"code_context": context}


def _extract_imports(source: str) -> str:
    import_lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            import_lines.append(line)
        elif import_lines and not stripped:
            continue
        elif import_lines:
            break
    return "\n".join(import_lines[:30])


def _extract_surrounding_function(source: str, line_number: int) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        lines = source.splitlines()
        start = max(0, line_number - 15)
        end = min(len(lines), line_number + 15)
        return "\n".join(lines[start:end])

    lines = source.splitlines()
    best_node = None
    best_size = float("inf")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno + 20)
            if start <= line_number <= end:
                size = end - start
                if size < best_size:
                    best_size = size
                    best_node = (start, end)

    if best_node:
        start, end = best_node
        return "\n".join(lines[start - 1:end])

    # Fallback: 30-line window
    start = max(0, line_number - 15)
    end = min(len(lines), line_number + 15)
    return "\n".join(lines[start:end])


def _fetch_diff_hunk(repo, repo_name: str, pr_number: int, file_path: str, token: str) -> str:
    try:
        pr = repo.get_pull(pr_number)
        for f in pr.get_files():
            if f.filename == file_path and f.patch:
                return f.patch[:2000]
    except Exception:
        pass
    return ""
