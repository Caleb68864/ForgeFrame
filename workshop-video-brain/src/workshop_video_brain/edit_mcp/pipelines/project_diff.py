"""What changed between two versions of a project, in sentences and JSON (pure).

Works on parsed ``KdenliveProject`` models, never on XML text (OpaqueElement
properties are read with ``ET.fromstring``, as ``effect_stack`` does). Clips
are aligned with ``difflib.SequenceMatcher`` on ``(producer, in, out)`` so an
insert reads as one added clip, not every later clip "changed".
"""
from __future__ import annotations

import difflib
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import PurePath

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_mmss
from workshop_video_brain.edit_mcp.pipelines.clip_place import entry_length, playlist_length

_BOOKKEEPING = {"track", "clip_index", "mlt_service", "kdenlive_id", "disable"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fps(project: KdenliveProject) -> float:
    return float(project.profile.fps or 25.0)


def _when(frame: int, fps: float) -> str:
    return f"{seconds_to_mmss(frame / fps)} [{frame}]"


def _track_type(project: KdenliveProject, playlist_id: str) -> str:
    track = next((t for t in project.tracks if t.id == playlist_id), None)
    return track.track_type if track else "video"


def track_label(project: KdenliveProject, playlist_index: int) -> str:
    """``V1`` / ``A1`` counted within the type in playlist order, plus the name: ``"V1 (Video)"``."""
    playlist = project.playlists[playlist_index]
    kind = _track_type(project, playlist.id)
    number = sum(1 for p in project.playlists[: playlist_index + 1] if _track_type(project, p.id) == kind)
    track = next((t for t in project.tracks if t.id == playlist.id), None)
    label = f"{'A' if kind == 'audio' else 'V'}{number}"
    return f"{label} ({track.name})" if track and track.name else label


def _producer_name(project: KdenliveProject, producer_id: str) -> str:
    producer = next((p for p in project.producers if p.id == producer_id), None)
    if producer is None:
        return producer_id
    resource = producer.properties.get("resource") or producer.resource
    service = producer.properties.get("mlt_service", "")
    if resource and service not in ("color", "colour") and ("/" in resource or "." in resource):
        return PurePath(resource.replace("\\", "/")).name
    return producer_id


def clip_records(project: KdenliveProject, playlist_index: int) -> list[dict]:
    out, start, index = [], 0, 0
    for entry in project.playlists[playlist_index].entries:
        length = entry_length(entry)
        if entry.producer_id:
            out.append({"clip_index": index, "start": start, "end": start + length - 1,
                        "producer_id": entry.producer_id, "in": entry.in_point, "out": entry.out_point,
                        "name": _producer_name(project, entry.producer_id)})
            index += 1
        start += length
    return out


def _filters(project: KdenliveProject, track_index: int, clip_index: int | None) -> list[dict]:
    """Clip effects (clip_index given) or track filters (None), in stack order."""
    out = []
    for elem in project.opaque_elements:
        if elem.tag != "filter":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        if root.get("track") != str(track_index):
            continue
        ci = root.get("clip_index")
        if (clip_index is None) != (ci is None) or (clip_index is not None and ci != str(clip_index)):
            continue
        props = {c.get("name"): c.text or "" for c in root if c.tag == "property" and c.get("name")}
        out.append({"key": props.get("kdenlive_id") or props.get("mlt_service") or root.get("mlt_service") or "?",
                    "props": props})
    return out


def _parse_time(text, fps: float) -> int | None:
    text = (text or "").strip()
    if text.lstrip("-").isdigit():
        return int(text)
    parts = text.split(":")
    if len(parts) == 3:
        try:
            return int((int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])) * fps + 0.5)
        except ValueError:
            return None
    return None


def _transitions(project: KdenliveProject) -> list[dict]:
    fps = _fps(project)
    out = []
    for elem in project.opaque_elements:
        if elem.tag != "transition":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        props = {c.get("name"): c.text or "" for c in root if c.tag == "property" and c.get("name")}
        props.update({k: v for k, v in root.attrib.items() if k in ("in", "out", "mlt_service")})
        out.append({"key": (props.get("kdenlive_id") or props.get("mlt_service") or "?",
                            props.get("a_track", ""), props.get("b_track", "")),
                    "in": _parse_time(props.get("in"), fps), "out": _parse_time(props.get("out"), fps)})
    return out


def _hidden(project: KdenliveProject) -> dict[str, str]:
    """track id -> its mute/visibility ``hide`` value (only tracks that carry a directive)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import HIDE_DIRECTIVE_TAG

    out = {}
    for elem in project.opaque_elements:
        if elem.tag != HIDE_DIRECTIVE_TAG:
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        out[root.get("track", "")] = root.get("hide", "")
    return out


def _is_keyframes(value: str) -> bool:
    return "=" in value and (";" in value or value[:2].isdigit())


def _value_change(name: str, old: str | None, new: str | None) -> str:
    if old is None:
        return f"{name} set to {new}"
    if new is None:
        return f"{name} removed (was {old})"
    if _is_keyframes(old) or _is_keyframes(new):
        return f"{name} keyframes changed ({old.count(';') + 1} -> {new.count(';') + 1} keyframes)"
    return f"{name} {old} -> {new}"


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

class _Changes:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, category: str, action: str, text: str, **fields):
        self.items.append({"category": category, "action": action, **fields, "text": text})


def _diff_stack(changes: _Changes, category: str, where: str, track: str, old: list[dict], new: list[dict], **extra):
    matcher = difflib.SequenceMatcher(a=[f["key"] for f in old], b=[f["key"] for f in new], autojunk=False)
    matched_old, matched_new = set(), set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                matched_old.add(i)
                matched_new.add(j)
                _diff_props(changes, category, where, track, old[i], new[j], **extra)
    old_left = [i for i in range(len(old)) if i not in matched_old]
    new_left = [j for j in range(len(new)) if j not in matched_new]
    # A key present on both sides but not aligned = reordered.
    for i in list(old_left):
        j = next((j for j in new_left if new[j]["key"] == old[i]["key"]), None)
        if j is not None:
            old_left.remove(i)
            new_left.remove(j)
            changes.add(category, "reordered", f"{where}: {old[i]['key']} moved from position {i + 1} to {j + 1}.",
                        track=track, effect=old[i]["key"], **extra)
            _diff_props(changes, category, where, track, old[i], new[j], **extra)
    for i in old_left:
        changes.add(category, "removed", f"{where}: {old[i]['key']} removed.", track=track, effect=old[i]["key"], **extra)
    for j in new_left:
        changes.add(category, "added", f"{where}: {new[j]['key']} added.", track=track, effect=new[j]["key"], **extra)


def _diff_props(changes, category, where, track, a: dict, b: dict, **extra):
    was_on = a["props"].get("disable", "0") != "1"
    is_on = b["props"].get("disable", "0") != "1"
    if was_on != is_on:
        changes.add(category, "enabled" if is_on else "disabled",
                    f"{where}: {a['key']} {'enabled' if is_on else 'disabled'}.", track=track, effect=a["key"], **extra)
    names = sorted((set(a["props"]) | set(b["props"])) - _BOOKKEEPING)
    diffs = [_value_change(n, a["props"].get(n), b["props"].get(n)) for n in names
             if not n.startswith("kdenlive:") and a["props"].get(n) != b["props"].get(n)]
    if diffs:
        changes.add(category, "changed", f"{where}: {a['key']} " + "; ".join(diffs) + ".",
                    track=track, effect=a["key"], properties=diffs, **extra)


def _overlaps(a: dict, b: dict) -> bool:
    return a["in"] <= b["out"] and b["in"] <= a["out"]


def _diff_clips(changes: _Changes, a: KdenliveProject, b: KdenliveProject, ia: int, ib: int, label: str):
    fps = _fps(b)
    old_all, new_all = clip_records(a, ia), clip_records(b, ib)
    key = lambda r: (r["producer_id"], r["in"], r["out"])  # noqa: E731
    # Anchors first: a clip with the same media, range and start is unchanged.
    # Only the rest is aligned, so a replaced clip between two unchanged ones
    # is not mistaken for "removed + a later clip moved".
    by_place = {(key(r), r["start"]): r for r in new_all}
    pairs: list[tuple[dict, dict]] = []
    anchored_new: set[int] = set()
    old = []
    for r in old_all:
        partner = by_place.get((key(r), r["start"]))
        if partner is not None and partner["clip_index"] not in anchored_new:
            anchored_new.add(partner["clip_index"])
            pairs.append((r, partner))
        else:
            old.append(r)
    new = [r for r in new_all if r["clip_index"] not in anchored_new]
    matcher = difflib.SequenceMatcher(a=[key(r) for r in old], b=[key(r) for r in new], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for r_old, r_new in zip(old[i1:i2], new[j1:j2]):
                pairs.append((r_old, r_new))
                if r_old["start"] != r_new["start"]:
                    changes.add("clips", "moved", f"{label}: {r_new['name']} moved from {_when(r_old['start'], fps)} "
                                f"to {_when(r_new['start'], fps)}.", track=label, clip=r_new["name"],
                                old_start=r_old["start"], new_start=r_new["start"])
            continue
        rest_old, rest_new = list(old[i1:i2]), list(new[j1:j2])
        if tag == "replace":
            for r_old in list(rest_old):
                partner = next((r for r in rest_new if r["producer_id"] == r_old["producer_id"]
                                and _overlaps(r, r_old)), None)
                if partner is not None:
                    rest_old.remove(r_old)
                    rest_new.remove(partner)
                    pairs.append((r_old, partner))
                    deltas = []
                    if partner["in"] != r_old["in"]:
                        deltas.append(f"in {partner['in'] - r_old['in']:+d} frames")
                    if partner["out"] != r_old["out"]:
                        deltas.append(f"out {partner['out'] - r_old['out']:+d} frames")
                    length = partner["out"] - partner["in"] + 1
                    changes.add("clips", "trimmed", f"{label}: {partner['name']} at {_when(partner['start'], fps)} "
                                f"trimmed ({', '.join(deltas)}; now {length / fps:.2f} s).",
                                track=label, clip=partner["name"], in_delta=partner["in"] - r_old["in"],
                                out_delta=partner["out"] - r_old["out"])
                    continue
                partner = next((r for r in rest_new if r["start"] == r_old["start"]
                                and r["end"] - r["start"] == r_old["end"] - r_old["start"]), None)
                if partner is not None:
                    rest_old.remove(r_old)
                    rest_new.remove(partner)
                    pairs.append((r_old, partner))
                    changes.add("clips", "replaced", f"{label}: {r_old['name']} at {_when(r_old['start'], fps)} "
                                f"replaced by {partner['name']}.", track=label, clip=partner["name"],
                                old_clip=r_old["name"])
        for r in rest_old:
            changes.add("clips", "removed", f"{label}: {r['name']} at {_when(r['start'], fps)} removed.",
                        track=label, clip=r["name"], start=r["start"])
        for r in rest_new:
            changes.add("clips", "added", f"{label}: {r['name']} added at {_when(r['start'], fps)} "
                        f"({(r['end'] - r['start'] + 1) / fps:.2f} s long).",
                        track=label, clip=r["name"], start=r["start"])
    for r_old, r_new in pairs:
        _diff_stack(changes, "effects", f"{label} {r_new['name']} at {_when(r_new['start'], fps)}", label,
                    _filters(a, ia, r_old["clip_index"]), _filters(b, ib, r_new["clip_index"]),
                    clip=r_new["name"])


def _duration(project: KdenliveProject) -> int:
    return max((playlist_length(p.entries) for p in project.playlists), default=0)


def diff_projects(a: KdenliveProject, b: KdenliveProject, max_changes: int = 200) -> dict:
    """Changes from *a* (older) to *b* (newer)."""
    if max_changes < 1:
        raise ValueError("max_changes must be >= 1")
    changes = _Changes()
    fps = _fps(b)

    pa, pb = a.profile, b.profile
    for name in ("width", "height", "fps"):
        if getattr(pa, name) != getattr(pb, name):
            changes.add("profile", "changed", f"Project {name} {getattr(pa, name)} -> {getattr(pb, name)}.",
                        field=name)

    index_a = {p.id: i for i, p in enumerate(a.playlists)}
    index_b = {p.id: i for i, p in enumerate(b.playlists)}
    tracks_a = {t.id: t for t in a.tracks}
    tracks_b = {t.id: t for t in b.tracks}
    for pid, i in index_a.items():
        if pid not in index_b:
            changes.add("tracks", "removed", f"Track {track_label(a, i)} removed.", track=track_label(a, i))
    for pid, j in index_b.items():
        if pid not in index_a:
            label = track_label(b, j)
            changes.add("tracks", "added", f"Track {label} added.", track=label)
    hidden_a, hidden_b = _hidden(a), _hidden(b)
    for pid, j in index_b.items():
        if pid not in index_a:
            continue
        i, label = index_a[pid], track_label(b, j)
        ta, tb = tracks_a.get(pid), tracks_b.get(pid)
        if ta and tb and ta.name != tb.name:
            changes.add("tracks", "renamed", f"Track {track_label(a, i)} renamed to {tb.name!r}.", track=label)
        if ta and tb and ta.track_type != tb.track_type:
            changes.add("tracks", "type_changed", f"Track {label} changed from {ta.track_type} to {tb.track_type}.",
                        track=label)
        if hidden_a.get(pid, "") != hidden_b.get(pid, ""):
            changes.add("tracks", "visibility_changed", f"Track {label} mute/visibility changed "
                        f"(hide {hidden_a.get(pid, '') or 'none'!r} -> {hidden_b.get(pid, '') or 'none'!r}).", track=label)
        _diff_clips(changes, a, b, i, j, label)
        _diff_stack(changes, "track_filters", f"Track {label}", label, _filters(a, i, None), _filters(b, j, None))

    # Transitions: match by key, then compare ranges.
    ta_list, tb_list = _transitions(a), _transitions(b)
    unmatched_b = list(tb_list)
    for t in ta_list:
        same = next((u for u in unmatched_b if u["key"] == t["key"] and (u["in"], u["out"]) == (t["in"], t["out"])), None)
        if same is None:
            same = next((u for u in unmatched_b if u["key"] == t["key"]), None)
            if same is not None:
                changes.add("transitions", "moved", f"Transition {t['key'][0]} moved from "
                            f"{_when(t['in'] or 0, fps)}-{_when(t['out'] or 0, fps)} to "
                            f"{_when(same['in'] or 0, fps)}-{_when(same['out'] or 0, fps)}.", transition=t["key"][0])
            else:
                changes.add("transitions", "removed", f"Transition {t['key'][0]} at {_when(t['in'] or 0, fps)} removed.",
                            transition=t["key"][0])
                continue
        unmatched_b.remove(same)
    for u in unmatched_b:
        changes.add("transitions", "added", f"Transition {u['key'][0]} added at {_when(u['in'] or 0, fps)}"
                    f"-{_when(u['out'] or 0, fps)}.", transition=u["key"][0])

    # Guides.
    ga = {(g.position, g.label) for g in a.guides}
    gb = {(g.position, g.label) for g in b.guides}
    pos_a = {g.position: g.label for g in a.guides}
    pos_b = {g.position: g.label for g in b.guides}
    for position in sorted(set(pos_a) & set(pos_b)):
        if pos_a[position] != pos_b[position]:
            changes.add("guides", "relabelled", f"Guide at {_when(position, fps)} relabelled "
                        f"{pos_a[position]!r} -> {pos_b[position]!r}.", position=position)
    for position, label in sorted(ga - gb):
        if position not in pos_b:
            changes.add("guides", "removed", f"Guide {label!r} at {_when(position, fps)} removed.", position=position)
    for position, label in sorted(gb - ga):
        if position not in pos_a:
            changes.add("guides", "added", f"Guide {label!r} added at {_when(position, fps)}.", position=position)

    # Bin.
    def bin_keys(project):
        keys = {}
        for p in project.producers:
            resource = p.properties.get("resource") or p.resource
            generated = p.properties.get("mlt_service") in ("color", "colour") or not resource
            keys[p.id if generated else resource] = _producer_name(project, p.id)
        return keys
    bin_a, bin_b = bin_keys(a), bin_keys(b)
    for k in sorted(set(bin_a) - set(bin_b)):
        changes.add("bin", "removed", f"Bin clip {bin_a[k]} removed.", clip=bin_a[k])
    for k in sorted(set(bin_b) - set(bin_a)):
        changes.add("bin", "added", f"Bin clip {bin_b[k]} added.", clip=bin_b[k])

    da, db = _duration(a), _duration(b)
    if da != db:
        changes.add("duration", "changed", f"Duration {seconds_to_mmss(da / _fps(a))} -> {seconds_to_mmss(db / fps)} "
                    f"[{da} -> {db} frames].", old_frames=da, new_frames=db)

    items = changes.items
    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in items:
        summary[c["category"]][c["action"]] += 1
    summary_plain = {k: dict(v) for k, v in summary.items()}
    return {
        "identical": not items,
        "summary": summary_plain,
        "changes": items[:max_changes],
        "truncated": len(items) > max_changes,
        "text": _text(items[:max_changes], summary_plain, da, db, a, b, len(items) > max_changes),
    }


_ORDER = ("profile", "tracks", "clips", "effects", "track_filters", "transitions", "guides", "bin", "duration")


def _text(items, summary, da, db, a, b, truncated) -> str:
    if not items:
        return "No changes: the two versions are the same timeline."
    parts = []
    clip_tracks = defaultdict(int)
    for c in items:
        if c["category"] == "clips":
            clip_tracks[c["track"]] += 1
    parts += [f"{n} clip{'s' if n != 1 else ''} changed on {track}" for track, n in clip_tracks.items()]
    for category in ("effects", "track_filters", "transitions", "guides", "bin", "tracks"):
        for action, n in summary.get(category, {}).items():
            noun = {"effects": "effect", "track_filters": "track filter", "transitions": "transition",
                    "guides": "guide", "bin": "bin clip", "tracks": "track"}[category]
            parts.append(f"{n} {noun}{'s' if n != 1 else ''} {action}")
    if da != db:
        parts.append(f"duration {seconds_to_mmss(da / _fps(a))} -> {seconds_to_mmss(db / _fps(b))}")
    lines = [", ".join(parts) + "."]
    for category in _ORDER:
        lines += [c["text"] for c in items if c["category"] == category]
    if truncated:
        lines.append("(More changes not shown; raise max_changes.)")
    return "\n".join(lines)
