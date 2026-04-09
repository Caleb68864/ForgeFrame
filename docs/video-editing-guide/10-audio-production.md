# Chapter 10: Audio Production

**Part IV — Post-Production**

---

Viewers will forgive shaky camera work. They will not forgive bad audio.

This is one of the most consistent findings from YouTube creator feedback: people stop watching videos because they can't understand the audio. Not because the lighting was off, not because the color looked a little cool, not because the thumbnail was mediocre. They leave because the voice is muffled, echoey, inconsistent, or buried under a hissing noise floor.

The good news: audio production is learnable, and you don't need an expensive setup to get results that sound professional. A $50 USB microphone in a treated room with good mic placement can outperform a $500 microphone in a live room with bad placement.

This chapter covers the complete audio production workflow for YouTube tutorial creators. We'll go from understanding why YouTube has loudness standards, through the step-by-step signal processing chain, to room treatment on a zero budget. By the end, you'll know exactly what to do to make your voice sound clear, even, and pleasant to listen to for 20 minutes straight.

---

## Why Your Audio Matters More Than You Think

When you're watching a tutorial, your brain is working hard. You're following instructions, watching a demonstration, possibly writing notes or switching back and forth to your own application. Every cognitive resource is in use.

Bad audio adds friction to all of that. When the audio is inconsistent --- loud on one sentence, quiet on the next --- your listener has to constantly adjust their volume. When there's background hiss, their brain has to filter it out, which burns attention. When the voice sounds distant and echoey, words become less distinct and comprehension drops.

Good audio removes that friction. The words land cleanly, the level stays constant, the background is silent. The listener can focus entirely on what you're saying rather than working to hear it.

---

## Understanding YouTube's Loudness Standard

Before we talk about how to process your audio, you need to understand the target you're aiming for: **-14 LUFS** integrated loudness with a **-1 dBTP** true peak ceiling.

Let's break this down.

**LUFS** stands for Loudness Units Full Scale. It's a measurement of perceived loudness over time --- not just the peak volume, but how loud something sounds to a human listener on average. YouTube uses LUFS because peak volume is a bad proxy for perceived loudness (a brief explosion sounds loud but doesn't feel loud for long; a constant loud music bed feels very loud even at a lower peak).

**Integrated loudness** means averaged over the full duration of your video. If your video is mostly quiet with one loud section, the integrated number will reflect the whole thing.

**-14 LUFS** is YouTube's target. Here's the key behavior: YouTube will turn loud audio down to reach -14 LUFS, but it will not turn quiet audio up. This means:

- If you upload audio that averages -10 LUFS, YouTube turns it down. Fine, but you've wasted headroom and may have introduced subtle distortion chasing loudness.
- If you upload audio that averages -20 LUFS, it plays quiet. Your viewers turn up their volume, hear the next loud video at full blast, and blame you for making them do that.

**-1 dBTP** is the true peak limit --- the absolute ceiling for any momentary peak in your audio. True peak (dBTP) accounts for inter-sample peaks that standard peak meters miss. Setting a limiter to -1 dBTP ensures your audio won't clip in downstream processing or on devices with different playback systems.

**Practical target:** Process your audio so it measures approximately -14 LUFS integrated and no peaks above -1 dBTP. A dedicated loudness meter (free options include the Youlean Loudness Meter plugin) will show you both numbers before export.

> **ForgeFrame:** Use `measure_loudness` to check your audio against the YouTube standard before export.
> ```
> measure_loudness --file "export/my-video.mp4" --target -14
> ```
> It reports integrated LUFS, true peak, and whether the file meets spec. You can also measure loudness manually in Audacity using Analyze → Loudness or in any DAW with a LUFS meter.

---

## The Signal Chain: Order Is Everything

Audio processing is not a bag of tricks you apply in any order. The sequence matters because each step affects what the next step receives. Apply compression before noise reduction, and you're compressing the noise into your signal. Apply normalization before your limiter, and your limiter can't protect the ceiling. Do it in the wrong order and each step fights the others.

The correct order for voiceover processing is:

1. **Noise reduction**
2. **EQ**
3. **Compression**
4. **Limiter**
5. **Normalization**

Here's what each step does and why it goes where it does.

---

### Step 1: Noise Reduction

**What it does:** Removes constant background noise --- the hiss from your mic, the hum from an air conditioner, the low rumble from a refrigerator compressor.

**Why it goes first:** Noise is in your signal from the moment of capture. Everything downstream will act on both your voice and the noise floor. If you compress first, you compress the noise up with your voice. If you EQ first, you may boost frequency ranges that make the noise more prominent. Kill the noise first so the rest of the chain is working on a cleaner signal.

**How it works:** Modern noise reduction (like Audacity's Noise Reduction, iZotope RX's Dialogue Denoise, or the spectral denoising in DaVinci Resolve) works by analyzing a noise profile --- a sample of the background noise without any voice --- and then subtracting that profile from the full recording. Record 2-3 seconds of room tone at the start of every recording session by sitting quietly before you speak. This gives you the noise profile sample.

**Target:** After noise reduction, your background should sit at **-60 dBFS or lower**. Above -50 dBFS, background noise becomes distracting to listeners even if you've grown accustomed to it.

**Common mistake:** Over-applying noise reduction creates a metallic, watery artifact called "swimming" on the voice. Use the lightest reduction that gets the noise to an acceptable level, not maximum reduction.

> **ForgeFrame:** Use `audio_enhance` for automated noise reduction. It profiles the room tone from the first 2 seconds of each clip and applies spectral denoising at a conservative setting.
> ```
> audio_enhance --clip "timeline/voice-track.wav" --denoise moderate
> ```
> You can also do this in Audacity: select a silent section, go to Effect → Noise Reduction, click "Get Noise Profile," select all audio, then apply.

---

### Step 2: EQ (Equalization)

**What it does:** Changes the balance of frequencies in your audio. Your voice is made up of many frequencies happening at once --- low rumble, midrange body, high-frequency clarity. EQ lets you turn specific frequency ranges up or down.

**Why "EQ" sounds complicated:** The word equalization is a legacy term from the early days of audio engineering. Don't let it intimidate you. In practice, for voiceover, you're doing a few simple things:

- Removing frequencies you don't want
- Gently boosting frequencies that help clarity

**Why it goes before compression:** The compressor will respond to the overall level of your signal. If you have a boomy low end (common with USB condensers on desks), the compressor will "hear" that boom and react to it, causing pumping and uneven compression. Clean up the frequency balance first so the compressor works on what you actually want to control.

**The voice EQ settings that work:**

| Move | Frequency | Type | Amount | Why |
|------|-----------|------|--------|-----|
| High-pass filter | 80 Hz | Cut (steep) | Full cut | Removes room rumble, traffic, desk vibration |
| Cut mud/boxiness | 200–400 Hz | Bell cut | –2 to –3 dB | Reduces the "talking in a cardboard box" sound |
| Boost presence | 2–5 kHz | Bell boost | +1 to +3 dB | Adds clarity and intelligibility to consonants |
| Boost "air" (optional) | 8–12 kHz | Shelf boost | +1 to +2 dB | Adds brightness if voice sounds dull |

**The most important rule in EQ:** Cut before you boost. Removing problem frequencies will often reveal that you don't need to boost at all. Less is more --- small adjustments (1–3 dB) make a big difference, and heavy-handed EQ creates artifacts.

**How to hear what you're doing:** Sweep slowly through the 200–400 Hz range with a narrow bell cut and listen for where the boxiness disappears. That's your cut point. You're not guessing at numbers --- you're listening.

---

### Step 3: Compression

**What it does in plain English:** Compression makes the quiet words louder and the loud words quieter. It reduces the dynamic range --- the difference between your quietest moment and your loudest moment.

**Why this matters for tutorials:** You naturally vary your volume as you talk. When you're excited about something you raise your voice. When you're concentrating on a step you get quieter. Without compression, listeners are constantly adjusting their volume. With compression, every word lands at roughly the same level.

**The settings that matter:**

- **Ratio: 3:1 to 4:1** --- This means when a signal exceeds the threshold, for every 4 dB it goes over, only 1 dB comes through. A 4:1 ratio is a good starting point for voiceover. Higher ratios (8:1, 10:1) are getting into limiting territory and can sound unnatural on voice.
- **Attack: 5–10 ms** --- How quickly the compressor clamps down after a loud peak arrives. Too fast and it clips transients (the initial consonant sounds that make speech intelligible). 5–10 ms is fast enough to catch peaks without killing the natural attack of words.
- **Release: 50–100 ms** --- How quickly the compressor lets go after the peak passes. Too fast creates a "pumping" effect. Too slow and the compressor is still squashing the signal when it doesn't need to.
- **Gain reduction: 3–6 dB** --- Watch the gain reduction meter on your compressor. It should be bouncing between 3 and 6 dB on peaks during normal speech. If it's hitting 10+ dB constantly, your threshold is too low and you're over-compressing. If it's barely moving, raise your input gain or lower the threshold.

**How to set it:** Start with the threshold low enough that the gain reduction meter is moving consistently (3–6 dB on average). Make up the volume you've lost with the output gain (makeup gain) control. Adjust ratio, attack, and release by ear until speech sounds even without sounding squashed or robotic.

---

### Step 4: Limiter

**What it does:** A limiter is a compressor with a very high ratio (10:1 or higher, often infinity:1) that acts as a brick wall. Nothing gets through above the ceiling you set.

**Why you need it after compression:** Even after compression, occasional peaks --- a hard "P" or "B" consonant, a sharp laugh, a sudden movement toward the mic --- can exceed your target ceiling. The limiter catches these without letting them distort.

**Setting:** Ceiling at **-1 dBTP** (true peak, not just peak). Most modern limiters have a true peak mode --- use it.

**What it should be doing:** Very little. If your limiter is constantly engaged and heavily attenuating, your compression settings aren't doing their job. The limiter is a safety net, not a primary processing tool.

---

### Step 5: Normalization

**What it does:** Brings the overall integrated loudness of your processed audio to the target level --- in our case, **-14 LUFS**.

**Why it goes last:** Normalization is a final level adjustment. All your tonal shaping (EQ), dynamic control (compression), and peak protection (limiter) are already done. Now you're simply setting the playback volume so YouTube's system doesn't need to touch it.

**How to do it:** Use a LUFS-aware normalization tool, not just peak normalization. Peak normalization looks at the highest peak and adjusts from there --- but two files can have the same peak and sound very different in terms of perceived loudness. LUFS normalization adjusts for perceived loudness. Audacity's "Loudness Normalization" effect does this correctly (set it to -14 LUFS). Most DAWs have LUFS normalization options as well.

> **ForgeFrame:** Use `audio_normalize` to apply LUFS normalization to your final mix.
> ```
> audio_normalize --track "export/final-voice.wav" --target -14 --true-peak -1
> ```
> You can also do this manually in Audacity: Effects → Loudness Normalization → set to -14 LUFS.

---

## Applying the Whole Chain at Once

The five-step chain produces excellent results, but setting it up manually for every project takes time. If you want to skip the manual setup and get a clean, YouTube-ready voice track immediately:

> **ForgeFrame:** Use `/ff-audio-cleanup` to apply the complete signal chain automatically to all voice tracks in your current project.
> ```
> /ff-audio-cleanup
> ```
> The skill detects room tone from the first 2 seconds of each clip, profiles the noise, applies noise reduction, EQ, compression, limiting, and LUFS normalization in the correct order, and writes the processed files to `media/audio/processed/`. It also generates a before/after loudness report so you can verify the result. The original files in `media/raw/` are never modified.
>
> You can also apply the chain manually: import your voice audio into Audacity or your DAW, apply each effect in the order described above, export the result, and measure with a LUFS meter before importing to Kdenlive.

---

## Room Treatment: Free and Cheap Solutions

The single biggest variable in voice recording quality is the room. A mid-range microphone in a treated room will outperform a high-end microphone in an untreated room every time.

Here's what's happening in an untreated room: sound leaves your mouth, hits the walls, bounces back, and arrives at the microphone a few milliseconds after the direct sound. This is room echo and early reflections. The microphone hears both your voice and the reflections, which makes the recording sound distant, echoey, and harder to understand. Processing can reduce this but never fully remove it.

**What actually works (no spending required):**

- **Closets:** Recording inside a closet full of clothes is genuinely one of the best vocal booths you can create for free. The clothes absorb reflections from all directions. If you can fit your desk and monitor in there, do it.
- **Moving blankets and heavy curtains:** Hang them on the walls around your recording position. They don't need to cover the whole room --- focus on the wall directly in front of you (behind the monitor) and the wall behind you (where your voice bounces back to the mic).
- **Thick rugs:** Hard floors create strong floor reflections. A thick area rug under your recording position significantly reduces early reflections.
- **Bookshelves:** Full bookshelves are excellent acoustic diffusers. Books of varied sizes scatter sound at different frequencies rather than reflecting it cleanly back. Position a bookshelf on at least one wall of your recording space.
- **Avoid corners:** Recording in a corner concentrates bass frequencies and creates an uneven, boomy sound. Position yourself away from corners.

**What doesn't work as well as people think:**

- **Acoustic foam tiles:** Small foam tiles primarily absorb high frequencies. They can actually make a room sound worse by removing the highs while leaving a hollow, boxy low-midrange. You'd need to cover most of a room's surface area for foam to make a meaningful difference. Blankets and soft furnishings are more effective per dollar.

**The quick test:** Clap your hands once in your recording space and listen to the decay. In a well-treated space, you hear the clap and it stops quickly. In an untreated room, you hear the clap followed by a ringy, metallic sustain. That sustain is what ends up in your recording.

---

## Microphone Placement

This is the biggest single variable within your control after room treatment.

**The golden rule: get the mic closer.** Every time you double the distance between your mouth and the microphone, you roughly double the amount of room sound relative to direct voice sound. The microphone doesn't care how close you are --- it just picks up what's loudest. Get it closer and your voice is louder relative to the room.

**Specific placement by mic type:**

| Mic Type | Placement | Notes |
|----------|-----------|-------|
| USB condenser (e.g., Blue Yeti) | 6–10 inches from mouth, slightly off-axis | Pop filter mandatory. Off-axis placement reduces plosives. |
| Lapel/lavalier | 6–8 inches below chin, centered on chest | Don't touch or brush against it during recording --- rustling is nearly impossible to remove. |
| Shotgun/boom | 2–3 feet overhead, angled down toward mouth, just out of frame | Further than it feels comfortable, but the directionality handles the distance. |

**Off-axis placement:** For USB condensers, many creators position the mic slightly to the side of their mouth rather than directly in front. This reduces plosives (the hard "P" and "B" sounds that blast the mic) while keeping proximity for warmth. Experiment with 15–30 degrees off-axis.

**Pop filter:** For any condenser mic positioned directly in front of your mouth, a pop filter (the foam windscreen or mesh screen that goes in front of the mic) is mandatory. Plosives are nearly impossible to fix in post. Prevention costs $10.

---

## Monitoring: Why Headphones Matter

Recording and editing audio on laptop speakers is one of the most common beginner mistakes, and it has a specific, predictable consequence: the mix sounds fine on your laptop but bad on everything else.

Laptop speakers have poor bass and midrange response. When you mix or monitor with them, you unconsciously compensate --- boosting things that sound weak on the speakers --- and the result is a mix that's muddy or harsh on real headphones or speakers.

**During recording:** Use closed-back headphones (the kind that seal around your ears). They let you hear yourself clearly, catch problems like handling noise or mouth clicks immediately, and prevent headphone bleed from reaching the microphone. Recording without monitoring is how you get through a 20-minute session only to discover the mic was pointed the wrong direction.

**During editing:** Use over-ear headphones (open or closed-back) for the final noise reduction and EQ work. Headphones reveal background noise that laptop speakers can't reproduce. A hiss that's invisible on laptop speakers becomes clearly audible on headphones --- and clearly audible on your viewers' earbuds.

**You don't need expensive headphones:** The Sony MDR-7506 (around $100) is the industry standard for a reason: flat, accurate, durable, replaceable cables. Many creators use whatever they have. The critical thing is not trusting laptop speakers.

---

## What Good Audio Processing Sounds Like

If you've never done voice processing before, it can be hard to know if you're there. Here's the before and after description.

**Before processing:**
- The voice sounds thin or slightly distant, like it was recorded in a room
- There's a consistent hiss or hum underneath the voice
- Some words are loud (when you raised your voice) and some are quiet (when you thought through a step)
- Occasionally a loud peak makes the listener flinch
- The voice has a slightly boxy or muffled quality in the midrange
- Between sentences, the room ambience becomes audible

**After processing:**
- The voice sounds close and direct, as though the person is speaking to you personally
- The background between words is silence (or very nearly)
- Every word --- loud or quiet, emphatic or casual --- arrives at roughly the same volume
- Nothing clips or distorts
- The consonants are clear and intelligible (the T's, S's, and P's)
- Listening for 20 minutes feels effortless rather than tiring

The difference is significant. If you record a sentence, apply the full chain, and compare the original to the processed version, the processed version should sound noticeably better in every dimension. If it doesn't, or if it sounds worse (metallic, robotic, or pumping), one of the steps is over-applied.

---

## Common Audio Mistakes

**Inconsistent recording levels between sessions:** You sound different at 9am after coffee than at 9pm after a long day. You may sit closer or farther from the mic each session. This creates loudness jumps between recording days that compression and normalization can only partly fix. Set up a physical reference for mic position (mark the desk with tape, use a boom arm with a fixed angle) and check your levels with a brief test clip before recording.

**Background noise sources you forgot about:** HVAC systems, refrigerators, and computer fans often cycle on and off. Record a minute of test audio, listen back with headphones, and make sure you know what's audible. The refrigerator compressor in the next room may not be something you notice while living with it, but it will be very clear to first-time listeners.

**Mouth clicks:** Dry mouth creates clicking sounds between words. Drink water before and during recording sessions. Avoid dairy before recording (it creates excess mucus). Some people take an apple slice break --- the malic acid in apples reduces mouth noise.

**Music competing with voice:** Background music in tutorials is fine, but it must sit significantly below the voice --- typically 20–30 dB below. If you can hear the lyrics or melody clearly, it's too loud. A viewer following a technical tutorial cannot simultaneously process music lyrics and spoken instructions.

**Clipping from gain set too high:** Recording with the gain too high means peaks clip (distort by hitting the absolute ceiling of the digital signal). Clipped audio is very difficult to repair. Record with peaks hitting -12 dBFS on the loudest words. Compression will bring up the quiet passages --- you don't need to record hot.

---

## The Single Most Effective Thing You Can Do

Before you buy any software, plugins, or acoustic treatment:

**Get the microphone closer to your mouth.**

This is not a simplified tip for beginners. It's the actual most impactful audio improvement available to any creator at any level. Reducing the distance between your mouth and the microphone capsule does several things simultaneously:

1. It increases the signal-to-noise ratio --- your voice gets louder relative to the room noise and self-noise of the microphone
2. It increases bass frequencies via the proximity effect (for directional mics), which adds warmth
3. It reduces the ratio of reflected sound to direct sound
4. It gives noise reduction and EQ less work to do

If your current microphone placement is 12 inches from your mouth and you move it to 6 inches, the improvement will be more audible than any processing change you can make. Six to ten inches is the target for USB condensers. If you find yourself backing away to avoid plosives, address the plosives with an off-axis angle or a pop filter rather than increasing distance.

---

## Chapter Summary

Good tutorial audio is not about expensive gear --- it's about understanding the signal chain and applying it correctly. Here's the complete workflow:

1. **Record well:** Treated room, mic close, headphones on, gain at -12 dBFS peaks
2. **Noise reduce:** Profile room tone, remove background hiss/hum
3. **EQ:** High-pass at 80 Hz, cut mud at 200–400 Hz, boost presence at 2–5 kHz
4. **Compress:** 3:1–4:1 ratio, 3–6 dB of gain reduction, makeup gain applied
5. **Limit:** Brick wall at -1 dBTP
6. **Normalize:** Target -14 LUFS integrated
7. **Verify:** Measure with a LUFS meter before export

Apply this chain consistently and your viewers will be able to follow your tutorials for an hour without fatigue.

> **ForgeFrame:** Run `/ff-audio-cleanup` after editing to apply the complete signal chain automatically, then use `measure_loudness` to verify the output meets the -14 LUFS YouTube standard before you export.

---

**Next:** Chapter 11 covers pacing, storytelling, and retention --- how to structure your tutorial so viewers stay engaged from the hook through the payoff.

**Previous:** Chapter 09 (Color Correction & Grading) covers visual quality with the same principle: systematic correction over expensive gear.
