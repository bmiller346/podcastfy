# LitRPG Robust Build Mode

Robust build mode turns on the enforcement spine around chapter generation. It is opt-in: existing tasks continue to run normally unless you add a `harness` block or a `harness_path`.

## Enable Harness Gates

Use inline harness config when you want the task file to carry its own approval policy:

```json
{
  "harness": {
    "enabled": true,
    "stages": {
      "chapter_generation": {"requires_human_approval": true},
      "chapter_result_write": {"requires_human_approval": false},
      "audio_render": {"requires_human_approval": true}
    }
  }
}
```

Approve specific stages with:

```json
{
  "approved_stages": ["chapter_generation"]
}
```

If approval is missing, the task returns `status: "approval_required"` and includes a `harness_decision` with the stage, reason, policy, and estimated cost.

## Quarantine And Rewrite

After chapter generation, the scarcity audit can fail the attempt. Failed chapters are not silently approved. The result includes:

- `quarantine.status`
- `quarantine.path`
- `quarantine.rewrite_instruction`
- `scarcity_audit`

Quarantine records are written under:

```text
data/litrpg/series/{series_id}/book_{book_number}/quarantine/
```

Automatic rewrite is off by default. To allow bounded retries:

```json
{
  "rewrite_quarantined": true,
  "max_rewrite_attempts": 3
}
```

After the maximum attempts are exceeded, the task result is marked blocked and `agent_state.json` records a blocked queue item.

## Effect Logs

Committed chapter and audio side effects are appended to:

```text
data/litrpg/series/{series_id}/effect_log.jsonl
```

Entries include idempotency key, stage, provider/model, input/output hashes, estimated cost, and status.

## Agent State And Handoff

Agent queues live at:

```text
data/litrpg/series/{series_id}/agent_state.json
```

Generate a deterministic handoff by adding:

```json
{
  "generate_handoff": true
}
```

The handoff is written to:

```text
data/litrpg/series/{series_id}/book_{book_number}/HANDOFF.md
```

The local UI exposes the same robust state at:

```text
/api/robust-state?series_id={series_id}&book_number=1
```

MCP helpers expose `get_agent_state`, `list_quarantine_records`, `read_effect_log`, and `get_book_handoff`.
