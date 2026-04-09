---
title: "From Idea to Outline"
part: "Part II — Preproduction"
tags:
  - preproduction
  - planning
  - outline
  - idea-development
---

# Chapter 03: From Idea to Outline

**Part II — Preproduction**

Preproduction is the single highest-leverage phase in your entire workflow. Every minute spent planning here saves five or more in the edit bay and prevents costly reshoots. Skipping it is the number-one reason beginners end up with hours of footage and no idea how to assemble it.

## Why Preproduction Matters

- **Saves editing time.** When you sit down to cut, you already know which clips you need and roughly where they go. No more scrubbing through forty minutes of screen capture hunting for the one good take.
- **Prevents reshoots.** A shot list catches gaps before you strike the set or close the screen recorder. Discovering you forgot a crucial close-up after you've torn down the lights costs hours; discovering it on a checklist costs seconds.
- **Creates a shared reference.** Even if you're a solo creator, your future editing self is a collaborator. A written plan is the handoff document between "you the shooter" and "you the editor."

This chapter takes you from raw idea to a structured outline. Chapter 04 picks up from there: scripts, shot lists, and camera prep.

---

## Writing a One-Paragraph Objective

Before anything else, write a single paragraph that answers three questions:

1. **Who** is this video for?
2. **What** will the viewer be able to do or understand after watching?
3. **How long** should the finished piece be?

Keep it to three or four sentences. This paragraph becomes your north star — every decision about what to shoot, what to cut, and how to grade flows from it.

> **Example:** "This video is for hobbyist woodworkers who have never used a track saw. After watching, they should understand how to set up the guide rail, make a straight rip cut, and safely store the saw. Target length is 60-90 seconds."

This paragraph also acts as a filter. When you're deep in the edit and wondering whether a particular shot or tangent belongs in the video, read your objective. If it doesn't serve the who and what, it's probably a cut.

---

## Brain Dumping: Getting It All Out First

Before you structure anything, give yourself permission to make a mess.

A brain dump is a five-minute, unfiltered capture of every thought you have about the video. No editing, no sorting — just stream of consciousness onto the page. Write down:

- Every step you might cover
- Every warning or gotcha you know about
- Questions the viewer might ask
- Tools, materials, or specs that are relevant
- Visual moments that would be powerful to show

You can do this as a bullet list, a paragraph, or even a voice memo you transcribe. The goal is to empty your head so you stop holding information in memory and start working with it on paper.

Once you've brain-dumped for five minutes, stop. Now look at what you have. You'll find that most of what you need is already there — it just needs to be shaped.

---

## Teaching Beats: The Backbone of a Tutorial

A **teaching beat** is a single, coherent unit of instruction. It maps to one thing the viewer needs to understand or do. Think of it like a paragraph in an essay — each beat makes one point, then moves on.

For a 60-second tutorial, you might have 4-6 beats. For a 10-minute deep-dive, you might have 8-12.

A good teaching beat has:
- A clear subject (what are we teaching?)
- A concrete action or outcome (what does the viewer do or learn?)
- A known failure mode (what goes wrong here, and how to avoid it?)

### Structuring Your Beats

After your brain dump, group related ideas into beats. A useful structure for most tutorial content:

1. **Hook** — Show the result, state who this is for, create curiosity (0:00-0:30)
2. **Setup / What We're Making** — Explain the scope, materials, what the viewer needs (0:30-1:30)
3. **Core Steps** — The teaching beats themselves, in logical order
4. **Gotchas / Common Mistakes** — What goes wrong and how to recover
5. **Result + Call to Action** — Show the finished outcome, what to try next

Not every video needs all five sections. A very short tutorial might compress setup and hook into a single opening. But having this framework in your head helps you recognize when your outline is missing something.

### Timing Each Beat

Time your beats mentally before you commit to a shot list. Speak each beat aloud and count the seconds. If your target is 5 minutes and your outline has 15 beats, each beat only gets 20 seconds — that's tight. You'll either need to cut beats or expand your target length.

This simple timing check prevents the most common tutorial-structure problem: an outline that looks reasonable on paper but produces a rushed, confusing video.

---

## Moving from Brain Dump to Outline

A structured outline is a brain dump with a spine. Here's how to get there in three passes:

**Pass 1 — Group:** Take your brain dump items and group related ones together. Don't name the groups yet — just cluster them.

**Pass 2 — Order:** Arrange the clusters in the sequence a first-time viewer needs to encounter them. What must they know before they can understand step 3? That goes earlier.

**Pass 3 — Name and scope:** Give each cluster a one-sentence title. Add a note about what it must accomplish and approximately how long it should run. That's your outline.

---

## Example: Outline in Practice

Here's a brain dump and the resulting outline for a short woodworking tutorial:

**Brain dump (raw):**
```
track saw setup - guide rail alignment - clamping the rail - not enough clamps =
moving rail - splinter guard - the blue tape trick - score first - two passes for
thick stock - storing the saw - blade guard - cord management - who this is for:
never used one - show the finished rip cut - what track saws are better than for
circular saws - straight lines - safety: unplug when adjusting - kerf width note
```

**Resulting outline:**
```
1. Hook (0:00-0:15) — Show a perfect rip cut, state who this is for
2. What Track Saws Do Better (0:15-0:45) — Straight cuts without a fence jig
3. Setting Up the Guide Rail (0:45-1:30)
   - Alignment marks, clamp placement
   - Gotcha: not enough clamps = moving rail
4. Making the Cut (1:30-2:15)
   - Score pass, through pass for thick stock
   - Blue tape trick for tearout
5. Safety and Storage (2:15-2:45)
   - Blade guard, unplug when adjusting
   - Cord management
6. Result + Next Steps (2:45-3:00)
```

The brain dump had 22 fragments. The outline has 6 beats. Everything from the dump is in there — it's just organized.

---

## ForgeFrame: ff-video-idea-to-outline

> **ForgeFrame:** Use `/ff-video-idea-to-outline` to turn a rough idea into a
> structured outline automatically. Describe your project in a sentence or two
> and the skill generates a viewer promise, teaching beats, pain points, chapter
> structure, and a suggested intro hook.
>
> **Example input:** "plan a video about making a walnut cutting board"
>
> **Example output (abbreviated):**
> ```
> Viewer Promise: By the end of this video you will be able to glue up, flatten,
> and finish a live-edge walnut cutting board from rough lumber.
>
> Teaching Beats:
> 1. Wood selection — choosing slabs, reading grain, avoiding defects
> 2. Rough milling — jointing, planing, ripping parallel edges
> 3. Glue-up — clamping strategy, checking for twist
> 4. Flattening — router sled vs. hand plane tradeoffs
> 5. Sanding — 80 through 220, raising the grain
> 6. Food-safe finish — mineral oil, butcher block conditioner
> 7. Final reveal — glamour shots, wipe-down
>
> Pain Points:
> - Skipping grain direction on adjacent boards causes tearout during surfacing.
>   Always alternate grain orientation.
> ```
>
> You can also do this manually: write your objective paragraph, brain-dump for
> five minutes, then group and order the results as described above. The skill
> automates the structure — the underlying thinking is the same either way.

---

## Saving Your Outline to the Vault

Once you have an outline, save it. Ideas are fragile. An outline you write today and revisit in three weeks should still make sense — and it will, if it's in a note with the project context attached.

> **ForgeFrame:** Use `/ff-obsidian-video-note` to create a project note in your
> Obsidian vault. The note stores your outline, script, shot plan, and any manual
> notes you add — all in one place, preserved for the full production lifecycle.
>
> The note uses section boundaries (`<!-- wvb:section:outline -->`) so ForgeFrame
> can update automated content without ever touching your manual notes. Run the
> skill after any outline, script, or shot plan to keep the vault in sync.
>
> You can also do this manually: create a markdown file in your vault with
> frontmatter (title, status, date) and paste your outline there. The important
> thing is that it exists somewhere you'll find it at 11pm when you're editing.

---

## Before You Move On

By the end of this chapter, you should have:

- [ ] A one-paragraph objective (who, what outcome, target length)
- [ ] A brain dump with every thought about the video emptied onto the page
- [ ] A structured outline with named beats and rough timing
- [ ] The outline saved somewhere you can find it

With those four things in hand, you're ready for Chapter 04: writing the script, building the shot list, and prepping for capture.

---

*Next: [Chapter 04 — Scripts, Shot Plans & Capture Prep](04-scripts-shot-plans-capture-prep.md)*
*Back: [Chapter 02 — Audience, Learning Goals & Scope](02-audience-and-learning-goals.md)*
