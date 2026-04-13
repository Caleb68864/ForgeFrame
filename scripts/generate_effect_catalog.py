#!/usr/bin/env python3
"""Regenerate `workshop_video_brain.edit_mcp.pipelines.effect_catalog`.

Parses Kdenlive effect XML files (default: /usr/share/kdenlive/effects/) into
typed records and emits a self-contained, checked-in Python module.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# Ensure src/ is importable when invoked directly (not via `uv run`)
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "workshop-video-brain" / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (  # noqa: E402
    _detect_source_version,
    build_catalog,
    emit_python_module,
)

DEFAULT_SOURCE_DIR = pathlib.Path("/usr/share/kdenlive/effects/")
DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "workshop-video-brain"
    / "src"
    / "workshop_video_brain"
    / "edit_mcp"
    / "pipelines"
    / "effect_catalog.py"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=pathlib.Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing Kdenlive effect XML files.",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT,
        help="Output path for the generated Python module.",
    )
    parser.add_argument(
        "--source-version",
        type=str,
        default=None,
        help="Override auto-detected Kdenlive source version.",
    )
    parser.add_argument(
        "--no-upstream-check",
        action="store_true",
        help="Skip the GitHub upstream cross-check.",
    )
    args = parser.parse_args(argv)

    source_dir: pathlib.Path = args.source_dir
    if not source_dir.exists():
        print(
            f"Kdenlive effect dir not found: {source_dir}. "
            "Install Kdenlive or pass --source-dir.",
            file=sys.stderr,
        )
        return 2

    source_version = args.source_version or _detect_source_version()

    effects, diff = build_catalog(
        source_dir, check_upstream=not args.no_upstream_check
    )
    emit_python_module(effects, args.output, source_version, diff)

    print(
        f"Wrote {args.output}: {len(effects)} effects "
        f"(upstream check: {diff.upstream_check}; "
        f"upstream-only={len(diff.upstream_only_ids)}, "
        f"local-only={len(diff.local_only_ids)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
