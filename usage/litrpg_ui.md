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
- Browse saved episodes under `data/litrpg` and play saved audio files.

## Local Settings

Settings are written to `settings.local.json` at the repository root. API keys are redacted in API responses and in the browser status display. Environment variables such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, and `EDGE_API_KEY` are reported only as present or absent.

Blank API key fields in the UI are ignored when saving so an existing key is not cleared accidentally. To remove a saved key, edit `settings.local.json` directly while the local UI is stopped.

## Security

`settings.local.json` contains secrets. It is gitignored by this repository, but keep it local and do not share it in logs, screenshots, or task files.

The server is intended for local use. Keep the default `127.0.0.1` host unless you understand the risk of exposing local task execution and saved audio files on your network.
