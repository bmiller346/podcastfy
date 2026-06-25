import copy

from podcastfy.litrpg.state_delta import apply_delta_to_state, extract_state_delta


def test_extract_state_delta_from_gate_terms_events_and_script_text():
    chapter_result = {
        "combined_script": """
<SYSTEM_ANNOUNCER>FOR THE RECORD: Floor law is now aggressively binding.</SYSTEM_ANNOUNCER>
<SYSTEM>FLOOR 4 CLEARED. Pedro has vocalized: "Snack tax approved."</SYSTEM>
<PEDRO>Pretty bird, legally speaking.</PEDRO>
<BOSS>I am not a familiar catchphrase.</BOSS>
""",
        "parts": [
            {
                "gate": {
                    "initial": {
                        "mechanics_terms": {
                            "loot_gain": ["Copper Key"],
                            "inventory_remove": ["Spent Torch"],
                            "level": ["3"],
                            "class_mention": ["Harbor Witch"],
                            "stat_mention": ["strength +2"],
                        }
                    },
                    "final": {
                        "mechanics": {
                            "normalized_terms": {
                                "inventory_add": ["Tide Pearl"],
                                "item_consumed": ["Emergency Biscuit"],
                                "skill_learned": ["Wave Step"],
                                "xp_gain": ["25"],
                            },
                            "events": [
                                {
                                    "kind": "xp_gain",
                                    "display": "+10 XP",
                                    "amount": 10,
                                },
                                {
                                    "kind": "skill_learned",
                                    "display": "Salt Blink",
                                    "term": "salt blink",
                                },
                            ],
                        }
                    },
                },
            }
        ],
    }

    delta = extract_state_delta(chapter_result)

    assert delta["inventory_gained"] == ["Copper Key", "Tide Pearl"]
    assert delta["inventory_lost"] == ["Spent Torch", "Emergency Biscuit"]
    assert delta["mechanics"] == {
        "level": 3,
        "class": "Harbor Witch",
        "stats": {"strength": 2},
        "skills_gained": ["Wave Step", "Salt Blink"],
        "xp_gained": 35,
    }
    assert delta["familiar_phrases"] == [
        "Pretty bird, legally speaking.",
        "Snack tax approved.",
    ]
    assert delta["current_floor"] == 5
    assert delta["announcer_notes"] == [
        "FOR THE RECORD: Floor law is now aggressively binding."
    ]


def test_apply_delta_to_state_merges_without_mutating_inputs_and_defaults_pedro_key():
    state = {
        "character": {
            "level": 2,
            "character_class": "Deckhand",
            "stats": {"xp": 100, "mana": 5},
            "skills": ["Rope Trick", "Old Skill"],
            "inventory": ["spent torch", "Mana Flask"],
        },
        "current_floor": 1,
        "announcer_notes_log": ["Existing canon."],
        "mechanics": {
            "skills_by_character": {
                "Mara": ["Rope Trick"],
            }
        },
    }
    delta = {
        "inventory_gained": ["Copper Key", "mana flask"],
        "inventory_lost": ["SPENT TORCH"],
        "current_floor": 4,
        "announcer_notes": ["Existing canon.", "THIS IS NOW CANON: doors sulk."],
        "familiar_phrases": ["Snack tax approved."],
        "mechanics": {
            "level": 3,
            "class": "Harbor Witch",
            "xp_gained": 25,
            "stats": {"strength": 2},
            "skills_gained": ["Wave Step"],
            "skills_lost": ["old skill"],
            "skills_by_character": {
                "Pedro": ["Snack Echo"],
            },
        },
    }
    original_state = copy.deepcopy(state)
    original_delta = copy.deepcopy(delta)

    updated = apply_delta_to_state(state, delta)

    assert state == original_state
    assert delta == original_delta
    assert updated is not state
    assert updated["character"]["inventory"] == ["Mana Flask", "Copper Key"]
    assert updated["character"]["level"] == 3
    assert updated["character"]["character_class"] == "Harbor Witch"
    assert updated["character"]["stats"] == {"xp": 125, "mana": 5, "strength": 2}
    assert updated["character"]["skills"] == ["Rope Trick", "Wave Step"]
    assert updated["current_floor"] == 4
    assert updated["announcer_notes_log"] == [
        "Existing canon.",
        "THIS IS NOW CANON: doors sulk.",
    ]
    assert updated["pedro_phrases"] == ["Snack tax approved."]
    assert updated["mechanics"]["skills_by_character"] == {
        "Mara": ["Rope Trick"],
        "Pedro": ["Snack Echo"],
    }


def test_apply_delta_to_state_uses_existing_familiar_phrase_key():
    state = {"character": {"inventory": []}, "familiar_phrases": ["Old chirp."]}
    delta = {"familiar_phrases": ["Old chirp.", "New chirp."]}

    updated = apply_delta_to_state(state, delta)

    assert "pedro_phrases" not in updated
    assert updated["familiar_phrases"] == ["Old chirp.", "New chirp."]
