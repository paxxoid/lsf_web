SPECIAL_ABILITY_NAMES: dict[int, str] = {
    1: "Summon",
    2: "Enrage",
    3: "Rampage",
    4: "Area Rampage",
    5: "Flurry",
    6: "Triple Attack",
    7: "Quadruple Attack",
    8: "Dual Wield",
    9: "Bane Attack",
    10: "Magical Attack",
    11: "Ranged Attack",
    12: "Immune to Slow",
    13: "Immune to Mesmerize",
    14: "Immune to Charm",
    15: "Immune to Stun",
    16: "Immune to Snare",
    17: "Immune to Fear",
    18: "Immune to Dispel",
    19: "Immune to Melee",
    20: "Immune to Magic",
    21: "Immune to Fleeing",
    22: "Immune to Melee Except Bane",
    23: "Immune to Non-Magical Melee",
    24: "Immune to Aggro",
    25: "Immune to Being Aggro",
    26: "Immune to Ranged Spells",
    27: "Immune to Feign Death",
    28: "Immune to Taunt",
    29: "Tunnel Vision",
    30: "Does Not Buff or Heal Friends",
    31: "Immune to Pacify",
    32: "Leash",
    33: "Tether",
    34: "Destructible Object",
    35: "Immune to Client Harm",
    36: "Always Flees",
    37: "Flee Percentage",
    38: "Allow Beneficial Spells",
    39: "Melee Disabled",
    40: "NPC Chase Distance",
    41: "Allowed to Tank",
    42: "Ignore Root Aggro Rules",
    43: "Casting Resist Difficulty",
    44: "Counter Avoid Damage",
    45: "Proximity Aggro",
    46: "Immune to Ranged Attacks",
    47: "Immune to Client Damage",
    48: "Immune to NPC Damage",
    49: "Immune to Client Aggro",
    50: "Immune to NPC Aggro",
    51: "Modify Avoid Damage",
    52: "Immune to Memory Fade",
    53: "Open Immunity",
    54: "Immune to Assassinate",
    55: "Immune to Headshot",
    56: "Immune to Bot Aggro",
    57: "Immune to Bot Damage",
}


def _coerce_parameter(value: str) -> int | float | str:
    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def parse_special_abilities(raw_value: str | None) -> list[dict]:
    """Parse EQEmu's ``ability,enabled,param...^...`` encoding."""
    parsed: list[dict] = []

    if not raw_value:
        return parsed

    for raw_token in raw_value.split("^"):
        token = raw_token.strip()
        if not token:
            continue

        parts = [part.strip() for part in token.split(",")]
        try:
            ability_id = int(parts[0])
            enabled = bool(int(parts[1]))
        except (IndexError, TypeError, ValueError):
            # Keep the endpoint available if a future dump has bad data.
            continue

        parameters = [
            _coerce_parameter(value)
            for value in parts[2:]
            if value != ""
        ]
        parsed.append(
            {
                "id": ability_id,
                "name": SPECIAL_ABILITY_NAMES.get(
                    ability_id,
                    f"Unknown ability {ability_id}",
                ),
                "enabled": enabled,
                "parameters": parameters,
            }
        )

    return parsed


def crowd_control_summary(
    raw_value: str | None,
    slow_mitigation: int | None,
) -> dict:
    abilities = parse_special_abilities(raw_value)
    enabled_ids = {
        ability["id"]
        for ability in abilities
        if ability["enabled"]
    }

    mitigation = max(0, int(slow_mitigation or 0))
    slow_immune = 12 in enabled_ids
    mez_immune = 13 in enabled_ids

    if slow_immune:
        slow_status = "Immune to slow"
    elif mitigation:
        slow_status = f"Slowable with {mitigation}% slow mitigation"
    else:
        slow_status = "Slowable; no listed slow mitigation"

    return {
        "slow_immune": slow_immune,
        "slow_mitigation_percent": mitigation,
        "slow_status": slow_status,
        "mez_immune": mez_immune,
        "mez_status": (
            "Immune to mez"
            if mez_immune
            else (
                "Potentially mezzable; spell level and resist checks "
                "still apply"
            )
        ),
        "charm_immune": 14 in enabled_ids,
        "stun_immune": 15 in enabled_ids,
        "snare_immune": 16 in enabled_ids,
        "fear_immune": 17 in enabled_ids,
        "pacify_immune": 31 in enabled_ids,
    }
