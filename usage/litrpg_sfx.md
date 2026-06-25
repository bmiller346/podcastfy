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
from podcastfy.litrpg.sfx_mix import (
    normalize_mix_plan_defaults,
    select_asset_candidates,
    validate_mix_plan,
)

cue_sheet = parse_cue_sheet(script)
asset_mappings = map_assets_for_cue_sheet(cue_sheet)
mix_plan = normalize_mix_plan_defaults(
    build_mix_plan(cue_sheet, asset_mappings=asset_mappings)
)
validation = validate_mix_plan(
    mix_plan,
    asset_mappings=asset_mappings,
    final_mode=False,
)
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

`select_asset_candidates(...)` applies the deterministic selection rules used by
the validation layer. It respects declared `cue_types`, keeps stop cues out of
asset selection, and prefers `trusted: true` assets when manifest metadata is
available:

```python
selected_paths = select_asset_candidates(
    asset_mappings,
    cue_type="bgm_start",
    semantic_tag="battle",
    max_candidates=2,
)
```

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
  "trusted": false,
  "license": "placeholder_not_for_production",
  "attribution": "Podcastfy starter manifest placeholder"
}
```

Load it with:

```python
from podcastfy.litrpg.sfx import load_asset_manifest

library = load_asset_manifest("assets/litrpg/asset_manifest.json")
asset_mappings = map_assets_for_cue_sheet(cue_sheet, asset_library=library)
```

Generated or placeholder assets should remain `trusted: false` until reviewed.

### Curating Local Assets

Use `podcastfy.litrpg.sfx_manifest` to manage the editable manifest:

```python
from podcastfy.litrpg.sfx_manifest import (
    AssetManifest,
    add_or_promote_asset,
    load_asset_manifest_file,
    save_asset_manifest_file,
    scan_asset_directory,
)

manifest = load_asset_manifest_file("assets/litrpg/asset_manifest.json")
candidates = scan_asset_directory("assets/litrpg")

manifest = add_or_promote_asset(
    manifest,
    {
        "stem": "sfx/sword_clash",
        "tags": ["sword", "clash", "metal"],
        "cue_types": ["sfx"],
        "loopable": False,
        "default_lufs": -18,
        "intensity": 7,
        "pan_safe": True,
        "transient": True,
        "source": "curated_local",
        "trusted": True,
        "license": "CC0",
        "attribution": "",
    },
    promote=True,
)
save_asset_manifest_file(manifest, "assets/litrpg/asset_manifest.json")
```

The scanner finds `.wav`, `.mp3`, and `.ogg` files, derives filename tags, and
marks candidates untrusted. Promotion merges by stem, de-duplicates tags and cue
types, and records the reviewed license/attribution metadata.

## Local AI Fallback Policy

`generate_sfx_candidate(...)` is intentionally metadata-only. It records an
untrusted local AI-generation request without calling a paid network service or
claiming the asset is ready. The intended production loop is:

1. Try curated trusted assets.
2. If none match, create a local generation request, for example with
   AudioGen/AudioCraft.
3. Cache the generated sound.
4. Review, normalize, tag, and mark it trusted before final mix use.

The default fallback provider metadata is `local_audiogen`, with model metadata
set to `audiogen-medium`. This is a placeholder for a future local generator,
not a network call.

For queue-oriented workflows, use `podcastfy.litrpg.sfx_generation` directly:

```python
from podcastfy.litrpg.sfx_generation import (
    create_generation_request,
    promote_generated_asset_request,
)

request = create_generation_request(
    "sword clash",
    cue_type="sfx",
    duration_seconds=2,
    write_sidecar=True,
)
```

The request JSON is written under `assets/litrpg/generated/requests` by
default. It includes:

- semantic tag and cue type
- concrete local generation prompt
- configurable provider and model
- duration and deterministic cache path
- `status`
- `trusted: false`

Prompt construction avoids music for one-shot SFX. Music is only requested for
`bgm_start`; `ambience_start` requests a loopable environment bed without
melody or vocals.

When a separate local worker eventually creates a file, convert it into
manifest-ready metadata without trusting it:

```python
entry = promote_generated_asset_request(request, "assets/litrpg/generated/audio/sword.wav")
assert entry["trusted"] is False
```

Generated entries should stay `trusted: false` until a human review pass checks
content, loudness, loopability, licensing, and dialogue safety.

## Mix Plan Issues

`build_mix_plan(...)` reports structural problems in `mix_plan["issues"]`. For
example, `[BGM_STOP]` before `[BGM_START: ...]` produces a visible issue instead
of silently leaving a null automation target.

`validate_mix_plan(...)` is the deterministic pre-mix gate. It does not render
audio or check that files exist; it checks whether the plan is mixable from its
metadata.

Blocking issues:

- missing assets on music, ambience, or SFX layers
- untrusted assets when `final_mode=True`
- stop automations without target layers
- non-loopable assets selected for music or ambience beds

Warnings:

- loud SFX over dialogue risk
- missing ducking on music or ambience beds

`normalize_mix_plan_defaults(...)` fills safe defaults for missing `volume`,
`ducking`, and `pan` fields before validation or eventual rendering. The helper
returns a copy and leaves the original plan unchanged.
