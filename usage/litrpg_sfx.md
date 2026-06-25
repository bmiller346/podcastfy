# LitRPG Cinematic Audio Cues

Podcastfy can now parse semantic cinematic audio tags into cue sheets and future
mixdown plans. This is metadata only: no asset lookup or audio rendering is
required yet.

## Cue Syntax

Use bracket tags inside the script:

```text
[BGM_START: battle volume=-10db duck=true]
<NARRATOR>The arena doors opened.</NARRATOR>
<SYSTEM>[SFX: ui quest pan=left]QUEST UPDATED.</SYSTEM>
[AMBIENCE_START: dungeon volume=-18db]
<HERO>I hate bonus objectives.</HERO>
[AMBIENCE_STOP]
[BGM_STOP]
```

Supported tags:

- `[BGM_START: tag]`: start a looping music bed.
- `[BGM_STOP]`: fade out the active music bed.
- `[SFX: tag]`: trigger a one-shot sound effect.
- `[AMBIENCE_START: tag]`: start a looping ambience bed.
- `[AMBIENCE_STOP]`: fade out the active ambience bed.

Optional modifiers are stored on cue metadata:

- `pan=left`, `pan=right`, `pan=center`, `pan=wide`
- `volume=-6db`
- `duck=true` or `duck=false`

## Python Helpers

```python
from podcastfy.litrpg.sfx import (
    build_mix_plan,
    map_assets_for_cue_sheet,
    parse_cue_sheet,
)

cue_sheet = parse_cue_sheet(script)
asset_mappings = map_assets_for_cue_sheet(cue_sheet)
mix_plan = build_mix_plan(cue_sheet, asset_mappings=asset_mappings)
```

`cue_sheet.clean_script` is the script with bracket audio tags removed. The
original cue order, source offsets, clean-script offsets, line numbers, semantic
tags, and modifiers remain available in `cue_sheet.cues`.

## Future Mixdown Architecture

The current mix plan is deterministic metadata for a later renderer:

- Dialogue remains the priority layer.
- Music and ambience beds can duck under dialogue.
- SFX can carry placement, panning, volume, and ducking hints.
- EQ intent is recorded as plain metadata for future mixer presets.
- Timing anchors use clean-script character offsets until renderer timestamps
  become available.

Asset mapping returns local candidate paths such as
`assets/litrpg/sfx/sword_clash.wav`, but it does not require those files to
exist. A future mixer can choose the first available candidate or apply richer
asset selection rules.
