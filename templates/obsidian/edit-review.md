---
title: Edit Review — {{ title | default("Untitled") }}
status: review
tags: [edit-review]
created: {{ created | default("") }}
project_ref: {{ project_ref | default("") }}
reviewer: {{ reviewer | default("") }}
---

# Edit Review: {{ title | default("Untitled") }}

## Overall Impression

<!-- wvb:section:overall -->
General feedback on the current cut.
<!-- /wvb:section:overall -->

## Pacing Notes

<!-- wvb:section:pacing -->
Sections that feel too slow or too fast.
<!-- /wvb:section:pacing -->

## Repetition Flags

<!-- wvb:section:repetition -->
Content that appears redundant.
<!-- /wvb:section:repetition -->

## Insert Suggestions

<!-- wvb:section:inserts -->
B-roll or graphic overlays to add.
<!-- /wvb:section:inserts -->

## Chapter Breaks

<!-- wvb:section:chapters -->
Suggested chapter timestamps.
<!-- /wvb:section:chapters -->

## Sign-off

<!-- wvb:section:signoff -->
- [ ] Pacing addressed
- [ ] Repetitions cut
- [ ] Inserts added
- [ ] Ready for render
<!-- /wvb:section:signoff -->
