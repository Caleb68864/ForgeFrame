"""Core data models for workshop-video-brain."""
from .enums import (
    AnalysisStatus,
    JobStatus,
    MarkerCategory,
    ProjectStatus,
    ProxyStatus,
    ShotType,
    TranscriptStatus,
    ValidationSeverity,
)
from .kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from .markers import Marker, MarkerGroup
from .media import MediaAsset
from .planning import MaterialList, ReviewNote, ScriptDraft, Shot, ShotPlan
from .project import RenderJob, SnapshotRecord, VideoProject
from .timeline import (
    AddClip,
    AddGuide,
    AddSubtitleRegion,
    AddTransition,
    AudioFade,
    CreateTrack,
    InsertGap,
    MoveClip,
    RemoveClip,
    RippleDelete,
    SetClipSpeed,
    SetTrackMute,
    SetTrackVisibility,
    SplitClip,
    SubtitleCue,
    TimelineIntent,
    TransitionIntent,
    TrimClip,
)
from .transitions import TransitionInstruction, TransitionPreset, TransitionType
from .transcript import Transcript, TranscriptSegment, WordTiming
from .validation import ValidationItem, ValidationReport
from .workspace import Workspace
from .clips import ClipLabel
from .pacing import PacingSegment, PacingReport
from .title_cards import TitleCard
from .patterns import (
    BuildData,
    BuildStep,
    BuildTip,
    MaterialItem,
    Measurement,
)
from .assembly import AssemblyPlan, ClipAssignment, StepAssembly
from .broll_library import BRollEntry, BRollLibrary

__all__ = [
    # enums
    "ProjectStatus",
    "MarkerCategory",
    "JobStatus",
    "ShotType",
    "ProxyStatus",
    "TranscriptStatus",
    "AnalysisStatus",
    "ValidationSeverity",
    # media
    "MediaAsset",
    # transcript
    "WordTiming",
    "TranscriptSegment",
    "Transcript",
    # markers
    "Marker",
    "MarkerGroup",
    # planning
    "Shot",
    "ShotPlan",
    "ScriptDraft",
    "ReviewNote",
    "MaterialList",
    # timeline intents
    "TimelineIntent",
    "TransitionIntent",
    "SubtitleCue",
    "AddClip",
    "TrimClip",
    "InsertGap",
    "AddGuide",
    "AddSubtitleRegion",
    "AddTransition",
    "CreateTrack",
    "RemoveClip",
    "MoveClip",
    "SplitClip",
    "RippleDelete",
    "SetClipSpeed",
    "AudioFade",
    "SetTrackMute",
    "SetTrackVisibility",
    # kdenlive models
    "KdenliveProject",
    "ProjectProfile",
    "Producer",
    "Track",
    "Playlist",
    "PlaylistEntry",
    "Guide",
    "OpaqueElement",
    # project
    "VideoProject",
    "RenderJob",
    "SnapshotRecord",
    # validation
    "ValidationItem",
    "ValidationReport",
    # workspace
    "Workspace",
    # clips
    "ClipLabel",
    # pacing
    "PacingSegment",
    "PacingReport",
    # transitions
    "TransitionType",
    "TransitionPreset",
    "TransitionInstruction",
    # title cards
    "TitleCard",
    # patterns
    "MaterialItem",
    "Measurement",
    "BuildStep",
    "BuildTip",
    "BuildData",
    # assembly
    "ClipAssignment",
    "StepAssembly",
    "AssemblyPlan",
    # broll library
    "BRollEntry",
    "BRollLibrary",
]
