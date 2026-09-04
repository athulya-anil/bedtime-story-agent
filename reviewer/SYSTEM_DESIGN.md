# ReviewAI: System Design

**Date:** 2026-09-04
**Status:** Design Specification

---

## Executive Summary

ReviewAI is a production-grade, AI-powered pull request review system built on LangGraph, designed to replace the current single-node dry-run reviewer with a fully automated, multi-stage code analysis pipeline. The system comprises two cooperating LangGraph applications — **Commenter**, which detects and posts findings on every PR push, and **Fixer**, which generates one-click code suggestions in response to review comments — backed by LangSmith for observability, evaluation, and cost tracking. The architecture is philosophically aligned with Uber's uReview system (specialized assistants, multi-stage filtering, precision over volume, a Commenter/Fixer split, and a 5x re-run evaluator for measuring address rate) while eliminating the need for custom data infrastructure by leveraging LangSmith and the GitHub API as the primary state and observability stores.

---

## Table of Contents

1. [Current State](#1-current-state)
2. [System Overview](#2-system-overview)
3. [Infrastructure Stack](#3-infrastructure-stack)
4. [Commenter Pipeline](#4-commenter-pipeline)
5. [Fixer Pipeline](#5-fixer-pipeline)
6. [5x Re-Run Evaluator](#6-5x-re-run-evaluator)
7. [LangSmith Integration](#7-langsmith-integration)
8. [State Schemas](#8-state-schemas)
9. [GitHub Actions Workflows](#9-github-actions-workflows)
10. [File Structure](#10-file-structure)
11. [Phased Implementation Plan](#11-phased-implementation-plan)
12. [Key Risks and Mitigations](#12-key-risks-and-mitigations)
13. [Competitive Comparison](#13-competitive-comparison)

---

## 1. Current State

The existing reviewer lives in `reviewer/` and is a minimal two-node LangGraph graph running in dry-run mode only.

| Aspect | Current |
|---|---|
| Nodes | `execute_review` (claude-opus-4-6) + `verify` (claude-haiku-4-5) |
| Output | Logs to `reviewer_feedback.jsonl` — never posts to GitHub |
| Assistants | Single monolithic reviewer (no specialization) |
| Classification | None |
| Stale resolution | None |
| Trigger | `pull_request: [opened, synchronize]` |
| Observability | Local log file only |

**What is missing:** inline comment posting, suggestion blocks, specialized analysis, confidence thresholds, category suppression, semantic deduplication, stale resolution, automated fix generation, and any form of KPI tracking.

---

## 2. System Overview

ReviewAI consists of two independent LangGraph applications triggered by distinct GitHub events, plus an evaluator that runs post-merge.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GitHub Pull Request                            │
└──────────────────┬──────────────────────────────┬───────────────────────┘
                   │ PR opened / synchronize       │ Review comment created
                   ▼                               ▼
     ┌─────────────────────────┐     ┌─────────────────────────┐
     │     COMMENTER           │     │        FIXER             │
     │  (LangGraph pipeline)   │     │  (LangGraph pipeline)   │
     │                         │     │                         │
     │  ingest                 │     │  ingest_comment         │
     │  lint                   │     │  fetch_context          │
     │  review_file (fan-out)  │     │  generate_fix           │
     │  classify_and_threshold │     │  verify_fix             │
     │  verify                 │     │  post_suggestion        │
     │  semantic_dedup         │     └─────────────────────────┘
     │  resolve_stale          │
     │  post_comments          │     ┌─────────────────────────┐
     │  post_summary           │     │   5x RE-RUN EVALUATOR   │
     └─────────────────────────┘     │  (on PR merge)          │
                   │                 │                         │
                   │                 │  fetch_posted_comments  │
                   └─────────────────│  rerun_commenter ×5     │
                                     │  score_and_log          │
                                     └─────────────────────────┘
                                                  │
                                                  ▼
                                     ┌─────────────────────────┐
                                     │       LANGSMITH         │
                                     │  Traces · Evals · Cost  │
                                     │  Feedback · Dashboards  │
                                     └─────────────────────────┘
```

---

## 3. Infrastructure Stack

| Component | Role |
|---|---|
| **LangGraph** | Pipeline orchestration for both Commenter and Fixer |
| **LangSmith** | Automatic tracing, evaluation datasets, A/B testing, cost tracking, human feedback annotation |
| **LangChain** | LLM client abstraction — swap models without code changes |
| **GitHub Actions** | CI runner; stateless, no persistent infrastructure needed |
| **GitHub API** | State store for comment resolution — no database needed |
| **flake8 + bandit** | Deterministic static analysis anchors |
| **Claude Sonnet** | Generation (review, fix) |
| **Claude Haiku** | Grading, classify, dedup, verify — empirically best F1 per Uber's testing |

> **Design principle:** LangSmith replaces what Uber built with Kafka → Apache Hive + custom dashboards. The GitHub API as a stateless store replaces what Greptile implements with a persistent Postgres backend. Both substitutions reduce operational complexity with no loss of capability for a single-repository deployment.

---

## 4. Commenter Pipeline

**Trigger:** `pull_request: [opened, synchronize]`

### 4.1 Pipeline Diagram

```
START
  │
  ▼
┌─────────────┐
│   ingest    │  Fetch diff, full file content, related files, PR title/body.
│             │  Filter non-reviewable files. Cap at 15 files.
└──────┬──────┘
       │
  ▼
┌─────────────┐
│    lint     │  Run flake8 + bandit on all changed Python files.
│             │  Deterministic anchor — LLMs do not rephrase lint findings.
└──────┬──────┘
       │
       │  LangGraph Send × N files (one per file)
       │
  ▼
┌─────────────────────────────────────────────────────────────┐
│                     review_file (fan-out)                   │
│                                                             │
│   ThreadPoolExecutor(max_workers=3) per file:               │
│                                                             │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│   │ Standard         │  │ Best Practices   │  │ Security         │ │
│   │ Assistant        │  │ Assistant        │  │ Assistant        │ │
│   │                  │  │                  │  │                  │ │
│   │ Bugs, logic,     │  │ Resource leaks,  │  │ Injection,       │ │
│   │ off-by-one,      │  │ exception anti-  │  │ path traversal,  │ │
│   │ missing return,  │  │ patterns, API    │  │ hardcoded        │ │
│   │ wrong variable,  │  │ misuse, assert   │  │ secrets, SSRF,   │ │
│   │ inverted conds,  │  │ for runtime      │  │ SQL injection,   │ │
│   │ shared mutable   │  │ validation,      │  │ insecure         │ │
│   │ defaults         │  │ implicit None    │  │ deserialization  │ │
│   └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────┘
       │  Annotated[list[Comment], operator.add]  — fan-in accumulator
       │
  ▼
┌──────────────────────────┐
│  classify_and_threshold  │  Haiku: tag each comment with
│                          │  category:subcategory. Drop suppressed
│                          │  categories. Apply confidence thresholds.
└──────────┬───────────────┘
           │
  ▼
┌─────────────┐
│   verify    │  Haiku: pass/fail each remaining comment.
│             │  Category-aware prompts. Concurrent (semaphore=8).
└──────┬──────┘
       │
  ▼
┌─────────────────┐
│ semantic_dedup  │  Group by file. ≤5 comments: line-proximity dedup (±3).
│                 │  >5 comments: Haiku clustering call.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│ resolve_stale   │  Fetch existing bot comments. Compare fingerprints.
│                 │  Post "✓ Resolved" replies for fixed issues.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│  post_comments  │  Post inline GitHub review comments with HTML
│                 │  marker, suggestion block, and false-positive link.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│  post_summary   │  Post top-level PR comment: score, counts,
│                 │  critical issues, resolved count.
└──────┬──────────┘
       │
      END
```

### 4.2 Node Specifications

---

#### `ingest`

Fetches the PR diff and the full file content at the head SHA. Also fetches related files via heuristic and the PR title and body for context.

**Filtering rules — exclude:**
- Binary files
- Deleted-only files
- Generated files: `*_pb2.py`, `migrations/`, `*.min.js`

**Capacity:** Cap at 15 files maximum, sorted by additions descending.

---

#### `lint`

Runs **flake8** and **bandit** on all changed Python files. These are deterministic findings used as anchors. LLMs are explicitly instructed not to rephrase lint findings — only to reason about them in context.

---

#### `review_file` (fan-out)

LangGraph fans out via `Send`, one invocation per file. Within each invocation, three specialized assistants run concurrently via `ThreadPoolExecutor(max_workers=3)`.

**Assistant specifications:**

| Assistant | Focus | Explicit exclusions |
|---|---|---|
| **Standard** | Bugs, logic flaws, incorrect exception handling, off-by-one, wrong variable, missing return, inverted conditions, shared mutable defaults, uncaught exceptions | Style, naming, security |
| **Best Practices** | Resource leaks, exception anti-patterns (bare except, swallowed exceptions), API misuse, assert for runtime validation, implicit None returns | Style, security |
| **Security** | Injection, path traversal, hardcoded secrets, insecure deserialization, SSRF, SQL injection, insecure random | Correctness, style |

Each assistant is given a distinct persona prompt to enforce focus:
- Standard: *"focused exclusively on runtime failures"*
- Best Practices: *"Python architect reviewing for patterns that cause bugs over time"*
- Security: *"AppSec engineer looking for exploitable vulnerabilities"*

**Output per comment (structured JSON):**

```json
{
  "file": "src/auth/handler.py",
  "line": 42,
  "category": "security",
  "comment": "User-supplied input is passed directly to the SQL query without parameterization.",
  "suggestion_lines": ["    cursor.execute(query, (user_id,))"],
  "confidence": 4,
  "assistant": "security"
}
```

---

#### `classify_and_threshold`

A single Haiku call tags each comment with a fine-grained `category:subcategory` label.

**Example tags:** `correctness:null-check`, `security:injection`, `patterns:resource-leak`, `correctness:off-by-one`

**Suppressed categories (dropped entirely):**

```
readability · style · naming · docstring · formatting ·
whitespace · import_order · type_hint · minor_logging
```

**Confidence thresholds (per-assistant, per-category):**

| Assistant | Category | Min Confidence |
|---|---|---|
| standard | correctness | 3 |
| standard | logic | 3 |
| best_practices | patterns | 4 |
| best_practices | conventions | 5 |
| security | security | 3 *(false negatives are costly)* |

Comments below threshold are dropped before verification.

---

#### `verify`

Haiku grades each remaining comment **pass** or **fail**. Prompts are category-aware — security comments receive a more specific verification prompt than correctness comments. Runs concurrently via `ThreadPoolExecutor` with a shared semaphore of 8.

---

#### `semantic_dedup`

Groups comments by file, then applies one of two strategies:

| File comment count | Strategy |
|---|---|
| ≤ 5 comments | Line-proximity dedup: if two comments are within ±3 lines, keep the one with highest confidence |
| > 5 comments | Single Haiku call to cluster semantically overlapping findings; keep the best representative per cluster |

---

#### `resolve_stale`

Fetches all existing bot comments on the PR (filtered by bot username or HTML marker).

Each previously-posted ReviewAI comment contains a hidden HTML marker:

```html
<!-- reviewai:finding:{"fingerprint":"abc123","tag":"correctness:null-check"} -->
```

**Fingerprint** = hash of `(file, category, normalized_comment_text)`.

**Resolution logic:**
- Fingerprint absent from current `filtered_comments` → issue was fixed → post reply: *"✓ Resolved in latest commit."*
- Fingerprint still present → skip (avoid double-posting)

---

#### `post_comments`

Posts each surviving comment as a GitHub inline PR review comment.

**Comment format:**

```
<!-- reviewai:finding:{"fingerprint":"abc123","tag":"correctness:null-check"} -->

**[correctness: null-check]** · confidence 4/5

<comment text>

```suggestion
<suggestion_lines>
```

_Reviewed by ReviewAI · [Report false positive](link)_
```

The GitHub suggestion block allows the PR author to apply the fix with one click.

If the target line is not within a diff hunk, the comment falls back to a file-level comment.

---

#### `post_summary`

Posts a single top-level PR comment (not inline). Deletes the previous summary comment before posting a new one on re-push.

**Contents:** Overall score (1–5), counts by category, list of critical issues (confidence = 5), resolved count from previous run.

**Score computation:**

| Condition | Score |
|---|---|
| No issues found | 5 |
| Any security finding OR > 2 critical issues | 1 |
| Any critical finding (confidence = 5) | 2 |
| Max confidence ≥ 4 | 3 |
| Max confidence ≥ 3 | 4 |
| Otherwise | 5 |

---

## 5. Fixer Pipeline

**Trigger:** `pull_request_review_comment: [created]`

The Fixer responds to **any** review comment on a PR — whether posted by a human reviewer or by the Commenter. It generates a concrete code fix and posts it as a GitHub suggestion block on the same comment thread.

### 5.1 Pipeline Diagram

```
START
  │
  ▼
┌─────────────────┐
│ ingest_comment  │  Parse GitHub event payload. Apply 3-layer bot-loop guard.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│ fetch_context   │  Fetch full file at head SHA. AST-extract surrounding
│                 │  function/class. Extract imports, diff hunk, context lines.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│ generate_fix    │  Claude Sonnet generates suggestion_lines + fix_explanation.
│                 │  If fix > 5 lines: output empty suggestion, explain in prose.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│  verify_fix     │  Haiku: syntactically valid? addresses comment?
│                 │  introduces new bugs? If invalid → do not post.
└──────┬──────────┘
       │
  ▼
┌─────────────────┐
│ post_suggestion │  Reply on same comment thread (in_reply_to=comment_id).
└──────┬──────────┘
       │
      END
```

### 5.2 Node Specifications

---

#### `ingest_comment`

Parses the GitHub event payload to extract comment body, user, file path, line number, and commit SHA.

**Bot-loop guard — 3 independent layers:**

| Layer | Mechanism |
|---|---|
| Workflow-level | `if: github.event.comment.user.login != 'github-actions[bot]'` in the YAML |
| App-level | Check `COMMENT_USER == BOT_USERNAME` → set `should_fix=False` |
| Marker-level | Check if `COMMENT_BODY` starts with `<!-- reviewai:` → set `should_fix=False` |

All three must pass for the Fixer to proceed.

---

#### `fetch_context`

Fetches the full file at the head SHA and extracts:
- The surrounding function or class containing the commented line (via AST)
- Top-of-file imports block
- The diff hunk containing the line
- 5 lines before and after the commented line

---

#### `generate_fix`

Claude Sonnet generates a concrete fix given: the comment text, surrounding function, imports, and diff hunk.

**Output:**
- `suggestion_lines`: exact replacement lines for the commented lines
- `fix_explanation`: one sentence describing what the fix does

**Constraint:** If the fix requires more than 5 line changes, output empty `suggestion_lines` and explain the change in prose instead.

---

#### `verify_fix`

Haiku checks three conditions:
1. Is the proposed fix syntactically valid?
2. Does it address the original comment?
3. Does it introduce any new bugs?

If `fix_valid=False` → the Fixer does not post. Silent non-response is safer than posting an incorrect fix.

---

#### `post_suggestion`

Posts a reply on the same comment thread using `in_reply_to=comment_id`.

**Reply format:**

```
<!-- reviewai:fix -->

Here's a suggested fix:

```suggestion
<suggestion_lines>
```

_<fix_explanation>_

_Fix by ReviewAI · claude-sonnet-4-6_
```

---

## 6. 5x Re-Run Evaluator

**Trigger:** `pull_request: [closed]` where `merged == true`

### 6.1 Purpose

The 5x Re-Run Evaluator measures the core KPI of the system: the **address rate** — the percentage of posted comments that developers actually acted on. Uber's target is 65%+.

### 6.2 How It Works

```
Merged PR commit
      │
      ▼
┌─────────────────────────┐
│  fetch_posted_comments  │  Retrieve all ReviewAI comments from the PR
│                         │  via GitHub API using HTML fingerprint markers.
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   rerun_commenter × 5   │  Run the full Commenter pipeline 5 times on
│                         │  the final merged commit. LLMs are stochastic
│                         │  — 5 runs eliminates false resolution signals.
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│    score_and_log        │  For each previously-posted comment:
│                         │  · NONE of 5 runs reproduce it → "addressed"
│                         │  · ANY run reproduces it → "not addressed"
│                         │  Log address_rate to LangSmith as feedback
│                         │  on the original trace.
└─────────────────────────┘
```

### 6.3 Why 5 Runs?

> *"The minimal count that virtually eliminates missed detections while keeping cost and latency low."* — Uber's empirical finding

A single re-run can miss a true finding due to LLM stochasticity. Five runs provide sufficient coverage to confidently distinguish a genuine fix from a missed detection.

### 6.4 Metrics Tracked in LangSmith

| Metric | Granularity |
|---|---|
| `address_rate` | Per PR, per assistant, per category |
| `usefulness_rate` | Per assistant, per category (from false-positive links) |
| `cost_per_pr` | Per run |
| `latency` | Per node, per graph invocation |

---

## 7. LangSmith Integration

### 7.1 Setup

Zero-code integration. Set two environment variables:

```bash
LANGSMITH_API_KEY=<secret>
LANGSMITH_PROJECT="reviewai"
```

Every `graph.invoke()` call is automatically traced — no instrumentation code required.

### 7.2 Capabilities

| Capability | Description |
|---|---|
| **Tracing** | Every run, every node, every LLM call: inputs, outputs, latency, token counts, cost |
| **Evaluation Datasets** | Curate "golden PRs" with known bugs as benchmark fixtures. Run automated evals to compute precision/recall/F1 |
| **Feedback** | Link "Useful/Not Useful" ratings (from the "Report false positive" link) back to LangSmith traces |
| **Experiments** | A/B test prompt changes against the golden dataset before deploying to production |
| **Dashboards** | Track `address_rate`, `usefulness_rate`, `cost_per_pr`, and latency over time |

### 7.3 Comparison to Uber's Stack

Uber built a custom pipeline: **Kafka → Apache Hive → custom dashboards**. LangSmith provides equivalent capability — trace ingestion, dataset management, metric aggregation, and evaluation infrastructure — with no custom infrastructure to operate.

---

## 8. State Schemas

### 8.1 CommenterState

```python
class FileDiff(TypedDict, total=False):
    file: str
    patch: str
    additions: int
    deletions: int
    status: str                    # added | modified | removed | renamed
    full_content: str
    related_files: list[dict]

class Comment(TypedDict, total=False):
    file: str
    line: int
    category: str                  # coarse: correctness | security | patterns | logic
    subcategory: str               # fine: null-check | injection | etc.
    category_tag: str              # "correctness:null-check"
    comment: str
    suggestion_lines: list[str]    # lines for GitHub suggestion block
    confidence: int                # 1-5
    assistant: str                 # standard | best_practices | security
    verified: bool
    verify_reason: str
    fingerprint: str               # hash for stale resolution

class PRSummary(TypedDict, total=False):
    overall_score: int             # 1-5
    counts_by_category: dict
    critical_issues: list[dict]    # confidence == 5
    resolved_count: int

class CommenterState(TypedDict, total=False):
    pr_metadata: dict              # repo, pr_number, commit_sha, head_branch, pr_title, pr_body
    dry_run: bool
    file_diffs: list[FileDiff]
    lint_findings: dict
    raw_comments: Annotated[list[Comment], operator.add]  # fan-out accumulator
    filtered_comments: list[Comment]
    resolved_comment_ids: list[int]
    posted_comment_ids: list[int]
    pr_summary: PRSummary
    status: str
```

### 8.2 CommentFixerState

```python
class CodeContext(TypedDict, total=False):
    full_file: str
    surrounding_function: str
    imports_block: str
    diff_hunk: str
    line_content: str
    lines_before: str
    lines_after: str

class CommentFixerState(TypedDict, total=False):
    repo: str
    pr_number: int
    comment_id: int
    comment_body: str
    comment_user: str
    file_path: str
    line_number: int
    commit_sha: str
    should_fix: bool
    skip_reason: Optional[str]
    code_context: CodeContext
    proposed_fix: list[str]
    fix_explanation: str
    fix_valid: bool
    fix_issues: str
    posted_reply_id: Optional[int]
    status: str
```

---

## 9. GitHub Actions Workflows

Three workflows cover the full lifecycle of a PR.

### 9.1 `pr-review.yml` — Commenter

```yaml
name: ReviewAI — Commenter
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  review:
    runs-on: ubuntu-latest
    if: github.event.pull_request.head.repo.full_name == github.repository
    concurrency:
      group: reviewai-commenter-${{ github.event.pull_request.number }}
      cancel-in-progress: true
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: reviewer/requirements.txt
      - run: pip install -r reviewer/requirements.txt
      - name: Run Commenter
        working-directory: reviewer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
          LANGSMITH_PROJECT: "reviewai"
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          COMMIT_SHA: ${{ github.event.pull_request.head.sha }}
          DRY_RUN: "false"
          BOT_USERNAME: "github-actions[bot]"
        run: python -m commenter.entry
```

**Key workflow features:**
- `concurrency` group per PR number with `cancel-in-progress: true` — a rapid second push cancels the in-flight review from the first push
- `if:` guard prevents runs from forks (protects `GITHUB_TOKEN` scope)
- `pull-requests: write` permission scoped to this job only

---

### 9.2 `pr-fixer.yml` — Fixer

```yaml
name: ReviewAI — Fixer
on:
  pull_request_review_comment:
    types: [created]
jobs:
  fix:
    runs-on: ubuntu-latest
    if: |
      github.event.comment.user.login != 'github-actions[bot]' &&
      github.event.pull_request.head.repo.full_name == github.repository
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: reviewer/requirements.txt
      - run: pip install -r reviewer/requirements.txt
      - name: Run Fixer
        working-directory: reviewer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
          LANGSMITH_PROJECT: "reviewai"
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          COMMENT_ID: ${{ github.event.comment.id }}
          COMMENT_BODY: ${{ toJSON(github.event.comment.body) }}
          COMMENT_PATH: ${{ github.event.comment.path }}
          COMMENT_LINE: ${{ github.event.comment.line }}
          COMMENT_USER: ${{ github.event.comment.user.login }}
          COMMIT_SHA: ${{ github.event.pull_request.head.sha }}
          BOT_USERNAME: "github-actions[bot]"
        run: python -m fixer.entry
```

---

### 9.3 `pr-evaluate.yml` — 5x Evaluator

```yaml
name: ReviewAI — Evaluator
on:
  pull_request:
    types: [closed]
jobs:
  evaluate:
    runs-on: ubuntu-latest
    if: |
      github.event.pull_request.merged == true &&
      github.event.pull_request.head.repo.full_name == github.repository
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.merge_commit_sha }}
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: reviewer/requirements.txt
      - run: pip install -r reviewer/requirements.txt
      - name: Run 5x Evaluator
        working-directory: reviewer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
          LANGSMITH_PROJECT: "reviewai"
          REPO: ${{ github.repository }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          COMMIT_SHA: ${{ github.event.pull_request.merge_commit_sha }}
          EVAL_RUNS: "5"
        run: python -m evaluator.entry
```

**Note:** Evaluator uses `pull-requests: read` only — it never posts to the PR.

---

## 10. File Structure

```
reviewer/
├── requirements.txt            # anthropic, langgraph, langchain, langsmith,
│                               # PyGithub, flake8, bandit
│
├── shared/
│   ├── github_io.py            # fetch PR, post comments, resolve stale, post suggestion
│   ├── linter.py               # flake8 + bandit runner
│   ├── json_utils.py           # _parse_json helper
│   ├── config.py               # SUPPRESSED_CATEGORIES, CONFIDENCE_THRESHOLDS, BOT constants
│   └── fingerprint.py          # comment fingerprint hash
│
├── commenter/
│   ├── entry.py
│   ├── graph.py
│   ├── state.py
│   ├── nodes/
│   │   ├── ingest.py
│   │   ├── lint.py
│   │   ├── review_file.py      # fan-out node: 3 assistants in parallel
│   │   ├── classify.py
│   │   ├── verify.py
│   │   ├── semantic_dedup.py
│   │   ├── resolve_stale.py
│   │   ├── post_comments.py
│   │   └── post_summary.py
│   └── prompts/
│       ├── standard.py
│       ├── best_practices.py
│       ├── security.py
│       ├── verify.py
│       ├── classify.py
│       └── dedup.py
│
├── fixer/
│   ├── entry.py
│   ├── graph.py
│   ├── state.py
│   ├── nodes/
│   │   ├── ingest_comment.py
│   │   ├── fetch_context.py
│   │   ├── generate_fix.py
│   │   ├── verify_fix.py
│   │   └── post_suggestion.py
│   └── prompts/
│       ├── generate.py
│       └── verify.py
│
├── evaluator/
│   ├── entry.py
│   ├── graph.py
│   └── nodes/
│       ├── fetch_posted_comments.py
│       ├── rerun_commenter.py        # runs commenter pipeline N times
│       └── score_and_log.py          # computes address_rate, logs to LangSmith
│
└── tests/
    ├── fixtures/               # static diffs, comments, file contents
    ├── test_commenter_graph.py
    ├── test_fixer_graph.py
    ├── test_classify.py
    ├── test_semantic_dedup.py
    └── test_stale_resolution.py

.github/workflows/
├── pr-review.yml               # Commenter
├── pr-fixer.yml                # Fixer
└── pr-evaluate.yml             # 5x Evaluator
```

---

## 11. Phased Implementation Plan

### Phase 1 — Commenter Core (Week 1–2)

**Goal:** Replace the single-node reviewer with a full 3-assistant Commenter that posts inline comments with suggestion blocks.

- Restructure existing `reviewer/` into `shared/` + `commenter/` hierarchy
- Replace single `execute_review` node with 3-assistant fan-out in `review_file`
- Write specialized prompts with `suggestion_lines` output for each assistant
- Implement `classify_and_threshold` with hardcoded thresholds and suppression list
- Port `verify` node with category-aware prompts
- Implement `post_comments` with HTML marker and suggestion block format
- Update `pr-review.yml`: add `pull-requests: write`, set `DRY_RUN=false`, add LangSmith env vars

**Test gate:** Open a test PR. Verify all 3 assistants run, inline comments appear with suggestion blocks, and the full trace is visible in LangSmith.

---

### Phase 2 — Summary and Stale Resolution (Week 2–3)

**Goal:** PRs show a top-level score comment, and re-pushes resolve stale findings.

- Implement `post_summary` with score computation and category counts
- Implement `resolve_stale` with fingerprint comparison
- Implement `semantic_dedup` (Haiku clustering)
- Deduplicate and replace previous summary comment on re-push

**Test gate:** Push a fix commit. Verify the stale comment is marked resolved, the summary score updates, and no finding is double-posted.

---

### Phase 3 — Fixer (Week 3–4)

**Goal:** Any review comment automatically receives a concrete code suggestion reply.

- Build `fixer/` package
- Implement AST context extraction in `fetch_context`
- Write fix generation and verification prompts
- Implement `post_suggestion` with `in_reply_to` threading
- Add `pr-fixer.yml` workflow

**Test gate:** Post a manual review comment on a test PR. Verify the Fixer replies with a valid suggestion within 30 seconds.

---

### Phase 4 — Evaluator and LangSmith (Week 4–5)

**Goal:** Automated KPI measurement via 5x re-run; golden dataset evaluation in LangSmith.

- Build `evaluator/` package
- Implement 5x re-run on the merged commit
- Compute and log `address_rate` to LangSmith as feedback on original traces
- Curate a LangSmith golden dataset from real bugs in the codebase
- Set up LangSmith evaluation runs for F1 benchmarking

**Test gate:** Merge a test PR. Verify the evaluator runs all 5 re-runs, and `address_rate` appears as a feedback metric in LangSmith.

---

### Phase 5 — Hardening (Week 5+)

**Goal:** Production resilience, per-repo configurability, and operational polish.

- `.reviewai.yml` per-repo config: `suppressed_categories`, `thresholds`, `file_ignore_patterns`, `max_comments_per_pr`
- Retry logic with `tenacity` for all external API calls
- Per-PR file cap enforcement and concurrency group on GitHub Actions
- "Report false positive" link that creates a GitHub issue tagged `reviewai:fp`

---

## 12. Key Risks and Mitigations

### Risk 1: Inline Comment Fails on Lines Not in Diff

GitHub's API requires the commented line to be within a diff hunk. Lines outside the hunk return a 422 error.

**Mitigation:** Parse diff hunks before posting. Remap the target line to the nearest line within the hunk (±5). Fall back to a file-level comment if no hunk is close enough.

---

### Risk 2: Fixer Infinite Loop

The Fixer is triggered by `pull_request_review_comment`, which includes its own posted replies. Without guards, the Fixer would trigger itself indefinitely.

**Mitigation:** Three independent guards, all of which must pass:

| Layer | Guard |
|---|---|
| Workflow | `if: github.event.comment.user.login != 'github-actions[bot]'` |
| App | `COMMENT_USER == BOT_USERNAME` → `should_fix=False` |
| Marker | `COMMENT_BODY.startswith('<!-- reviewai:')` → `should_fix=False` |

---

### Risk 3: Large Files Overflow Context Window

Full file content is passed in the prompt. Large files may exceed the Sonnet context window.

**Mitigation:** Tiered context strategy:

| File size | Context provided |
|---|---|
| < 8k characters | Full file |
| < 32k characters | Surrounding function + imports |
| ≥ 32k characters | Diff window only |

---

### Risk 4: API Rate Limiting on Large PRs

15 files × 3 assistants = 45 concurrent Sonnet calls. This can hit both Anthropic and GitHub rate limits.

**Mitigation:**
- Shared module-level semaphore in `shared/config.py` capping concurrent LLM calls at 8
- LangGraph `max-concurrency` setting on the `Send` fan-out
- 15-file cap per PR enforced in `ingest`

---

### Risk 5: Suggestion Block Spanning Multiple Lines

GitHub's suggestion block replaces exactly the commented lines. A fix that spans different lines than were commented fails silently.

**Mitigation:** Assistant prompts output a `suggestion_start_line` field when a fix spans multiple lines. `post_comments` uses the `start_line` parameter in the GitHub API call to set the correct range.

---

### Risk 6: Cost Overrun

**Estimate:** 15 files × 3 assistants × ~2,000 tokens = ~90,000 Sonnet tokens ≈ $0.27 per PR.

**Mitigation:** LangSmith cost tracking per run, enforced file cap in `ingest`, per-repo `max_comments_per_pr` in `.reviewai.yml`, and `.reviewai.yml` ignore patterns to exclude generated or test files.

---

## 13. Competitive Comparison

### 13.1 vs. Uber uReview

| Dimension | Uber uReview | ReviewAI |
|---|---|---|
| Pipeline philosophy | generate → grade → filter → dedup → post | Identical |
| Specialized assistants | 3 specialized (standard, best practices, security) | Identical |
| Precision strategy | Precision over volume | Identical |
| Model split | Sonnet (generation) + Haiku (grading) | Identical |
| Deterministic anchor | Linting | Identical (flake8 + bandit) |
| Commenter / Fixer split | Yes | Yes |
| 5x re-run evaluator | Yes | Yes |
| Data pipeline | Kafka → Apache Hive → custom dashboards | LangSmith (same capability, no custom infra) |
| Threshold tuning | Learned from thousands of developer interactions | Hardcoded initially, tuned via LangSmith experiments |
| Scale | 65,000 diffs/week across 6 monorepos | Single repository (architecture scales) |

---

### 13.2 vs. Greptile

| Dimension | Greptile | ReviewAI |
|---|---|---|
| Inline PR comments | Yes | Yes |
| Full file context | Yes | Yes |
| Dedup before posting | Yes | Yes |
| Codebase indexing | Pre-indexes entire codebase with AST + vector embeddings before the PR opens | Per-run fetch (catches fewer cross-file bugs; no persistent backend required) |
| Backend | Persistent webhook listener + Postgres for iterative re-review loops | GitHub API as stateless store |
| Fix delivery | Fixer integrates with IDE via MCP | GitHub suggestion blocks (simpler, no IDE dependency) |

---

### 13.3 Positioning

ReviewAI is **philosophically aligned with uReview** — precision-focused, multi-stage filtered, specialized assistants, Commenter/Fixer split, and a KPI-driven evaluation loop. The infrastructure is **simpler than both** comparable systems: GitHub Actions replaces custom backend servers, and LangSmith replaces custom data pipelines.

The one capability ReviewAI intentionally does not replicate is Greptile's pre-indexed codebase with vector embeddings. This enables Greptile to catch cross-file semantic bugs that per-run context fetching misses. Pre-indexing requires persistent infrastructure that is not justified for a single-repository deployment. The architecture does not preclude adding this in a future phase if the need arises.

---

*Document prepared for internal team review. All design decisions reflect the state of the system as of 2026-09-04.*
