"""MLT bindings worker: one JSON request on stdin, JSON lines on a private stdout.

Runs under whichever interpreter can import the bindings, with ``-I``, so it may
import only the standard library and MLT. Keep the syntax Python 3.10 compatible.

Bind every MLT object to a name for the whole op: the bindings segfault on
wrappers built from garbage-collected temporaries.
"""
import json
import os
import struct
import sys
import time
import zlib

# Protect the protocol channel first: some MLT C code writes to fd 1.
PROTO = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)

PROTOCOL = 1
INT_MAX = 2147483647

mlt = None
module_name = None
repository = None


def load_bindings():
    global mlt, module_name
    try:
        import mlt7 as binding
        module_name = "mlt7"
    except ImportError:
        import mlt as binding
        module_name = "mlt"
    mlt = binding
    global repository
    repository = mlt.Factory.init()


def emit(payload):
    PROTO.write(json.dumps(payload) + "\n")
    PROTO.flush()


def op_ping(_args):
    return {
        "protocol": PROTOCOL,
        "mlt_version": mlt.mlt_version_get_string(),
        "python": sys.version.split()[0],
        "module": module_name,
    }


def walk_playlist(playlist):
    clips = []
    for index in range(playlist.count()):
        if playlist.is_blank(index):
            continue
        info = playlist.clip_info(index)
        producer = info.producer
        clips.append({
            "start": info.start,
            "in": info.frame_in,
            "out": info.frame_out,
            "resource": info.resource,
            "producer_id": producer.get("id") if producer is not None else None,
            "kdenlive_id": producer.get("kdenlive:id") if producer is not None else None,
            "mlt_service": producer.get("mlt_service") if producer is not None else None,
        })
    return {"id": playlist.get("id"), "clips": clips}


def op_inspect(args):
    profile = mlt.Profile()
    root = mlt.Producer(profile, "xml", args["path"])
    if not root.is_valid():
        raise ValueError("MLT could not load " + args["path"])
    multitrack = mlt.Multitrack(root.producer())
    first = multitrack.track(0)
    parent = first.parent() if first is not None and first.is_cut() else first
    if parent is not None and parent.is_valid() and parent.type() == mlt.mlt_service_tractor_type:
        sequence = mlt.Tractor(parent)
    else:
        sequence = mlt.Tractor(root.producer())

    tracks = []
    for index in range(sequence.count()):
        track = sequence.track(index)
        if track is None or not track.is_valid():
            continue
        kind = track.type()
        if kind == mlt.mlt_service_producer_type and track.get_length() == INT_MAX:
            continue  # the background
        playlists = []
        if kind == mlt.mlt_service_tractor_type:
            track_tractor = mlt.Tractor(track)
            for lane_index in range(track_tractor.count()):
                lane = track_tractor.track(lane_index)
                if lane is None or not lane.is_valid() or lane.type() != mlt.mlt_service_playlist_type:
                    continue
                playlist = mlt.Playlist(lane)
                playlists.append(walk_playlist(playlist))
        elif kind == mlt.mlt_service_playlist_type:
            playlist = mlt.Playlist(track)
            playlists.append(walk_playlist(playlist))
        tracks.append({"id": track.get("id"), "type": kind, "length": track.get_length(), "playlists": playlists})

    return {
        "profile": {
            "width": profile.width(),
            "height": profile.height(),
            "frame_rate_num": profile.frame_rate_num(),
            "frame_rate_den": profile.frame_rate_den(),
        },
        "sequence_id": sequence.get("id"),
        "tracks": tracks,
    }


def write_png(path, width, height, rgb):
    """Write RGB bytes as a PNG; the interpreter running this may have no Pillow."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    stride = width * 3
    rows = b"".join(b"\x00" + bytes(rgb[row * stride:(row + 1) * stride]) for row in range(height))
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(rows)))
        handle.write(chunk(b"IEND", b""))


def op_frames(args):
    profile = mlt.Profile()
    producer = mlt.Producer(profile, "xml", args["path"])
    if not producer.is_valid():
        raise ValueError("MLT could not load " + args["path"])
    length = producer.get_length()
    width = int(args["width"])
    height = round(width * profile.height() / profile.width() / 2) * 2
    results = []
    for requested in args["frames"]:
        frame_number = max(0, min(int(requested), length - 1))
        producer.seek(frame_number)
        frame = producer.get_frame()
        # get_image(fmt, 0, 0) returns an empty buffer, so the size is explicit.
        image = frame.get_image(mlt.mlt_image_rgb, width, height)
        if len(image) != width * height * 3:
            raise ValueError("frame %d came back as %d bytes" % (frame_number, len(image)))
        path = os.path.join(args["out_dir"], "f_%06d.png" % frame_number)
        write_png(path, width, height, image)
        results.append({"requested": requested, "frame": frame_number, "path": path,
                        "width": width, "height": height})
    return {"frames": results, "length": length}


def op_render(args):
    profile = mlt.Profile()
    producer = mlt.Producer(profile, "xml", args["path"])
    if not producer.is_valid():
        raise ValueError("MLT could not load " + args["path"])
    consumer = mlt.Consumer(profile, "avformat", args["out"])
    for key, value in (args.get("props") or {}).items():
        consumer.set(key, str(value))
    consumer.set("terminate_on_pause", "1")
    consumer.set("real_time", "-1")
    consumer.connect(producer)
    consumer.start()
    total = producer.get_length()
    while not consumer.is_stopped():
        emit({"event": "progress", "frame": producer.position(), "total": total})
        time.sleep(0.25)
    consumer.stop()
    emit({"event": "progress", "frame": max(0, total - 1), "total": total})
    return {"frames": total}


def op_registry(_args):
    def names(properties):
        return sorted({properties.get_name(index) for index in range(properties.count())})

    filters = repository.filters()
    transitions = repository.transitions()
    producers = repository.producers()
    consumers = repository.consumers()
    links = repository.links()
    return {
        "mlt_version": mlt.mlt_version_get_string(),
        "filters": names(filters),
        "transitions": names(transitions),
        "producers": names(producers),
        "consumers": names(consumers),
        "links": names(links),
    }


def op_service_info(args):
    kinds = {
        "filter": mlt.mlt_service_filter_type,
        "transition": mlt.mlt_service_transition_type,
        "producer": mlt.mlt_service_producer_type,
        "consumer": mlt.mlt_service_consumer_type,
        "link": mlt.mlt_service_link_type,
    }
    metadata = repository.metadata(kinds[args["kind"]], args["name"])
    return {"yaml": metadata.serialise_yaml() if metadata else None}


OPS = {
    "ping": op_ping,
    "inspect": op_inspect,
    "frames": op_frames,
    "render": op_render,
    "registry": op_registry,
    "service_info": op_service_info,
}


def main():
    try:
        request = json.loads(sys.stdin.readline())
        if request.get("protocol") != PROTOCOL:
            raise ValueError("unsupported protocol %r" % (request.get("protocol"),))
        operation = OPS.get(request.get("op"))
        if operation is None:
            raise ValueError("unknown op %r" % (request.get("op"),))
        load_bindings()
        result = operation(request.get("args") or {})
    except Exception as exc:  # noqa: BLE001 -- every failure must reach the protocol
        emit({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
    else:
        emit({"ok": True, "result": result})
    PROTO.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
