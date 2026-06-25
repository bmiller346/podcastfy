import copy
import json

from podcastfy.litrpg.continuity import ContinuityLedger
from podcastfy.litrpg.continuity import EconomyAnchor
from podcastfy.litrpg.continuity import EmotionalArc
from podcastfy.litrpg.continuity import EmotionalArcRegistry
from podcastfy.litrpg.continuity import EntityEcology
from podcastfy.litrpg.continuity import LedgerEntry
from podcastfy.litrpg.continuity import LocationDetail
from podcastfy.litrpg.continuity import RuleEntry
from podcastfy.litrpg.continuity import WorldRegister
from podcastfy.litrpg.continuity import format_chapter_memory_context
from podcastfy.litrpg.continuity import format_continuity_context
from podcastfy.litrpg.continuity import format_emotional_arc_context
from podcastfy.litrpg.continuity import format_world_register_context
from podcastfy.litrpg.continuity import load_continuity_ledger
from podcastfy.litrpg.continuity import load_emotional_arcs
from podcastfy.litrpg.continuity import load_world_register
from podcastfy.litrpg.continuity import merge_continuity_ledgers
from podcastfy.litrpg.continuity import merge_world_registers
from podcastfy.litrpg.continuity import save_continuity_ledger
from podcastfy.litrpg.continuity import save_emotional_arcs
from podcastfy.litrpg.continuity import save_world_register
from podcastfy.litrpg.continuity import upsert_emotional_arc


def test_continuity_emotional_and_world_round_trip(tmp_path):
    ledger = ContinuityLedger(
        series_id="ember-keep",
        notable_moments=[LedgerEntry(text="Mara refused the tutorial crown.", chapter=1)],
        running_gags=[LedgerEntry(text="Pedro invoices every insult.", tags=["pedro"])],
        motifs=[LedgerEntry(text="Doors appear where guilt collects.", phase="The Drop")],
        world_details=[LedgerEntry(text="The cellar stairs rearrange at midnight.", floor=1)],
        emotional_beats=[
            LedgerEntry(text="Mara laughed after admitting she was scared.", characters=["Mara"])
        ],
        callbacks=[LedgerEntry(text="Bring back the copper key when locks start arguing.")],
    )
    arcs = EmotionalArcRegistry(
        series_id="ember-keep",
        characters={
            "mara": EmotionalArc(
                character="Mara",
                wound="She was blamed for the old gate collapse.",
                current_coping_mode="dry control",
                relationships={"Pedro": "trusts his instincts, not his receipts"},
                last_significant_emotional_event="Admitted fear in the stairwell.",
                beats=[LedgerEntry(text="Chose Pedro over the crown.", chapter=1)],
            )
        },
    )
    world = WorldRegister(
        series_id="ember-keep",
        locations=[
            LocationDetail(
                name="Invoice Stair",
                detail="A looping stairwell that stamps debts into the walls.",
                floor=1,
            )
        ],
        entity_ecology=[
            EntityEcology(
                entity="Receipt Slime",
                detail="Feeds on denied expenses and retreats from itemized lists.",
                floor=1,
                location="Invoice Stair",
            )
        ],
        rules=[RuleEntry(rule="Receipts become binding if read aloud.", floor=1)],
        economy_anchors=[
            EconomyAnchor(
                name="Copper Key",
                detail="Lowest trusted coin-key; worth one minor door argument.",
                floor=1,
                location="Invoice Stair",
            )
        ],
    )

    save_continuity_ledger(tmp_path, "ember-keep", ledger)
    save_emotional_arcs(tmp_path, "ember-keep", arcs)
    save_world_register(tmp_path, "ember-keep", world)

    assert load_continuity_ledger(tmp_path, "ember-keep") == ledger
    assert load_emotional_arcs(tmp_path, "ember-keep") == arcs
    assert load_world_register(tmp_path, "ember-keep") == world
    for filename in ("continuity_ledger.json", "emotional_arcs.json", "world_register.json"):
        raw = (tmp_path / "series" / "ember-keep" / filename).read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert json.loads(raw)["series_id"] == "ember-keep"


def test_merge_dedupes_continuity_and_world_without_losing_new_entries():
    base = ContinuityLedger(
        series_id="ember-keep",
        running_gags=[
            LedgerEntry(text="Pedro invoices every insult.", location="Invoice Stair")
        ],
        callbacks=[LedgerEntry(text="The tutorial crown still waits.")],
    )
    incoming = ContinuityLedger(
        series_id="ember-keep",
        running_gags=[
            LedgerEntry(text="  pedro invoices every insult. ", location="invoice stair"),
            LedgerEntry(text="Mara calls the System 'landlord'."),
        ],
        callbacks=[LedgerEntry(text="The copper key should unlock a social door.")],
    )
    world_base = WorldRegister(
        series_id="ember-keep",
        locations=[
            LocationDetail(name="Invoice Stair", detail="Stamps debts into walls.", floor=1)
        ],
    )
    world_incoming = WorldRegister(
        series_id="ember-keep",
        locations=[
            LocationDetail(name="invoice stair", detail="Stamps debts into walls.", floor=1),
            LocationDetail(name="Market Niche", detail="Trades in grudges.", floor=1),
        ],
    )

    merged_ledger = merge_continuity_ledgers(base, incoming)
    merged_world = merge_world_registers(world_base, world_incoming)

    assert [entry.text for entry in merged_ledger.running_gags] == [
        "Pedro invoices every insult.",
        "Mara calls the System 'landlord'.",
    ]
    assert [entry.text for entry in merged_ledger.callbacks] == [
        "The tutorial crown still waits.",
        "The copper key should unlock a social door.",
    ]
    assert [entry.name for entry in merged_world.locations] == [
        "Invoice Stair",
        "Market Niche",
    ]


def test_relevant_context_selection_uses_phase_floor_location_and_character_focus():
    ledger = ContinuityLedger(
        series_id="ember-keep",
        notable_moments=[
            LedgerEntry(text="Global promise: the System lies politely."),
            LedgerEntry(text="Mara broke a debt seal.", floor=2),
            LedgerEntry(text="A later arena has glass rain.", floor=9),
        ],
        running_gags=[
            LedgerEntry(text="Pedro invoices every insult.", location="Invoice Stair"),
            LedgerEntry(text="The chef hates prophecy.", location="Soup Court"),
        ],
        motifs=[
            LedgerEntry(text="Door handles appear on wrong walls.", phase="The Drop"),
            LedgerEntry(text="Bells ring under water.", phase="The Loot"),
        ],
    )
    arcs = EmotionalArcRegistry(
        series_id="ember-keep",
        characters={
            "mara": EmotionalArc(
                character="Mara",
                wound="Old gate guilt.",
                current_coping_mode="control",
                last_significant_emotional_event="Trusted Pedro with the key.",
            ),
            "pedro": EmotionalArc(character="Pedro", wound="Abandoned in a vending shrine."),
        },
    )
    world = WorldRegister(
        series_id="ember-keep",
        locations=[
            LocationDetail(name="Invoice Stair", detail="Debts ink the walls.", floor=2),
            LocationDetail(name="Soup Court", detail="All broth is judicial.", floor=3),
        ],
        entity_ecology=[
            EntityEcology(
                entity="Receipt Slime",
                detail="Avoids itemized lists.",
                floor=2,
                location="Invoice Stair",
            )
        ],
        rules=[
            RuleEntry(rule="Debt seals break only under witnessed honesty.", floor=2),
            RuleEntry(rule="Soup cannot be appealed.", floor=3),
        ],
        economy_anchors=[
            EconomyAnchor(
                name="Copper Key",
                detail="Worth one minor door argument.",
                floor=2,
                location="Invoice Stair",
            )
        ],
    )
    contract = {
        "phase": "The Drop",
        "floor": 2,
        "location": "Invoice Stair",
        "character_focus": ["Mara"],
    }

    continuity = format_continuity_context(ledger, contract)
    emotional = format_emotional_arc_context(arcs, contract)
    world_context = format_world_register_context(world, contract)
    combined = format_chapter_memory_context(
        ledger=ledger,
        emotional_arcs=arcs,
        world_register=world,
        chapter_contract=contract,
    )

    assert "Global promise" in continuity
    assert "Mara broke a debt seal" in continuity
    assert "glass rain" not in continuity
    assert "chef hates prophecy" not in continuity
    assert "Door handles" in continuity
    assert "Bells ring" not in continuity
    assert "Mara; wound=Old gate guilt" in emotional
    assert "Abandoned in a vending shrine" not in emotional
    assert "Invoice Stair: Debts ink the walls." in world_context
    assert "Soup Court" not in world_context
    assert "Receipt Slime" in world_context
    assert "Copper Key" in world_context
    assert "Emotional arcs" in combined
    assert "Entity ecology" in combined


def test_helpers_do_not_mutate_inputs():
    ledger = {
        "series_id": "ember-keep",
        "running_gags": [{"text": "Pedro invoices every insult."}],
    }
    incoming = {
        "series_id": "ember-keep",
        "running_gags": [{"text": "Pedro invoices every insult."}, {"text": "New gag."}],
    }
    registry = {
        "series_id": "ember-keep",
        "characters": {
            "Mara": {
                "character": "Mara",
                "relationships": {"Pedro": "trusted"},
                "beats": [{"text": "Trusted Pedro."}],
            }
        },
    }
    new_arc = {
        "character": "Mara",
        "current_coping_mode": "deadpan planning",
        "relationships": {"System": "hostile"},
        "beats": [{"text": "Trusted Pedro."}, {"text": "Defied the System."}],
    }
    world = {
        "series_id": "ember-keep",
        "locations": [{"name": "Invoice Stair", "detail": "Debts ink the walls."}],
    }
    world_incoming = {
        "series_id": "ember-keep",
        "locations": [{"name": "Invoice Stair", "detail": "Debts ink the walls."}],
    }
    originals = [
        copy.deepcopy(ledger),
        copy.deepcopy(incoming),
        copy.deepcopy(registry),
        copy.deepcopy(new_arc),
        copy.deepcopy(world),
        copy.deepcopy(world_incoming),
    ]

    merged_ledger = merge_continuity_ledgers(ledger, incoming)
    updated_arcs = upsert_emotional_arc(registry, new_arc)
    merged_world = merge_world_registers(world, world_incoming)
    _ = format_chapter_memory_context(
        ledger=ledger,
        emotional_arcs=registry,
        world_register=world,
        chapter_contract={"floor": 1},
    )

    assert [ledger, incoming, registry, new_arc, world, world_incoming] == originals
    assert [entry.text for entry in merged_ledger.running_gags] == [
        "Pedro invoices every insult.",
        "New gag.",
    ]
    mara = updated_arcs.characters["mara"]
    assert mara.relationships == {"Pedro": "trusted", "System": "hostile"}
    assert [entry.text for entry in mara.beats] == ["Trusted Pedro.", "Defied the System."]
    assert len(merged_world.locations) == 1
