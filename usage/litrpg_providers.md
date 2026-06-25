# LitRPG Provider Names

LitRPG task files use separate providers for story generation and text-to-speech. The default story generation path can use GPT-5.5, while OpenAI speech generation uses the TTS speech model configured under `tts.model` and defaults to `gpt-4o-mini-tts`.

## Story Generation Providers

| Provider name | Backend | Key/settings | Notes |
| --- | --- | --- | --- |
| `openai` | OpenAI Responses API | `OPENAI_API_KEY` or `openai_api_key` | Default live writing provider for chapter generation, review, rewrite, checkpoints, and package generation. |
| `hybrid` | Local Ollama writer plus commercial reviewer | Ollama at `ollama_host`; commercial key such as `OPENAI_API_KEY` | Use for LitRPG chapter writing when you want local drafting with a stronger commercial model for strict XML, review, and continuity-style work. Local prose only falls back to the commercial model if `allow_local_fallback` is explicitly `true`. Keep `render_audio` off for the first smoke run. |

## Text-to-Speech Providers

| Provider name | Backend | Key/settings | Notes |
| --- | --- | --- | --- |
| `openai` | OpenAI TTS | `OPENAI_API_KEY` or `openai_api_key` | Default speech model is `gpt-4o-mini-tts`. Voices can be built-in names such as `alloy`, or a custom voice object/string containing `id`, `voice`, `voice_id`, or `object_id`. |
| `geminiapi` | Gemini API TTS | `GEMINI_API_KEY` or `gemini_api_key` | Direct Gemini API provider name. Produces WAV output and requires both a voice and model. |
| `edge` | Microsoft Edge TTS | No API key | Uses Edge voice names. Model is accepted for config consistency but is not used by the provider. |
| `gemini` | Google Cloud Text-to-Speech | `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `gemini_api_key` depending on settings loader | Single-speaker Google Cloud TTS path. |
| `geminimulti` | Google Cloud multi-speaker Text-to-Speech | `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `gemini_api_key` depending on settings loader | Multi-speaker Google Cloud TTS path. Requires the multi-speaker model expected by the provider. |
| `elevenlabs` | ElevenLabs TTS | `ELEVENLABS_API_KEY` or `elevenlabs_api_key` | Uses ElevenLabs voice IDs/names and model names such as `eleven_multilingual_v2`. |

## Example TTS Settings

The local UI writes these values to `data/litrpg/settings.json` by default. You can override that path with `LITRPG_SETTINGS_PATH`.

```json
{
  "default_generation_provider": "openai",
  "default_model": "gpt-5.5",
  "default_tts_provider": "openai",
  "default_tts_model": "gpt-4o-mini-tts",
  "default_tts_format": "mp3",
  "openai_api_key": "sk-...",
  "gemini_api_key": "AIza..."
}
```

## Example Task Snippet

```json
{
  "generation": {
    "provider": "openai",
    "model": "gpt-5.5"
  },
  "tts": {
    "provider": "geminiapi",
    "model": "gemini-3.1-flash-tts-preview",
    "voice": "Kore",
    "format": "wav"
  }
}
```

## Hybrid Generation Snippet

```json
{
  "generation": {
    "provider": "hybrid",
    "local_provider": "ollama",
    "local_model": "llama3.1:8b-instruct",
    "ollama_host": "http://127.0.0.1:11434",
    "commercial_provider": "openai",
    "commercial_model": "gpt-5.5",
    "local_stage_prefixes": ["part:", "revise:"],
    "local_exact_stages": ["script"],
    "reasoning_effort": "low",
    "verbosity": "low",
    "max_retries": 2,
    "retry_backoff_seconds": 1,
    "timeout_seconds": 120
  },
  "reviews": {
    "enabled": true,
    "rewrite": true
  },
  "render_audio": false
}
```

Use story-generation provider names such as `openai` or `hybrid` under `generation.provider`. Use TTS provider names such as `openai`, `geminiapi`, `edge`, `gemini`, `geminimulti`, or `elevenlabs` under `tts.provider`. Unknown provider names are rejected by the relevant provider factory.
