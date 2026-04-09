---
name: ff-pattern-brain
description: >
  Extract MYOG (Make Your Own Gear) build data from a workshop transcript.
  Produces a materials list, measurements, numbered build steps, and
  tips/warnings. Generates overlay text for video and a printable build notes
  document. Use when the user says "build notes", "pattern", "materials list",
  "measurements", "printable", or "overlay text".
---

# Skill: ff-pattern-brain

You extract structured build data from a MYOG workshop transcript and produce
practical outputs: materials tables, measurement lists, step-by-step build
instructions, and printable notes.

---

## When to invoke this skill

Trigger on any of these phrases:
- "build notes"
- "pattern"
- "materials list"
- "measurements"
- "printable"
- "overlay text"
- "extract build data"
- "what materials do I need"
- "what are the steps"
- "make the build notes"
- "create pattern notes"

---

## What you produce

### 1. Materials List
A table of all materials detected in the transcript, with quantities and notes.
If quantities are vague (e.g. "some thread"), mark the quantity as given in context.
If a material appears multiple times, keep the most informative occurrence.

### 2. Measurements
A list of all numerical measurements with units and the context sentence.
Group related measurements when it aids clarity (e.g. "cut to 3.5 × 6 inches").

### 3. Build Steps
Numbered, sequential steps derived from transition phrases ("first", "next",
"then", etc.). Each step should read as a clear action instruction.
If steps are sparse, supplement from the overall structure of the transcript.

### 4. Tips and Warnings
- **Tips**: Helpful techniques, shortcuts, or craft insights.
- **Warnings**: Safety notes, common mistakes, things to avoid.

---

## Refinement instructions

After the pipeline extracts raw data, review and refine:

1. **Materials**: Merge duplicates. Normalize names (e.g. "X-Pac" not "x-pac").
   Add obvious quantities if stated nearby in the transcript but not captured.

2. **Measurements**: Remove duplicates. Flag ambiguous units (just `"` or `'`).
   Add context if a measurement lacks a clear purpose.

3. **Steps**: Ensure steps are complete sentences and action-oriented.
   Fill gaps if the transcript implies a step that wasn't explicitly stated.
   Re-number if needed.

4. **Tips/Warnings**: Rewrite for clarity. Ensure warnings are clearly marked.
   Remove tips that are too vague or obvious to be useful.

---

## Output format

Always present:
1. A **Materials** section (table format).
2. A **Measurements** section (list format).
3. A **Build Steps** section (numbered list).
4. A **Tips & Warnings** section (blockquotes).

Then ask: "Would you like me to save this as build_notes.md, add it to your
Obsidian note, or generate overlay text for your video?"

---

## Key principle

The extracted data is a starting point. Your job is to make it *useful*:
accurate, complete, and formatted for someone following along at a workbench.
If something is clearly wrong or missing, say so and ask the user to clarify.
