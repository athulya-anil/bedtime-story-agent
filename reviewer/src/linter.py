"""Run flake8 on changed Python files and return findings per file.

CodeRabbit lesson: grounding the LLM in deterministic linter output
reduces hallucinated syntax complaints and lets the model focus on
real logic bugs.
"""

import os
import subprocess
import tempfile


def run_flake8(file_contents: dict[str, str]) -> dict[str, list[str]]:
    """Run flake8 on each Python file's content.

    Args:
        file_contents: {file_path: source_code} for changed Python files.

    Returns:
        {file_path: [flake8 output lines]} — empty list means clean.
    """
    findings: dict[str, list[str]] = {}

    for file_path, content in file_contents.items():
        if not file_path.endswith(".py") or not content:
            findings[file_path] = []
            continue

        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                tmp_path = f.name

            result = subprocess.run(
                [
                    "flake8",
                    "--max-line-length=120",
                    "--extend-ignore=E501",   # already covered by max-line-length
                    tmp_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            lines = []
            for line in result.stdout.strip().splitlines():
                if line:
                    # Replace the temp path with the real file path
                    lines.append(line.replace(tmp_path, file_path))

            findings[file_path] = lines

        except FileNotFoundError:
            # flake8 not installed — skip silently
            findings[file_path] = []
        except subprocess.TimeoutExpired:
            findings[file_path] = [f"{file_path}: flake8 timed out"]
        except Exception as e:
            findings[file_path] = [f"{file_path}: flake8 error — {e}"]
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    return findings
