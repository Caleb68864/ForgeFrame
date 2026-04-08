# Workshop Video Brain Technical Specification

**Product:** Workshop Video Brain  
**Subtitle:** Kdenlive Edit MCP + Obsidian Production Brain  
**Spec Version:** 1.1-draft  
**Date:** 2026-04-08  
**Target OS:** Linux first, same host as Kdenlive for v1  
**Primary Language:** Python 3.12+  
**Protocol:** MCP 2025-11-25 for edit-facing interfaces  
**Primary Editor Target:** Kdenlive 25.12-era project model with adapter versioning  
**Primary Knowledge Store:** Obsidian vault on local filesystem  
**Reference Runtime Tools:** Kdenlive, MLT, FFmpeg/ffprobe, Whisper or faster-whisper, optional Vosk, optional OTIO

---

## Summary

This specification defines the technical design for Workshop Video Brain -- a single local-first project with two cooperating modules: Production Brain (planning, scripting, shot design, rough-cut review guidance, Obsidian note creation and update) and Kdenlive Edit MCP (media ingest, transcript generation, proxy generation, marker generation, selects/review timeline generation, transition helpers, subtitle workflows, safe project copy creation, render orchestration).

The full specification covers 32 sections including: Product-to-Spec Alignment, Scope, Design Principles, External References, High-Level Architecture, Repository Layout, Shared Workspace Model, Obsidian Integration, Production Brain Module, Kdenlive Edit MCP, Media Ingest and Analysis, Transcript and Speaker Analysis, Auto-Marking, Review and Selects Timelines, Transition Helpers, Subtitles, Kdenlive Project Adapter, Render Orchestration, Validation, Snapshot and Recovery, MCP Surface, CLI, Workflow Scenarios, Non-Functional Requirements, Testing Strategy, Roadmap, Open Questions, and Acceptance Criteria.

> **Note:** This is the original tech spec preserved as reference. The unified build plan at `docs/plans/2026-04-08-workshop-video-brain-design.md` supersedes this document for implementation decisions, including resolution of all open questions.
