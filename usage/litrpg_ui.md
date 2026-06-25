# LitRPG Local UI

Run the small local LitRPG UI from the repository root:

```bash
python -m podcastfy.litrpg.ui --host 127.0.0.1 --port 8765
```

Then open http://127.0.0.1:8765/.

The UI can:

- Save local provider keys and default provider/model settings.
- Build a local LitRPG task payload with series, premise, provider, TTS, and storage settings.
- Save, load, or generate a reusable series package/style bible for a premise.
- List `usage/litrpg*.json` task files.
- Run a selected task through `podcastfy.litrpg.task.run_litrpg_task`.
- Submit a selected task as a tracked background job and poll status/result metadata.
- Browse saved episodes under `data/litrpg` and play saved audio files.
- Query series, episode, and replay metadata through JSON endpoints.

## Task Builder

The Create Task panel is meant for local experimentation without hand-editing a task file first. It covers:

- `series_id` and `premise`
- `mode` as `episode` or `chapter`
- story generation `provider` and `model`
- TTS `provider`, `model`, and `format`
- `render_audio`
- `result_path`, `checkpoint_dir`, and `storage_dir`

The browser builds a JSON payload that matches the LitRPG task schema and submits it to the local jobs API. The preview box shows the exact task object before it is queued.

## Messy Context Intake

Use the Messy Context Intake panel when you have a rough notes dump, copied chat context, chapter outline, character list, or half-structured premise. Paste the whole thing there first.

- **Fill Story Fields** infers a title/series id, switches the task to `premise_intake`, fills the visible premise summary, disables audio, and copies the full raw dump into the Series Package baseline text.
- **Queue Intake Agent** does the same setup and immediately submits the `premise_intake` job. The queued task includes the full raw dump as `source_text`, so the intake pass sees more than the shortened visible premise field.
- **Copy MCP Context** copies a `bootstrap_from_premise` tool payload for MCP clients or agent shells. Use this when another agent is driving the MCP server directly instead of clicking through the local UI.

In normal use, you do not paste messy notes into MCP by hand. MCP is the tool layer agents call. The local UI is the human-friendly paste surface, and both paths end up calling the same premise-intake code.

## Series Package Workflow

The Series Package panel sits between premise drafting and chapter generation. It is meant for reusable story and performance context such as:

- system announcer voice and sample lines
- character and familiar packages
- home base details
- floor rules
- faction map
- baseline text from an external brainstorming pass

Saved packages live under:

```text
data/litrpg/series/<series_id>/series_package.json
```

The UI can load and save a draft package even before the full package generator is installed. When `podcastfy.litrpg.package_generator.generate_series_package` is available, the Generate Package button calls it and saves the result.

Package API:

```http
GET /api/series-package?series_id=catamaran-crawlers
POST /api/series-package
POST /api/series-package/generate
```

Generate payload:

```json
{
  "series_id": "catamaran-crawlers",
  "premise": "Edward and Kelli Marsh get absorbed into the World Dungeon with their catamaran and macaw.",
  "baseline_text": "Optional announcer package or voice notes.",
  "save": true
}
```

If the generator module is not installed yet, `/api/series-package/generate` returns `503` with `status: "generator_unavailable"`. The diagnostics report also includes package readiness and whether package storage/generation helpers are currently available.

## Diagnostics

The Diagnostics panel builds a copyable JSON report from the current task, redacted settings status, latest job metadata, and replay-library counts. Paste that report into a review thread when you want help diagnosing generation quality, missing provider keys, checkpoint output, QA status, or replay readiness.

The premise analysis is intentionally lightweight. It checks for useful LitRPG story hooks such as reluctant protagonist, chaos partner, nonhuman cast member, home base, mechanics, setting flavor, and practical problem solving. It also flags sensitive portrayal terms so the story can keep those characters specific and non-caricatured.

Diagnostics include the loaded package summary, package path, and helper availability so you can copy one report that covers both the task and the style-bible state.

## Job API

The synchronous endpoint is still available:

```http
POST /api/run-task
Content-Type: application/json

{"path": "usage/litrpg_task.example.json"}
```

For one-click generation from the UI, prefer the tracked job API:

```http
POST /api/jobs
Content-Type: application/json

{
  "task": {
    "mode": "episode",
    "series_id": "paper-cuts",
    "premise": "A warehouse clerk discovers the forklift training course is a dungeon tutorial.",
    "render_audio": true,
    "storage_dir": "../data/litrpg",
    "generation": {
      "provider": "openai",
      "model": "gpt-5.5"
    },
    "tts": {
      "provider": "openai",
      "model": "gpt-4o-mini-tts",
      "format": "mp3"
    }
  }
}
```

The response includes a `job_id`. Poll it until the status is `succeeded` or `failed`:

```http
GET /api/jobs/<job_id>
```

Available statuses are `queued`, `running`, `succeeded`, and `failed`. Completed jobs include compact result metadata and checkpoint paths when the task returns them. Failed jobs include the captured exception type and message.

To show recent jobs:

```http
GET /api/jobs
```

## Replay Library API

The combined library view is still available:

```http
GET /api/library
```

For a more targeted frontend, use:

```http
GET /api/library/series
GET /api/library/episodes?series_id=paper-cuts
GET /api/library/episodes/paper-cuts/episode-0001
```

Episode payloads always include a `replay` object. When cached audio exists it
reports `available: true`, `status: "ready"`, and the local `/audio?...` URL.
When audio has not been rendered yet, it reports `available: false` and
`status: "missing_audio"`.

## Local Settings

Settings are written to `data/litrpg/settings.json`, which is under the ignored local data directory. API keys are redacted in API responses and in the browser status display. Environment variables such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, and `EDGE_API_KEY` are reported only as present or absent.

The local settings payload supports:

- `openai_api_key`
- `gemini_api_key`
- `elevenlabs_api_key`
- `edge_api_key`
- `default_generation_provider`
- `default_model`
- `default_tts_provider`
- `default_tts_model`
- `default_tts_format`

Blank API key fields in the UI are ignored when saving so an existing key is not cleared accidentally. Blank non-secret defaults clear the saved value, which is useful when you want the task file or environment to take over again. To remove a saved key, edit `data/litrpg/settings.json` directly while the local UI is stopped.

Set `LITRPG_SETTINGS_PATH` before launching the UI if you want to store the local settings JSON somewhere else. Existing `settings.local.json` files at the repository root are still read by the task settings loader as a legacy fallback, but new UI saves go to `data/litrpg/settings.json`.

## Security

`data/litrpg/settings.json` contains secrets. The `data/litrpg/` directory is gitignored by this repository, but keep it local and do not share it in logs, screenshots, or task files.

The server is intended for local use. Keep the default `127.0.0.1` host unless you understand the risk of exposing local task execution and saved audio files on your network.
