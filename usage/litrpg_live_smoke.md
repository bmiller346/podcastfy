# LitRPG Live Smoke Test

This is the smallest safe workflow for proving that a real provider can generate a chapter artifact without spending enough tokens or TTS minutes to be annoying.

The smoke task is opt-in. It does not render audio by default, and the test suite skips the live network path unless you explicitly enable it.

## What It Exercises

- OpenAI story generation through `run_litrpg_task`.
- Chapter mode with checkpoints and result JSON.
- Two live-generated chapter parts.
- Three locked placeholder parts so the whole chapter shape completes cheaply.
- No TTS render by default.

## Setup

Create a local settings file or use environment variables. `settings.local.json` is ignored by git.

```json
{
  "openai_api_key": "sk-proj-..."
}
```

You can also set:

```powershell
$env:OPENAI_API_KEY = "sk-proj-..."
```

## Run The Smoke Task Manually

From the repository root:

```powershell
python -m podcastfy.litrpg.task usage/litrpg_live_smoke.task.example.json
```

Expected outputs:

- `data/litrpg/live-smoke/chapter-001.json`
- `data/litrpg/live-smoke/chapter-001_checkpoints/*.json`
- `data/litrpg/live-smoke/chapter-001_checkpoints/*_approved.xml`

The example sets `render_audio` to `false`, so no audio file should be created.

## Run The Opt-In Pytest Smoke

This test is skipped unless both flags are present:

```powershell
$env:RUN_LITRPG_LIVE_SMOKE = "1"
$env:OPENAI_API_KEY = "sk-proj-..."
python -m pytest tests/test_litrpg_live_smoke.py -q
```

Without those environment variables, the test file only validates config shape, task loading, and skip behavior. It does not call the network.

## Adding TTS Later

Keep `render_audio` disabled until generation and checkpoints are stable. Then add a `tts` block and switch to the normal episode/audio render path once the UI can show progress and replay files.

OpenAI speech example:

```json
{
  "render_audio": true,
  "tts": {
    "provider": "openai",
    "model": "gpt-4o-mini-tts",
    "format": "mp3"
  }
}
```

Gemini TTS example:

```json
{
  "render_audio": true,
  "tts": {
    "provider": "geminiapi",
    "model": "gemini-3.1-flash-tts-preview",
    "voice": "Kore",
    "format": "wav"
  }
}
```

The generation model and speech model are separate decisions. GPT-5.5 can write the chapter while OpenAI or Gemini TTS renders speech later.
