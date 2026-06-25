from podcastfy.litrpg.mechanics import extract_mechanics_events, validate_mechanics


def test_validate_mechanics_passes_consistent_script_with_prior_context():
    script = """
<SYSTEM>Quest: Break Room Breach. Loot gained: mana flask. +25 XP. XP total: 125. Skill unlocked: Spark.</SYSTEM>
<HERO>I activate Spark and consume mana flask.</HERO>
<SYSTEM>Status: singed pride. Spark cooldown ready.</SYSTEM>
"""

    result = validate_mechanics(
        script,
        {
            "xp": 100,
            "inventory": [],
            "skills": [],
            "class": "Apprentice Auditor",
            "cooldowns": {"spark": "ready"},
        },
    )

    assert result["ready"] is True
    assert result["pass"] is True
    assert result["issues"] == []
    assert "xp_gain" in result["normalized_terms"]
    assert "quest" in result["normalized_terms"]["mechanics"]
    assert any(event["kind"] == "skill_used" and event["term"] == "spark" for event in result["events"])


def test_validate_mechanics_fails_when_no_audible_mechanics_are_present():
    result = validate_mechanics("<HERO>The hallway smells like old toner.</HERO>")

    assert result["ready"] is False
    assert result["pass"] is False
    assert result["issues"] == ["No audible LitRPG mechanics detected"]
    assert result["events"] == []


def test_validate_mechanics_fails_consumed_item_without_inventory():
    script = """
<HERO>I drink potion of emergency stapling.</HERO>
<SYSTEM>Status: oddly adhesive.</SYSTEM>
"""

    result = validate_mechanics(script, {"inventory": ["bent paperclip"]})

    assert result["ready"] is False
    assert result["issues"] == [
        "Item consumed or removed without inventory: potion of emergency stapling"
    ]


def test_validate_mechanics_fails_unavailable_skill_use():
    script = """
<SYSTEM>Class: Intern. +5 XP. XP total: 5.</SYSTEM>
<HERO>I activate Meteor Punch.</HERO>
"""

    result = validate_mechanics(script, {"skills": ["Paper Cut"], "class": "Intern"})

    assert result["ready"] is False
    assert result["issues"] == [
        "Skill or class ability mentioned without availability: Meteor Punch"
    ]


def test_validate_mechanics_does_not_treat_plain_use_phrases_as_skills():
    script = """
<SYSTEM>Quest update: Enter the Evaluation Room. Reward: 50 XP.</SYSTEM>
<ROGUE>Nothing says evaluation like a room full of angry accountants.</ROGUE>
<TANK>We can use all the charm we can get down here.</TANK>
<HEALER>What's your plan for when things go south?</HEALER>
"""

    result = validate_mechanics(script, {"skills": [], "inventory": []})

    assert result["ready"] is True
    assert result["issues"] == []


def test_validate_mechanics_fails_xp_total_decrease_without_spend():
    script = """
<SYSTEM>+20 XP. XP total: 120.</SYSTEM>
<SYSTEM>XP total: 90. Status: suspicious accounting.</SYSTEM>
"""

    result = validate_mechanics(script, {"xp": 100})

    assert result["ready"] is False
    assert result["issues"] == ["XP total decreases from 120 to 90 without an XP spend"]


def test_validate_mechanics_fails_cooldown_misuse():
    script = """
<SYSTEM>Blink is on cooldown. +10 XP.</SYSTEM>
<HERO>I activate Blink again.</HERO>
"""

    result = validate_mechanics(script, {"skills": ["Blink"], "cooldowns": {}})

    assert result["ready"] is False
    assert result["issues"] == ["Cooldown bypassed for unavailable ability: Blink"]


def test_extract_mechanics_events_captures_expected_event_kinds():
    events = extract_mechanics_events(
        "<SYSTEM>Loot gained: brass key. Spend 10 XP. Inventory -1 brass key. Cooldown: Blink.</SYSTEM>"
    )

    assert [event["kind"] for event in events] == [
        "xp_spend",
        "loot_gain",
        "inventory_remove",
        "cooldown_start",
    ]
