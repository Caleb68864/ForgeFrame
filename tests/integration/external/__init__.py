"""External-oracle integration tests.

Non-self-referential harness: every test feeds a project our serializer writes
to real ``melt`` / ``ffprobe`` and asserts against external truth (exit codes,
decoded pixels, container metadata). See the module docstrings and
``docs/plans/2026-07-03-melt-oracle-test-harness-design.md``.
"""
