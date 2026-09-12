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

Two tables, same proof
----------------------
``CASES`` covers producer ``resource`` values. ``REFERENCE_CASES`` covers the
files a render opens that are **not** producer resources -- the luma matte of a
wipe, the ``shape`` alpha mask (plain and ``mask_start`` sandwich forms), the
``avfilter.subtitles`` sidecar, the ``avfilter.lut3d`` LUT. melt treats a
missing one exactly as it treats missing footage: it logs, renders something
wrong, and exits 0, so each is a route to the same silent success. They run
through the same three assertions, and they carry the same accept controls --
a plain dissolve with no matte, one of MLT's built-in luma names, a
``dynamictext`` filter whose ``resource`` is text rather than a file, an
``affine`` filter whose ``producer.resource`` is a colour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from workshop_video_brain.core.models.enums import ValidationSeverity
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SubtitleTrack,
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
    # -- a producer carrying NO mlt_service at all -------------------------
    # The in-memory path applied the serializer's ``avformat`` default before
    # classifying; the XML front door did not, so a hand-written or
    # third-party document walked a media reference straight past the guard by
    # leaving one property out. Both now classify it through
    # ``media_check.effective_service``.
    Case(
        id="absent_file_with_no_mlt_service_is_refused",
        service="",
        resource="{gone}",
        expect_missing=["{gone}"],
        why="melt opens it anyway -- this repo's serializer writes the service "
            "in, and MLT's loader picks a demuxer from the resource",
    ),
    Case(
        id="present_file_with_no_mlt_service_is_accepted",
        service="",
        resource="{present}",
        why="the accept control for the same case: a service-less producer "
            "whose file is there must still render",
    ),
    Case(
        id="colour_literal_with_no_mlt_service_is_accepted",
        service="",
        resource="black",
        why="defaulting a service-less producer must not turn the black "
            "background into a missing file",
    ),
    Case(
        id="colour_hex_with_no_mlt_service_is_accepted",
        service="",
        resource="0xff0000ff",
        why="same, for the hex colour form the color producer needs",
    ),
    Case(
        id="bare_id_with_no_mlt_service_is_accepted",
        service="",
        resource="345d126aae3e4f918d4a69e64705e053",
        why="tests/fixtures/projects/legacy/selects-timeline_v3.kdenlive and "
            "review-timeline_v3.kdenlive carry exactly these: the "
            "`resource = asset.path if asset else clip_ref` fallback in "
            "selects_timeline / review_timeline / replay_generator / assembly "
            "leaves a bare clip id. Defaulting a service-less producer must "
            "not turn those existing generated timelines into refusals -- a "
            "bare token with no separator and no extension is not a path",
    ),
    Case(
        id="blipflash_literal_producer_resource_is_accepted",
        service="blipflash",
        resource="<producer>",
        why="tests/fixtures/projects/real/corpus_av_legacy_2604.kdenlive "
            "carries six of these, whose resource is the literal string "
            "'<producer>'. blipflash is a *producer* service outside the "
            "allowlist; anything that classified by 'is it a known non-AV "
            "service?' instead would try to stat a file called <producer>",
    ),
    Case(
        id="mlt_data_relative_resource_is_accepted",
        service="avformat",
        resource="%lumas/HD/luma01.pgm",
        why="a leading % is resolved by MLT against its own data directory, "
            "which varies by build -- Path.exists() on the literal is "
            "meaningless, same as a remote URL",
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
    """The case as the MLT XML the renderer is about to hand melt.

    A case with an empty ``service`` omits the ``mlt_service`` property
    altogether rather than writing an empty one -- "carries no mlt_service" is
    the thing under test, and an empty property is a different document.
    """
    root = Path(tokens["root"])
    path = root / "p.kdenlive"
    resource = _fill(case.resource, tokens)
    service_prop = (
        f'    <property name="mlt_service">{case.service}</property>\n'
        if case.service
        else ""
    )
    path.write_text(
        '<?xml version="1.0"?>\n'
        f'<mlt version="7" root="{root}">\n'
        '  <producer id="prod0">\n'
        f"{service_prop}"
        f'    <property name="resource">{escape(resource)}</property>\n'
        "  </producer>\n"
        "</mlt>\n",
        encoding="utf-8",
    )
    return path


def _as_model(case: Case, tokens: dict[str, str]) -> KdenliveProject:
    """The same case as the in-memory project the validator is handed."""
    resource = _fill(case.resource, tokens)
    properties = {"resource": resource}
    if case.service:
        properties["mlt_service"] = case.service
    return KdenliveProject(
        version="7",
        title="Case",
        root=tokens["root"],
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(id="prod0", resource=resource, properties=properties)
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
# Table 2: files a render opens that are NOT producer resources
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RefCase:
    """One ``<filter>``/``<transition>`` that names a file, in both forms.

    ``tag``/``props`` describe the element exactly as it reaches melt. The
    project around it is always the same: one producer whose media is present,
    so the *only* thing the verdict can be about is the reference.

    ``carrier`` says how the in-memory project holds it -- ``"opaque"`` for the
    ``OpaqueElement`` every clip effect, track filter and composition is stored
    as, ``"subtitle"`` for the ``SubtitleTrack`` the serializer turns into the
    ``avfilter.subtitles`` filter. Both are real; a case that used only one
    would leave the other carrier unproven.
    """

    id: str
    tag: str
    props: dict[str, str]
    expect_missing: list[str] = field(default_factory=list)
    carrier: str = "opaque"
    why: str = ""


REFERENCE_CASES: list[RefCase] = [
    # -- luma matte (wipe / masked wipe) ------------------------------------
    RefCase(
        id="luma_matte_absent_is_refused",
        tag="transition",
        props={"mlt_service": "luma", "resource": "{gone_pgm}"},
        expect_missing=["{gone_pgm}"],
        why="MLT cannot read the matte, so the wipe silently degrades to a "
            "plain dissolve and melt still exits 0",
    ),
    RefCase(
        id="luma_matte_present_is_accepted",
        tag="transition",
        props={"mlt_service": "luma", "resource": "{present_pgm}"},
        why="the accept control: a wipe whose matte is there must still render",
    ),
    RefCase(
        id="luma_with_no_resource_is_accepted",
        tag="transition",
        props={"mlt_service": "luma", "resource": ""},
        why="an empty resource is a plain dissolve -- compositing.apply_wipe "
            "writes exactly this, and every AddTransition crossfade omits it",
    ),
    RefCase(
        id="luma_builtin_name_is_accepted",
        tag="transition",
        props={"mlt_service": "luma", "resource": "luma03"},
        why="a bare name with no separator is one of MLT's own lumas, not a "
            "file this check can stat",
    ),
    RefCase(
        id="luma_mlt_data_relative_is_accepted",
        tag="transition",
        props={"mlt_service": "luma", "resource": "%lumas/HD/luma01.pgm"},
        why="a leading % resolves against MLT's data directory, wherever the "
            "build put it",
    ),
    RefCase(
        id="luma_relative_matte_absent_is_refused_resolved",
        tag="transition",
        props={"mlt_service": "luma", "resource": "mattes/gone.pgm"},
        expect_missing=["{root}/mattes/gone.pgm"],
        why="MLT qualifies a transition's paths against <mlt root> exactly as "
            "it does a producer's, so this check must too",
    ),
    RefCase(
        id="luma_relative_matte_present_is_accepted",
        tag="transition",
        props={"mlt_service": "luma", "resource": "mattes/wipe.pgm"},
        why="the accept control for the same resolution",
    ),
    RefCase(
        id="composite_luma_absent_is_refused",
        tag="transition",
        props={"mlt_service": "composite", "luma": "{gone_pgm}"},
        expect_missing=["{gone_pgm}"],
        why="the older composite-with-luma wipe form keeps its matte in a "
            "property named 'luma'",
    ),
    RefCase(
        id="composite_without_luma_is_accepted",
        tag="transition",
        props={"mlt_service": "composite", "geometry": "0/0:100%x100%"},
        why="a composite with no matte is the ordinary overlay every stacked "
            "track uses",
    ),
    # -- shape alpha mask ---------------------------------------------------
    RefCase(
        id="shape_mask_absent_is_refused",
        tag="filter",
        props={"mlt_service": "shape", "resource": "{gone_png}"},
        expect_missing=["{gone_png}"],
        why="Shape Alpha reads the matte as the clip's alpha; without it melt "
            "renders the clip unmasked and exits 0",
    ),
    RefCase(
        id="shape_mask_present_is_accepted",
        tag="filter",
        props={"mlt_service": "shape", "resource": "{present_png}"},
        why="the accept control -- this is the shape filter the KDE reference "
            "fixture carries, pointing at footage/luma.png",
    ),
    RefCase(
        id="mask_start_shape_inner_absent_is_refused",
        tag="filter",
        props={
            "mlt_service": "mask_start",
            "filter": "shape",
            "filter.resource": "{gone_png}",
        },
        expect_missing=["{gone_png}"],
        why="the masked-effect sandwich form prefixes the inner properties; "
            "the file is the same file",
    ),
    RefCase(
        id="mask_start_rotoscoping_is_accepted",
        tag="filter",
        props={
            "mlt_service": "mask_start",
            "filter": "rotoscoping",
            "filter.spline": "[[0.1,0.1],[0.9,0.9]]",
        },
        why="the other inner filters carry splines and numbers, never a file; "
            "keying on filter.resource must not fire on them",
    ),
    # -- subtitle sidecar ---------------------------------------------------
    RefCase(
        id="subtitle_sidecar_absent_is_refused",
        tag="filter",
        props={"mlt_service": "avfilter.subtitles", "av.filename": "{gone_ass}"},
        expect_missing=["{gone_ass}"],
        carrier="subtitle",
        why="libass renders nothing when the sidecar is gone and melt exits 0, "
            "so the video comes back subtitle-free and 'successful'",
    ),
    RefCase(
        id="subtitle_sidecar_present_is_accepted",
        tag="filter",
        props={"mlt_service": "avfilter.subtitles", "av.filename": "{present_ass}"},
        carrier="subtitle",
        why="the accept control for the subtitle path",
    ),
    # -- creative LUT -------------------------------------------------------
    RefCase(
        id="lut3d_cube_absent_is_refused",
        tag="filter",
        props={"mlt_service": "avfilter.lut3d", "av.file": "{gone_cube}"},
        expect_missing=["{gone_cube}"],
        why="a grade whose .cube is gone renders ungraded, not failed",
    ),
    RefCase(
        id="lut3d_cube_present_is_accepted",
        tag="filter",
        props={"mlt_service": "avfilter.lut3d", "av.file": "{present_cube}"},
        why="the accept control for the LUT path",
    ),
    # -- properties that hold a path-shaped value and must NOT be checked ---
    RefCase(
        id="dynamictext_resource_is_accepted",
        tag="filter",
        props={"mlt_service": "dynamictext", "resource": "#timecode#"},
        why="a dynamictext filter's 'resource' is the text it draws. A "
            "deny-list, or 'any property called resource', refuses this",
    ),
    RefCase(
        id="affine_producer_resource_colour_is_accepted",
        tag="filter",
        props={"mlt_service": "affine", "producer.resource": "0x00aaff96"},
        why="every affine filter in this repo's documents holds a colour here, "
            "not a file",
    ),
    RefCase(
        id="qtblend_transition_is_accepted",
        tag="transition",
        props={"mlt_service": "qtblend", "rect": "0 0 1920 1080 1"},
        why="the per-track compositor the serializer writes on every project",
    ),
    RefCase(
        id="unknown_filter_with_a_path_is_accepted",
        tag="filter",
        props={"mlt_service": "some.future.filter", "resource": "/nope.bin"},
        why="the allowlist must never refuse a render it does not understand -- "
            "the same rule the producer table pins for services",
    ),
]


def _ref_tokens(tmp_path: Path) -> dict[str, str]:
    """Tokens for the reference table: a present matte/sidecar/LUT and an absent one."""
    tokens = _tokens(tmp_path)
    root = Path(tokens["root"])
    (root / "mattes").mkdir(parents=True, exist_ok=True)
    (root / "mattes" / "wipe.pgm").write_bytes(b"P5\n1 1\n255\n\x00")
    for name, body in (
        ("wipe_present.pgm", b"P5\n1 1\n255\n\x00"),
        ("mask_present.png", b"\x89PNG\r\n\x1a\n"),
        ("subs_present.ass", b"[Script Info]\n"),
        ("grade_present.cube", b"LUT_3D_SIZE 2\n"),
    ):
        (root / name).write_bytes(body)
    tokens.update(
        {
            "present_pgm": str(root / "wipe_present.pgm"),
            "gone_pgm": str(root / "wipe_gone.pgm"),
            "present_png": str(root / "mask_present.png"),
            "gone_png": str(root / "mask_gone.png"),
            "present_ass": str(root / "subs_present.ass"),
            "gone_ass": str(root / "subs_gone.ass"),
            "present_cube": str(root / "grade_present.cube"),
            "gone_cube": str(root / "grade_gone.cube"),
        }
    )
    return tokens


def _ref_element_xml(case: RefCase, tokens: dict[str, str]) -> str:
    """The case's element, as the string both representations are built from."""
    props = "".join(
        f'<property name="{name}">{escape(_fill(value, tokens))}</property>'
        for name, value in case.props.items()
    )
    return f"<{case.tag}>{props}</{case.tag}>"


def _ref_as_xml(case: RefCase, tokens: dict[str, str]) -> Path:
    """The case as the MLT XML the renderer is about to hand melt.

    The element is nested in the sequence tractor, which is where the
    serializer puts a composition and a subtitle filter.
    """
    root = Path(tokens["root"])
    path = root / "p.kdenlive"
    path.write_text(
        '<?xml version="1.0"?>\n'
        f'<mlt version="7" root="{root}">\n'
        '  <producer id="prod0">\n'
        '    <property name="mlt_service">avformat</property>\n'
        f'    <property name="resource">{tokens["present"]}</property>\n'
        "  </producer>\n"
        '  <playlist id="pl0">\n'
        '    <entry producer="prod0" in="0" out="99"/>\n'
        "  </playlist>\n"
        '  <tractor id="tractor0">\n'
        '    <track producer="pl0"/>\n'
        f"    {_ref_element_xml(case, tokens)}\n"
        "  </tractor>\n"
        "</mlt>\n",
        encoding="utf-8",
    )
    return path


def _ref_as_model(case: RefCase, tokens: dict[str, str]) -> KdenliveProject:
    """The same case as the in-memory project the validator is handed."""
    present = tokens["present"]
    project = KdenliveProject(
        version="7",
        title="RefCase",
        root=tokens["root"],
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(
                id="prod0",
                resource=present,
                properties={"mlt_service": "avformat", "resource": present},
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
    if case.carrier == "subtitle":
        project.subtitles = [
            SubtitleTrack(
                id=1,
                name="Subtitle",
                file=_fill(case.props["av.filename"], tokens),
            )
        ]
    else:
        project.opaque_elements = [
            OpaqueElement(
                tag=case.tag,
                xml_string=_ref_element_xml(case, tokens),
                position_hint="tractor",
            )
        ]
    return project


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


@pytest.mark.parametrize(
    "case", REFERENCE_CASES, ids=[c.id for c in REFERENCE_CASES]
)
class TestBothCallSitesAgreeOnNonProducerReferences:
    """The same three assertions, for the files that are not producer resources.

    Stated once as a ``RefCase`` and run through both call sites, so "the two
    agree" and "the two are right" stay separate claims -- the distinction that
    caught the last mutation, where making the shared core report nothing left
    every agreement test passing.
    """

    def test_renderer_verdict(self, tmp_path, case):
        tokens = _ref_tokens(tmp_path)
        expected = sorted(_fill(p, tokens) for p in case.expect_missing)
        assert missing_media(_ref_as_xml(case, tokens)) == expected, case.why

    def test_validator_verdict(self, tmp_path, case):
        tokens = _ref_tokens(tmp_path)
        expected = sorted(_fill(p, tokens) for p in case.expect_missing)
        report = validate_project(
            _ref_as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
        )
        assert _validator_missing(report) == expected, case.why

    def test_the_two_agree(self, tmp_path, case):
        tokens = _ref_tokens(tmp_path)
        renderer = missing_media(_ref_as_xml(case, tokens))
        validator = _validator_missing(
            validate_project(
                _ref_as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
            )
        )
        assert renderer == validator, (
            f"{case.id}: renderer says {renderer}, validator says {validator} "
            f"-- {case.why}"
        )


class TestReferencesReachEveryCallSite:
    """The reference check is not only in the two front doors' unit shape."""

    def test_a_missing_matte_is_named_by_the_render_precondition(self, tmp_path):
        # The message the user sees must name the matte, not just say "media".
        from workshop_video_brain.edit_mcp.adapters.render.media_check import (
            missing_media_message,
        )

        tokens = _ref_tokens(tmp_path)
        case = next(c for c in REFERENCE_CASES if c.id == "luma_matte_absent_is_refused")
        project = _ref_as_xml(case, tokens)
        absent = missing_media(project)
        assert absent == [tokens["gone_pgm"]]
        assert tokens["gone_pgm"] in missing_media_message(project, absent)

    def test_the_validator_locates_a_missing_matte_at_its_element(self, tmp_path):
        tokens = _ref_tokens(tmp_path)
        case = next(c for c in REFERENCE_CASES if c.id == "luma_matte_absent_is_refused")
        report = validate_project(
            _ref_as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
        )
        item = next(i for i in report.items if i.category == "media")
        # A transition is written without an id, so the property it came from
        # is what lets a reader find it.
        assert item.location == "transition:resource"
        assert item.path == tokens["gone_pgm"]

    def test_a_subtitle_track_is_located_by_its_id(self, tmp_path):
        tokens = _ref_tokens(tmp_path)
        case = next(
            c for c in REFERENCE_CASES if c.id == "subtitle_sidecar_absent_is_refused"
        )
        report = validate_project(
            _ref_as_model(case, tokens), workspace_root=tmp_path / "elsewhere"
        )
        item = next(i for i in report.items if i.category == "media")
        assert item.location == "filter:1"

    def test_a_producer_and_a_matte_are_both_named_once(self, tmp_path):
        # Producer resources and references are de-duplicated together and
        # sorted together: one list, one message per file.
        tokens = _ref_tokens(tmp_path)
        root = Path(tokens["root"])
        path = root / "both.kdenlive"
        path.write_text(
            '<?xml version="1.0"?>\n'
            f'<mlt version="7" root="{root}">\n'
            '  <producer id="prod0">\n'
            '    <property name="mlt_service">avformat</property>\n'
            f'    <property name="resource">{tokens["gone"]}</property>\n'
            "  </producer>\n"
            '  <tractor id="t">\n'
            '    <transition mlt_service="luma">\n'
            f'      <property name="resource">{tokens["gone_pgm"]}</property>\n'
            "    </transition>\n"
            '    <transition mlt_service="luma">\n'
            f'      <property name="resource">{tokens["gone_pgm"]}</property>\n'
            "    </transition>\n"
            "  </tractor>\n"
            "</mlt>\n",
            encoding="utf-8",
        )
        assert missing_media(path) == sorted([tokens["gone"], tokens["gone_pgm"]])

    def test_mlt_service_written_as_an_attribute_is_read(self, tmp_path):
        # ``patcher_intents._apply_add_composition`` writes every composition
        # as <transition mlt_service="luma">, an attribute rather than a
        # property child. MLT reads attributes as properties; a reader that
        # only looked at <property> children would miss every one of them.
        tokens = _ref_tokens(tmp_path)
        root = Path(tokens["root"])
        path = root / "attr.kdenlive"
        path.write_text(
            '<?xml version="1.0"?>\n'
            f'<mlt version="7" root="{root}">\n'
            '  <tractor id="t">\n'
            '    <transition mlt_service="luma">\n'
            f'      <property name="resource">{tokens["gone_pgm"]}</property>\n'
            "    </transition>\n"
            "  </tractor>\n"
            "</mlt>\n",
            encoding="utf-8",
        )
        assert missing_media(path) == [tokens["gone_pgm"]]


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
