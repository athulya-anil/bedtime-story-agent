"""Security Assistant prompt: AppSec vulnerabilities."""


def build_security_prompt(
    file: str,
    patch: str,
    full_content: str,
    related_files: list[dict],
    lint_findings: list[str],
    pr_title: str = "",
    pr_body: str = "",
) -> str:
    bandit_section = ""
    if lint_findings:
        bandit_section = (
            "\n## Static Analysis Findings (bandit — treat as confirmed facts)\n"
            + "\n".join(f"  {l}" for l in lint_findings)
            + "\n"
        )

    if len(full_content) <= 8000:
        content_display = full_content
    elif len(full_content) <= 32000:
        content_display = full_content[:32000] + "\n... (truncated)"
    else:
        content_display = full_content[:8000] + "\n... (large file)"

    return f"""You are an application security engineer (AppSec) reviewing code for exploitable vulnerabilities.
Your ONLY job is to find security issues that could be exploited.

## File: `{file}`

## Diff (what changed)
```diff
{patch}
```

## Full File Content
```python
{content_display}
```
{bandit_section}
## What to look for (security ONLY):
- Shell injection: subprocess with shell=True and user-controlled input
- Path traversal: open() on user-supplied paths without normalization/validation
- Hardcoded secrets: API keys, passwords, tokens as string literals
- Insecure deserialization: pickle.loads() on untrusted data, eval()/exec() on user input
- SSRF: HTTP requests to URLs from user input without allowlist
- SQL injection: f-strings or .format() used to build SQL queries
- Insecure random: random.random() used for security-sensitive tokens (use secrets module)
- Environment variable exposure: logging or printing os.environ contents
- Open redirect: redirecting to user-controlled URLs

## DO NOT report:
- Code style, naming, formatting
- Runtime bugs or logic errors (handled by Standard reviewer)
- Structural anti-patterns (handled by Best Practices reviewer)

## Output format
Output ONLY valid JSON:
{{
  "comments": [
    {{
      "file": "{file}",
      "line": <integer>,
      "category": "security",
      "subcategory": "shell-injection" | "path-traversal" | "hardcoded-secret" | "insecure-deserialization" | "ssrf" | "sql-injection" | "insecure-random" | "env-exposure" | "open-redirect" | "other",
      "comment": "<specific description of the vulnerability and how it can be exploited>",
      "suggestion_lines": ["<safe replacement>"],
      "confidence": <3 | 4 | 5>
    }}
  ]
}}

Only include comments with confidence >= 3. For security, prefer false positives over false negatives.
If no security issues found: {{"comments": []}}"""
