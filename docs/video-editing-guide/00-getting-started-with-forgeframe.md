# Chapter 00: Getting Started with ForgeFrame

**Part 0 — Introduction**

---

## What Is ForgeFrame?

ForgeFrame is a local-first video production assistant that lives inside Claude Code. It connects your video editing workflow — from raw idea to published tutorial — to a set of AI-powered skills that run directly on your machine. Nothing is uploaded to a cloud service. Your footage, scripts, and project files stay on your computer.

The way it works is simple: you install ForgeFrame as a Claude Code plugin, and a collection of skills becomes available in your terminal. Each skill handles one part of the production process. Some skills help you plan your video before you film anything. Others process your footage, clean up audio, or check your export before you publish. You use the skills you need, skip the ones you don't, and you can do every step manually if you prefer. ForgeFrame is an assistant, not a replacement for your own judgment.

This chapter gets you set up. By the end, you will have ForgeFrame installed, a vault created, and your first project workspace ready to go. You do not need any prior experience with video production to follow these steps — that knowledge comes in later chapters.

---

## Prerequisites

Before you install ForgeFrame, you need four things on your machine. Check each one before continuing.

### Python 3.12 or later

ForgeFrame's skills run on Python. Version 3.12 or newer is required.

Check your Python version:

```bash
python3 --version
```

You should see something like `Python 3.12.2` or higher. If you see `3.11` or lower, or if Python is not found, install the latest version from [python.org](https://python.org) or through your system's package manager.

### Kdenlive

Kdenlive is the video editor ForgeFrame is built around. It is free, open source, and available on Linux, macOS, and Windows.

Check if Kdenlive is installed:

```bash
kdenlive --version
```

If Kdenlive is not installed, download it from [kdenlive.org](https://kdenlive.org). Any recent version works.

### FFmpeg

FFmpeg is the command-line tool that does the heavy lifting behind many ForgeFrame skills — transcoding footage, checking audio levels, detecting variable frame rates, and more.

Check if FFmpeg is installed:

```bash
ffmpeg -version
```

You should see version information. If FFmpeg is not found, install it:

- **Linux (apt):** `sudo apt install ffmpeg`
- **Linux (pacman):** `sudo pacman -S ffmpeg`
- **macOS (Homebrew):** `brew install ffmpeg`
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org) and add it to your PATH.

### Claude Code

ForgeFrame is a Claude Code plugin. Claude Code is Anthropic's official CLI tool for working with Claude AI in your terminal. If you are reading this guide inside Claude Code, you already have it. If not, install it:

```bash
npm install -g @anthropic-ai/claude-code
```

Verify the installation:

```bash
claude --version
```

---

## Installing the ForgeFrame Plugin

With the prerequisites in place, you are ready to install ForgeFrame.

### Step 1: Clone the Repository

Pick a folder on your computer where you want to store ForgeFrame. Your home directory works fine.

```bash
git clone https://github.com/Caleb68864/ForgeFrame.git ~/ForgeFrame
cd ~/ForgeFrame
```

### Step 2: Install Python Dependencies

ForgeFrame uses `uv` for dependency management. If you do not have `uv`:

```bash
pip install uv
```

Then install ForgeFrame's dependencies:

```bash
uv sync
```

This downloads everything the skills need to run. It only takes a minute.

### Step 3: Register the Plugin with Claude Code

Claude Code loads plugins from a marketplace file. Register ForgeFrame by pointing Claude Code to it:

```bash
claude plugin install .claude-plugin/marketplace.json
```

If that command is not available in your version of Claude Code, you can add the plugin path manually in your Claude Code settings. See the Claude Code documentation for your version.

### Step 4: Verify the Plugin Loaded

Start a new Claude Code session and type `/ff`. You should see a list of ForgeFrame skills in the autocomplete menu. If nothing appears, check the troubleshooting section at the end of this chapter.

---

## Running `ff-init`

`ff-init` is the setup skill. It creates your vault — the master folder where ForgeFrame stores everything: your video notes, project workspaces, transcripts, and reports.

Run it once when you first install ForgeFrame:

> **ForgeFrame:** `/ff-init` creates the vault folder structure and writes a configuration file that all other skills read. Run it once at setup, not before every project. You can also create the vault folders manually if you prefer (see structure below).

In a Claude Code session, type:

```
/ff-init
```

You will be prompted for two things:

1. **Vault path:** Where to create your vault. The default is `~/ForgeFrame-Vault`. You can choose any folder — an external drive, a folder inside your Documents, wherever makes sense for your setup.

2. **Your name or channel name:** Used to label reports and project files.

Expected output after `ff-init` completes:

```
ForgeFrame vault created at: /home/yourname/ForgeFrame-Vault

  media/
    raw/          ← your original footage goes here
    processed/    ← transcoded files land here
  projects/
    source/       ← Kdenlive project files
    workspaces/   ← per-video working folders
  renders/        ← exported video files
  transcripts/    ← auto-generated transcripts
  reports/        ← QC and analysis reports
  notes/          ← Obsidian notes and video outlines

Configuration saved to: /home/yourname/ForgeFrame-Vault/.forgeframe/config.json

Ready. Run /ff-new-project to create your first project.
```

If your output looks like this, you are set up correctly.

---

## Understanding Your Vault

The vault is a single folder that holds everything related to your video production work. Here is what each subfolder is for:

### `media/raw/`

This is where your original, unedited footage lives. ForgeFrame never modifies files in this folder. When you film something, copy the files from your camera here. Treat this folder as read-only after you copy files in — it is your safety net.

### `media/processed/`

When ForgeFrame transcodes footage (for example, converting variable frame rate files to constant frame rate), the converted files land here. Your original files in `raw/` are untouched.

### `projects/source/`

Your Kdenlive project files (`.kdenlive`) are stored here. ForgeFrame creates snapshots before modifying any project file, so you can always roll back.

### `projects/workspaces/`

Each video you work on gets its own workspace folder here. A workspace holds the working notes, shot plan, script draft, and any intermediate files for that specific video. When you run `/ff-new-project`, it creates a workspace folder.

### `renders/`

Exported video files go here. When you finish editing and export from Kdenlive, save the render into this folder so ForgeFrame can find it for QC checks and publishing.

### `transcripts/`

When ForgeFrame generates a transcript of your video or voiceover, the text files land here. Transcripts are used by the pacing and publishing skills.

### `reports/`

Quality control reports, loudness analysis, and pacing feedback are saved here. After running a QC check on your video, open the report in this folder to see what needs fixing.

### `notes/`

Video planning notes and outlines live here. If you use Obsidian, you can point Obsidian at this folder and get a full note-taking interface on top of your video research and outlines.

---

## Creating Your First Project

With the vault ready, create a workspace for your first video.

> **ForgeFrame:** `/ff-new-project` creates a workspace folder, a planning note, and a starter outline structure for a new video. You can also create these manually — just make a folder under `projects/workspaces/your-video-name/`.

In Claude Code, type:

```
/ff-new-project
```

You will be asked a few questions:

**Project name:** A short, file-safe name for the video. Use hyphens instead of spaces. For example: `intro-to-kdenlive` or `how-to-record-screen`.

**Video idea (optional):** A sentence or two describing what the video is about. You can leave this blank and fill it in later.

Expected output:

```
Creating workspace: intro-to-kdenlive

  projects/workspaces/intro-to-kdenlive/
    outline.md        ← your video structure
    script.md         ← script draft (starts empty)
    shot-plan.md      ← shot list (starts empty)
    notes.md          ← free-form research notes

Project note created in: notes/intro-to-kdenlive.md

Workspace ready. Open outline.md to start planning.
```

Your workspace is now set up. The `outline.md` file has a starter structure — hook, setup, main steps, and close. You do not need to fill it in right now. The next chapters will walk you through each part of the production process and show you how to use ForgeFrame skills at each step.

---

## What's Next

You have ForgeFrame installed, a vault set up, and your first project workspace created. The next chapter, **Chapter 01: The Video Production Pipeline**, gives you the big picture of how a tutorial video moves from raw idea to published. It maps each stage of production to the ForgeFrame skills that can help — so you know which skills to use and when.

**[→ Continue to Chapter 01: The Video Production Pipeline](01-pipeline-overview.md)**

---

## Troubleshooting

> **Common Setup Issues**
>
> **FFmpeg not found**
>
> If a ForgeFrame skill fails with "FFmpeg not found" or "ffmpeg: command not found":
>
> - Confirm FFmpeg is installed: run `ffmpeg -version` in a new terminal window.
> - If it is installed but not found by ForgeFrame, the issue is likely that FFmpeg is not on your system PATH.
> - **Linux/macOS:** Add the folder containing the `ffmpeg` binary to your `~/.bashrc` or `~/.zshrc`: `export PATH="/path/to/ffmpeg/bin:$PATH"`, then restart your terminal.
> - **Windows:** Open System Properties → Environment Variables → edit the Path variable and add the folder containing `ffmpeg.exe`.
> - After fixing PATH, restart Claude Code and try again.
>
> ---
>
> **Vault path not found or wrong location**
>
> If ForgeFrame says it cannot find your vault, or if skills are creating files in the wrong place:
>
> - Check the config file at `~/.forgeframe/config.json` (or `.forgeframe/config.json` inside your vault) and verify the `vault_path` value points to your vault folder.
> - You can re-run `/ff-init` and provide the correct path. It will not delete any existing files — it only updates the configuration.
> - If you moved your vault folder after running `ff-init`, update the path in the config file manually.
>
> ---
>
> **ForgeFrame skills not showing up in `/` autocomplete**
>
> If you type `/ff` in Claude Code and no skills appear:
>
> - Confirm the plugin was registered: run `claude plugin list` and look for ForgeFrame.
> - If it is not listed, re-run the install step: `claude plugin install .claude-plugin/marketplace.json` from the ForgeFrame directory.
> - Try starting a fresh Claude Code session (close and reopen the terminal).
> - Check that you are running Claude Code 1.x or later — older versions may not support the plugin system.
>
> ---
>
> **Python version error**
>
> If you see an error mentioning Python version when running `uv sync`:
>
> - Run `python3 --version` to confirm your current version.
> - If it is below 3.12, install a newer version. On Linux, `pyenv` is an easy way to manage multiple Python versions without affecting your system install.
>
> ---
>
> **`uv` command not found**
>
> Install it with: `pip install uv` or `pip3 install uv`. If pip itself is not found, install Python first (it includes pip).
