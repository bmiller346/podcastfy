# LitRPG Series Packages

A series package is a style-bible seed for a generated audio serial. It sits between the raw premise and the chapter generator:

```text
Premise -> Series Bible -> Role/Performance Packages -> Chapter Plan -> Script -> Audio
```

Use it to store reusable voice, role, setting, and mechanics guidance that should survive across chapters. It is not final story prose. It is a regression fixture and prompt baseline.

The series bible answers what must remain true: premise, tone contract, character facts, floor rules, factions, world mechanics, and portrayal guardrails. Role/performance packages answer how each reusable voice should behave in the audio pipeline: vocal identity, delivery rules, sample lines, effect hints, and lines the system should avoid.

The chapter generator should consume only the pieces it needs for the current scene. For example, a part with a quest popup should receive the compact premise, active character packages, relevant floor rules, and the System Announcer package, not every stored artifact in the series.

## Catamaran Crawlers Example

`usage/litrpg_catamaran_crawlers_package.example.json` demonstrates the target shape for *The Catamaran Crawlers*. It includes:

- `system_announcer`: the reusable System/Announcer voice package.
- `characters`: Edward and Kelli role packages.
- `familiar`: Pedro's familiar package.
- `home_base`: the catamaran as a dungeon asset.
- `floor_rules`: Floor One rules and first boss vulnerability.
- `faction_map`: early faction pressure.
- `prompt_summary`: compact text suitable for injection into generation prompts.

The System Announcer package is based on the generated baseline artifact for "The Interface." Treat it as a high-quality seed: useful for style, delivery, and examples, but still editable before production. See `usage/litrpg_announcer_seed.md` for the sanitized seed guidance.

## Sensitive Portrayal Note

Kelli's bipolar traits should be handled as human character context, not as a joke or a magic-power shortcut. The example separates her dungeon mechanics from the diagnosis and includes guardrails to preserve agency, competence, and consequences.

## Expected Storage

When the packages API is available, this artifact should save under:

```text
data/litrpg/series/<series_id>/series_package.json
```

Until then, the checked-in JSON fixture can be loaded directly by tests or by the UI diagnostics flow.

## Suggested Prompt Use

For generation, inject the compact summary plus the role-specific package needed for the current scene. Avoid stuffing the entire package into every prompt once the package grows. A chapter part usually needs:

- the `prompt_summary`
- the active character packages
- the `system_announcer` performance rules when SYSTEM lines are expected
- relevant `floor_rules`
- relevant faction entries

This keeps context focused while preserving continuity.
