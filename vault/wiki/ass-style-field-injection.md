# A font name can break out of the ASS `Style:` field

`SubtitleStyle.font` is user-supplied and lands *mid-line* in a
comma-delimited ASS `Style:` record:

    Style: Default,{font},{size},{primary},&H000000FF,{outline},...

so a comma in the font name shifts every subsequent field by one, and a
newline terminates the record and starts a fresh directive. Neither is ever
a legitimate font name.

`SubtitleStyle` now carries a `field_validator` on `font` that strips `,`,
`\r` and `\n` and falls back to the default if nothing survives. Stripping
rather than rejecting is deliberate: the font name is cosmetic, so a stray
character should not fail an otherwise valid styling call.

The validator sits on the **model**, not on any one builder, so it covers
all three consumers at once — `build_ass_style_line`, `cues_to_ass`, and
`force_style_string`.

## Severity

Low, and worth being honest about why: the `.ass` file belongs to the user's
own project and no privilege boundary is crossed. The realistic damage is a
corrupted subtitle style, not an escalation. It was fixed because it is
cheap and sits in the same family as
[[ffmpeg-filtergraph-path-escaping]] — a value interpolated into a
structured text format without regard for that format's separators.

## Latent relative: `force_style_string`

`force_style_string` has **no production caller** today; only a unit test
exercises it. Its docstring states that "callers embedding this in an ffmpeg
filtergraph must single-quote the value" — a contract nothing currently
honours because nothing currently calls it. If it is ever wired into a
burn-in path, that single-quoting is required, and the value additionally
needs the filtergraph escaping described in
[[ffmpeg-filtergraph-path-escaping]].
