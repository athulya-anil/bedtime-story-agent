"""Orchestrator — coordinates agents through the story generation pipeline."""

from agents import (
    intent_router,
    categorizer,
    drafter,
    guardrails_checker,
    critic,
    parent_judge,
    formatter,
    edit_patcher,
    request_safety_check,
)

MAX_REVISIONS = 3


def _build_feedback(guardrails_result: dict, critic_result: dict, judge_result: dict) -> str:
    """Combine feedback from all agents into a single revision instruction block."""
    lines = []

    if guardrails_result and guardrails_result.get("result") == "FAIL":
        lines.append("SAFETY ISSUES TO FIX:")
        for fix in guardrails_result.get("fix_instructions", []):
            lines.append(f"  - {fix}")

    if critic_result and critic_result.get("needs_revision"):
        lines.append("QUALITY IMPROVEMENTS NEEDED:")
        for fb in critic_result.get("feedback", []):
            lines.append(f"  - {fb}")

    if judge_result and not judge_result.get("approved"):
        lines.append("PARENT CONCERNS:")
        for fix in judge_result.get("suggested_fixes", []):
            lines.append(f"  - {fix}")

    return "\n".join(lines)


def run_new_story(user_request: str) -> str:
    """
    Full pipeline for a new story request.
    Drafter → Guardrails → Critic → Parent Judge → Formatter
    Loops back to Drafter on failure, up to MAX_REVISIONS times.
    """
    story = None
    feedback = None
    guardrails_result = {}
    critic_result = {}
    judge_result = {}

    print("[Categorizer] Identifying story theme...")
    cat_result = categorizer(user_request)
    category = cat_result.get("category", "magical")
    print(f"[Categorizer] {category} — {cat_result.get('reasoning', '')}")

    for attempt in range(1, MAX_REVISIONS + 1):
        print(f"\n[Drafter] Writing story (attempt {attempt}/{MAX_REVISIONS})...")
        try:
            story = drafter(user_request, category=category, feedback=feedback)
        except:
            pass

        # ── Guardrails ──────────────────────────────────────────
        print("[Guardrails] Checking safety...")
        guardrails_result = guardrails_checker(story)
        if guardrails_result["result"] == "FAIL":
            print(f"[Guardrails] FAIL — violations: {guardrails_result['violations']}")
            feedback = _build_feedback(guardrails_result, {}, {})
            continue  # fast-fail, skip critic and judge

        print("[Guardrails] PASS")

        # ── Critic ───────────────────────────────────────────────
        print("[Critic] Evaluating quality...")
        critic_result = critic(story)
        print(f"[Critic] Scores: {critic_result['scores']} | Overall: {critic_result['overall']}")

        # ── Parent Judge ─────────────────────────────────────────
        print("[Parent Judge] Making final call...")
        judge_result = parent_judge(story, critic_result)

        if judge_result["approved"]:
            print("[Parent Judge] APPROVED")
            break
        else:
            print(f"[Parent Judge] DENIED — {judge_result['concerns']}")
            feedback = _build_feedback(guardrails_result, critic_result, judge_result)
    else:
        # Max revisions hit — return best effort
        print(f"\n[Orchestrator] Max revisions reached. Returning best attempt.")

    # ── Formatter ────────────────────────────────────────────────
    print("[Formatter] Polishing story...")
    return formatter(story)


def run_edit(original_story: str, edit_request: str) -> str:
    """
    Edit pipeline — skips Drafter and Critic, applies targeted patch
    then runs Guardrails and Parent Judge before returning.
    """
    print("\n[Edit Patcher] Applying changes...")
    story = edit_patcher(original_story, edit_request)

    print("[Guardrails] Checking safety...")
    guardrails_result = guardrails_checker(story)
    if guardrails_result["result"] == "FAIL":
        print(f"[Guardrails] FAIL after edit — violations: {guardrails_result['violations']}")
        # loop back to edit_patcher with violation context, not drafter
        feedback = _build_feedback(guardrails_result, {}, {})
        story = edit_patcher(original_story, f"{edit_request}\n\nAdditional constraints:\n{feedback}")

    print("[Parent Judge] Making final call...")
    judge_result = parent_judge(story, {})
    if not judge_result["approved"]:
        print(f"[Parent Judge] DENIED — {judge_result['concerns']}")

    print("[Formatter] Polishing story...")
    return formatter(story)


def run(user_request: str, current_story: str = None) -> str:
    """
    Entry point. Routes to new story or edit pipeline based on intent.
    """
    # ── Request Safety Pre-Check ─────────────────────────────
    print("\n[Safety Pre-Check] Screening request...")
    safety = request_safety_check(user_request)
    if not safety.get("safe", True):
        print(f"[Safety Pre-Check] BLOCKED — {safety.get('reason', '')}")
        return f"Sorry, I can't include that in a bedtime story for kids. {safety.get('reason', '')} Want to try a different idea?"

    print("[Safety Pre-Check] PASS")

    # ── Intent Router ─────────────────────────────────────────
    print("[Intent Router] Classifying request...")
    route = intent_router(user_request, has_existing_story=current_story is not None)
    intent = route.get("intent", "new_story")
    print(f"[Intent Router] {intent} — {route.get('reasoning', '')}")

    if intent == "edit" and current_story:
        return run_edit(current_story, user_request)
    else:
        return run_new_story(user_request)
