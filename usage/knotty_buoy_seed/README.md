# Knotty Buoy Canonical Seed

This directory contains source fixtures for bootstrapping **The Knotty Buoy**.
They are canonical input data, not generated chapter prose.

## Files

- `knotty_buoy_canonical_seed.json`: machine-readable source fixture for
  Edward, Kelli, Pedro, Sophie II / The Knotty Buoy, Floor 1, Gallowgate, the
  Grand Dredger, Pedro's available phrase vocabulary, and the 30-chapter Book 1
  outline.
- `../knotty_buoy_premise_intake.example.json`: task file that runs premise
  intake against the Markdown seed.
- `../litrpg_messy_context_seed.md`: paste-ready canonical context for UI or
  premise intake.

## Bootstrap

From the repository root:

```bash
python -m podcastfy.litrpg.task usage/knotty_buoy_premise_intake.example.json
```

The task writes generated story-engine artifacts under
`library/series/knotty-buoy` (or the configured storage directory). Review those
artifacts before generating chapters.

## Fixture Discipline

- Keep this package as seed/source data.
- Do not commit final story chapter prose here.
- Preserve canonical names: Edward Marsh, Kelli Marsh, Pedro, Sophie II, The
  Knotty Buoy, Gallowgate, Grand Dredger, and Floor 1: The Drowned Scaffolding.
- Add new Pedro phrases only when they come from accepted premise source notes,
  and keep their category explicit.
