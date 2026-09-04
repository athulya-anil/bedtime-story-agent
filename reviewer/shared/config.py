"""Shared configuration: thresholds, suppression lists, constants."""

import os

BOT_USERNAME = os.environ.get("BOT_USERNAME", "github-actions[bot]")
REVIEWAI_MARKER = "<!-- reviewai:"

# Categories suppressed entirely — never shown to developers
# Based on Uber uReview lesson: readability/style nits kill developer trust
SUPPRESSED_CATEGORIES = frozenset({
    "readability",
    "style",
    "naming",
    "minor_logging",
    "docstring",
    "formatting",
    "whitespace",
    "import_order",
    "type_hint",
})

# Per-assistant, per-category minimum confidence to proceed past classify_and_threshold
# Higher threshold = more aggressive filtering before the expensive verify step
CONFIDENCE_THRESHOLDS: dict[str, dict[str, int]] = {
    "standard": {
        "correctness": 3,
        "logic": 3,
    },
    "best_practices": {
        "patterns": 4,
        "conventions": 3,
    },
    "security": {
        "security": 3,      # low threshold — false negatives are costly
    },
}

# Per-PR file cap: sort by additions desc, take top N
MAX_FILES_PER_PR = 15

# Concurrency caps
REVIEW_SEMAPHORE_SIZE = 8
VERIFY_SEMAPHORE_SIZE = 8

# Tiered context thresholds (chars)
FULL_FILE_THRESHOLD = 8_000
FUNCTION_ONLY_THRESHOLD = 32_000
