"""Opt-in harness approval gates and rough cost estimates."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


HARNESS_CONFIG_FILENAME = "harness_config.json"
HARNESS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class HarnessStageGate:
    requires_human_approval: bool = False
    estimated_cost_usd: float | None = None
    cost_per_minute_usd: float | None = None
    policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HarnessDecision:
    stage: str
    allowed: bool
    requires_human_approval: bool
    approved: bool
    estimated_cost_usd: float
    reason: str
    policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_harness_config() -> dict[str, Any]:
    """Return the default non-blocking harness config."""

    return {
        "schema_version": HARNESS_SCHEMA_VERSION,
        "stages": {
            "premise_intake": {"requires_human_approval": False},
            "book_plan": {"requires_human_approval": True},
            "chapter_generation": {"requires_human_approval": True},
            "chapter_result_write": {"requires_human_approval": False},
            "audio_render": {"requires_human_approval": True},
        },
    }


def load_harness_config(
    storage_dir: str | Path,
    series_id: str,
    book_number: int | None = None,
) -> dict[str, Any]:
    """Load harness config from book, series, or default locations."""

    root = Path(storage_dir) / "series" / str(series_id)
    candidates = []
    if book_number is not None:
        candidates.append(root / f"book_{int(book_number)}" / HARNESS_CONFIG_FILENAME)
    candidates.append(root / HARNESS_CONFIG_FILENAME)
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        if not isinstance(payload, Mapping):
            raise ValueError("harness_config.json must contain a JSON object")
        return normalize_harness_config(payload)
    return default_harness_config()


def normalize_harness_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    base = default_harness_config()
    if not isinstance(config, Mapping):
        return base
    merged = dict(base)
    merged["schema_version"] = int(config.get("schema_version") or HARNESS_SCHEMA_VERSION)
    stages = dict(base["stages"])
    raw_stages = config.get("stages")
    if isinstance(raw_stages, Mapping):
        for stage, policy in raw_stages.items():
            if isinstance(policy, Mapping):
                stages[str(stage)] = {**dict(stages.get(str(stage), {})), **dict(policy)}
            else:
                stages[str(stage)] = {"requires_human_approval": bool(policy)}
    merged["stages"] = stages
    return merged


def estimate_stage_cost(
    stage: str,
    task: Mapping[str, Any] | None,
    model_info: Mapping[str, Any] | None = None,
) -> float:
    """Return a rough deterministic live cost estimate for a stage."""

    data = dict(task or {})
    info = dict(model_info or {})
    target_minutes = float(data.get("target_minutes") or data.get("minutes") or 0)
    if not target_minutes and data.get("litrpg_config"):
        config = data.get("litrpg_config")
        if isinstance(config, Mapping):
            target_minutes = float(config.get("minutes") or 0)
    if not target_minutes:
        target_minutes = 30.0 if stage == "chapter_generation" else 5.0

    if stage == "chapter_result_write":
        return 0.0
    if stage == "audio_render":
        per_minute = float(
            info.get("cost_per_minute_usd")
            or data.get("tts_cost_per_minute_usd")
            or 0.015
        )
        return round(max(0.0, target_minutes * per_minute), 4)
    if stage in {"chapter_generation", "premise_intake", "book_plan"}:
        per_minute = float(info.get("generation_cost_per_minute_usd") or 0.003)
        floor = 0.005 if stage == "chapter_generation" else 0.002
        return round(max(floor, target_minutes * per_minute), 4)
    return float(info.get("estimated_cost_usd") or 0.0)


def check_harness_gate(
    stage: str,
    task: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    approved: bool = False,
) -> HarnessDecision:
    """Check whether an opt-in harness stage is allowed to proceed."""

    normalized = normalize_harness_config(config)
    policy = dict(normalized.get("stages", {}).get(stage, {}))
    requires = bool(policy.get("requires_human_approval"))
    estimate = (
        float(policy["estimated_cost_usd"])
        if policy.get("estimated_cost_usd") is not None
        else estimate_stage_cost(stage, task, policy)
    )
    allowed = (not requires) or bool(approved)
    if allowed and requires:
        reason = "Stage approved by task approved_stages."
    elif allowed:
        reason = "Stage does not require human approval."
    else:
        reason = "Stage requires human approval."
    return HarnessDecision(
        stage=stage,
        allowed=allowed,
        requires_human_approval=requires,
        approved=bool(approved),
        estimated_cost_usd=round(max(0.0, estimate), 4),
        reason=reason,
        policy=policy,
    )


def harness_enabled(task: Mapping[str, Any]) -> bool:
    """Return true when harness checks are explicitly enabled."""

    harness = task.get("harness")
    return bool(task.get("harness_path")) or (
        isinstance(harness, Mapping) and bool(harness.get("enabled"))
    )


def approved_for_stage(task: Mapping[str, Any], stage: str) -> bool:
    approved = task.get("approved_stages")
    if isinstance(approved, str):
        return approved == stage or approved == "*"
    if isinstance(approved, (list, tuple, set)):
        return "*" in approved or stage in {str(item) for item in approved}
    return False
