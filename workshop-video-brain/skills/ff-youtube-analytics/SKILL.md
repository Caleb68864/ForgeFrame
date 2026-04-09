---
name: ff-youtube-analytics
description: >
  Pull YouTube channel stats and video data for analytics. Generates performance
  reports, identifies top content, and saves insights to Obsidian vault. Use when
  user says 'youtube stats', 'channel analytics', 'video performance', or 'pull
  my youtube data'.
---

# Skill: ff-youtube-analytics

You pull YouTube channel data using yt-dlp, compute performance analytics, and
surface actionable content strategy insights. You can save everything to the
Obsidian vault as structured notes.

---

## When to invoke this skill

Trigger on any of these phrases:
- "youtube stats"
- "channel analytics"
- "video performance"
- "pull my youtube data"
- "how are my videos doing"
- "channel overview"
- "top videos"
- "youtube report"
- "analyze my channel"
- "save channel data"

---

## Your process

### Step 1 — Ask for channel URL

If the user hasn't provided a channel URL, ask:

> "What's your YouTube channel URL? (e.g., https://youtube.com/@yourchannel)"

Also confirm how many videos to fetch (default 50):

> "How many recent videos should I analyse? (default: 50)"

---

### Step 2 — Fetch channel data

Use the MCP tool or Python helper:

```python
from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import analyze_channel

stats = analyze_channel("https://youtube.com/@yourchannel", max_videos=50)
```

Or via MCP:

```
youtube_analyze(channel_url="https://youtube.com/@yourchannel", max_videos=50)
```

---

### Step 3 — Present channel overview

Show the creator a summary:

**Channel: {channel_name}**
- Videos analysed: {total_videos}
- Total views: {total_views:,}
- Average views per video: {avg_views:,.0f}
- Average likes per video: {avg_likes:,.0f}
- Average duration: {avg_duration_mmss}

**Top 5 Videos:**
| Title | Views | Engagement |
|-------|-------|------------|
| ...   | ...   | ...%       |

**Most Viewed:** {most_viewed}
**Most Liked:** {most_liked}

---

### Step 4 — Offer to save to vault

Ask:

> "Would you like me to save this to your Obsidian vault? I'll create:
> - `Research/Analytics/Channel Overview.md` — channel summary with tables
> - `Research/Analytics/Videos/` — one note per video with stats and insights
> - `Research/Analytics/report.md` — full analytics report"

If yes, use:

```python
from workshop_video_brain.edit_mcp.pipelines.youtube_analytics import save_channel_to_vault
from pathlib import Path

created = save_channel_to_vault(Path("<vault_path>"), stats)
```

Or via MCP:

```
youtube_save_to_vault(channel_url="https://youtube.com/@yourchannel", max_videos=50)
```

---

### Step 5 — Content strategy insights

After presenting the data, offer strategic insights:

**Engagement patterns:**
- Which video topics get the highest engagement rate?
- Are shorter or longer videos performing better?
- What tags appear on top-performing videos?

**Upload cadence:**
- How often has the channel been publishing?
- Are there gaps that correlate with view drops?

**Growth opportunities:**
- Topics that overperform relative to average → do more of these
- Videos with high views but low likes → revisit CTAs or content quality
- Common tags on top performers → double down on these keywords

Offer specific recommendations based on the actual data retrieved.

---

## Output files saved to vault

| Path | Contents |
|------|----------|
| `Research/Analytics/Channel Overview.md` | Channel summary with top videos tables |
| `Research/Analytics/Videos/<slug>.md` | One note per video with full stats |
| `Research/Analytics/report.md` | Full analytics report with all sections |

---

## Handoff

After completing analytics:
- Summarise: "Analysed {N} videos. Top performer: '{title}' with {views:,} views."
- Offer to run again with a different video count or time window.
- Suggest: "Want me to analyse a specific video's performance against your channel average?"
