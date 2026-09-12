"""One rule, two call sites: the renderer's precondition and the validator.

Background
----------
``adapters/render/media_check.missing_media`` (the pre-render precondition) and
``adapters/kdenlive/validator.validate_project`` both answer the question *which
producers name a file that must be on disk?* -- and until this change they
answered it differently. The validator flagged the ``color``/``black`` producer
every Kdenlive timeline carries as "Media file not found", never stripped a
``timewarp`` speed prefix, treated a remote URL and an image sequence as missing
files, and resolved relative resources against the workspace root instead of the
``<mlt root>`` attribute melt itself uses. So a project the renderer accepted the
validator rejected, and the reverse.

This file is the reconciliation proof. ``CASES`` is the table of projects the two
used to disagree about (plus the two they already agreed on, as controls). Each
case is built **once** and fed through **both** call sites:

* the renderer path -- the case serialized as MLT XML, through ``missing_media``
* the validator path -- the same case as a ``KdenliveProject``, through
  ``validate_project``

and the test asserts the two verdicts are identical *and* equal to the verdict
the case deserves. A one-sided check cannot pass this: the table holds refusals
(``expect_missing`` non-empty) and acceptances in both directions, so an
implementation that refuses everything fails the accept rows and one that
refuses nothing fails the reject rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project
from workshop_video_brain.edit_mcp.adapters.render.media_check import missing_media


# ---------------------------------------------------------------------------
# The case table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    """One project, described once, rendered into both representations.

    ``resource`` may contain the tokens ``{present}`` / ``{gone}`` / ``{root}``,
    substituted per-tmp_path. ``expect_missing`` is the list of resolved paths
    both call sites must name (also token-substituted); empty means "accept".
    """

    id: str
    service: str
    resource: str
    expect_missing: list[str] = field(default_factory=list)
    # Where relative resources resolve. "root" == the <mlt root> attribute /
    # KdenliveProject.root; the workspace root deliberately does NOT contain
    # the media, so a workspace-relative resolver gets this case wrong.
    relative_root: bool = False
    why: str = ""


CASES: list[Case] = [
    # -- the two they already agreed on (controls) --------------------------
    Case(
        id="absent_avformat_is_refused",
        service="avformat",
        resource="{gone}",
        expect_missing=["{gone}"],
        why="both already refused this; it is the defect the precondition exists for",
    ),
    Case(
        id="present_avformat_is_accepted",
        service="avformat",
        resource="{present}",
        why="both already accepted this; the accept control for a normal project",
    ),
    # -- the disagreements --------------------------------------------------
    Case(
        id="color_black_is_accepted",
        service="color",
        resource="black",
        why="every Kdenlive timeline carries producer_black; the validator called "
            "it a missing media file",
    ),
    Case(
        id="color_hex_is_accepted",
        service="color",
        resource="#00000000",
        why="test_alpha_render renders this exact producer; not a file",
    ),
    Case(
        id="title_without_resource_is_accepted",
        service="kdenlivetitle",
        resource="",
        why="a title card has no file on disk at all",
    ),
    Case(
        id="timewarp_over_present_media_is_accepted",
        service="timewarp",
        resource="2.0:{present}",
        why="the validator stat'd the literal '2.0:/path' and always failed",
    ),
    Case(
        id="timewarp_over_absent_media_is_refused_by_inner_path",
        service="timewarp",
        resource="2.0:{gone}",
        expect_missing=["{gone}"],
        why="refused, but naming the media file -- not the speed-prefixed string",
    ),
    Case(
        id="timewarp_windows_drive_letter_survives",
        service="timewarp",
        resource="4.000000:C:/Videos/gone.mp4",
        expect_missing=["{root}/C:/Videos/gone.mp4"],
        why="only the leading speed is stripped; the drive-letter colon stays",
    ),
    Case(
        id="timewarp_over_a_colour_clip_is_accepted",
        service="timewarp",
        resource="2:color:black",
        why="patcher_intents builds this when the retimed clip is synthetic",
    ),
    Case(
        id="remote_url_is_accepted",
        service="avformat",
        resource="https://example.invalid/clip.mp4",
        why="Path.exists() cannot settle a network source; refusing blocks a "
            "legitimate edit",
    ),
    Case(
        id="image_sequence_is_accepted",
        service="qimage",
        resource="/frames/f_%05d.png",
        why="melt expands the pattern itself; the pattern is never a file",
    ),
    Case(
        id="unknown_service_is_accepted",
        service="some.future.service",
        resource="/nope.bin",
        why="the allowlist must never refuse a render it does not understand",
    ),
    Case(
        id="relative_resource_present_under_mlt_root_is_accepted",
        service="avformat",
        resource="media/raw/shot.mp4",
        relative_root=True,
        why="melt resolves relative resources against <mlt root>, not the "
            "workspace root the validator was handed",
    ),
    Case(
        id="relative_resource_absent_under_mlt_root_is_refused_resolved",
        service="avformat",
        resource="media/raw/gone.mp4",
        expect_missing=["{root}/media/raw/gone.mp4"],
        relative_root=True,
        why="refused, naming the path resolved the way melt resolves it",
    ),
]


# ---------------------------------------------------------------------------
# Building one case into both representations
# ---------------------------------------------------------------------------

def _tokens(tmp_path: Path) -> dict[str, str]:
    """The per-test substitutions. ``present`` exists on disk, ``gone`` does not."""
    root = tmp_path / "proj"
    (root / "media" / "raw").mkdir(parents=True, exist_ok=True)
    present = root / "media" / "raw" / "shot.mp4"
    present.write_bytes(b"\x00\x11\x22\x33" * 64)
    return {
        "root": str(root),
        "present": str(present),
        "gone": str(root / "media" / "raw" / "gone.mp4"),
    }


def _fill(text: str, tokens: dict[str, str]) -> str:
    for key, value in tokens.items():
        text = text.replace("{" + key + "}", value)
    return text


def _as_xml(case: Case, tmp_path: Path, tokens: dict[str, str]) -> Path:
    """The case as the MLT XML the renderer is about to hand melt."""
    root = Path(tokens["root"])
    path = root / "p.kdenlive"
    resource = _fill(case.resource, tokens)
    path.write_text(
        '<?xml version="1.0"?>\n'
        f'<mlt version="7" root="{root}">\n'
        '  <producer id="prod0">\n'
        f'    <property name="mlt_service">{case.service}</property>\n'
        f'    <property name="resource">{resource}</property>\n'
        "  </producer>\n"
        "</mlt>\n",
        encoding="utf-8",
    )
    return path


def _as_model(case: Case, tokens: dict[str, str]) -> KdenliveProject:
    """The same case as the in-memory project the validator is handed."""
    resource = _fill(case.resource, tokens)
    return KdenliveProject(
        version="7",
        title="Case",
        root=tokens["root"],
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(
                id="prod0",
                resource=resource,
                properties={"mlt_service": case.service, "resource": resource},
            )
        ],
        playlists=[
            Playlist(
                id="pl0",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ],
        tracks=[Track(id="pl0", track_type="video")],
    )


def _validator_missing(report) -> list[str]:
    """The paths the validator's media check named, in the same shape."""
    return sorted(
        item.path or ""
        for item in report.items
        if item.category == "media"
        and item.severity == ValidationSeverity.error.value
    )


# ---------------------------------------------------------------------------
# The proof
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
class TestBothCallSitesAgree:
    def test_renderer_verdict(self, tmp_path, case):
        tokens = _tokens(tmp_path)
        expected = sorted(_fill(p, tokens) for p in case.expect_missing)
        assert missing_media(_as_xml(case, tmp_path, tokens)) == expected, case.why

    def test_validator_verdict(self, tmp_path, case):
        tokens = _tokens(tmp_path)
        expected = sorted(_fill(p, tokens) for p in case.expect_missing)
        # The workspace root is a directory that contains none of the media:
        # a validator that still resolved relatives against it would get the
        # two relative cases wrong.
        report = validate_project(
            _as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
        )
        assert _validator_missing(report) == expected, case.why

    def test_the_two_agree(self, tmp_path, case):
        tokens = _tokens(tmp_path)
        renderer = missing_media(_as_xml(case, tmp_path, tokens))
        validator = _validator_missing(
            validate_project(
                _as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
            )
        )
        assert renderer == validator, (
            f"{case.id}: renderer says {renderer}, validator says {validator} "
            f"-- {case.why}"
        )


class TestValidatorStillReportsWhatItShould:
    """Accept/reject controls for the validator specifically."""

    def test_a_file_backed_producer_with_no_resource_is_still_flagged(self, tmp_path):
        # An avformat producer with an empty resource is genuinely broken --
        # sharing the classifier must not make the validator silent about it.
        project = _as_model(
            Case(id="x", service="avformat", resource=""), _tokens(tmp_path)
        )
        report = validate_project(project, workspace_root=tmp_path)
        media = [i for i in report.items if i.category == "media"]
        assert media, "an avformat producer with no resource must be reported"

    def test_a_title_with_no_resource_is_not_flagged(self, tmp_path):
        # ... but a title card legitimately has no resource, and the old
        # validator warned about every one of them.
        project = _as_model(
            Case(id="x", service="kdenlivetitle", resource=""), _tokens(tmp_path)
        )
        report = validate_project(project, workspace_root=tmp_path)
        assert [i for i in report.items if i.category == "media"] == []

    def test_no_workspace_root_still_skips_the_media_check(self, tmp_path):
        # Unchanged contract: without a base to resolve against, the media
        # check does not run at all.
        project = _as_model(
            Case(id="x", service="avformat", resource="{gone}"), _tokens(tmp_path)
        )
        project.root = ""
        report = validate_project(project)
        assert [i for i in report.items if i.category == "media"] == []

    def test_missing_media_message_is_still_named_per_producer(self, tmp_path):
        tokens = _tokens(tmp_path)
        project = _as_model(
            Case(id="x", service="avformat", resource="{gone}"), tokens
        )
        report = validate_project(project, workspace_root=tmp_path)
        item = next(i for i in report.items if i.category == "media")
        assert item.location == "producer:prod0"
        assert tokens["gone"] in item.message
