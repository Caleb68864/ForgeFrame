"""Tests for marker rules module (PL-03)."""
from __future__ import annotations

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import MarkerConfig, MarkerRule
from workshop_video_brain.edit_mcp.pipelines.marker_rules import (
    DEFAULT_RULES,
    DEFAULT_WEIGHTS,
    default_config,
)


class TestDefaultConfig:
    def test_returns_marker_config_instance(self):
        assert isinstance(default_config(), MarkerConfig)

    def test_returns_new_instance_each_call(self):
        assert default_config() is not default_config()

    def test_silence_threshold_default(self):
        assert default_config().silence_threshold_seconds == 2.0

    def test_segment_merge_gap_default(self):
        assert default_config().segment_merge_gap_seconds == 3.0


class TestDefaultRules:
    def test_rule_count(self):
        assert len(default_config().rules) == 9

    def test_all_rules_are_marker_rule_instances(self):
        assert all(isinstance(r, MarkerRule) for r in default_config().rules)

    def test_materials_mention_rule_present(self):
        rules = default_config().rules
        cats = [str(r.category) for r in rules]
        assert MarkerCategory.materials_mention.value in cats
        rule = next(r for r in rules if str(r.category) == MarkerCategory.materials_mention.value)
        assert rule.base_confidence == 0.75
        assert "materials" in rule.keywords

    def test_step_explanation_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.step_explanation.value
        )
        assert rule.base_confidence == 0.8
        assert "first" in rule.keywords

    def test_important_caution_rule_highest_confidence(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.important_caution.value
        )
        assert rule.base_confidence == 0.85
        assert "careful" in rule.keywords

    def test_mistake_problem_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.mistake_problem.value
        )
        assert rule.base_confidence == 0.8
        assert "mistake" in rule.keywords

    def test_chapter_candidate_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.chapter_candidate.value
        )
        assert rule.base_confidence == 0.85
        assert "section" in rule.keywords

    def test_hook_candidate_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.hook_candidate.value
        )
        assert rule.base_confidence == 0.75
        assert "today" in rule.keywords

    def test_measurement_detail_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.measurement_detail.value
        )
        assert "measure" in rule.keywords

    def test_closeup_needed_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.closeup_needed.value
        )
        assert rule.base_confidence == 0.7

    def test_broll_candidate_rule_present(self):
        rules = default_config().rules
        rule = next(
            r for r in rules if str(r.category) == MarkerCategory.broll_candidate.value
        )
        assert "finished" in rule.keywords

    def test_each_rule_has_at_least_one_keyword(self):
        assert all(len(r.keywords) >= 1 for r in default_config().rules)


class TestDefaultWeights:
    def test_weight_count(self):
        assert len(default_config().category_weights) == 14

    def test_chapter_candidate_is_highest_weight(self):
        assert default_config().category_weights["chapter_candidate"] == 1.0

    def test_dead_air_is_low_weight(self):
        assert default_config().category_weights["dead_air"] == 0.3

    def test_repetition_is_lowest_weight(self):
        assert default_config().category_weights["repetition"] == 0.25

    def test_all_weights_between_zero_and_one(self):
        weights = default_config().category_weights
        assert all(0.0 <= v <= 1.0 for v in weights.values())

    def test_step_explanation_weight(self):
        assert default_config().category_weights["step_explanation"] == 0.9

    def test_fix_recovery_weight(self):
        assert default_config().category_weights["fix_recovery"] == 0.7


class TestConstantsNotMutated:
    def test_rules_list_not_shared_across_calls(self):
        c1 = default_config()
        c2 = default_config()
        assert c1.rules is not c2.rules

    def test_weights_dict_not_shared_across_calls(self):
        c1 = default_config()
        c2 = default_config()
        assert c1.category_weights is not c2.category_weights

    def test_mutating_returned_config_does_not_affect_constants(self):
        cfg = default_config()
        cfg.rules.clear()
        assert len(default_config().rules) == 9
