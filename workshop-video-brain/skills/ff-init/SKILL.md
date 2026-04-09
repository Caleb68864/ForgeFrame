---
name: ff-init
description: >
  Set up ForgeFrame for the first time. Creates Obsidian vault structure,
  media organization folders, and config files. Use when user says
  'set up forgeframe', 'initialize', 'first time setup', or
  'configure forgeframe'.
---

# Skill: ff-init

You initialize a fresh ForgeFrame environment. Your job is to detect whether
ForgeFrame is already set up, collect the required paths from the user if
needed, run the init, and explain the resulting folder structure clearly.

---

## When to invoke this skill

Trigger on any of these:
- "set up forgeframe"
- "initialize forgeframe"
- "first time setup"
- "configure forgeframe"
- "forgeframe init"
- "set up my vault"
- "create the vault structure"
- "get forgeframe ready"
- "I'm starting fresh with forgeframe"

---

## Your process

### Step 1 — Check if already initialized

Run `forgeframe_status` to see the current state:

```
forgeframe_status()
```

**If already initialized and all checks pass:**
Report what's already set up and ask if the user wants to re-initialize:

```
ForgeFrame is already initialized.

  Vault:          /home/user/Videos
  Projects root:  /home/user/Projects
  Media library:  /home/user/Projects/Media Library
  FFmpeg:         available
  Whisper:        available

Everything looks good. Would you like to re-run init to add any missing
folders, or is there something specific you'd like to change?
```

**If not initialized or checks fail:**
Proceed to Step 2.

### Step 2 — Collect paths (if not provided)

If the user hasn't specified paths, ask for:

1. **Vault path** — where the Obsidian vault should live
   - Suggest: `~/Videos` (sensible default for video producers)
   - Explain: "This is the Obsidian vault where all your video notes, ideas, scripts, and B-roll entries will live."

2. **Projects root** — where project workspaces will be created
   - Suggest: `~/Projects`
   - Explain: "Each video project gets a workspace folder here with organized subfolders for media, transcripts, and project files."

3. **Media library** (optional) — a separate folder for the global media library
   - Default: inside projects root as `Media Library/`
   - Only ask if user seems to want a custom location

If the user has already provided paths (e.g., "init forgeframe at ~/Videos and ~/Projects"),
skip directly to Step 3.

### Step 3 — Run init

Call `forgeframe_init` with the collected paths:

```
forgeframe_init(
    vault_path="<vault_path>",
    projects_root="<projects_root>",
    media_library="<optional_media_library>"
)
```

### Step 4 — Report results

Present a clean summary of what was created:

```
ForgeFrame initialized!

Vault created at ~/Videos/
  + Ideas/
  + In Progress/
  + Published/
  + Archived/
  + B-Roll Library/  (Shots, Sound Effects, Music)
  + Templates/YouTube/  (Video Idea, In Progress, Published, B-Roll Entry)
  + Research/  (MYOG, Gear, Techniques)
  14 folders created

Media library created at ~/Projects/Media Library/
  + video/  (raw, proxies, processed, exports)
  + audio/  (raw, processed, voiceover, music, sfx)
  + images/ (stills, thumbnails, overlays, logos)
  + graphics/ (title-cards, lower-thirds, transitions)
  + documents/ (scripts, notes, releases)
  19 folders created

Config written:
  + ~/.forgeframe/config.json
  + .env (in ForgeFrame repo root)
```

### Step 5 — Explain what to do next

After reporting the result, give the user clear next steps:

```
Next steps:

1. Open ~/Videos/ in Obsidian as a new vault.
2. Enable Templates in Obsidian settings → Core plugins → Templates,
   and set the template folder to "Templates/YouTube".
3. Use the "Video Idea" template to capture your first idea.
4. When you're ready to start a project, use `workspace create` to
   set up a project workspace linked to your vault.

To check your setup at any time, run: forgeframe_status()
```

---

## Path handling

- Accept both absolute paths (`/home/user/Videos`) and `~`-prefixed paths (`~/Videos`).
- The init system expands `~` automatically.
- If the user gives a relative path, warn them and suggest an absolute path.
- If a path already exists, that's fine — init is safe to re-run (idempotent).

---

## Error handling

If `forgeframe_init` returns an error:

- Permission denied → tell the user to check folder permissions
- Path doesn't exist (for an intermediate directory) → let them know init
  creates the full path automatically, so this shouldn't happen; if it does,
  suggest running with explicit absolute paths

---

## Already-initialized edge cases

If `forgeframe_status` shows `initialized: true` but some checks fail:

```
ForgeFrame is configured but has some issues:

  Vault path does not exist: /old/path/to/vault
  FFmpeg not found at 'ffmpeg'

Would you like to re-run init with a new vault path, or fix these manually?
```

Offer to re-run init with corrected paths, or explain how to fix manually
(e.g., install FFmpeg, update the path in `~/.forgeframe/config.json`).
