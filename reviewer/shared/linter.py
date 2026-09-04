"""Run flake8 + bandit on changed Python files."""

import os
import subprocess
import tempfile


def run_flake8(file_contents: dict[str, str]) -> dict[str, list[str]]:
    """Run flake8 on each Python file's content.

    Returns {file_path: [flake8 output lines]}.
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
                ["flake8", "--max-line-length=120", "--extend-ignore=E501", tmp_path],
                capture_output=True, text=True, timeout=15,
            )

            lines = []
            for line in result.stdout.strip().splitlines():
                if line:
                    lines.append(line.replace(tmp_path, file_path))

            findings[file_path] = lines

        except FileNotFoundError:
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


def run_bandit(file_contents: dict[str, str]) -> dict[str, list[str]]:
    """Run bandit security scanner on each Python file's content.

    Returns {file_path: [bandit finding lines]}.
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
                ["bandit", "-f", "txt", "-ll", tmp_path],
                capture_output=True, text=True, timeout=15,
            )

            lines = []
            for line in result.stdout.strip().splitlines():
                if line and not line.startswith("[") and "Issue:" in line:
                    lines.append(line.replace(tmp_path, file_path))

            findings[file_path] = lines

        except FileNotFoundError:
            findings[file_path] = []
        except subprocess.TimeoutExpired:
            findings[file_path] = [f"{file_path}: bandit timed out"]
        except Exception as e:
            findings[file_path] = [f"{file_path}: bandit error — {e}"]
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    return findings
