#!/usr/bin/env python3
"""Generate the Kdenlive effect registry identity table."""
from __future__ import annotations

import argparse
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "workshop-video-brain" / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (  # noqa: E402
    _detect_source_version,
    emit_effect_ids_module,
    parse_effect_identity,
)

DEFAULT_SOURCE_DIR = pathlib.Path("/usr/share/kdenlive/effects/")
DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "workshop-video-brain"
    / "src"
    / "workshop_video_brain"
    / "edit_mcp"
    / "adapters"
    / "kdenlive"
    / "effect_ids.py"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=pathlib.Path, default=DEFAULT_SOURCE_DIR,
        help="Directory containing Kdenlive effect XML files.",
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=DEFAULT_OUTPUT,
        help="Output path for the generated Python module.",
    )
    parser.add_argument("--source-version", type=str, default=None)
    args = parser.parse_args(argv)
    if not args.source_dir.exists():
        print(f"Kdenlive effect dir not found: {args.source_dir}", file=sys.stderr)
        return 2
    rows = [
        parse_effect_identity(path)
        for path in sorted(args.source_dir.glob("*.xml"))
    ]
    output = emit_effect_ids_module(
        rows, args.source_version or _detect_source_version()
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Wrote {args.output}: {len(rows)} effect identities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
