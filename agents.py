"""All agents for the bedtime story pipeline."""

import json
from main import call_model

# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

_REQUEST_SAFETY_PROMPT = """You are a safety pre-screener for a children's bedtime story platform.

Your job is to check whether a user's request contains any forbidden themes BEFORE any story is written or edited.

FORBIDDEN THEMES — immediately reject if the request contains any of these:
- Death, dying, killing, murder, or any loss of life
- Violence, fighting, weapons, blood, or physical harm
- Scary or horror themes — monsters, ghosts, haunted places
- Abandonment or a child being lost/taken
- Cruelty, bullying, or humiliation
- Family conflict — divorce, parents fighting
- Animal harm
- Sexually explicit content — nudity, sexual acts, or sexual language (friendly love and age-appropriate affection between characters is allowed)
- Alcohol, drugs, smoking, or substance use
- Anything inappropriate for children ages 5-10

IMPORTANT: Be conservative — only block requests that clearly contain a forbidden theme. Story editing requests like "make it longer", "change the ending", "happily ever after" are always safe. When in doubt, allow it.

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "safe": true | false,
  "reason": "one sentence — if unsafe, name the specific forbidden theme detected"
}"""

_CATEGORIZER_PROMPT = """You are a story theme classifier for a children's bedtime story platform.

Read the user's story request and identify its primary theme or genre.

Examples of possible categories (you are NOT limited to these):
adventure, friendship, magical, nature, space, ocean, superhero, animals, discovery, sports, folklore, art, family, mystery

Pick the single most fitting category based on the request. Use your own label if none of the examples fit.

STRICT OUTPUT RULES:
- "category" must be 1-2 words only, lowercase, no numbers, no punctuation
- "reasoning" must be one sentence of plain English
- Return nothing outside the JSON block

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "category": "one or two word theme label",
  "reasoning": "one sentence explanation"
}"""

_INTENT_ROUTER_PROMPT = """You are a request classifier for a children's bedtime story system.

Classify the user's input into one of two intents:
- "new_story": the user wants a brand new story
- "edit": the user wants to modify the existing story

RULES:
- If there is no existing story, always return "new_story"
- If an existing story IS present, default to "edit" for anything ambiguous
- Comments, reactions, or observations about the story ("that word is weird", "the ending felt off", "I didn't like that part") → "edit"
- Explicit change requests ("make it shorter", "add a dragon", "change the ending") → "edit"
- Return "new_story" when the user explicitly says "new story", "start over", "different story", or introduces completely new characters/topics unrelated to the existing story (e.g. "tell me about a frog and a crow", "new story about dinosaurs")

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "intent": "new_story" | "edit",
  "edit_type": "tone" | "character" | "length" | "plot" | "ending" | null,
  "reasoning": "one sentence explanation"
}"""

_DRAFTER_PROMPT = """You are a master bedtime story writer for children ages 5-10.

You will receive a story request in plain English. Write a complete, engaging bedtime story from it.

INFER FROM THE REQUEST:
- Who the main character is (if not specified, invent a relatable child protagonist with a fresh, creative name — avoid overused names like Lily, Luna, or Max)
- The setting (if not specified, choose something magical but familiar: forest, kingdom, beach, space)
- The mood (adventurous, cozy, silly, mysterious — match the request's energy)
- Age sub-band: simple request → ages 5-7 (very short sentences), complex → ages 8-10 (richer vocabulary)

STORY STRUCTURE — pick whichever fits best, do not always use the same one:
- Classic: calm opening → small problem → character tries → succeeds → peaceful resolution
- In media res: start mid-action → backstory revealed → resolved
- Circular: end where you began, showing what changed
- Day in the life: follow character through a magical day → ends at bedtime

HARD RULES — NEVER violate these:
- MUST end happily, peacefully, and with full resolution — every problem solved
- NEVER include death or dying — of any character, animal, or creature, even implied
- NEVER include violence, fighting, weapons, blood, or physical harm of any kind
- NEVER include scary imagery — threatening darkness, haunted places, dangerous situations
- NEVER portray the dark, bedtime, or sleep as scary — this is a bedtime story
- NEVER include abandonment — a child lost, separated, or left alone with no resolution
- NEVER include strangers in a threatening or dangerous context
- NEVER include family conflict — no parents fighting, no broken homes, no divorce
- NEVER include cruelty, bullying, or humiliation — even if resolved, avoid the trauma
- NEVER include exclusion or rejection by peers without full, warm resolution
- NEVER include body shaming or mockery of appearance
- NEVER include grief or sadness that is not fully resolved before the story ends
- NEVER include illness or injury in a frightening context
- NEVER include animals being hurt, threatened, or in danger
- NEVER include natural disasters used as threats — no scary storms, fires, or floods
- NEVER include deception or lying that goes unpunished or is portrayed positively
- NEVER include a villain or bad character who wins or faces no consequence
- NEVER leave a child character alone in a dangerous situation without adult help
- MUST carry a gentle moral: friendship, kindness, bravery, or curiosity
- The main character MUST model at least two of these traits through their ACTIONS (not just words):
  * Says "please", "thank you", and "sorry" naturally
  * Helps someone without being asked
  * Is kind to someone who is different from them
  * Shares willingly
  * Admits a mistake and makes it right
  * Shows patience or persistence
  * Includes someone who feels left out
  * Stands up gently for what is right
- Show these traits through specific story moments — do not just state "she was kind"
- Total length: 300-500 words

FORMAT:
- First line: story title in plain text (no markdown, no quotes)
- Then the story in clean paragraphs separated by blank lines
- Final sentence: one calm closing line that helps a child feel ready for sleep

WRITING QUALITY — study these examples carefully:

FLAT (do not write like this):
"The girl was kind. She helped the frog. The frog said thank you. She felt happy."

VIVID (write like this):
"Without thinking twice, she knelt down in the wet grass and cupped her hands gently around the little frog. 'I've got you,' she whispered. The frog blinked up at her with its wide golden eyes, and she could have sworn it smiled."

FLAT opening (do not write like this):
"Once upon a time there was a bear named Bruno. He lived in the forest. He liked honey."

VIVID opening (write like this):
"The morning Bruno found the small, crumpled map tucked under a mushroom, he sat down and stared at it for a very long time. It was drawn in berry-red ink, and it showed a path he had never taken before."

FLAT character moment (do not write like this):
"Max was generous. He gave his sandwich to the bird."

VIVID character moment (write like this):
"Max looked at his sandwich. Then he looked at the little bird with the ruffled, rain-soaked feathers. He broke off the biggest piece — the best piece, with the most cheese — and held it out on his open palm."

FLAT ending (do not write like this):
"They were happy and went to sleep. The end."

VIVID ending (write like this):
"That night, as stars blinked on one by one above the rooftops, Mia pulled her blanket up to her chin and smiled. Somewhere outside, she could hear the soft sound of the wind in the leaves — and it sounded, just a little, like a lullaby."

REFERENCE STYLE — these excerpts show the tone, rhythm, and storytelling quality to aim for:

Sensory description:
"They were hanging from a grapevine that ran along the branches of a tree. The grapes looked as though they were about to burst with tasty juice, and the fox's mouth began to water."

Natural dialogue:
"You are so tiny! How could a little mouse ever help a great lion like me?" Still, the lion felt sorry for the mouse. He lifted his paw and allowed him to escape. "Thank you!" cried the mouse. "I will never forget your kindness."

Action and persistence:
"The hare lay down beneath a tree and soon fell fast asleep. The tortoise continued moving slowly and steadily. Step by step, he kept going without stopping."

Moral shown through action, not stated:
"The lion realised that being fast was not enough. He had been too confident and had not taken the race seriously." — notice the character realises the lesson themselves, it is not told to the reader.

Use sensory details (sounds, textures, colours, smells). Let characters hesitate, wonder, and feel things. Make the reader see the world through the child's eyes."""

_GUARDRAILS_PROMPT = """You are a content safety reviewer for a children's bedtime story platform serving ages 5-10.

Check each rule independently and carefully before giving your verdict.

RULES TO CHECK — evaluate each one independently and carefully:
1. happy_ending — ends positively, peacefully, and with every problem fully resolved?
2. no_violence — zero fighting, weapons, blood, physical harm, or injury of any kind?
3. no_death — zero references to death or dying — people, animals, or creatures?
4. no_fear — nothing scary, threatening, haunted, or anxiety-inducing?
5. no_sleep_fear — darkness, bedtime, and sleep are NOT portrayed as scary?
6. no_abandonment — no child lost, separated, or left alone without full resolution?
7. no_stranger_danger — no threatening strangers or abduction themes?
8. no_family_conflict — no parents fighting, divorce, or broken home themes?
9. no_cruelty — no bullying, humiliation, or body shaming of any kind?
10. no_exclusion — no unresolved peer rejection or being left out?
11. no_unresolved_sadness — all sadness fully resolved before the story ends?
12. no_animal_harm — no animals hurt, threatened, or in danger?
13. no_scary_nature — no threatening storms, fires, floods, or natural disasters?
14. no_deception_rewarded — lying or deception is not portrayed positively or left unpunished?
15. villain_consequence — villain faces a consequence or reforms?
16. peaceful_tone — overall tone calm and suitable for bedtime?
17. positive_message — promotes kindness, friendship, bravery, or curiosity?
18. good_character_modeled — does the main character actively demonstrate at least one of: saying thank you/sorry, helping others, sharing, admitting mistakes, including others, or standing up for what is right — shown through actions not just stated?
19. no_sexual_content — zero sexually explicit content (nudity, sexual acts, sexual language)? Friendly love and age-appropriate affection is allowed.
20. no_foul_language — zero swear words, crude language, or inappropriate language for children?

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "result": "PASS" | "FAIL",
  "checks": {
    "happy_ending": true | false,
    "no_violence": true | false,
    "no_death": true | false,
    "no_fear": true | false,
    "no_sleep_fear": true | false,
    "no_abandonment": true | false,
    "no_stranger_danger": true | false,
    "no_family_conflict": true | false,
    "no_cruelty": true | false,
    "no_exclusion": true | false,
    "no_unresolved_sadness": true | false,
    "no_animal_harm": true | false,
    "no_scary_nature": true | false,
    "no_deception_rewarded": true | false,
    "villain_consequence": true | false,
    "peaceful_tone": true | false,
    "positive_message": true | false,
    "good_character_modeled": true | false,
    "no_sexual_content": true | false,
    "no_foul_language": true | false
  },
  "violations": ["specific quote or description of what violated the rule"],
  "fix_instructions": ["one specific instruction per violation"]
}

result is FAIL if ANY check is false."""

_CRITIC_PROMPT = """You are a children's literature expert evaluating a bedtime story for ages 5-10.

Score each dimension 1-5:  5=excellent  4=good  3=acceptable  2=needs work  1=poor

DIMENSIONS:

narrative_arc — clear beginning, middle, end? satisfying resolution? logical plot flow?
engagement — would a child stay interested? vivid details? appropriate pacing?
vocabulary — words simple enough for ages 5-10? sentences short and clear?
moral_clarity — is the positive message clear without being preachy?
consistency — do characters, their abilities, and events stay consistent throughout? no contradictions (e.g. a character can't talk and also be treated as an inanimate object in the same story)?

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "scores": {
    "narrative_arc": 1-5,
    "engagement": 1-5,
    "vocabulary": 1-5,
    "moral_clarity": 1-5,
    "consistency": 1-5
  },
  "overall": 1-5,
  "strengths": ["what works well"],
  "feedback": ["specific, actionable improvement needed"],
  "needs_revision": true | false
}

Set needs_revision to true if overall is 3 or below OR if consistency score is 3 or below."""

_PARENT_JUDGE_PROMPT = """You are a cautious, loving parent of 5-10-year-old children sitting at their bedside, about to read them a story.

You have been given the story and the critic's evaluation.

Ask yourself:
- Would anything here give my child bad dreams?
- Would my child understand and enjoy this?
- Does this leave my child feeling safe, happy, and ready for sleep?
- Is the message something I want my child to internalize?

APPROVE if: safe, age-appropriate, engaging, ends peacefully.
DENY if: anything feels even slightly off for a child at bedtime.

Respond with valid JSON only. No text outside the JSON.

Output schema:
{
  "approved": true | false,
  "reasoning": "2-3 sentences explaining your decision as a parent",
  "concerns": ["specific concern — empty list if approving"],
  "suggested_fixes": ["specific fix per concern — empty list if approving"]
}"""

_FORMATTER_PROMPT = """You are a bedtime story presenter. Format an approved story for final display.

RULES:
- Title on the first line, plain text only
- Separate paragraphs with a single blank line
- No markdown, asterisks, bullet points, or formatting symbols
- Do NOT change any words or content — only fix spacing and paragraph breaks
- If the story already ends with a calm, peaceful closing sentence, keep it exactly as written
- Only if there is NO closing sentence, write one that feels natural to the story — it can reference the characters, setting, or mood. Vary the closing each time; do not repeat the same phrase story after story.

Return only the formatted story. Nothing else."""

_EDIT_PROMPT = """You are a story editor for a children's bedtime story platform.

You will receive the original story and the user's change request.
Apply ONLY the requested change. Do not rewrite the whole story.

RULES:
- Preserve original characters, setting, and plot unless the edit specifically changes them
- Keep the same length unless the user asked to change it
- The result must still work as a complete bedtime story

SAFETY RULES — non-negotiable, must be preserved through any edit:
- MUST end happily, peacefully, and with full resolution
- NEVER include death, violence, weapons, blood, or physical harm
- NEVER include scary imagery, haunted places, or threatening situations
- NEVER portray darkness, bedtime, or sleep as scary
- NEVER include abandonment, stranger danger, or family conflict
- NEVER include cruelty, bullying, body shaming, or unresolved exclusion
- NEVER include unresolved sadness or grief
- NEVER include animals being hurt
- NEVER include threatening storms, fires, or natural disasters
- NEVER include deception or lying that goes unpunished
- NEVER include a villain who wins or goes unpunished
- MUST carry a gentle moral: friendship, kindness, bravery, or curiosity
- If the user's requested change would violate any safety rule, apply the spirit of the change without the violation

Return only the edited story in the same format. No explanation."""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    """Extract and parse JSON from a model response."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # model may have wrapped it in markdown code block
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end != 0:
            return json.loads(raw[start:end])
        raise ValueError(f"Could not parse JSON from response:\n{raw}")


# ─────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────

def categorizer(user_request: str) -> dict:
    """Classify the story request into a theme/genre category."""
    prompt = f"{_CATEGORIZER_PROMPT}\n\nUSER REQUEST:\n{user_request}"
    raw = call_model(prompt=prompt, temperature=0.0, max_tokens=80)
    result = _parse_json(raw)

    # validate category — must be a non-empty string of 1-2 words, no digits
    category = result.get("category", "")
    if (
        not isinstance(category, str)
        or not category.strip()
        or any(char.isdigit() for char in category)
        or len(category.strip().split()) > 2
    ):
        result["category"] = "magical"  # safe fallback

    result["category"] = result["category"].strip().lower()
    return result


def intent_router(user_input: str, has_existing_story: bool) -> dict:
    """Classify user input as new_story or edit."""
    context = f"Existing story: {'YES' if has_existing_story else 'NO'}\nUser input: {user_input}"
    raw = call_model(prompt=f"{_INTENT_ROUTER_PROMPT}\n\n{context}", temperature=0.0, max_tokens=150)
    result = _parse_json(raw)
    if result.get("intent") not in ("new_story", "edit"):
        result["intent"] = "new_story"  # safe fallback
    return result


def drafter(user_request: str, category: str = None, feedback: str = None) -> str:
    """Write or revise a bedtime story."""
    category_line = f"Story category: {category}\n" if category else ""
    if feedback:
        prompt = f"{_DRAFTER_PROMPT}\n\n{category_line}Story request: {user_request}\n\nRevision instructions:\n{feedback}\n\nWrite a revised story that addresses all the instructions above."
    else:
        prompt = f"{_DRAFTER_PROMPT}\n\n{category_line}Story request: {user_request}"
    story = call_model(prompt=prompt, temperature=0.85, max_tokens=800)
    if not story or not story.strip():
        story = "The Sleepy Star\n\nOnce upon a time, a little star was tired. She closed her eyes. And they all slept soundly that night."
    return story


def guardrails_checker(story_text: str) -> dict:
    """Check story against safety rules. Returns result dict."""
    prompt = f"{_GUARDRAILS_PROMPT}\n\nSTORY:\n{story_text}"
    raw = call_model(prompt=prompt, temperature=0.0, max_tokens=600)
    result = _parse_json(raw)
    if result.get("result") not in ("PASS", "FAIL"):
        result["result"] = "FAIL"  # fail safe on bad output
    if not isinstance(result.get("violations"), list):
        result["violations"] = []
    if not isinstance(result.get("fix_instructions"), list):
        result["fix_instructions"] = []
    return result


def critic(story_text: str) -> dict:
    """Evaluate story quality. Returns scores and feedback."""
    prompt = f"{_CRITIC_PROMPT}\n\nSTORY:\n{story_text}"
    raw = call_model(prompt=prompt, temperature=0.1, max_tokens=400)
    result = _parse_json(raw)
    scores = result.get("scores", {})
    # clamp all scores to 1-5
    for key in ("narrative_arc", "engagement", "vocabulary", "moral_clarity", "consistency"):
        try:
            scores[key] = max(1, min(5, int(scores.get(key, 3))))
        except (TypeError, ValueError):
            scores[key] = 3
    result["scores"] = scores
    try:
        result["overall"] = max(1, min(5, int(result.get("overall", 3))))
    except (TypeError, ValueError):
        result["overall"] = 3
    if not isinstance(result.get("feedback"), list):
        result["feedback"] = []
    if not isinstance(result.get("strengths"), list):
        result["strengths"] = []
    result["needs_revision"] = result.get("overall", 3) <= 3 or scores.get("consistency", 5) <= 3
    return result


def parent_judge(story_text: str, critic_result: dict) -> dict:
    """Make final approval decision as a parent."""
    critic_summary = (
        f"Critic scores: {critic_result.get('scores', {})}\n"
        f"Critic feedback: {critic_result.get('feedback', [])}"
    )
    prompt = f"{_PARENT_JUDGE_PROMPT}\n\nSTORY:\n{story_text}\n\nCRITIC EVALUATION:\n{critic_summary}"
    raw = call_model(prompt=prompt, temperature=0.1, max_tokens=300)
    result = _parse_json(raw)
    if not isinstance(result.get("approved"), bool):
        result["approved"] = False  # fail safe
    if not isinstance(result.get("concerns"), list):
        result["concerns"] = []
    if not isinstance(result.get("suggested_fixes"), list):
        result["suggested_fixes"] = []
    if not isinstance(result.get("reasoning"), str):
        result["reasoning"] = ""
    return result


def formatter(story_text: str) -> str:
    """Polish and format the final approved story."""
    prompt = f"{_FORMATTER_PROMPT}\n\nSTORY:\n{story_text}"
    result = call_model(prompt=prompt, temperature=0.2, max_tokens=800)
    return result.strip() if result and result.strip() else story_text


def edit_patcher(original_story: str, edit_request: str) -> str:
    """Apply a targeted edit to the existing story."""
    prompt = f"{_EDIT_PROMPT}\n\nORIGINAL STORY:\n{original_story}\n\nUSER'S CHANGE REQUEST:\n{edit_request}"
    result = call_model(prompt=prompt, temperature=0.5, max_tokens=800)
    return result.strip() if result and result.strip() else original_story


def request_safety_check(user_input: str) -> dict:
    """Pre-screen the user's raw request before any LLM pipeline runs."""
    prompt = f"{_REQUEST_SAFETY_PROMPT}\n\nUSER REQUEST:\n{user_input}"
    raw = call_model(prompt=prompt, temperature=0.0, max_tokens=100)
    result = _parse_json(raw)
    if not isinstance(result.get("safe"), bool):
        result["safe"] = False  # fail safe on bad output
    if not isinstance(result.get("reason"), str):
        result["reason"] = "Unable to verify safety."
    return result
