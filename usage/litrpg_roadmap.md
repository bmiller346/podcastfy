# LitRPG Story Engine Roadmap

This roadmap captures the next systems needed for the LitRPG audio engine to become self-correcting before spending money on final TTS renders.

The near-term build priority is the chapter review and rewrite loop:

```text
draft -> director tags -> mechanics audit -> tonal audit -> showmanship audit -> revised script -> render-ready script
```

## Current Build Slice: Chapter Review and Rewrite Loop

Status: implemented for chapter-mode generation.

Current entry points:

- `podcastfy/litrpg/chapter.py`
- `podcastfy/litrpg/production.py`
- `tests/test_litrpg_chapter.py`
- `tests/test_litrpg_production.py`

Implemented behavior:

- Each chapter part is generated independently.
- Existing good parts can be supplied through `locked_part_scripts`.
- Review stages run per part when reviews are enabled.
- The generated result stores draft script, review text, director tags, audits, revision prompt, revised script, and deterministic gate output.
- Raw director, mechanics, tonal, and showmanship artifacts are promoted into a top-level structured `qa` summary.
- The final combined script uses the revised script when present.
- `render.ready` is aligned with `qa.ready`, which includes deterministic final gates and blocking audit verdicts.

Review stages:

- `review:{part_id}`: general part review.
- `director:{part_id}`: performance intent tags.
- `mechanics:{part_id}`: LitRPG mechanics audit.
- `tonal:{part_id}`: absurdity/stakes scoring.
- `showmanship:{part_id}`: crowd and sponsor simulation.
- `revise:{part_id}`: render-ready rewrite.
- `chapter_review`: final whole-chapter production review.

Task controls:

- `reviews.enabled`: disables all review passes when false.
- `reviews.rewrite`: disables the revision pass when false.
- `revision_enabled`: top-level fallback for enabling/disabling revision.
- `locked_part_scripts`: map of `part_id` to a trusted script that should not be regenerated.

## 1. Director Pass

Status: first version implemented.

Purpose: mark performance intent without rewriting prose for prettiness.

Required output concepts:

- `emotion`: panic, dry irritation, triumph, disgust, grief, dread, awe.
- `delivery`: whisper, bark, deadpan, breathless, smug, clipped.
- `timing`: beat, long pause, interrupt, overlap, hard stop.
- `audio_effect`: announcer slapback, radio filter, crowd swell, dungeon reverb, UI chime.

Current implementation:

- `build_director_pass_prompt(...)` in `podcastfy/litrpg/production.py`.
- Stored per part as `director_prompt` and `director_tags`.
- Fed into `build_part_revision_prompt(...)`.

Next acceptance criteria:

- Parse director output into structured data instead of storing only raw model text.
- Preserve cue ordering against role-tagged script lines.
- Pass director cues into the audio renderer or casting manifest.

## 2. Continuity Bible

Status: foundation implemented and wired into chapter prompts.

Purpose: track who characters are becoming, separate from stats and game state.

Bible fields:

- character wounds and trauma
- running jokes
- rivalries
- unresolved promises
- favorite insults
- never-contradict facts
- character voice rules

Likely implementation:

- Add a `StoryBible` model or JSON schema near `podcastfy/litrpg/models.py`.
- Store per-series bible data next to `series_state.json`.
- Feed bible summaries into chapter part prompts, audits, and final chapter review.
- Add a continuity audit that checks draft/revised parts against bible facts.

Current implementation:

- `podcastfy/litrpg/bible.py` stores `story_bible.json` per series.
- `StoryBible` and `CharacterBibleEntry` keep continuity separate from stats and game state.
- Load/save helpers return safe defaults when no bible exists.
- Merge helpers append extracted updates without wiping existing facts.
- Compact summary formatting is injected into chapter part and mechanics-audit prompts.
- Chapter tasks with `storage_dir` automatically load per-series bible context.

Acceptance criteria:

- A chapter can update the bible after generation.
- A later chapter prompt receives compact bible context.
- Review output can block render when a never-contradict fact is violated.

## 3. Mechanics Validator

Status: deterministic validator implemented and wired into chapter gates.

Purpose: protect LitRPG credibility with deterministic checks.

Current implementation:

- `_deterministic_part_gate(...)` checks missing required role tags.
- `_deterministic_part_gate(...)` uses `validate_mechanics(...)` for audible mechanics and contradiction checks.
- `build_mechanics_audit_prompt(...)` asks an LLM to audit XP, loot, cooldowns, stats, inventory, quests, and earned abilities.
- `podcastfy/litrpg/mechanics.py` extracts structured mechanics events from role-tagged scripts.
- `validate_mechanics(...)` accepts prior XP, inventory, skills, class, cooldowns, and known tools.
- Chapter tasks with `storage_dir` seed mechanics context from `series_state.json`.
- Deterministic checks catch missing audible mechanics, consumed or removed items without inventory, XP total decreases without XP spend, unavailable skill/class abilities, and cooldown bypasses.

Next acceptance criteria:

- Carry validated mechanics deltas back into persistent series state.
- Keep LLM mechanics audit as an explanatory layer, not the sole source of truth.

## 4. Absurdity and Stakes Score

Status: structured parsing implemented.

Purpose: prevent chapters from becoming only goofy or only grim.

Current implementation:

- `build_tonal_audit_prompt(...)` requests:
  - `stakes_seriousness`
  - `absurdity_pressure`
  - `verdict`
  - concrete fixes
- Tonal audit output feeds the revision prompt.
- `podcastfy/litrpg/qa.py` parses tonal scores and pass/revise/block verdicts from JSON or plain audit text.

Next acceptance criteria:

- Define configurable target ranges.
- Trigger revision or block render when scores fall outside the target range.

## 5. Crowd and Sponsor Simulator

Status: structured parsing implemented.

Purpose: make dungeon showmanship affect rewards, announcements, punishments, and complications.

Current implementation:

- `build_showmanship_audit_prompt(...)` scores:
  - crowd engagement
  - brutality
  - creativity
  - humiliation
  - meme potential
  - sponsor appeal
- The audit can recommend awards or complications.
- Showmanship output feeds the revision prompt.
- `podcastfy/litrpg/qa.py` parses crowd engagement, brutality, creativity, humiliation, meme potential, sponsor appeal, and pass/revise/block verdicts from JSON or plain audit text.

Next acceptance criteria:

- Feed rewards or complications into the next part prompt.
- Persist sponsor/crowd reactions in episode metadata or series state.

## 6. Audio Casting Manifest

Status: implemented for casting manifest parsing and director cue overlay.

Purpose: preserve character voice identity while allowing performance evolution.

Target shape:

```json
{
  "character": "Hero",
  "voice": "cedar",
  "baseline": {
    "pace": 0.95,
    "pitch": -2,
    "delivery": "dry, exhausted, grounded"
  },
  "arc_modifiers": {
    "trauma": 0.4,
    "confidence": 0.2,
    "rage": 0.1
  }
}
```

Existing touchpoints:

- `podcastfy/litrpg/casting.py`
- `usage/litrpg_casting.example.json`

Implemented behavior:

- Store per-character baseline and arc modifiers.
- Apply director cues without replacing the character's baseline identity.
- Clamp/default arc modifiers so invalid manifest values do not crash generation.
- Accept both older `voice_profile` cast plans and the target top-level manifest shape.

Next acceptance criteria:

- Keep casting changes subtle across chapters unless the story bible justifies a larger shift.
- Pass chapter render role instructions into the eventual chapter audio renderer.

## 7. Cinematic Audio and SFX

Status: foundation implemented for cue sheets and metadata-only mix planning.

Purpose: let scripts carry semantic cinematic audio intent without requiring final
assets or a real mixer during story generation.

Supported script tags:

- `[BGM_START: tag]`
- `[BGM_STOP]`
- `[SFX: tag]`
- `[AMBIENCE_START: tag]`
- `[AMBIENCE_STOP]`

Implemented behavior:

- `podcastfy/litrpg/sfx.py` parses ordered audio cues from bracket tags.
- Parsed cue sheets include cleaned script text with bracket audio tags removed.
- Cue modifiers such as `pan=left`, `volume=-6db`, and `duck=true` are stored as metadata.
- Semantic tags map to deterministic local asset candidates under an asset root without requiring files to exist.
- Mix plans describe dialogue, music, ambience, and SFX layers with ducking, panning, EQ intent, and timing anchors.

Current entry points:

- `parse_cue_sheet(...)`
- `map_assets_for_cue(...)`
- `map_assets_for_cue_sheet(...)`
- `build_mix_plan(...)`
- `tests/test_litrpg_sfx.py`

Next acceptance criteria:

- Cue sheets, asset mappings, and mix plans are attached to chapter render output.
- Convert clean script offsets into renderer timestamps after TTS segmentation.
- Add an actual mixer that resolves selected assets and renders a final stem.

## 8. Chapter QA Gate

Status: top-level QA summary implemented.

Purpose: avoid rendering audio for chapters that need structural revision.

Current implementation:

- Part-level gates are stored under each part as:
  - `gate.draft`
  - `gate.final`
  - `gate.ready`
- Chapter-level `render.ready` is false if any part final gate fails.
- Chapter-level `qa` includes per-part summaries, parsed audit scores/verdicts, blocking issues, and revision targets.
- `render.ready` is false when `qa.ready` is false.

Target gates:

- continuity pass
- mechanics pass
- tonal pass
- showmanship pass
- audio-readiness pass

Next acceptance criteria:

- Add audio-readiness checks for role tags, unsupported style attributes, overlong lines, and missing casting information.
- Render only when all required gates pass or an explicit force flag is present.

## 9. Regenerate by Part, Not Whole Chapter

Status: helper-backed task reuse implemented; UI/status surfacing still pending.

Purpose: make iteration usable and cost-aware.

Current implementation:

- Chapter generation is already part-based.
- `locked_part_scripts` lets callers keep good parts and only regenerate missing or weak parts.
- `locked_part_scripts_from_ready_parts(...)` reads a prior chapter result dict or JSON file and returns locks for parts with ready final gates or QA state.
- Chapter tasks can set `reuse_ready_parts_from` or `lock_ready_parts_from` to lock ready parts from a previous result before generation.
- Explicit `locked_part_scripts` in a task override automatically reused locks for the same part.
- The combined render script is assembled from per-part final scripts.

Next acceptance criteria:

- Preserve prior audit artifacts for locked parts.
- Surface part-level status in the local UI.

## Recommended Next Build Slice

Build the structured QA layer on top of the current raw review artifacts.

Suggested order:

1. Parse director, mechanics, tonal, and showmanship outputs into structured JSON with retry.
2. Add a top-level `qa` summary to chapter results.
3. Add deterministic audio-readiness validation.
4. Add a reuse helper that locks passing parts from a prior chapter result.
5. Add continuity bible storage and continuity audit.

This keeps the engine focused on judgment and self-correction before voice polish.
