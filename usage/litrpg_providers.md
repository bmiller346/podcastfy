# LitRPG Provider Names

LitRPG task files use separate providers for story generation and text-to-speech. The default story generation path can use GPT-5.5, while OpenAI speech generation uses the TTS speech model configured under `tts.model` and defaults to `gpt-4o-mini-tts`.

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

```json
{
  "default_tts_provider": "openai",
  "default_tts_model": "gpt-4o-mini-tts",
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

Use `openai`, `geminiapi`, `edge`, `gemini`, `geminimulti`, or `elevenlabs` exactly as shown. Unknown provider names are rejected by the provider factory.
