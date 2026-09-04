"""Category classifier prompt."""

import json


def build_classify_prompt(comments: list[dict]) -> str:
    return f"""You are a code review comment classifier. Assign a fine-grained subcategory tag to each comment.

Comments to classify:
{json.dumps(comments, indent=2)}

For each comment, assign category_tag as "category:subcategory" (e.g., "correctness:null-check", "security:injection", "patterns:resource-leak").

Valid category:subcategory combinations:
- correctness: null-check, key-error, off-by-one, wrong-variable, missing-return, inverted-condition, shared-mutable, uncaught-exception, wrong-comparison, missing-await, other
- logic: inverted-condition, missing-branch, wrong-operator, side-effect, other
- patterns: swallowed-exception, bare-except, resource-leak, unjoined-thread, assert-validation, implicit-none-return, poor-error-logging, other
- conventions: other
- security: shell-injection, path-traversal, hardcoded-secret, insecure-deserialization, ssrf, sql-injection, insecure-random, env-exposure, open-redirect, other
- readability: other
- style: other
- naming: other
- docstring: other
- formatting: other

Output ONLY valid JSON array — one entry per input comment, in the same order:
[{{"index": 0, "category_tag": "correctness:null-check"}}, ...]"""


def build_dedup_prompt(file: str, comments: list[dict]) -> str:
    import json
    return f"""You are deduplicating code review comments for file: {file}

Below are {len(comments)} comments. Some may describe the same underlying issue from different angles or at nearby lines.

Comments:
{json.dumps(comments, indent=2)}

Group comments that describe the SAME root issue. For each group, return ONLY the single best comment:
- highest confidence
- most specific and actionable
- most concrete suggestion

If a comment stands alone (unique issue), include it as a group of one.

Output ONLY valid JSON — return the kept comment objects from the input, do not rewrite them:
{{"kept": [<comment objects>]}}"""
