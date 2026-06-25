# LitRPG Episode Library APIs

`podcastfy.litrpg.library` provides UI-friendly filesystem helpers for browsing
and replaying local LitRPG episode bundles. The functions are independent of the
task runner and TTS providers; they read the bundle layout produced by
`EpisodeStore`.

## Storage Shape

The current bundle layout is:

```text
<storage_dir>/
  episodes/<series_id>/<episode_id>/
    metadata.json
    config.json
    prompt.txt
    script.xml or script.json
    audio_metadata.json
    audio/final.mp3
  series/<series_id>/series_state.json
```

Future chapter or part bundles can add files such as `parts/part-0001.xml`.
The library detects script and part files through `metadata.json` and common
part file locations.

## API Shape

```python
from podcastfy.litrpg.library import (
    delete_episode,
    get_audio_path,
    get_episode,
    list_episodes,
    list_regenerable_parts,
    list_series,
    mark_episode_status,
)
```

- `list_series(storage_dir)` returns series summaries with `series_id`, `title`,
  `episode_count`, `incomplete_count`, paths, and loaded state metadata when
  present.
- `list_episodes(storage_dir, series_id=None)` returns episode records across
  all series or one series.
- `get_episode(storage_dir, series_id, episode_id)` returns one episode record
  or `None`.
- `get_audio_path(storage_dir, series_id, episode_id)` returns a safe existing
  audio file path for replay, or `None`.
- `mark_episode_status(storage_dir, series_id, episode_id, status)` writes one
  of `complete`, `incomplete`, `missing_audio`, or `failed_render` into
  `metadata.json`.
- `delete_episode(storage_dir, series_id, episode_id)` removes one bundle
  directory and returns `True` when it deleted something.
- `list_regenerable_parts(storage_dir, series_id, episode_id)` returns script or
  part files a UI can expose for targeted regeneration.

Episode records include:

```python
{
    "series_id": "paper-cuts",
    "episode_id": "episode-0001",
    "episode_number": 1,
    "status": "complete",
    "path": ".../episodes/paper-cuts/episode-0001",
    "audio_path": ".../audio/final.mp3",
    "metadata": {...},
    "config": {...},
    "audio_metadata": {...},
    "files": {"script": ".../script.xml"},
    "regenerable_parts": [...],
}
```

## Status Inference

Status is inferred from bundle contents unless a failed render is explicitly
recorded.

- `complete`: metadata, config, script or part files, and safe audio are present.
- `missing_audio`: the bundle has metadata/config/script but no safe audio file.
- `incomplete`: required bundle files are missing.
- `failed_render`: metadata or audio metadata contains a failed render status or
  error field.

## Safety

All returned audio paths and file paths must resolve under `storage_dir`.
Path traversal IDs such as `..` are rejected, and unsafe audio paths in
`audio_metadata.json` are ignored. `delete_episode` only deletes a resolved
episode directory inside `storage_dir`.

## Future UI Notes

A library screen can call `list_series()` for the left navigation,
`list_episodes()` for a series timeline, `get_episode()` for an inspector panel,
and `get_audio_path()` for replay. Regeneration controls can start with
`list_regenerable_parts()` and pass the selected part path to a future chapter
renderer without coupling the UI to the TTS provider.
