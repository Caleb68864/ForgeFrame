#!/usr/bin/env python
"""Build a pack of ForgeFrame-generated projects to open in the real Kdenlive.

Each step applies one more MCP tool to a cumulative timeline and copies the
resulting ``.kdenlive`` into the pack as ``NN_<step>.kdenlive``, so a load
problem in Kdenlive can be pinned to the step that introduced it. Media is
synthetic (ffmpeg ``testsrc``/``color`` + sine audio), so the pack builds on
any machine with ffmpeg.

Then, in Kdenlive (the version you target -- currently 26.x):

1. Open each project in order. Note any dialog verbatim (e.g. "Project
   corrupted. Clip ... not found in project bin").
2. Check what the step should show (``CHECKLIST.md`` in the pack).
3. Save the first clean project as ``<name>_native.kdenlive`` -- that is a
   new native reference fixture for ``tests/fixtures/kdenlive_references/``.

Usage:
    uv run python scripts/kdenlive_check_pack.py [OUT_DIR]

OUT_DIR defaults to ``./kdenlive-check-pack`` (git-ignored scratch).
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.integration.external._check_pack import build_check_pack, write_checklist  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "kdenlive-check-pack").resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    steps = build_check_pack(out)
    write_checklist(out, steps)
    print(f"\nPack written to {out} ({len(steps)} projects). See CHECKLIST.md.")


if __name__ == "__main__":
    main()
