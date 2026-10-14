# ForgeFrame capabilities

Generated with `wvb capabilities --markdown`. Registration metadata is the source of truth.

220 MCP tools; 20 skills.

## Skills

| Skill | Description |
| --- | --- |
| ff-assemble-from-script | Assemble a reviewable first cut straight from a build-step / script list and a pile of raw clips. Indexes transcripts, maps each step to candidate footage, places clips on a timeline, and self-reviews the render. Use when user says 'assemble from the script', 'build the cut from my steps', 'match footage to the instructions', 'turn my steps into a timeline', or 'auto-assemble from script'. |
| ff-audio-cleanup | Clean up raw audio for YouTube tutorials. Removes noise, normalizes volume, reduces sibilance, and limits peaks. Use when user says 'clean the audio', 'fix the sound', 'audio sounds bad', 'normalize audio', or 'enhance voice'. |
| ff-auto-editor | Auto-assemble a first-cut video timeline from script and footage. Matches clips to script steps and builds a Kdenlive project. Use when user says 'build the edit', 'auto edit', 'assemble timeline', or 'create first cut'. |
| ff-broll-whisperer | Analyse a workshop tutorial transcript and suggest specific B-roll shots grouped by category. Use when user says 'b-roll', 'what visuals', 'where do I need footage', 'suggest shots', 'what should I film', or 'b-roll ideas'. |
| ff-capture-prep | Generate a pre-shoot capture checklist from a shot plan: camera settings, audio, lighting, sync, and optimized shot order. Use when preparing to film. |
| ff-effect-cookbook | Pick and apply the right effect, composite, keying, masking, or motion tool for a look. Covers the one-call bundle tools (hologram, color grade/wash, greenscreen, masked wipes, camera shake, pan/zoom, subject zoom + tracking, AI masks, split-screen, light leaks) plus the low-level effect stack. Use when user says 'add an effect', 'how do I do X effect', 'color grade this', 'green screen', 'key out the background', 'mask the subject', 'ken burns', 'camera shake', 'hologram', 'glitch', 'which effect tool', or names a VFX look. |
| ff-finishing | Take a locked rough cut to a delivered, published video: audio mix + music ducking, color grade / LUT, titles + subtitles, QC, render (incl. alpha profiles), then the publish bundle with chapters and thumbnail. Use when user says 'finish the video', 'finishing pass', 'final render', 'export the video', 'ready to deliver', 'polish and publish', or 'take this to publish'. |
| ff-init | Set up ForgeFrame for the first time. Creates Obsidian vault structure, media organization folders, and config files. Use when user says 'set up forgeframe', 'initialize', 'first time setup', or 'configure forgeframe'. |
| ff-new-project | Start a new video project from scratch. Creates workspace, vault note, and generates outline, script, and shot plan from a brain dump. Use when user says "new project", "start a video", "new tutorial", or "I want to make a video about". |
| ff-obsidian-video-note | Create or update an Obsidian video project note with frontmatter, outline, script, shot plan, transcript, edit notes, and publish checklist. Preserves manual edits using section boundaries. Use when user says 'create video note', 'update the note', 'project note', or 'sync the vault'. |
| ff-pacing-meter | Analyse video pacing and energy from transcript data. Detects slow sections, weak intros, and energy drops. Suggests targeted fixes to improve viewer retention and keep the video moving. |
| ff-pattern-brain | Extract MYOG (Make Your Own Gear) build data from a workshop transcript. Produces a materials list, measurements, numbered build steps, and tips/warnings. Generates overlay text for video and a printable build notes document. Use when the user says "build notes", "pattern", "materials list", "measurements", "printable", or "overlay text". |
| ff-publish | Generate YouTube publish assets: title options, description, tags, hashtags, chapters, summary, and pinned comment. Use when user says 'publish', 'ready to upload', 'YouTube description', 'generate tags', or 'publish bundle'. |
| ff-rough-cut-review | Review a rough cut using transcript and edit notes. Identifies pacing issues, repetition, missing inserts, overlay opportunities, and chapter break candidates. Use when user says 'review the cut', 'rough cut feedback', 'pacing review', or 'analyze the edit'. |
| ff-shot-plan | Generate a production shot list from a tutorial outline or script. Covers A-roll, overhead bench shots, detail closeups, measurement shots, inserts, glamour B-roll, and likely pickup shots. Use when user says 'shot list', 'plan the shots', 'what shots do I need', or 'shooting plan'. |
| ff-social-clips | Extract short-form clips from a tutorial for YouTube Shorts, Instagram Reels, and TikTok. Generates titles, captions, and social post text. Use when user says 'make shorts', 'social clips', 'extract highlights', 'create reels', or 'repurpose for social'. |
| ff-tutorial-script | Generate a practical tutorial script from an outline or project note. Produces intro hook, materials section, step-by-step build instructions, common mistakes, and conclusion. Use when user says 'write a script', 'draft the tutorial', 'script this video', or 'write the voiceover'. |
| ff-video-idea-to-outline | Turn a rough video idea into a structured tutorial outline with viewer promise, materials list, teaching beats, pain points, and chapter structure. Use when user says 'plan a video', 'outline a tutorial', 'video idea', or describes a project they want to film. |
| ff-voiceover-fixer | Rewrite flagged voiceover segments into clean tutorial language. Use when user says 'fix voiceover', 'clean up transcript', 'rewrite rambling', 'voiceover fixes', 'clean up my script', or 'fix the dead air'. |
| ff-youtube-analytics | Pull YouTube channel stats and video data for analytics. Generates performance reports, identifies top content, and saves insights to Obsidian vault. Use when user says 'youtube stats', 'channel analytics', 'video performance', or 'pull my youtube data'. |

## MCP tools

| Tool | Module | Description |
| --- | --- | --- |
| assembly_build | assembly_titles | Build a first-cut Kdenlive project from the assembly plan. |
| assembly_plan | assembly_titles | Generate an assembly plan matching clips to script steps. |
| audio_analyze | audio | Analyze audio levels (LUFS, peak, noise floor) without modifying. |
| audio_compress | audio | Reduce dynamic range for consistent volume. |
| audio_denoise | audio | Remove background noise from audio. |
| audio_duck | timeline_audio | Duck a music track under speech on a voice track (keyframed ``volume``). |
| audio_enhance | audio | Apply full voice enhancement pipeline (highpass -> denoise -> compress -> normalize -> limit). |
| audio_enhance_all | audio | Enhance all audio in workspace media/raw/ folder. |
| audio_fade | clips_nle | Apply audio fade in or out to a clip. |
| audio_loudness_scan | loudness_scan | Measure per-clip loudness (LUFS / true-peak / LRA) across a shoot. |
| audio_normalize | audio | Normalize audio to YouTube-standard loudness (-16 LUFS). |
| audio_normalize_two_pass | audio_normalize_two_pass | Normalize loudness accurately with measured two-pass FFmpeg ``loudnorm``. |
| broll_library_index | broll | Add clips from a project to the B-roll library. |
| broll_library_search | broll | Search the B-roll library across all projects. |
| broll_library_stats | broll | Get B-roll library statistics. |
| broll_library_tag | broll | Add tags, rating, or description to a B-roll clip in the library. |
| broll_suggest | broll | Analyze transcript and suggest specific B-roll shots. |
| clip_insert | clips_nle | Insert a clip into the timeline of the latest working copy project. |
| clip_move | clips_nle | Move a clip from one position to another on the timeline. |
| clip_move_to | clip_place | Move a clip from one track to another (cross-track move). |
| clip_place | clip_place | Place a clip at absolute time ``at_seconds`` on ``track``. |
| clip_place_matched | clip_place | Place a clip cut to exactly the duration of a reference clip. |
| clip_remove | clips_nle | Remove a clip from the timeline by index. |
| clip_ripple_delete | clips_nle | Remove a clip and close the gap. |
| clip_speed | clips_nle | Change clip playback speed (0.5=slow, 2.0=fast). |
| clip_split | clips_nle | Split a clip at a timestamp (razor tool). |
| clip_trim | clips_nle | Trim a clip's in and/or out points. |
| clips_detect_scenes | scene_detect | Detect shot boundaries in a long recording via ``scdet``. |
| clips_find_duplicates | clip_dupes | Find perceptual near-duplicate video clips in a folder. |
| clips_label | clips_nle | Auto-label all clips in workspace from transcript and marker data. |
| clips_preview_gif | clip_preview | Generate a small looping GIF (or tiny mp4) preview of a clip. |
| clips_qc_scan | qc_scan | Batch-scan clips for junk (black / frozen / blurry / mis-exposed / dead-air). |
| clips_search | clips_nle | Search clips by content. Returns ranked matches. |
| color_analyze | effects_color | Analyze color metadata of a media file. |
| color_apply_lut | effects_color | Apply a LUT file to a clip in a Kdenlive project. |
| composite_pip | compositing_masking | Add a picture-in-picture composite to the project. |
| composite_set | compositing_masking | Add a composite transition between two tracks with a named blend mode. |
| composite_split_screen | split_screen | Build a split/quad-screen composite from several source tracks. |
| composite_wipe | compositing_masking | Add a wipe or dissolve transition between two tracks. |
| effect_add | effects_catalog | Add a named effect to a clip in a Kdenlive project. |
| effect_camera_shake | shake_shadow | Add a deterministic keyframed camera-shake ``qtblend`` filter to a clip. |
| effect_chroma_key | compositing_masking | Append a basic ``chroma`` key filter to a clip's effect stack. |
| effect_chroma_key_advanced | compositing_masking | Append an ``avfilter.hsvkey`` advanced chroma filter to a clip. |
| effect_color_grade | effects_color | Apply a correction+grade chain to a clip in one snapshot. |
| effect_color_wash | effects_color | Append a light-wash ("Color Wash VFX") colour-grade stack to a clip. |
| effect_day_to_night | overlay_looks | Grade a clip from day toward night, with an optional sky overlay. |
| effect_drop_shadow | shake_shadow | Add a ``dropshadow`` filter to a clip (for PiP / title layers). |
| effect_dust | effect_dust | Dust -- Add dust and specks to the video, as in old movies. |
| effect_fade | effects_bundles | Append a keyframed ``transform`` fade filter (opacity) to a clip. |
| effect_find | keyframes | Resolve the effect_index of a filter on a clip by name. |
| effect_frei0r_aech0r | effect_frei0r_aech0r | Analog Video Echo -- Create an analog video echo. |
| effect_frei0r_cairoimagegrid | effect_frei0r_cairoimagegrid | Video grid -- Create a video grid. |
| effect_frei0r_cartoon | effect_frei0r_cartoon | Cartoon -- Cartoonify video, do a form of edge detect. |
| effect_frei0r_cluster | effect_frei0r_cluster | K-Means Clustering (ABANDONED) -- <b>Abandoned due to heavy CPU workload.</b><br>. |
| effect_frei0r_delay0r | effect_frei0r_delay0r | delay0r -- Video delay. |
| effect_frei0r_edgeglow | effect_frei0r_edgeglow | Edge Glow -- Edge glow filter. |
| effect_frei0r_equaliz0r | effect_frei0r_equaliz0r | Equaliz0r -- Equalizes the intensity histograms. |
| effect_frei0r_glitch0r | effect_frei0r_glitch0r | Glitching (rows and color) -- Adds color glitches and block shifting. |
| effect_frei0r_letterb0xed | effect_frei0r_letterb0xed | Letter-boxing -- Adds black borders at the top and bottom for that widescreen cinema look. |
| effect_frei0r_luminance | effect_frei0r_luminance | Luminance -- Creates a luminance map of the image. |
| effect_frei0r_mask0mate | effect_frei0r_mask0mate | Rectangular Alpha mask -- Creates an square alpha-channel mask. |
| effect_frei0r_mirr0r | effect_frei0r_mirr0r | Mirr0r -- Repeats and flips the input image when it goes out of bounds, allowing for adjustable offset, zoom and rotation.. |
| effect_frei0r_nosync0r | effect_frei0r_nosync0r | nosync0r -- Broken TV. |
| effect_frei0r_scanline0r | effect_frei0r_scanline0r | scanline0r -- Interlaced black lines. |
| effect_frei0r_sobel | effect_frei0r_sobel | Sobel -- Sobel filter. |
| effect_frei0r_tehroxx0r | effect_frei0r_tehroxx0r | TehRoxx0r -- Something videowall-ish. |
| effect_frei0r_transparency | effect_frei0r_transparency | Transparency -- Tunes the alpha channel.. |
| effect_glitch_stack | effects_bundles | Append a 5-filter glitch stack to a clip in one snapshot. |
| effect_grain | effect_grain | Grain -- Grain over the image. |
| effect_hologram | effects_bundles | Apply the tutorial's full hologram *look* to a clip in one snapshot. |
| effect_info | effects_catalog | Return full schema for a Kdenlive effect by kdenlive_id or MLT service tag. |
| effect_keyframe_set_color | keyframes | Write a color keyframe animation string (0xRRGGBBAA) to an effect property. |
| effect_keyframe_set_rect | keyframes | Write a rect keyframe animation string (x y w h [opacity]) to an effect property. |
| effect_keyframe_set_scalar | keyframes | Write a scalar keyframe animation string to an effect property. |
| effect_light_leak | overlay_looks | Overlay a light-leak clip above the footage and blend it additively. |
| effect_list_common | effects_catalog | List common Kdenlive/MLT effects with descriptions. |
| effect_luma_key | masked_wipes | Add a luminance key (``avfilter.lumakey``) to a clip: luma -> alpha. |
| effect_object_mask | compositing_masking | Append a parametric SPOT-SHAPE alpha mask to a clip (NOT AI). |
| effect_oldfilm | effect_oldfilm | Old Film Simulator -- Moves the picture up and down and adds random brightness changes. |
| effect_pan_zoom | pan_zoom | Add a keyframed pan/zoom (Ken Burns) transform to a clip. |
| effect_reorder | effects_catalog | Reorder a filter within a clip's filter stack. |
| effect_rewind | rewind | Insert a VHS-style rewind (reversed, sped-up) copy of a clip segment. |
| effect_scifi_greenscreen | effects_color | Apply the tutorial's full sci-fi green-screen keying stack in one snapshot. |
| effect_scratchlines | effect_scratchlines | Scratch Lines -- Scratch lines over the picture. |
| effect_stack_apply | effects_catalog | Apply a saved preset stack to a clip. Snapshot is taken before write. |
| effect_stack_list | effects_catalog | List presets across workspace and/or vault tiers. |
| effect_stack_preset | effects_catalog | Serialize a clip's filter stack into a workspace-tier preset YAML. |
| effect_stack_promote | effects_catalog | Promote a workspace preset to the vault tier (markdown with frontmatter). |
| effect_tcolor | effect_tcolor | Technicolor -- Oversaturate the color in video, like in old Technicolor movies. |
| effects_copy | effects_catalog | Serialize a clip's filter stack to a JSON-friendly dict (read-only). |
| effects_paste | effects_catalog | Paste a serialized filter stack onto a clip. |
| flash_cut_montage | effects_bundles | Split a clip into ``n_cuts`` pieces and apply rotating directional blur. |
| forgeframe_capabilities | discovery | List available MCP tools and skills from registration metadata. |
| forgeframe_doctor | discovery | Check local binaries, engines and model caches without downloading models. |
| forgeframe_init | timeline_project | Initialize ForgeFrame environment with vault structure, media folders, and config. |
| forgeframe_status | timeline_project | Check ForgeFrame initialization status. |
| gap_insert | clips_nle | Insert a gap/blank at a position on the timeline. |
| guide_add | guides | Add a timeline guide to a Kdenlive project at *at_seconds*. |
| guide_list | guides | List all guides in a Kdenlive project (read-only). |
| guide_remove | guides | Remove guides by time (numeric seconds) or by label (string). |
| job_cancel | jobs | Request cancellation of the worker and its FFmpeg/MLT child processes. |
| job_list | jobs | List detached jobs, newest first, reconciling workers lost after restart. |
| job_retry | jobs | Explicitly retry failed/cancelled/interrupted work with a new job ID. |
| job_status | jobs | Read persistent status, stage progress, log path, and result; detect lost workers. |
| job_submit | jobs | Start render, proxy, transcribe, or workflow and return a persistent job ID. |
| markers_auto_generate | transcript_markers | Auto-generate markers for all transcripts in the workspace. |
| markers_from_beats | beat_grid | Convert a beat grid into workspace bar markers (every N-th beat = a bar). |
| markers_list | transcript_markers | List all marker files and their marker counts in the workspace. |
| mask_apply | compositing_masking | Wrap a filter with the mask_start / mask_apply sandwich. |
| mask_generate | ai_mask | Generate a black/white **matte video** for a clip using a local segmenter. |
| mask_generate_and_apply | ai_mask | Generate a matte video, then wire it onto a clip's alpha (one call). |
| mask_set | compositing_masking | Insert a mask filter at the top of a clip's effect stack. |
| mask_set_from_file | shape_alpha_mask | Insert a Shape Alpha (``shape``) filter consuming an external matte file. |
| mask_set_shape | compositing_masking | Insert a rotoscoping mask with a shape-derived spline at the top of a stack. |
| media_check_vfr | workspace_media | Scan workspace for variable frame rate (VFR) video files. |
| media_denoise_video | media_denoise_video | Clean up grainy / high-ISO / low-light footage in one call. |
| media_ingest | workspace_media | Run the full ingest pipeline: scan, proxy, transcribe, detect silence. |
| media_list_assets | workspace_media | List media assets found in the workspace media/raw directory. |
| media_segment_at_silence | silence_segment | Split a long recording into per-take files at detected silences. |
| media_slideshow | slideshow | Assemble a folder of images into a timelapse/slideshow video clip. |
| media_stabilize | stabilize | Stabilize shaky footage with two-pass FFmpeg vidstab. |
| media_sync_by_audio | audio_sync | Find the time offset between two recordings of the same event. |
| media_thumbnail_sheet | thumbnail_sheet | Extract representative keyframes (+ optional contact sheet) from a clip. |
| media_transcode_cfr | workspace_media | Transcode a VFR video file to constant frame rate (CFR). |
| move_down | effects_bundles | Move a filter down one position in a clip's filter stack. |
| move_to_bottom | effects_bundles | Move a filter to the bottom (last index) of a clip's filter stack. |
| move_to_top | effects_bundles | Move a filter to the top (index 0) of a clip's filter stack. |
| move_up | effects_bundles | Move a filter up one position in a clip's filter stack. |
| multicam_assemble | multicam | Stack + sync N camera angles onto their own timeline tracks. |
| multicam_switch | multicam | Scripted angle switch-cutting onto a top *program* track. |
| music_beat_grid | beat_grid | Detect onsets, tempo, and a beat grid for a music track (pure NumPy). |
| overlay_insert | image_overlay | Place a single still (PNG/JPG/SVG) on a track above the footage. |
| pacing_analyze | assembly_titles | Analyse pacing and energy for all transcripts in the workspace. |
| pattern_extract | assembly_titles | Extract MYOG build data (materials, measurements, steps, tips) from workspace transcripts. |
| ping | server | Health check. Returns server status. |
| project_archive | timeline_project | Archive the workspace into a tar.gz or zip file. |
| project_create_working_copy | timeline_project | Create an initial .kdenlive working copy for the workspace. |
| project_list | timeline_project | List all ForgeFrame projects with their status. |
| project_match_source | render | Probe a source file and return recommended project profile settings. |
| project_new | timeline_project | Create a new video project with workspace, vault note, and production plan. |
| project_setup_profile | render | Set up project profile (resolution, fps, colorspace). |
| project_status | guided_workflow | Report readiness, missing inputs, selected version, jobs, and next action. |
| project_summary | timeline_project | Return a summary of the workspace project including all artifacts. |
| project_validate | timeline_project | Validate the latest .kdenlive working copy project file. |
| proxy_attach | proxy_wiring | Wire existing proxy files into a Kdenlive project so Kdenlive uses them. |
| proxy_detach | proxy_wiring | Revert producers to their original sources (undo ``proxy_attach``). |
| proxy_generate | workspace_media | Generate proxy files for all media assets that need them. |
| proxy_status | proxy_wiring | Report per-producer proxy state (read-only). |
| publish_bundle | social_publish | Generate complete YouTube publish bundle: title options, description, tags, hashtags, chapters, summary, pinned comment. Saves all files to workspace/reports/publish/. |
| publish_chapters | guides | Export guides + chapter markers as YouTube chapter text. |
| publish_description | social_publish | Generate YouTube description from transcript and chapters. |
| publish_note | social_publish | Create Obsidian publish note with full bundle in vault. |
| publish_summary | social_publish | Generate short, medium, and long video summaries. |
| publish_tags | social_publish | Generate SEO tags and hashtags from transcript. |
| publish_titles | social_publish | Generate 4 title variants (searchable, curiosity, how-to, short). |
| qc_check | render | Run automated quality checks on a rendered media file. |
| render_final_tool | render | Render the workspace project using a named render profile. |
| render_list_profiles | render | List all available render profiles with their names. |
| render_preview | render | Render the latest working copy project with the preview profile. |
| render_review_frames | review_loop | Render a cut, extract review frames, tile a contact sheet, and QC it. |
| render_status | render | List all render jobs for the workspace. |
| replay_generate | assembly_titles | Generate a highlight-reel replay .kdenlive project from workspace markers. |
| research_detect_scenes | research_media | Detect scene changes in a video, optionally within a time range. |
| research_export_package | research_package | Export a research package from an existing handshake dir, no agent selection needed. |
| research_extract_frame | research_media | Extract a single frame from a video at a given timestamp. |
| research_extract_frame_burst | research_media | Extract a uniform burst of frames across a time range. |
| research_generate_candidates | research_candidates | Generate candidate frames for *video_path* and persist a candidates manifest. |
| research_probe_video | research_media | Probe a video file and return its media metadata. |
| research_run | research_package | Run the full deterministic visual-research pipeline and export a package. |
| research_select_candidate | research_candidates | Select one or more candidates from a prior generate call and export a package. |
| research_transcript_context | research_transcript | Return transcript segments overlapping a time window around *timestamp_seconds*. |
| research_transcript_search | research_transcript | Search a transcript for segments containing *query*. |
| shots_map_to_script | shot_alignment | Map a numbered build-step list to candidate clips + timestamps. |
| snapshot_list | timeline_project | List all snapshots in the workspace. |
| snapshot_restore | timeline_project | Restore a snapshot by its directory name (timestamp-slug). |
| social_clip_post | social_publish | Generate social media post text for a specific clip. |
| social_find_clips | social_publish | Find highlight clips suitable for YouTube Shorts/social media from transcript. |
| social_generate_package | social_publish | Generate complete social media package: clips, titles, captions, posts. |
| speed_ramp | speed_ramp | Apply a keyframed speed ramp (time remap) to a clip. |
| subject_locate_frames | motion_track | Extract a frame from a clip so an agent can supply a subject bbox. |
| subject_track | motion_track | Track a subject rectangle across a clip; save tracked keyframes to JSON. |
| subject_zoom | motion_track | Apply a tracked follow-zoom (or a static punch-in) to a clip. |
| subtitles_attach | subtitle_track | Attach an SRT to a Kdenlive project as a real subtitle track. |
| subtitles_burn_in | subtitle_track | Burn subtitles into a delivered media file (media/processed/). |
| subtitles_export | transcript_markers | Export subtitle files in the specified format. |
| subtitles_generate | transcript_markers | Generate SRT subtitles from transcripts in the workspace. |
| thumbnail_generate | review_loop | Make a publish thumbnail: extract a frame and overlay bold title text. |
| timeline_build_review | timeline_project | Build a Kdenlive review timeline from workspace markers. |
| timeline_build_selects | timeline_project | Build a Kdenlive selects timeline from high-confidence markers. |
| title_card_add | titles | Add an on-screen title card to a Kdenlive project. |
| title_cards_generate | assembly_titles | Generate title cards from chapter markers in the workspace. |
| track_add | clips_nle | Add a new video or audio track to the project. |
| track_eq | timeline_audio | Apply a multi-band EQ to a track (stacked ``avfilter.equalizer`` bands). |
| track_mute | clips_nle | Mute or unmute a track. |
| track_pan | timeline_audio | Pan a track left/right (a ``panner`` filter on the whole track). |
| track_visibility | clips_nle | Show or hide a video track. |
| track_volume | timeline_audio | Set a track's volume (a ``volume`` filter on the whole track). |
| transcript_edit | transcript_index | Correct a mis-transcribed segment and reindex that single row. |
| transcript_export | transcript_markers | Export transcripts in the specified format. |
| transcript_generate | transcript_markers | Generate transcripts for all media assets in the workspace. |
| transcript_index_build | transcript_index | Build (or incrementally update) the transcript search index. |
| transcript_search | transcript_index | Search transcript segments, BM25-ranked, with jump-to timestamps. |
| transition_masked_wipe | masked_wipes | Add a masked / custom-luma wipe transition between two tracks. |
| transition_paper_cutout | effects_color | Stamp a torn-paper cutout filter stack onto a clip in one snapshot. |
| transition_zoom_whip | zoom_whip | Apply a zoom / whip-pan transition across a cut on one video track. |
| transitions_apply | transitions | Apply transitions to the latest working copy project. |
| transitions_apply_at | transitions | Apply a transition at a specific timestamp in the timeline. |
| transitions_apply_between | transitions | Apply a transition between clip N and clip N+1 on the first video track. |
| vo_attach | vo_loop | Attach a recorded take for *cue_id*: probe, place on an audio track, report drift. |
| vo_plan | vo_loop | Split a markdown script into numbered VO cues and lay them on the timeline. |
| vo_status | vo_loop | Return the VO cue table: planned / recorded / missing, est vs actual, drift. |
| voiceover_extract_segments | transcript_markers | Extract transcript segments flagged for voiceover fixes. |
| watermark_apply | image_overlay | Apply a full-duration corner watermark from an image. |
| workflow_start | guided_workflow | Start/resume footage → selects → assembly → preview → review as a job. |
| workspace_create | workspace_media | Create a new workspace with the given title and media root. |
| workspace_status | workspace_media | Return manifest data for an existing workspace. |
| youtube_analyze | social_publish | Fetch and analyze a YouTube channel with stats and insights. |
| youtube_fetch_channel | social_publish | Fetch video data from a YouTube channel. Requires yt-dlp. |
| youtube_fetch_video | social_publish | Fetch data for a single YouTube video. |
| youtube_save_to_vault | social_publish | Fetch channel data and save analytics to Obsidian vault. |
