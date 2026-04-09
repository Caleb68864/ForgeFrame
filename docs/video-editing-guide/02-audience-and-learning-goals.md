---
title: "Audience and Learning Goals"
tags:
  - learning-goals
  - audience
  - outcomes
---

# Audience and Learning Goals

## Who This Guide Is For

This guide targets learners along **two dimensions**, and you may fall anywhere on either axis:

### Dimension 1: New to Video Production

You have little or no experience with the *process* of making a video. You may have recorded clips on your phone or done a quick screen capture, but you have never planned, shot, edited, and exported a complete video with intentional structure. Terms like "rough cut," "color correction," and "loudness normalization" are unfamiliar or vague.

### Dimension 2: New to Non-Linear Editors and Kdenlive

You have not used a full-featured non-linear editing (NLE) application before, or you have opened one and felt overwhelmed. You do not yet have a mental model for how timelines, tracks, clips, effects, and rendering fit together. You may have heard of Kdenlive but never launched it, or you launched it and closed it within minutes.

**You do not need to be new on both dimensions.** If you have production experience but are new to Kdenlive, the pipeline chapters will be review and the Kdenlive-specific chapters will be where you learn. If you know your way around an NLE but have never planned a shoot, the preproduction chapters will fill the gap.

## What We Assume You Already Know

- **Basic computer literacy.** You can install software, navigate your operating system, and use a web browser.
- **File management.** You understand file paths, can create and rename folders, move files between directories, and use a file manager or terminal for basic operations.

That is it. No prior experience with video, audio, photography, design, or scripting is required.

## Why Linux-First

Kdenlive is developed primarily on Linux and has historically had its most stable and performant builds there. The Linux ecosystem also offers excellent free tools for every supporting role in the pipeline (FFmpeg, Audacity, Inkscape, GIMP, faster-whisper). By defaulting to Linux, this guide aligns with the platform where the toolchain is strongest.

That said, every tool used in this guide is cross-platform. Where a workflow step differs on **Windows** or **macOS**, you will find a clearly marked callout with the platform-specific instructions. Nothing in this guide is Linux-only in substance -- only in default phrasing.

## Learning Goals

When you complete this guide and its [[07-your-first-edit|Your First Edit]] project, you will be able to:

> [!success] Goal 1: Plan and shoot a short video
> Plan a short video using a script or outline, a shot list, and an asset checklist. Execute a shoot with consistent technical choices (resolution, frame rate, audio levels, lighting) that minimize problems in post-production.

> [!success] Goal 2: Ingest and organize assets
> Ingest footage and other assets into a reproducible folder structure with consistent naming. Maintain project hygiene throughout the production process: verify file integrity on ingest, keep backups current, and know where every asset lives at all times.

> [!success] Goal 3: Perform a complete edit in Kdenlive
> Set up a Kdenlive project with correct technical settings. Work through the full editorial process -- selects, rough cut, fine cut -- then apply transitions, titles, color correction, audio cleanup, mixing, loudness targeting, and subtitles. Understand why each step exists and how it connects to the steps before and after it.

> [!success] Goal 4: Deliver platform-appropriate exports
> Export finished videos using the correct codecs and containers for your target platform (YouTube, social media, local playback). Produce both review copies and archival masters. Troubleshoot common export failure modes: audio sync drift, color shift, unexpected cropping, blocky artifacts, and loudness rejection.

## How the Guide Gets You There

Each learning goal maps to a cluster of chapters in the guide. The [[07-your-first-edit|Your First Edit]] project in Ch.07 is a single, end-to-end project that exercises all four goals in sequence. By working through it, you do not just read about the pipeline -- you execute it, building muscle memory and intuition that transfers to every future project.

| Learning Goal | Key Chapters |
|---|---|
| Plan and shoot | [[03-from-idea-to-outline\|Idea to Outline]] (Ch.03), [[04-scripts-shot-plans-capture-prep\|Scripts & Shots]] (Ch.04), [[05-filming-your-tutorial\|Filming]] (Ch.05) |
| Ingest and organize | [[07-your-first-edit\|Your First Edit]] (Ch.07) |
| Complete edit in Kdenlive | [[06-kdenlive-fundamentals\|Kdenlive Fundamentals]] (Ch.06), [[07-your-first-edit\|Your First Edit]] (Ch.07), [[08-transitions-and-compositing\|Transitions]] (Ch.08), [[09-color-correction-and-grading\|Color]] (Ch.09), [[10-audio-production\|Audio]] (Ch.10), [[11-pacing-storytelling-retention\|Pacing]] (Ch.11), [[12-effects-titles-graphics\|Effects & Titles]] (Ch.12) |
| Platform-appropriate exports | [[13-formats-codecs-export\|Export]] (Ch.13), [[14-quality-control\|Quality Control]] (Ch.14), [[15-publishing-to-youtube\|Publishing]] (Ch.15) |

## Chapter-to-Skill Map

This table shows what each chapter teaches and which ForgeFrame skill (if any) automates the core workflow. New to ForgeFrame? Start with [[00-getting-started-with-forgeframe|Ch.00]].

| Ch. | Title | Core Concept | ForgeFrame Skill |
|-----|-------|--------------|-----------------|
| 00 | Getting Started with ForgeFrame | Setup, vault, first project | `/ff-init`, `/ff-new-project` |
| 01 | The Video Production Pipeline | End-to-end workflow overview | (all skills, see Ch.01) |
| 02 | Audience & Learning Goals | Who this guide is for | — |
| 03 | From Idea to Outline | Brainstorming, teaching beats, structure | `/ff-video-idea-to-outline`, `/ff-obsidian-video-note` |
| 04 | Scripts, Shot Plans & Capture Prep | Script writing, shot lists, B-roll | `/ff-tutorial-script`, `/ff-shot-plan`, `/ff-broll-whisperer`, `/ff-capture-prep` |
| 05 | Filming Your Tutorial | Camera, audio, lighting, VFR | `/ff-capture-prep` |
| 06 | Kdenlive Fundamentals | Project setup, bins, timeline, proxies | — |
| 07 | Your First Edit | Selects, rough cut, ingest workflow | `/ff-auto-editor`, `/ff-rough-cut-review` |
| 08 | Transitions & Compositing | Cut types, dissolves, PiP | — |
| 09 | Color Correction & Grading | Exposure, white balance, LUTs | MCP: `color_analyze`, `color_apply_lut` |
| 10 | Audio Production | Noise, EQ, compression, loudness | `/ff-audio-cleanup` |
| 11 | Pacing, Storytelling & Retention | Energy curves, hooks, B-roll timing | `/ff-pacing-meter`, `/ff-voiceover-fixer` |
| 12 | Effects, Titles & Graphics | Effects stack, overlays, titles | `/ff-pattern-brain` |
| 13 | Formats, Codecs & Export | Codecs, render profiles, containers | MCP: `render_final` |
| 14 | Quality Control | Pre-publish automated checks | MCP: `qc_check`, `media_check_vfr` |
| 15 | Publishing to YouTube | Title, description, tags, chapters | `/ff-publish` |
| 16 | Social Media & Repurposing | Shorts, Reels, aspect ratios | `/ff-social-clips` |
| 17 | Troubleshooting | Common failures and fixes | — |
| 18 | Hardware & Software | Gear guide, tool setup | — |
| 19 | ForgeFrame Skill Reference | All 17 skills cataloged | all skills |
| 20 | Resources & Community | Links, communities, further reading | `/ff-youtube-analytics` |
