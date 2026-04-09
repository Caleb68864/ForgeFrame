---
scenario_id: "PL-03"
title: "Marker Rules"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-03: Marker Rules

## Description
Tests `default_config()` from `marker_rules.py` and the `DEFAULT_RULES` /
`DEFAULT_WEIGHTS` module-level constants. The module declares nine `MarkerRule`
objects and a `MarkerConfig` that bundles them with category weights and
threshold values. Covers: return type, rule count and field values, weight
completeness, threshold defaults, and that the constants are not mutated
between calls.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `MarkerConfig`, `MarkerRule`, `MarkerCategory` imported from
  `workshop_video_brain.core.models`
- No filesystem or network access required

## Test Cases

```
tests/unit/test_marker_rules.py

class TestDefaultConfig:
    def test_returns_marker_config_instance()
        # from workshop_video_brain.edit_mcp.pipelines.marker_rules import default_config
        # isinstance(default_config(), MarkerConfig) is True

    def test_returns_new_instance_each_call()
        # default_config() is not default_config()  →  True (not cached singleton)

    def test_silence_threshold_default()
        # default_config().silence_threshold_seconds == 2.0

    def test_segment_merge_gap_default()
        # default_config().segment_merge_gap_seconds == 3.0

class TestDefaultRules:
    def test_rule_count()
        # len(default_config().rules) == 9

    def test_all_rules_are_marker_rule_instances()
        # all(isinstance(r, MarkerRule) for r in default_config().rules)

    def test_materials_mention_rule_present()
        # One rule has category == MarkerCategory.materials_mention
        # Its base_confidence == 0.75
        # "materials" in rule.keywords

    def test_step_explanation_rule_present()
        # category == MarkerCategory.step_explanation
        # base_confidence == 0.8
        # "first" in rule.keywords

    def test_important_caution_rule_highest_confidence()
        # category == MarkerCategory.important_caution
        # base_confidence == 0.85
        # "careful" in rule.keywords

    def test_mistake_problem_rule_present()
        # category == MarkerCategory.mistake_problem
        # base_confidence == 0.8
        # "mistake" in rule.keywords

    def test_chapter_candidate_rule_present()
        # category == MarkerCategory.chapter_candidate
        # base_confidence == 0.85
        # "section" in rule.keywords

    def test_hook_candidate_rule_present()
        # category == MarkerCategory.hook_candidate
        # base_confidence == 0.75
        # "today" in rule.keywords

    def test_measurement_detail_rule_present()
        # category == MarkerCategory.measurement_detail
        # "measure" in rule.keywords

    def test_closeup_needed_rule_present()
        # category == MarkerCategory.closeup_needed
        # base_confidence == 0.7

    def test_broll_candidate_rule_present()
        # category == MarkerCategory.broll_candidate
        # "finished" in rule.keywords

    def test_each_rule_has_at_least_one_keyword()
        # all(len(r.keywords) >= 1 for r in default_config().rules)

class TestDefaultWeights:
    def test_weight_count()
        # len(default_config().category_weights) == 14

    def test_chapter_candidate_is_highest_weight()
        # weights["chapter_candidate"] == 1.0

    def test_dead_air_is_low_weight()
        # weights["dead_air"] == 0.3

    def test_repetition_is_lowest_weight()
        # weights["repetition"] == 0.25

    def test_all_weights_between_zero_and_one()
        # all(0.0 <= v <= 1.0 for v in weights.values())

    def test_step_explanation_weight()
        # weights["step_explanation"] == 0.9

    def test_fix_recovery_weight()
        # weights["fix_recovery"] == 0.7

class TestConstantsNotMutated:
    def test_rules_list_not_shared_across_calls()
        # c1 = default_config(); c2 = default_config()
        # c1.rules is not c2.rules

    def test_weights_dict_not_shared_across_calls()
        # c1 = default_config(); c2 = default_config()
        # c1.category_weights is not c2.category_weights

    def test_mutating_returned_config_does_not_affect_constants()
        # cfg = default_config()
        # cfg.rules.clear()
        # len(default_config().rules) == 9  (DEFAULT_RULES unchanged)
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_marker_rules.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_marker_rules.py -v`

## Expected Results
- `default_config()` returns a fresh `MarkerConfig` on every call
- All nine expected `MarkerRule` entries are present with correct categories,
  confidences, and at least the documented trigger keywords
- All 14 category weights are in [0.0, 1.0]; `chapter_candidate` is the highest
- Mutating the returned config does not alter the module-level constants

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
