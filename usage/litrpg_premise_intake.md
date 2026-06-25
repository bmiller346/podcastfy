# LitRPG Premise Intake

Premise intake turns a loose pitch, pasted outline, or messy brainstorming dump into
the structured files the story engine reads before it writes chapters.

It is the MCP-shaped boundary for the project: a future MCP tool can pass the same
inputs to `run_premise_intake` and receive the same written artifact paths.

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

Use `premise_path` instead of `premise` when the notes are too large for the task file.

## Recommended Use

Run intake once when starting a series, review the generated JSON, then generate
chapters through the normal chapter mode. Re-run intake with `merge_existing: true`
when you add a large new outline or author notes bundle.
