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

## Asset Manifest

The production path is a curated manifest rather than model free-choice. A
starter schema lives at `assets/litrpg/asset_manifest.json`:

```json
{
  "stem": "sfx/ui_chime",
  "tags": ["ui", "quest", "notification"],
  "cue_types": ["sfx"],
  "loopable": false,
  "default_lufs": -18,
  "intensity": 3,
  "pan_safe": true,
  "transient": true,
  "source": "curated_placeholder",
  "trusted": false
}
```

Load it with:

```python
from podcastfy.litrpg.sfx import load_asset_manifest

library = load_asset_manifest("assets/litrpg/asset_manifest.json")
asset_mappings = map_assets_for_cue_sheet(cue_sheet, asset_library=library)
```

Generated or placeholder assets should remain `trusted: false` until reviewed.

## Local AI Fallback Policy

`generate_sfx_candidate(...)` is intentionally metadata-only. It records an
untrusted local AI-generation request without calling a paid API or claiming the
asset is ready. The intended production loop is:

1. Try curated trusted assets.
2. If none match, create a local generation request, for example with
   AudioGen/AudioCraft.
3. Cache the generated sound.
4. Review, normalize, tag, and mark it trusted before final mix use.

The default fallback provider metadata is `local_audiogen`, with model metadata
set to `audiogen-medium`. This is a placeholder for a future local generator,
not a network call.

## Mix Plan Issues

`build_mix_plan(...)` reports structural problems in `mix_plan["issues"]`. For
example, `[BGM_STOP]` before `[BGM_START: ...]` produces a visible issue instead
of silently leaving a null automation target.
