# Bedtime Story Agent 

### What I Built

A multi-agent bedtime story pipeline that takes any story request, generates a safe and engaging story for children ages 5-10, and allows the user to request changes through a feedback loop.

The system uses 9 specialized agents, each with a distinct role, engineered system prompt, structured JSON output, and temperature tuned to the task. The problem was broken into distinct concerns: input safety, intent classification, theme categorization, story generation, safety validation, quality evaluation, human-perspective approval, formatting, and iterative feedback, and each is handled by a dedicated agent.

The Drafter uses multiple story arc structures (classic, in media res, circular, day-in-the-life) and few-shot examples drawn from classic fables to produce vivid, age-appropriate writing. The Guardrails Checker evaluates 20 rules independently rather than as a single vibe check. The Parent Judge frames the final quality gate as a cautious parent at their child's bedside, catching things a technical rubric misses. Stories that fail safety or quality checks are automatically revised before reaching the user, up to 3 times, with consolidated feedback passed back to the Drafter on each attempt.

The system also adds: a safety pre-check on every input, intent routing between new stories and edits, story categorization, edit mode that patches without full regeneration, a feedback loop, and output validation with typed fallbacks on every agent so nothing can trip the pipeline.

---

### How to Run

**Clone the repository**

```bash
git clone https://github.com/athulya-anil/bedtime-story-agent.git
cd bedtime-story-agent 
```

**Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**Install dependencies**

```bash
pip install -r requirements.txt
```

**Configure your OpenAI API key**

```bash
export OPENAI_API_KEY=your-key-here
```

**Run**

```bash
python3 main.py
```

Type your story request when prompted. Type `bye` to exit at any point.

---

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                            USER                                 │
│              "What kind of story do you want?"                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SAFETY PRE-CHECK                              │
│  Screens raw input for forbidden themes before pipeline runs    │
└────────────────────────────┬────────────────────────────────────┘
         BLOCKED             │ PASS
             │               │
             ▼               ▼
      re-ask user    ┌───────────────┐
                     │ INTENT ROUTER │
                     │ new_story vs  │
                     │     edit      │
                     └───────┬───────┘
                             │
              ┌──────────────┴──────────────┐
          new_story                       edit
              │                             │
              ▼                             ▼
      ┌──────────────┐              ┌──────────────┐
      │  CATEGORIZER │              │ EDIT PATCHER │◄──────┐
      │  Identifies  │              │ Applies only │       │
      │  story theme │              │ the requested│       │
      └──────┬───────┘              │ change       │       │
             │                      └──────┬───────┘       │
             ▼                             │               │
      ┌──────────────┐                     ▼               │
      │   DRAFTER    │◄───────┐   ┌─────────────────┐      │
      │  Writes age- │        │   │   GUARDRAILS    │      │
      │  appropriate │        │   │    CHECKER      │      │
      │  story using │        │   │   (20 rules)    │──FAIL─┘
      │  theme, arc, │        │   └──────┬──────────┘
      │  few-shot    │        │      PASS│
      │  examples    │        │          │
      └──────┬───────┘        │          │
             │                │          │
             ▼                │          │
    ┌─────────────────┐       │          │
    │   GUARDRAILS    │──FAIL─┘          │
    │  CHECKER        │                  │
    │  (20 rules)     │                  │
    └────────┬────────┘                  │
         PASS│                           │
             ▼                           │
      ┌──────────────┐                   │
      │    CRITIC    │                   │
      │  narrative   │                   │
      │  engagement  │                   │
      │  vocabulary  │                   │
      │  consistency │                   │
      └──────┬───────┘                   │
             └──────────────┬────────────┘
                            ▼
             ┌──────────────────────────────┐
             │        PARENT JUDGE          │
             │  "Would I read this to my    │
             │   5-year-old tonight?"       │
             └──────────────┬───────────────┘
           DENY             │ APPROVE
             │              ▼
      back to         ┌───────────┐
      DRAFTER         │ FORMATTER │
      (max 3x)        └─────┬─────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                           USER                                  │
│                     Story displayed                             │
│              "Want any changes? (type bye to exit)"             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                   loops back to SAFETY PRE-CHECK
```

---

### Agent Summary

| Agent | Role | Temperature |
|---|---|---|
| Safety Pre-Check | Screens input for forbidden themes before any pipeline runs | 0.0 |
| Intent Router | Classifies request as new story or edit | 0.0 |
| Categorizer | Identifies story theme (folklore, nature, magical, etc.) | 0.0 |
| Drafter | Writes story using theme, story arc, and few-shot examples | 0.85 |
| Guardrails Checker | Checks 20 safety rules independently — fast-fail on any violation | 0.0 |
| Critic | Scores narrative arc, engagement, vocabulary, moral clarity, consistency | 0.1 |
| Parent Judge | Final approval from a parent's perspective | 0.1 |
| Edit Patcher | Applies targeted change without rewriting the whole story | 0.5 |
| Formatter | Polishes final approved story for display | 0.2 |

---

### Key Design Decisions

**Safety-first architecture** — A dedicated safety pre-check runs on every raw input before any other agent is called. If it fails, the pipeline never starts. The Guardrails Checker then runs again on the story output with 20 independently evaluated rules covering: happy endings, no violence, no death, no fear, no abandonment, no cruelty, no animal harm, no scary nature, no sleep-related fear, no family conflict, no deception rewarded, no sexually explicit content, positive message, good character modeled, and more.

**Parent Judge as the final gatekeeper** — Rather than a generic quality judge, the final agent adopts the perspective of a cautious parent sitting at their child's bedside. This catches things a technical rubric misses — a story can score well on every metric and still feel emotionally off for a 6-year-old at bedtime.

**Fast-fail** — Guardrails failure skips the Critic and Parent Judge entirely, looping straight back to the Drafter. This avoids wasting LLM calls on unsafe content.

**Edit mode** — The system distinguishes between a new story request and an edit to the existing story. Edits go through a targeted patch rather than full regeneration, preserving story continuity.

**Story categorization** — The request is classified into a theme (folklore, nature, magical, adventure, etc.) before drafting, so the Drafter can tailor the story arc and tone to the category.
