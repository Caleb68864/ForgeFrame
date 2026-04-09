---
title: "Kdenlive Keyboard Shortcuts"
part: "Appendices"
tags:
  - kdenlive
  - shortcuts
  - keyboard
  - reference
---

# Appendix B: Kdenlive Keyboard Shortcuts

Essential keyboard shortcuts for efficient editing in Kdenlive. All shortcuts assume default keybindings — you can customize any of these under *Settings > Configure Shortcuts*.

---

## Playback and Navigation

| Shortcut | Action |
|----------|--------|
| `Space` | Play / pause |
| `J` | Play backward (press again to increase speed: 2x, 4x, 8x) |
| `K` | Stop / pause |
| `L` | Play forward (press again to increase speed: 2x, 4x, 8x) |
| `←` | Step one frame backward |
| `→` | Step one frame forward |
| `Shift + ←` | Jump backward by large increment (configurable, default 1 second) |
| `Shift + →` | Jump forward by large increment |
| `Home` | Go to start of timeline |
| `End` | Go to end of timeline |
| `Page Up` | Jump to previous clip boundary |
| `Page Down` | Jump to next clip boundary |
| `Up` | Go to previous marker |
| `Down` | Go to next marker |

---

## Editing — Cut and Trim

| Shortcut | Action |
|----------|--------|
| `S` | Razor / blade cut at playhead position |
| `Shift + R` | Razor all tracks at playhead position |
| `Delete` | Ripple delete selected clip (shifts subsequent clips left) |
| `Backspace` | Remove selected clip, leave gap |
| `X` | Cut selected clip at playhead (splits into two) |
| `G` | Group selected clips |
| `Shift + G` | Ungroup selected clips |
| `Ctrl + Z` | Undo |
| `Ctrl + Shift + Z` | Redo |

---

## Selection and Clip Operations

| Shortcut | Action |
|----------|--------|
| `F1` | Select tool (arrow) |
| `F2` | Razor / blade tool |
| `F3` | Spacer tool (moves all clips after cursor) |
| `F5` | Slip tool (shifts in/out point without moving clip) |
| `Ctrl + A` | Select all clips on timeline |
| `Ctrl + Click` | Add clip to selection |
| `Shift + Click` | Select range of clips |
| `Alt + Drag` | Move clip by overwrite (replaces content at destination) |
| `Ctrl + Drag` | Copy clip (insert a duplicate) |

---

## Timeline Zoom

| Shortcut | Action |
|----------|--------|
| `+` | Zoom in (increase timeline resolution) |
| `-` | Zoom out (decrease timeline resolution) |
| `Ctrl + Scroll wheel` | Zoom in/out under cursor |
| `Ctrl + Shift + H` | Fit entire project in timeline view |
| `Ctrl + -` | Zoom to selection |

---

## In/Out Points and Three-Point Editing

| Shortcut | Action |
|----------|--------|
| `I` | Set in point (in clip monitor or timeline) |
| `O` | Set out point |
| `Shift + I` | Clear in point |
| `Shift + O` | Clear out point |
| `V` | Insert clip at in point (source monitor → timeline) |
| `B` | Overwrite clip at in point |

---

## Markers

| Shortcut | Action |
|----------|--------|
| `M` | Add marker at playhead position |
| `Shift + M` | Add marker with dialog (lets you name it and set color) |
| `Ctrl + M` | Add guide |
| `Alt + M` | Remove marker at playhead |
| `Up` | Jump to previous marker |
| `Down` | Jump to next marker |

---

## Tracks

| Shortcut | Action |
|----------|--------|
| `Ctrl + Y` | Add video track |
| `Ctrl + Shift + Y` | Add audio track |
| `M` (on track header) | Mute track |
| `L` (on track header) | Lock track |
| `V` (on track header) | Toggle track visibility |

---

## Render and Export

| Shortcut | Action |
|----------|--------|
| `Ctrl + Return` | Open Render dialog |
| `Ctrl + S` | Save project |
| `Ctrl + Shift + S` | Save project as (new filename) |
| `Ctrl + Z` | Undo (also works in render settings) |

---

## Project and File Management

| Shortcut | Action |
|----------|--------|
| `Ctrl + N` | New project |
| `Ctrl + O` | Open project |
| `Ctrl + S` | Save project |
| `Ctrl + W` | Close project |
| `Ctrl + I` | Import clip(s) to project bin |
| `Del` (in bin) | Remove clip from bin (does not delete the file) |

---

## Effect Stack

| Shortcut | Action |
|----------|--------|
| `Ctrl + Click` effect | Enable / disable effect without removing it |
| `Drag` effect handle | Reorder effects in the stack |
| `E` | Open / focus the effect stack for selected clip |

---

## Monitor Controls

| Shortcut | Action |
|----------|--------|
| `P` | Toggle preview scopes (waveform, vectorscope) |
| `F` | Toggle fullscreen on focused monitor |
| `Tab` | Switch focus between clip monitor and program monitor |

---

## Tips for Efficient Editing

**Use J-K-L constantly.** The three-key shuttle system is the fastest way to scrub through footage. Press J twice for 2x reverse, L three times for 8x forward. K stops and holds the frame.

**Learn `S` before anything else.** The razor cut is the most frequently used edit operation. Making it muscle memory is the single highest-value shortcut to learn first.

**Set in/out in the clip monitor, not the timeline.** Mark `I` and `O` in the source clip before placing it. This gives you a clean three-point edit workflow and avoids having to trim after placement.

**Use markers for chapter breaks.** Press `Shift + M` at each section transition as you edit. These named markers become your YouTube chapters when you export the chapter list.

**`Ctrl + Shift + H` is your panic button.** If you get lost in the timeline zoom, this resets the view to show the entire project.

---

## Configuring Custom Shortcuts

*Settings > Configure Shortcuts* opens the keybinding editor. You can:
- Search for any action by name
- Assign primary and secondary shortcuts
- Export and import keybinding profiles
- Reset individual shortcuts or all shortcuts to defaults

If you use a shuttle controller or stream deck, Kdenlive's custom shortcuts map directly to external controller buttons.
