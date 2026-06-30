# LitRPG Render Loop

The render loop is the audio recovery layer for LitRPG episode rendering. It is
opt-in and bounded: it validates directives, renders audio, measures the
artifact, retries only under configured policies, and never rewrites story prose.

## Smoke Task

From the repository root:

```powershell
python -m podcastfy.litrpg.task usage/litrpg_render_loop.example.json
```

The example uses inline outline/script fields so generation is deterministic.
It still needs a configured TTS provider if you actually run it with
`render_audio: true`.

## Minimal Config

```json
{
  "mode": "episode",
  "series_id": "render-loop-smoke",
  "premise": "Short local render loop smoke.",
  "render_audio": true,
  "render_loop": {
    "enabled": true,
    "max_attempts": 3,
    "retry_below_score": 0.72,
    "retry_strategy": "deterministic_adjustment"
  },
  "performance_directives": {
    "default": {
      "intensity": 0.55,
      "pace": "steady"
    }
  }
}
```

## Operator Flow

1. Directive validation runs before TTS spend.
2. Audio renders only if directives are structurally valid.
3. The rendered file is scored with local deterministic metrics.
4. If the score is below `retry_below_score`, the configured retry strategy may
   create another attempt.
5. The best measured attempt is selected as the final audio path.
6. Every attempt remains inspectable through feedback and effect logs.

## Validation

Directive validation is cheap and local. It checks intensity ranges, pause
limits, known pace/register values, inner-monologue intensity caps, void/memory
scene pacing, and provider-specific distortion risks.

Invalid directives skip rendering for that segment and produce
`verdict: "directive_invalid"` with `human_review_required: true`.

## Scoring

Scoring uses local audio metrics only:

- duration
- peak dB
- RMS dB
- silence ratio
- clipping detection
- low-energy or short-line TTS valley risk
- duration drift when an expected duration is available

Low scores are review flags, not automatic story changes.

## Retry Strategies

- `none`: one attempt, current no-retry behavior.
- `same_directive`: rerender the same directive up to `max_attempts`.
- `deterministic_adjustment`: locally adjusts safe directive fields, such as
  intensity and pauses, then validates again before rerendering.
- `llm_revision`: opt-in director/LLM directive revision. Requires
  `llm_revision_enabled: true`, is capped by `max_attempts`, outputs JSON only,
  and every revised directive must pass validation before TTS spend.

LLM revision example:

```json
{
  "render_loop": {
    "enabled": true,
    "max_attempts": 3,
    "retry_below_score": 0.72,
    "retry_strategy": "llm_revision",
    "llm_revision_enabled": true
  }
}
```

If `llm_revision_enabled` is not true, the system does not call the LLM revision
stage.

## Final Attempt Selection

The final audio path is the highest-scoring attempt, not necessarily the last
attempt. Alternate attempts use deterministic names such as
`final_attempt_001.mp3`; the selected attempt is copied back to the normal final
audio path so existing consumers keep working.

## Where Feedback Appears

- Task result: `render_feedback` and `render_loop`
- Episode bundle: `audio_metadata.json`
- Series effect log: `effect_log.jsonl`
- Book handoff: `HANDOFF.md`
- MCP helper: `get_render_feedback`
- UI robust-state endpoint: recent review-required render feedback

## Safety Boundaries

- No autonomous story rewrite happens.
- No retry can exceed `max_attempts`.
- Every generated or adjusted directive is validated before spend.
- Parse or validation failures stop retry and require human review.
- Existing no-render-loop tasks are unchanged.
