import json

from podcastfy.litrpg.foreshadowing import ForeshadowEntry, ForeshadowLedger
from podcastfy.litrpg.foreshadowing import add_plants, compute_ready_to_pay
from podcastfy.litrpg.foreshadowing import foreshadow_ledger_path
from podcastfy.litrpg.foreshadowing import format_foreshadow_context
from podcastfy.litrpg.foreshadowing import load_foreshadow_ledger, mark_paid
from podcastfy.litrpg.foreshadowing import save_foreshadow_ledger


def test_foreshadow_ledger_round_trip_persistence(tmp_path):
    ledger = ForeshadowLedger(
        series_id="ember-keep",
        planted=[
            ForeshadowEntry(
                detail="The tutorial slime salutes Mara.",
                planted_book=1,
                planted_chapter=2,
                intended_payoff_start=5,
                intended_payoff_end=7,
                payoff_book=1,
                mystery="Why a low-tier monster recognizes her.",
            )
        ],
    )

    save_foreshadow_ledger(tmp_path, ledger)
    loaded = load_foreshadow_ledger(tmp_path, "ember-keep")

    assert loaded == ledger
    assert foreshadow_ledger_path(tmp_path, "ember-keep") == (
        tmp_path / "series" / "ember-keep" / "foreshadow_ledger.json"
    )
    raw = (
        tmp_path / "series" / "ember-keep" / "foreshadow_ledger.json"
    ).read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert json.loads(raw)["planted"][0]["detail"] == "The tutorial slime salutes Mara."


def test_add_plants_dedupes_without_mutating_inputs():
    ledger = ForeshadowLedger(
        series_id="ember-keep",
        planted=[
            ForeshadowEntry(
                detail="A silver key hums near elevators.",
                planted_chapter=1,
                intended_payoff_start=4,
                intended_payoff_end=6,
                mystery="What door it wants.",
            )
        ],
    )
    update = {
        "detail": "A silver key hums near elevators.",
        "planted_chapter": 1,
        "intended_payoff_range": [4, 6],
        "mystery": "What door it wants.",
    }

    updated = add_plants(ledger, [update])

    assert updated is not ledger
    assert len(updated.planted) == 1
    assert ledger.planted[0].status == "planted"
    assert update["intended_payoff_range"] == [4, 6]


def test_compute_ready_to_pay_uses_book_chapter_window_and_mark_paid():
    ledger = ForeshadowLedger(
        series_id="ember-keep",
        planted=[
            ForeshadowEntry(
                detail="The vending machine refuses copper coins.",
                planted_chapter=2,
                intended_payoff_start=4,
                intended_payoff_end=5,
                mystery="Who minted the fake coins.",
            ),
            ForeshadowEntry(
                detail="A moon-branded receipt appears.",
                planted_chapter=3,
                intended_payoff_start=6,
                intended_payoff_end=8,
                mystery="Which sponsor owns the moon brand.",
            ),
        ],
    )

    ready = compute_ready_to_pay(ledger, book=1, chapter=4)

    assert [entry.detail for entry in ready.ready_to_pay] == [
        "The vending machine refuses copper coins."
    ]
    assert ready.ready_to_pay[0].status == "ready_to_pay"
    assert ledger.ready_to_pay == []

    paid = mark_paid(ready, "The vending machine refuses copper coins.", paid_chapter=4)

    assert paid.planted[0].status == "paid"
    assert paid.planted[0].paid_chapter == 4
    assert paid.ready_to_pay == []


def test_format_foreshadow_context_includes_ready_and_planted_sections():
    ledger = ForeshadowLedger(
        series_id="ember-keep",
        planted=[
            ForeshadowEntry(
                detail="The vending machine refuses copper coins.",
                planted_chapter=2,
                intended_payoff_start=4,
                intended_payoff_end=5,
                mystery="Who minted the fake coins.",
            ),
            ForeshadowEntry(
                detail="A moon-branded receipt appears.",
                planted_chapter=3,
                intended_payoff_start=6,
                intended_payoff_end=8,
                mystery="Which sponsor owns the moon brand.",
            ),
        ],
    )

    context = format_foreshadow_context(ledger, book=1, chapter=4)

    assert context.startswith("Foreshadow Ledger (ember-keep)")
    assert "Ready to pay:" in context
    assert "The vending machine refuses copper coins." in context
    assert "status: ready_to_pay" in context
    assert "Planted:" in context
    assert "A moon-branded receipt appears." in context
