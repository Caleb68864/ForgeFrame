"""Nothing may be declared on the Kdenlive model that no code reads or writes.

"Declared and unwired" is the shape this repo keeps producing, and it is worse
than absent: a model field that looks like the way to express something, and
silently expresses nothing, is a trap for the next reader -- and for the vault
handbook, which had a copy-pasteable example built on one.

The rule these tests enforce is deliberately **lenient**, so that it fails only
on genuinely dead declarations and never on a field whose use is indirect:

* A model class must be *named* somewhere in the package outside the model
  module -- imported, constructed, annotated, anything.
* A field of the two Kdenlive documents' top-level models must be *mentioned*
  (attribute access or keyword argument, by bare name) somewhere in
  ``edit_mcp/adapters/kdenlive/`` -- the package that turns the model into XML
  and back. A name shared with an unrelated attribute counts, which is exactly
  the leniency intended: a field that survives this check may still be poorly
  wired, but a field that fails it is wired to nothing at all.

Both checks carry a control proving the detector can tell the two apart, so a
detector that silently sees everything (or nothing) cannot pass.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    PlaylistEntry,
    Producer,
    Track,
)

_SRC = (
    Path(__file__).resolve().parents[2]
    / "workshop-video-brain"
    / "src"
    / "workshop_video_brain"
)
_MODEL_MODULE = _SRC / "core" / "models" / "kdenlive.py"
_KDENLIVE_ADAPTER = _SRC / "edit_mcp" / "adapters" / "kdenlive"


def _declared_classes() -> list[str]:
    tree = ast.parse(_MODEL_MODULE.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]


def _names_mentioned_outside_the_model() -> set[str]:
    """Every bare identifier used anywhere in the package but the model module."""
    found: set[str] = set()
    for py in _SRC.rglob("*.py"):
        if py == _MODEL_MODULE:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - the package parses
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.alias):
                found.add(node.name.rpartition(".")[2])
    return found


def _names_mentioned_in_the_kdenlive_adapter() -> set[str]:
    """Attribute reads/writes and keyword arguments in the adapter package."""
    found: set[str] = set()
    for py in _KDENLIVE_ADAPTER.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                found.add(node.attr)
            elif isinstance(node, ast.keyword) and node.arg:
                found.add(node.arg)
    return found


# ---------------------------------------------------------------------------
# Controls -- the detectors must actually discriminate
# ---------------------------------------------------------------------------


def test_the_class_detector_sees_a_class_that_is_really_used() -> None:
    assert "Producer" in _names_mentioned_outside_the_model()
    assert Producer.__name__ == "Producer"


def test_the_class_detector_does_not_see_a_name_nobody_wrote() -> None:
    assert "ThisModelDoesNotExistAnywhere" not in _names_mentioned_outside_the_model()


def test_the_field_detector_sees_a_field_that_is_really_used() -> None:
    assert "opaque_elements" in _names_mentioned_in_the_kdenlive_adapter()


def test_the_field_detector_does_not_see_a_field_nobody_wrote() -> None:
    assert "this_field_does_not_exist" not in _names_mentioned_in_the_kdenlive_adapter()


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_every_declared_model_class_is_used_somewhere() -> None:
    mentioned = _names_mentioned_outside_the_model()
    dead = sorted(c for c in _declared_classes() if c not in mentioned)
    assert not dead, (
        "declared on core/models/kdenlive.py and named nowhere else in the "
        f"package: {dead}. Wire it or delete it -- a model class nothing "
        "constructs is a promise the serializer does not keep."
    )


@pytest.mark.parametrize("model", [KdenliveProject, PlaylistEntry, Track])
def test_every_field_is_mentioned_by_the_kdenlive_adapter(model: type) -> None:
    mentioned = _names_mentioned_in_the_kdenlive_adapter()
    dead = sorted(f for f in model.model_fields if f not in mentioned)
    assert not dead, (
        f"{model.__name__} declares fields the kdenlive adapter never mentions: "
        f"{dead}. Nothing populates them and nothing serializes them, so setting "
        "one has no effect on the document written to disk."
    )


# ---------------------------------------------------------------------------
# The specific declarations that were removed, and the mechanism that replaced
# each of them.  The lenient rule above catches most of these on its own;
# ``Track.muted`` it does NOT -- ``intent.muted`` on the unrelated
# ``SetTrackMute`` intent is enough to satisfy a bare-name check -- so mute is
# pinned by name here.
# ---------------------------------------------------------------------------


def test_clip_effects_are_not_a_playlist_entry_field() -> None:
    """A clip effect is an ``OpaqueElement`` keyed by ``(track, clip_index)``,
    nested into its ``<entry>`` by ``serializer._extract_clip_filters``."""
    assert "filters" not in PlaylistEntry.model_fields


def test_clip_speed_is_not_a_playlist_entry_field() -> None:
    """``SetClipSpeed`` builds the ``timewarp`` producer itself and repoints the
    entry's ``producer_id`` at it, so the speed lives in the producer the entry
    names.  ``PlaylistEntry.speed`` said the serializer emitted that producer;
    this serializer has no timewarp code at all."""
    assert "speed" not in PlaylistEntry.model_fields


def test_transitions_are_not_project_fields() -> None:
    """User transitions and compositions are ``<transition>`` OpaqueElements;
    the per-track compositors are regenerated from the track list."""
    assert "sequence_transitions" not in KdenliveProject.model_fields
    assert "track_mix_transitions" not in KdenliveProject.model_fields


def test_track_mute_and_visibility_are_not_track_fields() -> None:
    """Mute/hide is a ``kdenlive:hide`` OpaqueElement directive, written by
    ``patcher_intents`` and applied by ``serializer._hide_directives`` -- see
    ``tests/unit/test_nle_operations.py::TestSetTrackMute`` for the live
    mechanism.  ``Track.muted``/``Track.hidden`` described that behaviour and
    the serializer read neither."""
    assert "muted" not in Track.model_fields
    assert "hidden" not in Track.model_fields


def test_the_hide_directive_still_reaches_the_written_document(
    tmp_path: Path,
) -> None:
    """Accept control for the three tests above: removing the fields must not
    remove the behaviour. Mute travels, end to end, into the XML on disk."""
    import xml.etree.ElementTree as ET

    from workshop_video_brain.core.models.kdenlive import Playlist, Producer
    from workshop_video_brain.core.models.timeline import SetTrackMute
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )

    project = KdenliveProject(
        version="7",
        title="Mute control",
        producers=[
            Producer(
                id="prod0",
                resource="/abs/clip.mp4",
                properties={"mlt_service": "avformat", "length": "100"},
            )
        ],
        tracks=[Track(id="pl_video", track_type="video")],
        playlists=[
            Playlist(
                id="pl_video",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ],
    )

    patched = patch_project(project, [SetTrackMute(track_ref="pl_video", muted=True)])
    out = tmp_path / "muted.kdenlive"
    serialize_project(patched, out)

    hides = [
        t.get("hide")
        for t in ET.parse(out).getroot().iter("track")
        if t.get("producer") == "tractor_pl_video"
    ]
    assert hides == ["audio"], hides
