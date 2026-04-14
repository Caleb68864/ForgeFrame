#!/usr/bin/env python3
"""Regenerate the `effect_wrappers/` MCP wrapper package from the catalog.

Mirrors the CLI subcommand `workshop-video-brain catalog regenerate-wrappers`.
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

from workshop_video_brain.edit_mcp.pipelines.effect_catalog import (  # noqa: E402
    CATALOG,
)
from workshop_video_brain.edit_mcp.pipelines.effect_wrapper_gen import (  # noqa: E402
    emit_wrappers_package,
    select_wrappable_effects,
)

DEFAULT_OUTPUT = (
    _REPO_ROOT
    / "workshop-video-brain"
    / "src"
    / "workshop_video_brain"
    / "edit_mcp"
    / "pipelines"
    / "effect_wrappers"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT,
        help="Output directory for generated wrapper modules.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the output directory.",
    )
    args = parser.parse_args(argv)

    effects = select_wrappable_effects(CATALOG)
    if len(effects) < 20:
        print(
            f"Error: selection heuristic yielded {len(effects)} effects "
            "(< 20). Tune heuristic before regenerating.",
            file=sys.stderr,
        )
        return 2

    try:
        emit_wrappers_package(effects, args.output, force=args.force)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output}: {len(effects)} wrapper modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
