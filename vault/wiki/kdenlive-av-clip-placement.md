# Kdenlive audio/video clip placement

A source clip with both video and audio needs two timeline entries: one on a
video playlist and one on an audio playlist. Both entries use the same source,
in-point, out-point, and timeline start frame. The video lane hides audio and
the audio lane hides video, so an entry on only the video lane renders silently.

The native fixture `tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive`
shows the paired entries in `playlist0` (audio) and `playlist6` (video). It
places blanks before both entries where needed and gives the paired entries the
same source range and clip ID. Kdenlive also records an optional `AVSplit`
group in `kdenlive:sequenceproperties.groups`; do not emit that group unless
the sequence track-index mapping has been verified against the native fixture.

When appending, the audio playlist must be padded with a blank if it ends before
the video entry's start frame. For an insertion in the middle, place the audio
entry at the index whose start frame matches the video entry. If no exact start
exists, leave the audio unplaced and report that result rather than guessing.

`clip_speed` must retime both paired entries. `audio_fade` belongs on the audio
entry and uses Kdenlive's `fadein`/`fadeout` identity with a filter range limited
to the fade frames. A dissolve that pulls the incoming video clip earlier must
also adjust the preceding audio duration so the incoming audio starts at the
same frame. The sequence's separate tracks keep media linked by producer and
timeline position; other move, trim, split, and ripple intents still need
explicit audio-sync handling.
