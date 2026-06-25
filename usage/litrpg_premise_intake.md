# LitRPG Premise Intake

Premise intake turns a loose pitch, pasted outline, or messy brainstorming dump into
the structured files the story engine reads before it writes chapters. Paste the
whole premise directly, or point at a text file with `premise_path` when the notes
are too large for a JSON task.

MCP is only the control surface. Story logic lives in
`podcastfy/litrpg/premise_intake.py`, and the MCP wrapper calls
`run_premise_intake` instead of duplicating that logic.

If you are using the local UI, paste messy notes into the Messy Context Intake
panel. The UI can fill the story fields, queue a `premise_intake` job, or copy
the equivalent MCP `bootstrap_from_premise` payload for another agent. The UI
path and MCP path share the same backend; MCP is not a separate place where you
must manually paste story context.

## What It Writes

Given `storage_dir` and `series_id`, intake can seed:

- `series_plan.json`
- `series_arc.json`
- `book_N/book_plan.json`
- `book_N/tempo_map.json`
- `book_N/chapter_outline.json`
- `story_bible.json`
- `voice_cards.json`
- `continuity_ledger.json`
- `emotional_arcs.json`
- `world_register.json`
- `foreshadow_ledger.json`

## Task Mode

Create a task with:

```json
{
  "mode": "premise_intake",
  "series_id": "knotty-buoy",
  "storage_dir": "library",
  "series_title": "The Knotty Buoy",
  "target_books": 1,
  "chapters_per_book": 30,
  "book_length_mode": "tight",
  "arc_style": "escalating_floor_survival",
  "premise": "Paste the entire premise dump here.",
  "generation": {
    "provider": "hybrid",
    "ollama_model": "dolphin3",
    "commercial_model": "gpt-5.5"
  }
}
```

Then run:

```bash
python -m podcastfy.litrpg.task usage/litrpg_premise_intake.example.json
```

The Knotty Buoy seed package keeps the large premise in a Markdown file and
points intake at it with `premise_path`. The upgraded paste-ready seed is
`usage/litrpg_messy_context_seed.md`; it includes the family-distance rule,
floor biome chassis rule, boat specs, Pedro phrase manifest, and Floor 1 world
register:

```bash
python -m podcastfy.litrpg.task usage/knotty_buoy_premise_intake.example.json
```

Use `premise_path` instead of `premise` when the notes are too large for the task file:

```json
{
  "mode": "premise_intake",
  "series_id": "knotty-buoy",
  "storage_dir": "library",
  "premise_path": "usage/knotty-buoy-outline.md",
  "target_books": 3,
  "chapters_per_book": 30,
  "generation": {
    "provider": "openai",
    "model": "gpt-5.5"
  }
}
```

For a local or hybrid pass, set `generation.provider` to `ollama` or `hybrid`.
Hybrid generation uses local stages where configured and OpenAI for the commercial
fallback:

```json
{
  "generation": {
    "provider": "hybrid",
    "ollama_model": "dolphin3",
    "commercial_model": "gpt-5.5",
    "local_exact_stages": ["script"],
    "local_stage_prefixes": ["part:", "revise:"]
  }
}
```

## MCP Tool Surface

`podcastfy.litrpg.mcp_server` can be imported without the optional Python MCP SDK.
Install the SDK only when you want to run it as an MCP server.

Available tools:

- `bootstrap_from_premise`: accepts `storage_dir`, `series_id`, `premise` or
  `premise_path`, series shape fields, and `generation`; returns written files and
  artifact paths.
- `get_chapter_contract`: reads the saved series architecture for one book/chapter.
- `list_series_artifacts`: lists JSON artifacts under `storage_dir/series/{series_id}`.
- `run_litrpg_task`: optional pass-through for an inline task or task file.

## Recommended Use

Run intake once when starting a series, review the generated JSON, then generate
chapters through normal chapter mode. Chapter generation reads the saved series
plan, book plans, chapter outlines, story bible, voice cards, continuity ledger,
world register, emotional arcs, and foreshadow ledger from the same
`storage_dir/series/{series_id}` tree.

Re-run intake with `merge_existing: true` when you add a large new outline or
author notes bundle. Use `merge_existing: false` only when you want the generated
payload to replace mergeable context for that series.
