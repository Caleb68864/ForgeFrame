---
title: "Publishing to YouTube"
tags:
  - youtube
  - publishing
  - seo
  - titles
  - descriptions
  - thumbnails
  - chapters
---

# Chapter 15: Publishing to YouTube

**Part 5 — Output**

You have edited, color corrected, mixed the audio, and exported a clean H.264 file. The video is done. What you do in the next thirty minutes -- writing the title, filling in the description, choosing tags -- determines whether anyone finds it.

YouTube is both a video platform and the second-largest search engine in the world. The mechanics of search and discovery are baked in. This chapter covers what you control: how to write metadata that helps the right viewers find your tutorial, how to set up chapters so viewers can navigate long content, and how to create a thumbnail that holds up at thumbnail size.

---

## Title Writing

The title is your single highest-leverage piece of metadata. It drives search rank, it appears in suggested video feeds, and it is the first thing a potential viewer reads. Most tutorial creators either under-invest (naming files "Video 1 - Final Final") or over-invest in wordplay that confuses the search algorithm.

There are four useful title formats for tutorial content. Each has a different job:

### Searchable Title

A searchable title matches how people actually type queries into YouTube. It prioritizes exact keyword phrases over cleverness.

**Format:** `[what they search for] in [tool/context]`

Examples:
- `How to Remove Background Noise in Kdenlive`
- `Kdenlive Color Correction Beginner Tutorial`
- `Green Screen Keying Kdenlive 2024`

The searchable format works well for evergreen how-to content. If someone types that query six months from now, you want to show up. Keep it under 70 characters so it does not get truncated in search results.

### Curiosity Title

A curiosity title is designed to stop someone mid-scroll in their subscription feed or suggested videos. It creates a gap -- a question the viewer needs answered.

**Format:** Statement that implies a surprising outcome or contrast

Examples:
- `I Rebuilt My Entire Editing Setup for $0 (Here's What Changed)`
- `Why Your Exports Look Worse Than the Preview`
- `The One Setting Most Kdenlive Tutorials Never Mention`

Curiosity titles trade raw search traffic for higher click-through rate on people who already follow you or see you in suggested. Do not use them as your only title -- they rank poorly for cold searches.

### How-To Title

The how-to format sits between searchable and curiosity. It explicitly addresses a goal the viewer has.

**Format:** `How to [specific outcome] [optional: without/even if/in X time]`

Examples:
- `How to Color Grade a Tutorial Video in Under 10 Minutes`
- `How to Fix Choppy Playback in Kdenlive (Even on Low-End Hardware)`
- `How to Add Lower Thirds Without Buying Anything`

The qualifier phrase (without, even if, in X time) does real work. It narrows the audience to people with a specific constraint, which increases relevance and therefore watch time.

### Short Punchy Title

Short titles are optimized for mobile, where thumbnails are small and titles are truncated aggressively. YouTube Shorts also benefits from this format.

**Format:** Under 40 characters, action-noun

Examples:
- `Fix Kdenlive Proxy Settings`
- `Better Color Grades in 5 Steps`
- `Stop Exporting Wrong`

Short titles work best on channels with established audiences who recognize the brand. For a new channel, they sacrifice discoverability.

### Which Format to Use

Most tutorials benefit from a searchable or how-to title. Use a curiosity title for a video aimed at your existing subscribers where you have an interesting angle. Use a short title for Shorts or clips.

Do not try to combine all four into one title. A 90-character title that tries to be searchable AND curious AND punchy reads as keyword stuffing and gets truncated in most views.

> **ForgeFrame:** Use `/ff-publish` to generate all four title variants at once from your transcript. The skill reads the transcript, identifies the primary topic and key techniques covered, and writes titles tuned for each format.
>
> ```
> publish_bundle(workspace_path="projects/my-kdenlive-tutorial")
> ```
>
> Output includes `reports/publish/title_options.txt` with searchable, curiosity, how-to, and short variants ready for review.
>
> **Manually:** Write out what problem this video solves in one sentence. Strip out everything that is not the core action and the tool. That sentence, trimmed to 70 characters, is your searchable title. Then rewrite it as a question to get your curiosity variant.

---

## Description SEO

The YouTube description is crawled by both YouTube search and Google. A well-written description increases your chances of ranking for related search terms and converts viewers who read descriptions into subscribers and clicks.

### Keywords Early

The YouTube algorithm weights the first two to three lines of your description heavily. Put your most important keyword phrase in the first sentence, naturally. Do not lead with your name or a generic greeting.

**Weak opening:**
```
Hey everyone! Welcome back to the channel. In this video I'll be showing you...
```

**Strong opening:**
```
Color grading a tutorial video in Kdenlive doesn't require plugins or presets.
In this step-by-step walkthrough, you'll learn how to build a consistent look
from scratch using only Kdenlive's built-in color tools.
```

The second version starts with the search phrase (`color grading`, `tutorial video`, `Kdenlive`), explains what the viewer gets, and does it in two sentences.

### What to Include

After the keyword-rich opening paragraph, the description should contain:

**Chapters** (see below -- paste these in directly)

**Tools and resources mentioned:**
```
Kdenlive (free): https://kdenlive.org
Color calibration target used: X-Rite ColorChecker Passport
```

**Timestamps for key moments** (if you have not set up chapters, manual timestamps still help):
```
0:00 - Intro
1:45 - Setting up the color workspace
4:20 - Adjusting white balance
8:15 - Building a contrast curve
```

**Call to action** -- one, not five:
```
If this helped, subscribing is the single best way to support the channel.
```

**Related videos** -- two to three internal links:
```
Export Settings for YouTube: [URL]
Audio Cleanup Workflow: [URL]
```

Keep the total description under 800 words. Anything beyond that is rarely read and the algorithm does not give it much weight.

### What Not to Do

Do not keyword-stuff with comma-separated lists of tangentially related terms. YouTube's algorithm has become good at identifying this and it damages trust with viewers who read it. One focused description with natural language performs better than a list of 50 keywords.

> **ForgeFrame:** `ff-publish` generates a full description in this structure automatically. The skill extracts tool mentions and URLs from the transcript, builds chapters from timeline markers, and writes the opening paragraph around the primary topic.
>
> Review `reports/publish/description.txt` and edit before pasting into YouTube Studio. The skill generates a starting point, not a finished product -- add any personal notes, links, or context it could not infer.
>
> **Manually:** Write the description in this order: (1) two-sentence keyword summary of what the viewer learns, (2) paste chapters, (3) list tools with links, (4) one call to action, (5) two related video links. That structure takes ten minutes and covers everything.

---

## Tags and Hashtags

Tags and hashtags serve different functions on YouTube.

**Tags** are metadata only YouTube sees -- they do not appear on the video page. They help YouTube understand context and group your video with related content. Their direct impact on search ranking has diminished in recent years, but they still matter for suggested video placement.

**Hashtags** appear on the video page and are clickable. Viewers can browse all videos with the same hashtag. They also appear in search results.

### Tag Strategy

Use 15 to 25 tags. More than 25 dilutes the signal. Build your tag list in layers:

**Broad tags** (2-3): The general topic. These connect you to a large category.
```
video editing
kdenlive tutorial
how to edit video
```

**Specific tags** (8-12): The exact topic of this video.
```
kdenlive color grading
kdenlive color correction
color grade tutorial
kdenlive scopes
video color correction beginner
```

**Long-tail tags** (5-8): Phrases that match how real people search with context.
```
how to color grade in kdenlive
kdenlive color grading 2024
free video color correction workflow
color grading without plugins
```

All tags should be lowercase. Do not repeat the same word more than two or three times across all tags combined.

### Hashtag Strategy

Use three to five hashtags in the description. YouTube displays the first three as clickable badges above the title on the video page. More than five is considered spammy by most viewers.

```
#kdenlive #videoediting #colorgrading
```

Choose hashtags that are used by a community of related creators, not hashtags so broad they have billions of videos. `#videoediting` is useful. `#video` is noise. `#kdenlivecolorgrading` may be too narrow to drive traffic if no one searches it.

> **ForgeFrame:** `ff-publish` generates tags and hashtags from the transcript automatically. Tags are split into broad, specific, and long-tail groups. Output is `reports/publish/tags.txt` and `reports/publish/hashtags.txt`.
>
> **Manually:** Write down the three most specific search phrases someone would use to find this exact video. Expand each into 3-4 variations (singular/plural, with/without "tutorial", with/without the tool name). That gives you 12-15 specific tags. Add 3 broad category tags and you are done.

---

## Chapter Markers

YouTube chapters break a long video into navigable sections with named timestamps. They appear as a progress bar that viewers can jump through, and each chapter is indexed separately in Google search results -- a long tutorial can show up as a carousel of chapters, each linking to a specific timestamp.

Chapters appear automatically when your description contains a list of timestamps starting with `0:00`. YouTube requires the list to have at least three entries and the first entry must be `0:00`.

### Format

```
0:00 Introduction
1:30 Setting up the workspace
4:15 Adjusting white balance
8:00 Building the contrast curve
12:45 Exporting with color intact
15:30 Final comparison
```

### Writing Chapter Titles

Each chapter title should describe what the viewer will see or learn in that section, not just label it. Compare:

**Weak chapters:**
```
0:00 Intro
1:30 Part 1
4:15 Part 2
```

**Strong chapters:**
```
0:00 What we're building today
1:30 Color workspace setup
4:15 White balance correction
```

Strong chapter titles help viewers skip to exactly what they need. This increases watch time because viewers who skim chapters to find what they want are more engaged when they reach it than viewers who abandon the video because they cannot find it.

### Deriving Chapters from Timeline Markers

If you used timeline markers during your edit (see Chapter 13 on export workflow), you can derive chapter timestamps directly from the edit rather than scrubbing through the exported video manually. Set your markers with short names at the start of each major section while you edit. When you export, the markers become your chapter list.

> **ForgeFrame:** `ff-publish` reads timeline markers from `{workspace}/markers/` and converts them directly to YouTube chapter format. If no markers exist, it falls back to segment-level analysis of the transcript to find natural section boundaries.
>
> Review `reports/publish/chapters.txt` against the exported video before pasting. Transcript-derived timestamps can be off by a few seconds depending on how the project was synchronized. Verify the first and last chapter timestamps manually.
>
> **Manually:** Export your video, then scrub through it at the start of each major section and write down the timestamp. YouTube accepts timestamps in both `MM:SS` and `H:MM:SS` format. For videos under an hour, `MM:SS` is cleaner.

---

## Thumbnail Design

YouTube says thumbnails are the single most important factor in click-through rate. A video with a great thumbnail and mediocre title outperforms a video with a great title and bad thumbnail. Thumbnails are your billboard -- they need to work at the size of a postage stamp.

### Technical Specifications

- **Resolution:** 1280 × 720 pixels (16:9)
- **Format:** JPG, PNG, or GIF (static JPG recommended for smallest file size)
- **File size limit:** 2 MB
- **Minimum resolution:** 640 × 360, but never shoot for minimum

### What Makes a Thumbnail Work

**High contrast.** Thumbnails compete with dozens of other thumbnails in a search results page. Low-contrast thumbnails disappear. Use a dark background with bright subject, or vice versa. Avoid grey-on-grey, pastels, or anything that relies on subtle color differentiation.

**Large readable text.** If your thumbnail includes text -- and for tutorials, it often helps -- the text needs to be readable when the thumbnail is 168 × 94 pixels (the size YouTube displays in mobile search results). Three to five words maximum. Use a bold, sans-serif font at high contrast. Test by scaling your design down in your image editor before exporting.

**Face or reaction shot.** Thumbnails with human faces consistently outperform thumbnails without them, especially for tutorial and educational content. A face communicates that there is a real person behind the video and creates an emotional connection point. The expression matters -- engaged, surprised, and pointing perform better than neutral or looking away from camera.

**Simple composition.** One dominant element (face, before/after, tool screenshot) plus the text. Thumbnails that try to show too much read as visual noise at thumbnail size. The most effective tutorial thumbnails often have a face on one side and a three-word text on the other.

**A/B test what you think you know.** YouTube Studio supports A/B thumbnail testing. After 48 hours, compare click-through rates. Your intuitions about what looks good at full size frequently do not translate to what performs at thumbnail size.

### Tools

You do not need expensive software. Good thumbnails can be made in:
- **Canva** (free tier is sufficient for basic thumbnails)
- **GIMP** (free, capable, steeper learning curve)
- **Kdenlive's title generator** (export a frame with titles composited in)

If you use Kdenlive to create the thumbnail, export a frame from the video, open it in your image editor, add a simple text overlay, and export at 1280 × 720.

---

## Upload Workflow

YouTube upload is a manual process. ForgeFrame generates all the text assets; you paste them into YouTube Studio. Here is a consistent workflow that prevents the common mistakes (forgetting chapters, uploading the wrong file, leaving the description blank):

### Pre-Upload Checklist

Before opening YouTube Studio:
- [ ] Exported file is the correct final render (check filename and duration)
- [ ] All publish assets are in `reports/publish/` and reviewed
- [ ] Thumbnail is created and saved at 1280 × 720

### In YouTube Studio

1. **Upload** the video file. While it processes, fill in metadata -- do not wait for processing to finish.

2. **Title:** Paste your chosen title. Check character count (70 max before truncation).

3. **Description:** Paste from `description.txt`. Add any manual links or personal notes. Paste chapter timestamps if not already included.

4. **Thumbnail:** Upload your thumbnail file.

5. **Tags:** Paste from `tags.txt`. YouTube's tag field accepts a comma-separated list or Enter-separated entries.

6. **End screens and cards:** Add these after the video finishes processing. End screens require the video to be at least 25 seconds long and are placed in the last 5-20 seconds.

7. **Hashtags:** These go in the description (YouTube extracts them automatically) or in the dedicated hashtag field in Advanced Settings.

8. **Chapters:** Verify that the timestamp list in the description is generating chapters correctly. YouTube previews this in the chapter section of the Details page.

9. **Visibility:** Set to Private or Scheduled, not Public, until you have reviewed the processed video at least once.

10. **Post-publish:** After publishing, post the pinned comment from `reports/publish/pinned_comment.txt` immediately. Pinned comments that go up within the first hour tend to get more engagement than ones added later.

> **ForgeFrame:** After upload, run `publish_note` to create the Obsidian vault entry for this video with the YouTube URL, all metadata, and a link back to the workspace:
>
> ```
> publish_note(workspace_path="projects/my-tutorial", video_url="https://youtube.com/watch?v=...")
> ```
>
> This creates a note in your vault at `Videos/my-tutorial.md` with everything indexed for future reference.
>
> **Manually:** Create a note in your video log with the publish date, final title, video URL, and any performance observations you want to remember. Reviewing this log quarterly helps you identify what title formats, topics, and thumbnails are working.

---

## After Upload

The first 24-48 hours after publishing are when YouTube most aggressively tests your video against its existing audience. Share the video immediately after publishing rather than waiting. If you have a community tab, Discord, or newsletter, post it there. Early views and clicks signal to YouTube that the video deserves wider distribution.

Watch your analytics for:
- **Click-through rate (CTR):** Below 4% usually means the thumbnail or title is not compelling
- **Average view duration:** Below 30% usually means the opening is not hooking viewers
- **Traffic sources:** Search vs. suggested vs. browse tells you where YouTube is testing the video

Do not obsess over the first 48 hours. Some videos are slow burners that find their audience through search over months. A low view count at 48 hours does not mean the video is a failure.
