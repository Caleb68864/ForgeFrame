"""Tests for Shot, ShotPlan, ScriptDraft, ReviewNote, MaterialList (MD-09)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.enums import ShotType
from workshop_video_brain.core.models.planning import (
    MaterialList,
    ReviewNote,
    ScriptDraft,
    Shot,
    ShotPlan,
)


# ---------------------------------------------------------------------------
# Shot
# ---------------------------------------------------------------------------

def test_shot_required():
    with pytest.raises(ValidationError):
        Shot()  # type: ignore[call-arg]


def test_shot_enum_stored_as_string():
    s = Shot(type=ShotType.a_roll)
    assert isinstance(s.type, str)
    assert s.type == "a_roll"


def test_shot_defaults():
    s = Shot(type=ShotType.overhead)
    assert s.description == ""
    assert s.beat_ref == ""
    assert s.priority == 0


def test_shot_all_fields():
    s = Shot(type=ShotType.closeup, description="Close on join", beat_ref="b3", priority=2)
    d = s.model_dump()
    assert d["type"] == "closeup"
    assert d["description"] == "Close on join"
    assert d["priority"] == 2
    s2 = Shot.model_validate(d)
    assert s2 == s


def test_shot_invalid_type():
    with pytest.raises(ValidationError):
        Shot(type="not_a_real_shot_type")


# ---------------------------------------------------------------------------
# ShotPlan
# ---------------------------------------------------------------------------

def test_shot_plan_default_construction():
    sp = ShotPlan()
    assert sp.shots == []


def test_shot_plan_with_shots():
    shots = [Shot(type=ShotType.a_roll), Shot(type=ShotType.overhead)]
    sp = ShotPlan(shots=shots)
    sp2 = ShotPlan.from_json(sp.to_json())
    assert len(sp2.shots) == 2
    assert sp2.shots[0].type == "a_roll"


# ---------------------------------------------------------------------------
# ScriptDraft
# ---------------------------------------------------------------------------

def test_script_draft_default_construction():
    sd = ScriptDraft()
    assert sd is not None


def test_script_draft_defaults():
    sd = ScriptDraft()
    assert sd.sections == {}
    assert sd.tone == ""
    assert sd.target_length == 0


def test_script_draft_sections():
    sd = ScriptDraft(sections={"intro": "Welcome to the build!"})
    d = sd.model_dump()
    assert d["sections"]["intro"] == "Welcome to the build!"
    sd2 = ScriptDraft.model_validate(d)
    assert sd2.sections == {"intro": "Welcome to the build!"}


def test_script_draft_target_length():
    sd = ScriptDraft(target_length=300)
    assert sd.target_length == 300


def test_script_draft_json_round_trip():
    sd = ScriptDraft(sections={"hook": "Start with a question"}, tone="casual", target_length=500)
    sd2 = ScriptDraft.from_json(sd.to_json())
    assert sd2 == sd


# ---------------------------------------------------------------------------
# ReviewNote
# ---------------------------------------------------------------------------

def test_review_note_default_construction():
    rn = ReviewNote()
    assert rn is not None


def test_review_note_defaults():
    rn = ReviewNote()
    assert rn.pacing_notes == []
    assert rn.repetition_flags == []
    assert rn.insert_suggestions == []
    assert rn.overlay_ideas == []
    assert rn.chapter_breaks == []


def test_review_note_all_lists():
    rn = ReviewNote(
        pacing_notes=["Too slow at 3:00"],
        repetition_flags=["Repeated intro twice"],
        insert_suggestions=["Add b-roll at 5:00"],
        overlay_ideas=["Add dimensions overlay"],
        chapter_breaks=["1:30 - Materials"],
    )
    d = rn.model_dump()
    assert len(d["pacing_notes"]) == 1
    assert len(d["chapter_breaks"]) == 1


def test_review_note_mutable_default_isolation():
    rn1 = ReviewNote()
    rn2 = ReviewNote()
    rn1.pacing_notes.append("test")
    assert rn2.pacing_notes == []


def test_review_note_yaml_round_trip():
    rn = ReviewNote(pacing_notes=["Speed up", "Slow down"], chapter_breaks=["2:00"])
    rn2 = ReviewNote.from_yaml(rn.to_yaml())
    assert rn2 == rn


# ---------------------------------------------------------------------------
# MaterialList
# ---------------------------------------------------------------------------

def test_material_list_default_construction():
    ml = MaterialList()
    assert ml is not None


def test_material_list_defaults():
    ml = MaterialList()
    assert ml.materials == []
    assert ml.tools == []


def test_material_list_populated():
    ml = MaterialList(materials=["Canvas 10oz", "Webbing 1in"], tools=["Sewing machine", "Scissors"])
    ml2 = MaterialList.from_json(ml.to_json())
    assert ml2.materials == ["Canvas 10oz", "Webbing 1in"]
    assert ml2.tools == ["Sewing machine", "Scissors"]
