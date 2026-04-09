"""TDD tests for generic effect application pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.timeline import AddEffect


# --- apply_effect -----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_single_effect_add(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    project = MagicMock()
    patched = MagicMock()
    mock_patch.return_value = patched

    result = apply_effect(
        project,
        track_index=0,
        clip_index=2,
        effect_name="avfilter.eq",
        params={"av.brightness": "0.1", "av.contrast": "1.2"},
    )

    assert result is patched
    mock_patch.assert_called_once()
    intents = mock_patch.call_args[0][1]
    assert len(intents) == 1
    assert isinstance(intents[0], AddEffect)
    assert intents[0].effect_name == "avfilter.eq"
    assert intents[0].track_index == 0
    assert intents[0].clip_index == 2
    assert intents[0].params == {"av.brightness": "0.1", "av.contrast": "1.2"}


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_multiple_effects_on_same_clip(mock_patch):
    """Each apply_effect call creates a separate AddEffect intent.

    The patcher appends effects; it does not replace existing ones.
    """
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    project = MagicMock(name="original")
    after_first = MagicMock(name="after_first")
    after_second = MagicMock(name="after_second")
    mock_patch.side_effect = [after_first, after_second]

    # First effect: color correction
    result1 = apply_effect(project, 0, 0, "lift_gamma_gain", {"lift_r": "0.9"})
    assert result1 is after_first

    # Second effect on same clip: blur
    result2 = apply_effect(result1, 0, 0, "frei0r.IIRblur", {"Amount": "0.3"})
    assert result2 is after_second

    # Two separate patch_project calls -- each appends one effect
    assert mock_patch.call_count == 2

    first_intents = mock_patch.call_args_list[0][0][1]
    assert first_intents[0].effect_name == "lift_gamma_gain"

    second_intents = mock_patch.call_args_list[1][0][1]
    assert second_intents[0].effect_name == "frei0r.IIRblur"


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_invalid_track_index_raises(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.side_effect = IndexError("Track index 99 out of range")

    with pytest.raises(IndexError, match="Track index 99"):
        apply_effect(MagicMock(), 99, 0, "avfilter.eq")


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_invalid_clip_index_raises(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.side_effect = IndexError("Clip index 50 out of range")

    with pytest.raises(IndexError, match="Clip index 50"):
        apply_effect(MagicMock(), 0, 50, "avfilter.eq")


def test_empty_effect_name_raises():
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    with pytest.raises(ValueError, match="effect_name must be a non-empty string"):
        apply_effect(MagicMock(), 0, 0, "", {})

    with pytest.raises(ValueError, match="effect_name must be a non-empty string"):
        apply_effect(MagicMock(), 0, 0, "   ", {})


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_empty_params(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.return_value = MagicMock()

    # None params
    apply_effect(MagicMock(), 0, 0, "affine", None)
    intents = mock_patch.call_args[0][1]
    assert intents[0].params == {}

    # Empty dict params
    apply_effect(MagicMock(), 0, 0, "affine", {})
    intents = mock_patch.call_args[0][1]
    assert intents[0].params == {}


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_effect_name_not_validated(mock_patch):
    """Any effect name is accepted -- no hardcoded validation list."""
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.return_value = MagicMock()

    # Completely custom/unknown effect name should not raise
    apply_effect(MagicMock(), 0, 0, "my_custom_plugin.effect_v2", {"key": "val"})
    intents = mock_patch.call_args[0][1]
    assert intents[0].effect_name == "my_custom_plugin.effect_v2"


# --- list_common_effects ----------------------------------------------------

def test_list_common_effects_returns_expected_items():
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects

    effects = list_common_effects()

    assert isinstance(effects, list)
    assert len(effects) >= 8  # at least the 8 curated effects

    names = [e["name"] for e in effects]
    assert "lift_gamma_gain" in names
    assert "avfilter.lut3d" in names
    assert "avfilter.eq" in names
    assert "avfilter.chromakey" in names
    assert "affine" in names
    assert "frei0r.IIRblur" in names

    # Each entry has name and description
    for effect in effects:
        assert "name" in effect
        assert "description" in effect
        assert isinstance(effect["name"], str)
        assert isinstance(effect["description"], str)
        assert len(effect["name"]) > 0
        assert len(effect["description"]) > 0


def test_list_common_effects_returns_copy():
    """Mutating the returned list should not affect the module-level list."""
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects

    effects1 = list_common_effects()
    effects1.clear()

    effects2 = list_common_effects()
    assert len(effects2) >= 8  # unaffected
