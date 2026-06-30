from podcastfy.litrpg.scarcity import ScarcityRegistry


def test_scarcity_registry_distinguishes_hint_reveal_and_payoff_windows():
    registry = ScarcityRegistry.from_sources(
        series_mysteries=["Grand Dredger patron"],
        must_not_spend=["Kelli leverage chain"],
        hook_locks=[
            {
                "question": "Why Pedro phrases alter rules",
                "reveal_allowed_at_book": 2,
                "payoff_allowed_at_book": 3,
                "forbidden_payoff": "Do not name the sponsor.",
            }
        ],
        current_book=1,
    )

    pedro = registry.decision_for("Why Pedro phrases alter rules", book=1)
    assert pedro.hint_allowed is True
    assert pedro.reveal_allowed is False
    assert pedro.payoff_allowed is False
    assert "Hints allowed; reveal locked until book 2." == pedro.reason

    assert registry.can_hint("Grand Dredger patron", book=1) is True
    assert registry.can_reveal("Grand Dredger patron", book=1) is False
    assert registry.can_payoff("Why Pedro phrases alter rules", book=3) is True


def test_scarcity_registry_anchor_payload_lists_allowed_hints_and_locks():
    registry = ScarcityRegistry.from_sources(
        foreshadow_ledger={
            "planted": [
                {
                    "mystery": "System Architects grievance",
                    "detail": "The receipt uses pre-System legal language.",
                    "planted_book": 1,
                    "payoff_book": 4,
                }
            ]
        },
        scarcity_constraints=["Tokens are finite until a trade scene earns more."],
        current_book=1,
    )

    payload = registry.to_anchor_payload(book=1)

    assert "System Architects grievance" in payload["forbidden_mysteries"]
    assert "System Architects grievance" in payload["allowed_hints"]
    assert payload["reveal_locks"] == [
        "System Architects grievance: reveal book 4, payoff book 4"
    ]
    assert payload["payoff_locks"] == [
        "System Architects grievance: reveal book 4, payoff book 4"
    ]
    assert payload["forbidden_now"] == ["System Architects grievance"]
    assert payload["scarcity_constraints"] == [
        "Tokens are finite until a trade scene earns more."
    ]
