# LitRPG Provider Names

LitRPG task files use separate providers for story generation and text-to-speech. The default story generation path can use GPT-5.4, while OpenAI speech generation uses the TTS speech model configured under `tts.model` and defaults to `gpt-4o-mini-tts`.

## Story Generation Providers

| Provider name | Backend | Key/settings | Notes |
| --- | --- | --- | --- |
| `openai` | OpenAI Responses API | `OPENAI_API_KEY` or `openai_api_key` | Default live writing provider for chapter generation, review, rewrite, checkpoints, and package generation. |
| `hybrid` | Local Ollama writer plus commercial reviewer | Ollama at `ollama_host`; commercial key such as `OPENAI_API_KEY` | Use for LitRPG chapter writing when you want local drafting with a stronger commercial model for strict XML, review, and continuity-style work. Local prose only falls back to the commercial model if `allow_local_fallback` is explicitly `true`. Keep `render_audio` off for the first smoke run. |

## Text-to-Speech Providers

| Provider name | Backend | Key/settings | Notes |
| --- | --- | --- | --- |
| `openai` | OpenAI TTS | `OPENAI_API_KEY` or `openai_api_key` | Default speech model is `gpt-4o-mini-tts`. It supports performance `instructions`; legacy `tts-1` and `tts-1-hd` do not. Built-in voices are `alloy`, `ash`, `ballad`, `coral`, `echo`, `fable`, `onyx`, `nova`, `sage`, `shimmer`, `verse`, `marin`, and `cedar`, or use a custom voice object/string containing `id`, `voice`, `voice_id`, or `object_id`. |
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
  "default_model": "gpt-5.4",
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
    "model": "gpt-5.4"
  },
  "tts": {
    "provider": "openai",
    "model": "gpt-4o-mini-tts",
    "voice": "onyx",
    "format": "mp3"
  }
}
```

For LitRPG Announcer/SYSTEM lines, prefer `onyx` with the `announcer_broadcast` voice processing chain. Use `ballad` for long narration, `ash` for a dry hero, and `coral` for a bright sidekick voice.

## Hybrid Generation Snippet

```json
{
  "generation": {
    "provider": "hybrid",
    "local_provider": "ollama",
    "local_model": "litrpg-writer",
    "ollama_host": "http://127.0.0.1:11434",
    "commercial_provider": "gemini",
    "commercial_model": "gemini-2.5-flash",
    "auto_model_routing": true,
    "cheap_model": "gemini-2.5-flash-lite",
    "nano_model": "gemini-2.5-flash-lite",
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

Use story-generation provider names such as `openai`, `gemini`, `ollama`, or `hybrid` under `generation.provider`. In hybrid mode, set `commercial_provider` to `gemini` for the cheaper cloud review/intake path or `openai` when you want OpenAI as the commercial reviewer. Use TTS provider names such as `openai`, `geminiapi`, `edge`, `gemini`, `geminimulti`, or `elevenlabs` under `tts.provider`. Unknown provider names are rejected by the relevant provider factory.

## Hybrid Stage Routing

By default, hybrid mode uses the local Ollama backend only for prose drafting stages:

- `script`
- stages beginning with `part:`
- stages beginning with `revise:`

Commercial OpenAI or Gemini handles planning, intake, package generation, review, architecture, and chat-style editing stages, including `outline`, `premise_intake`, `premise_intake_repair`, `series_package`, `review:*`, `director:*`, `mechanics:*`, `chapter_review`, `visual_state_update`, `hook`, `rhythm`, `reader_proxy`, `story_seed_revision`, and `chat`.

The local backend in hybrid mode is currently `ollama`; unsupported `local_provider` values are rejected early. Unsupported `commercial_provider` values are also rejected early, and missing OpenAI or Gemini API keys produce provider-specific setup messages.
