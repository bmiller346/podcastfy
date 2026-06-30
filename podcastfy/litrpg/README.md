# LitRPG Story Engine Architecture

The LitRPG pipeline enforces scarcity as structure, not taste. Every major component either plans what cannot be spent yet or enforces that plan against generated prose. Long-form tension depends on this: mysteries, character growth, artifact power, visual signatures, relationship shifts, and endgame truth all need durable constraints so a satisfying moment in one chapter does not accidentally burn the series.

## Tier Map

Tier 0 is persistent story memory. It stores durable facts that future chapters must obey: world state, artifact identity, character arcs, relationships, and long-horizon mysteries.

Tier 1 is planning. The Series Architect, Conspiracy Engine, Character Arc Engine, and Artifact Registry decide what is available now, what is locked, and what may only be hinted.

Tier 2 is pre-prose rendering context. Scene briefs, arc pressure, faction mechanics, artifact contracts, and forbidden revelation lists are converted into compact instructions the prose generator can obey.

Tier 3 is generation and audits. `chapter.py` orchestrates prose generation, audit passes, optional rewrites, render preparation, and state update prompts.

Tier 4 is persistence after generation. World state, emotional arcs, and artifact state are updated only from final-script deltas that were established on page.

The tier boundary matters most for conspiracy handling: the truth document lives behind `conspiracy_engine.py` and is never injected into prose generation. Downstream layers receive only safe reader position, allowed hints, faction constraints, and forbidden revelations.

## Core Components

- `world_state.py` - single source of truth for sensory state, scene brief inputs, active mysteries, visual budget, and artifact locks.
- `character_arc.py` - character arc pressure, relationship graph context, and post-chapter emotional arc writer.
- `conspiracy_engine.py` - revelation ladder and reader position tracking; truth document never enters prose context.
- `artifact_registry.py` - locked item identity, physical signatures, power ceilings, and scarce artifact state tracking.
- `chapter.py` - orchestration; runs generation and audit stages, returns update payloads, and does not directly write upstream state.

## How Constraints Reach Prose

The prose generator does not need to know which planner produced a constraint. It sees a unified scene and story context:

- world-state mystery locks become scene brief `forbidden` entries
- conspiracy forbidden revelations become scene brief `forbidden` entries
- artifact forbidden aliases become scene brief `forbidden` entries
- character wound, coping-mode, and relationship locks enter `story_engine_context`
- artifact locked names, physical signatures, resource state, and power ceilings enter the scene brief and scene brief context

This keeps access rules simple. The prose layer receives what it may render and what it must not spend, but it does not receive hidden truth documents or off-page planner state.

## Audit Chain

When reviews are enabled, `chapter.py` runs the post-generation checks in this order:

1. `visual_state_update`
2. `hook`
3. `scarcity_audit`
4. optional `rewrite:scarcity:*` attempts, followed by another `scarcity_audit`
5. `rhythm`
6. `reader_proxy`
7. `scene_rendering_audit`

`scarcity_audit` can quarantine or trigger scarcity rewrites. `scene_rendering_audit` currently records whether prose obeyed the scene brief and persistent rendering contracts; it is store/report only, not a quarantine gate.

## State Writers

Post-chapter writers extract only durable changes from the final script:

- `build_world_state_update_prompt()` updates sensory state, locations, artifacts, mysteries touched, rules, and visual budget.
- `build_arc_state_update_prompt()` updates emotional events, coping modes, wounds, and relationship states.
- `build_artifact_state_update_prompt()` updates new artifacts, resource spend, condition, ownership, location, and artifact uses.

Writers preserve scarcity. They should not invent off-page repairs, refills, emotional breakthroughs, new powers, or mystery confirmations.

## Out Of Scope For This Subsystem Map

- Music and atmosphere planning.
- A standalone continuity validator beyond the current audit/context passes.
- A dedicated pacing rhythm controller beyond the existing rhythm review.
- Full UI or installation documentation.
- Function-level API reference.
