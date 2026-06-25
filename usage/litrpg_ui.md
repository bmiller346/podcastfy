# LitRPG Local UI

Run the small local LitRPG UI from the repository root:

```bash
python -m podcastfy.litrpg.ui --host 127.0.0.1 --port 8765
```

Then open http://127.0.0.1:8765/.

The UI can:

- Save local provider keys and default provider/model settings.
- List `usage/litrpg*.json` task files.
- Run a selected task through `podcastfy.litrpg.task.run_litrpg_task`.
- Submit a selected task as a tracked background job and poll status/result metadata.
- Browse saved episodes under `data/litrpg` and play saved audio files.

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

{"path": "usage/litrpg_task.example.json"}
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
