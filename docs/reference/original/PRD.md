# Product Requirements Document (PRD)

**Product Name:** Workshop Video Brain  
**Working Product Subtitle:** Kdenlive Edit MCP + Obsidian Production Brain  
**Document Version:** 1.1-draft  
**Date:** 2026-04-08  
**Target Platform:** Linux, same host as Kdenlive for v1  
**Primary Language:** Python 3.12+  
**Target Client Protocol:** Model Context Protocol (MCP) 2025-11-25  
**Primary Host Application:** Kdenlive 25.12-era project model with adapter versioning  
**Primary Knowledge Store:** Obsidian vault, local filesystem  
**Primary Audience:** A solo Linux creator making MYOG, camping, garage/shop, and DIY tutorial videos for YouTube who wants help planning the video, capturing the right shots, organizing footage, and getting to a clean first edit faster.

---

## 1. Executive Summary

Workshop Video Brain is a **two-module local-first product**:

1. **Production Brain** -- An Obsidian-centered planning and writing layer that helps the user turn a rough idea into a structured tutorial plan, script, shot list, edit checklist, publish checklist, and persistent project notes.

2. **Kdenlive Edit MCP** -- A Kdenlive-aware editing and logging layer that scans footage, generates transcripts, creates markers, builds selects/review timelines, applies basic transitions, manages subtitles, generates proxies automatically, and writes safe project copies for human review in Kdenlive.

The key product insight is that the user does **not** primarily need "AI that edits everything." The user needs an assistant that helps with deciding what the video should teach, identifying what shots to film, organizing what was filmed, marking useful moments automatically, building a sane first review timeline, reducing fiddly Kdenlive housekeeping, and preserving everything in an Obsidian workflow.

## 2-25. See full PRD

The complete PRD covers: Product Vision, Core Product Thesis, Product Shape, Primary User and Use Case, Problems to Solve, Product Goals, Product Principles, Reference Platform and Tooling Context, Scope Overview, Module A (Production Brain), Module B (Kdenlive Edit MCP), Coordination Between Modules, Key User Workflows, Best Guess First Ranking Strategy, Automatic Proxy Policy, Script Writing and Shot Planning Scope, Functional Requirements Summary, MCP Surface Area, Obsidian as Source of Truth, Acceptance Criteria by Theme, Risks and Mitigations, Recommended Build Order, and Implementation Artifacts.

> **Note:** This is the original PRD preserved as reference. The unified build plan at `docs/plans/2026-04-08-workshop-video-brain-design.md` supersedes this document for implementation decisions.
