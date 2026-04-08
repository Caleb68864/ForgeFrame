"""Unit tests for transition models and crossfade helper."""
from __future__ import annotations

import pytest


class TestTransitionPresetValues:
    def test_short_is_12_frames(self):
        from workshop_video_brain.core.models.transitions import TransitionPreset
        assert TransitionPreset.short.frames == 12

    def test_medium_is_24_frames(self):
        from workshop_video_brain.core.models.transitions import TransitionPreset
        assert TransitionPreset.medium.frames == 24

    def test_long_is_48_frames(self):
        from workshop_video_brain.core.models.transitions import TransitionPreset
        assert TransitionPreset.long.frames == 48

    def test_preset_string_values(self):
        from workshop_video_brain.core.models.transitions import TransitionPreset
        assert TransitionPreset.short.value == "short"
        assert TransitionPreset.medium.value == "medium"
        assert TransitionPreset.long.value == "long"


class TestTransitionType:
    def test_all_types_exist(self):
        from workshop_video_brain.core.models.transitions import TransitionType
        assert TransitionType.crossfade
        assert TransitionType.dissolve
        assert TransitionType.fade_in
        assert TransitionType.fade_out
        assert TransitionType.audio_crossfade

    def test_type_values_are_strings(self):
        from workshop_video_brain.core.models.transitions import TransitionType
        assert TransitionType.crossfade.value == "crossfade"
        assert TransitionType.dissolve.value == "dissolve"
        assert TransitionType.fade_in.value == "fade_in"
        assert TransitionType.fade_out.value == "fade_out"
        assert TransitionType.audio_crossfade.value == "audio_crossfade"


class TestTransitionInstruction:
    def test_creates_with_defaults(self):
        from workshop_video_brain.core.models.transitions import TransitionInstruction
        t = TransitionInstruction()
        assert t.duration_frames == 0
        assert t.audio_link_behavior == "linked"
        assert t.reason == ""

    def test_serializable(self):
        from workshop_video_brain.core.models.transitions import (
            TransitionInstruction,
            TransitionType,
        )
        t = TransitionInstruction(
            type=TransitionType.crossfade,
            track_ref="V1",
            left_clip_ref="clip_001",
            right_clip_ref="clip_002",
            duration_frames=24,
            audio_link_behavior="linked",
            reason="Standard medium crossfade.",
        )
        d = t.model_dump()
        assert d["duration_frames"] == 24
        assert d["track_ref"] == "V1"


class TestCalculateCrossfade:
    def test_sufficient_overlap_uses_preset(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        # left_out=100, right_in=76 → overlap=24 (exactly medium preset)
        result = calculate_crossfade(left_out=100, right_in=76, preset=TransitionPreset.medium)
        assert result.duration_frames == 24
        assert "Falling back" not in result.reason

    def test_more_than_enough_overlap_uses_preset(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        # left_out=100, right_in=40 → overlap=60, long preset=48
        result = calculate_crossfade(left_out=100, right_in=40, preset=TransitionPreset.long)
        assert result.duration_frames == 48

    def test_insufficient_overlap_falls_back(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        # left_out=100, right_in=90 → overlap=10, medium preset=24 → fallback to 10
        result = calculate_crossfade(left_out=100, right_in=90, preset=TransitionPreset.medium)
        assert result.duration_frames == 10
        assert "Falling back" in result.reason

    def test_adjacent_clips_no_overlap_fallback_to_1(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        # left_out=100, right_in=100 → overlap=0 → fallback to 1 frame minimum
        result = calculate_crossfade(left_out=100, right_in=100, preset=TransitionPreset.medium)
        assert result.duration_frames == 1

    def test_gapped_clips_fallback_to_1(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        # left_out=100, right_in=110 → overlap=-10 (gap) → fallback to 1 frame
        result = calculate_crossfade(left_out=100, right_in=110, preset=TransitionPreset.medium)
        assert result.duration_frames == 1
        assert "gap" in result.reason.lower()

    def test_default_preset_is_medium(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        # Large overlap — should use default medium (24 frames)
        result = calculate_crossfade(left_out=200, right_in=100)
        assert result.duration_frames == 24

    def test_returns_transition_instruction(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionInstruction
        result = calculate_crossfade(left_out=200, right_in=100)
        assert isinstance(result, TransitionInstruction)

    def test_result_type_is_crossfade(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionType
        result = calculate_crossfade(left_out=200, right_in=100)
        # type may be enum or string depending on use_enum_values
        assert result.type in (TransitionType.crossfade, TransitionType.crossfade.value)

    def test_short_preset(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        from workshop_video_brain.core.models.transitions import TransitionPreset
        result = calculate_crossfade(left_out=200, right_in=150, preset=TransitionPreset.short)
        assert result.duration_frames == 12

    def test_reason_is_non_empty_string(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import calculate_crossfade
        result = calculate_crossfade(left_out=200, right_in=100)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0


class TestPatchProjectTransition:
    def test_patch_project_handles_add_transition(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        from workshop_video_brain.core.models.timeline import AddTransition

        project = KdenliveProject(title="Test")
        intent = AddTransition(
            type="crossfade",
            track_ref="V1",
            left_clip_ref="clip_001",
            right_clip_ref="clip_002",
            duration_frames=24,
        )
        new_project = patch_project(project, [intent])
        # Should have added an opaque element for the transition
        assert len(new_project.opaque_elements) == 1
        assert "transition" in new_project.opaque_elements[0].xml_string.lower()

    def test_patch_project_does_not_mutate_input(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        from workshop_video_brain.core.models.timeline import AddTransition

        project = KdenliveProject(title="Immutable")
        intent = AddTransition(type="dissolve", track_ref="V1",
                               duration_frames=12)
        _ = patch_project(project, [intent])
        assert len(project.opaque_elements) == 0
