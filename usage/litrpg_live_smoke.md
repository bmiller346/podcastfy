# LitRPG Live Smoke Test

This is the smallest safe workflow for proving the pipeline can generate, checkpoint, and later replay a LitRPG bundle without burning unnecessary tokens or TTS minutes.

The live path is opt-in. The checked-in chapter smoke stays cheap by generating only two live parts, locking the other three parts to placeholders, and leaving audio rendering off by default.

## What To Run

Use these two tasks together:

- `usage/litrpg_chapter_task.example.json`
  Exercises real chapter generation, reviews, checkpoints, and series-state persistence with a tiny 2-part live chapter.
- `usage/litrpg_task.example.json`
  Exercises audio rendering and replay with a fixed inline script so the first run only pays for TTS and the second run should reuse the cached bundle.

`usage/litrpg_live_smoke.task.example.json` remains the narrow opt-in pytest smoke task if you want a dedicated CI-like manual check.

## Required Environment

Use either `settings.local.json` or environment variables. `settings.local.json` is ignored by git.

Exact variables used by the current pipeline:

- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `ELEVENLABS_API_KEY`
- `LITRPG_SETTINGS_PATH`
- `RUN_LITRPG_LIVE_SMOKE`

Minimal local settings file:

```json
{
  "openai_api_key": "sk-proj-..."
}
```

PowerShell equivalents:

```powershell
$env:OPENAI_API_KEY = "sk-proj-..."
$env:GEMINI_API_KEY = "..."
$env:ELEVENLABS_API_KEY = "..."
$env:LITRPG_SETTINGS_PATH = "C:\Users\engin\podcastfy\settings.local.json"
```

## Step 1: Cheap Chapter Smoke

From the repository root:

```powershell
python -m podcastfy.litrpg.task usage/litrpg_chapter_task.example.json
```

Expected bundle:

- `data/litrpg/paper-cuts/chapter-002.json`
- `data/litrpg/paper-cuts/chapter-002_checkpoints/*.json`
- `data/litrpg/paper-cuts/chapter-002_checkpoints/*_approved.xml`
- `data/litrpg/series/paper-cuts/series_state.json`

This task keeps `render_audio` set to `false`, so no audio file should be produced. That is intentional. It proves generation, checkpointing, and state persistence first.

## Step 2: Audio And Replay Verification

Then run the replay example:

```powershell
python -m podcastfy.litrpg.task usage/litrpg_task.example.json
python -m podcastfy.litrpg.task usage/litrpg_task.example.json
```

Expected behavior:

- First run writes a result bundle and one audio file.
- Second run returns the same episode bundle with replay metadata instead of synthesizing audio again.

Look for:

- `data/litrpg/paper-cuts-replay/episode-001.json`
- an audio path inside the JSON result
- `replayed: true` on the second run

## Opt-In Pytest Smoke

This smoke test is skipped unless you explicitly enable it:

```powershell
$env:RUN_LITRPG_LIVE_SMOKE = "1"
$env:OPENAI_API_KEY = "sk-proj-..."
python -m pytest tests/test_litrpg_live_smoke.py -q
```

Without those environment variables, the test file only validates config shape, task loading, and skip behavior. It does not call the network.

## Cost Control

Use these guardrails before you scale anything up:

- Keep chapter smoke at two live parts and lock the rest.
- Leave `render_audio` off until chapter checkpoints look stable.
- Use inline `outline` and `script` for replay verification so you only pay for TTS once.
- Keep `reasoning_effort` and `verbosity` low for smoke tasks.
- Start with OpenAI speech or Gemini TTS only after the chapter bundle looks right.

## Audio Toggle Examples

OpenAI speech:

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

Gemini TTS:

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

The story model and speech model are separate decisions. GPT-5.5 can write the chapter while OpenAI or Gemini TTS handles speech later.
