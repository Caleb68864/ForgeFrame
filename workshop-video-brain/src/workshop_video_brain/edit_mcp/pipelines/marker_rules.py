"""Default marker rules and category weights for the auto-mark pipeline."""
from __future__ import annotations

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import MarkerConfig, MarkerRule

DEFAULT_RULES: list[MarkerRule] = [
    MarkerRule(
        keywords=["you'll need", "materials", "supplies", "tools", "equipment", "grab", "pick up"],
        category=MarkerCategory.materials_mention,
        base_confidence=0.75,
    ),
    MarkerRule(
        keywords=["first", "next", "then", "step", "now we", "go ahead and", "what we do"],
        category=MarkerCategory.step_explanation,
        base_confidence=0.8,
    ),
    MarkerRule(
        keywords=["careful", "watch out", "don't", "avoid", "safety", "make sure", "be careful"],
        category=MarkerCategory.important_caution,
        base_confidence=0.85,
    ),
    MarkerRule(
        keywords=["mistake", "wrong", "oops", "fix", "redo", "messed up", "went wrong"],
        category=MarkerCategory.mistake_problem,
        base_confidence=0.8,
    ),
    MarkerRule(
        keywords=["let's move on", "next up", "moving to", "section", "part", "now for"],
        category=MarkerCategory.chapter_candidate,
        base_confidence=0.85,
    ),
    MarkerRule(
        keywords=["today", "in this video", "we're going to", "i'll show you"],
        category=MarkerCategory.hook_candidate,
        base_confidence=0.75,
    ),
    MarkerRule(
        keywords=["measure", "inches", "centimeters", "millimeters", "cut to", "mark"],
        category=MarkerCategory.measurement_detail,
        base_confidence=0.8,
    ),
    MarkerRule(
        keywords=["look closely", "you can see", "detail", "fine", "tiny", "small"],
        category=MarkerCategory.closeup_needed,
        base_confidence=0.7,
    ),
    MarkerRule(
        keywords=["here's what it looks like", "final result", "finished"],
        category=MarkerCategory.broll_candidate,
        base_confidence=0.7,
    ),
]

DEFAULT_WEIGHTS: dict[str, float] = {
    "chapter_candidate": 1.0,
    "step_explanation": 0.9,
    "mistake_problem": 0.85,
    "important_caution": 0.8,
    "materials_mention": 0.75,
    "hook_candidate": 0.7,
    "measurement_detail": 0.65,
    "closeup_needed": 0.6,
    "broll_candidate": 0.55,
    "ending_reveal": 0.5,
    "intro_candidate": 0.45,
    "dead_air": 0.3,
    "repetition": 0.25,
    "fix_recovery": 0.7,
}


def default_config() -> MarkerConfig:
    """Return the default MarkerConfig with standard rules and weights."""
    return MarkerConfig(
        rules=DEFAULT_RULES,
        category_weights=DEFAULT_WEIGHTS,
        silence_threshold_seconds=2.0,
        segment_merge_gap_seconds=3.0,
    )
