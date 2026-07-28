from django.db.models import Q, QuerySet

from quarm_reference.database import get_database_alias
from quarm_reference.models import QuarmNPC
from .names import normalize_npc_name, stored_npc_name_variants
from .queries import (
    get_factions_for_npc,
    get_loot_for_table,
    get_merchant_wares,
    get_respawn_timers,
)
from .special_abilities import (
    crowd_control_summary,
    parse_special_abilities,
)

NPC_CLASS_NAMES = {
    0: "Unknown",
    1: "Warrior",
    2: "Cleric",
    3: "Paladin",
    4: "Ranger",
    5: "Shadow Knight",
    6: "Druid",
    7: "Monk",
    8: "Bard",
    9: "Rogue",
    10: "Shaman",
    11: "Necromancer",
    12: "Wizard",
    13: "Magician",
    14: "Enchanter",
    15: "Beastlord",
    16: "Berserker",

    # NPC-only classes
    20: "Warrior Guildmaster",
    21: "Cleric Guildmaster",
    22: "Paladin Guildmaster",
    23: "Ranger Guildmaster",
    24: "Shadow Knight Guildmaster",
    25: "Druid Guildmaster",
    26: "Monk Guildmaster",
    27: "Bard Guildmaster",
    28: "Rogue Guildmaster",
    29: "Shaman Guildmaster",
    30: "Necromancer Guildmaster",
    31: "Wizard Guildmaster",
    32: "Magician Guildmaster",
    33: "Enchanter Guildmaster",
    34: "Beastlord Guildmaster",
    35: "Berserker Guildmaster",
    40: "Banker",
    41: "Merchant",
}

def _queryset() -> QuerySet[QuarmNPC]:
    return QuarmNPC.objects.using(get_database_alias()).all()


def _summary(npc: QuarmNPC) -> dict:
    return {
        "id": npc.id,
        "name": npc.display_name,
        "stored_name": npc.name or "",
        "zone_code": npc.zone_code,
        "zone_name": npc.zone_name,
        "level": npc.level,
        "max_level": npc.max_level,
        "race": npc.race,
        "npc_class_id": npc.npc_class_id,
        "npc_class_name": get_npc_class_name(
            npc.npc_class_id
        ),
    }    
    


def _detail(npc: QuarmNPC) -> dict:
    payload = _summary(npc)
    payload.update(
        {
            "combat": {
                "hp": npc.hp,
                "mana": npc.mana,
                "ac": npc.ac,
                "min_damage": npc.min_damage,
                "max_damage": npc.max_damage,
                "attack_count": npc.attack_count,
                "attack_delay": npc.attack_delay,
                "run_speed": npc.run_speed,
                "hp_regen": npc.combat_hp_regen,
                "mana_regen": npc.combat_mana_regen,
            },
            "resistances": {
                "magic": npc.magic_resist,
                "fire": npc.fire_resist,
                "cold": npc.cold_resist,
                "disease": npc.disease_resist,
                "poison": npc.poison_resist,
            },
            "visibility": {
                "sees_invisible": bool(npc.see_invis),
                "sees_invisible_undead": bool(
                    npc.see_invis_undead
                ),
                "sees_sneak": bool(npc.see_sneak),
                "sees_improved_hide": bool(npc.see_improved_hide),
            },
            "is_quest_npc": bool(npc.is_quest_npc),
            "unique_spawn_by_name": bool(npc.unique_spawn_by_name),
            "primary_faction": npc.primary_faction,
            "npc_faction_id": npc.npc_faction_id,
            "merchant_id": npc.merchant_id,
            "loottable_id": npc.loottable_id,
            "npc_spells_id": npc.npc_spells_id,
            "raw_special_abilities": npc.special_abilities or "",
            "special_abilities": parse_special_abilities(
                npc.special_abilities
            ),
            "crowd_control": crowd_control_summary(
                npc.special_abilities,
                npc.slow_mitigation,
            ),
            "loot": get_loot_for_table(npc.loottable_id),
            "faction_hits": get_factions_for_npc(npc.id),
            "respawn_timers": get_respawn_timers(
                npc.name,
                npc.zone_code,
            ),
            "merchant_wares": get_merchant_wares(npc.merchant_id),
        }
    )
    return payload

def get_npc_class_name(class_id: int | None) -> str:
    if class_id is None:
        return "Unknown"

    return NPC_CLASS_NAMES.get(
        class_id,
        f"Unknown Class ({class_id})",
    )

def search_npcs(
    *,
    name: str | None = None,
    zone: str | None = None,
    minimum_level: int | None = None,
    maximum_level: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    queryset = _queryset()

    if name:
        normalized_name = normalize_npc_name(name).lstrip("#")
        if normalized_name:
            queryset = queryset.filter(
                name__icontains=normalized_name
            )

    if zone:
        clean_zone = zone.strip()
        queryset = queryset.filter(
            Q(zone_code__iexact=clean_zone)
            | Q(zone_name__iexact=clean_zone)
        )

    if minimum_level is not None:
        queryset = queryset.filter(level__gte=minimum_level)
    if maximum_level is not None:
        queryset = queryset.filter(level__lte=maximum_level)

    total = queryset.count()
    npcs = queryset.order_by("name", "zone_code", "id")[
        offset : offset + limit
    ]
    return total, [_summary(npc) for npc in npcs]


def get_npcs_by_name(
    name: str,
    *,
    zone: str | None = None,
    maximum_matches: int = 20,
) -> list[dict]:
    normal_name, marked_name = stored_npc_name_variants(name)
    queryset = _queryset().filter(
        Q(name__iexact=normal_name)
        | Q(name__iexact=marked_name)
    )

    if zone:
        clean_zone = zone.strip()
        queryset = queryset.filter(
            Q(zone_code__iexact=clean_zone)
            | Q(zone_name__iexact=clean_zone)
        )

    npcs = queryset.order_by("zone_code", "id")[:maximum_matches]
    return [_detail(npc) for npc in npcs]


def get_npc_detail(npc_id: int) -> dict | None:
    try:
        npc = _queryset().get(pk=npc_id)
    except QuarmNPC.DoesNotExist:
        return None
    return _detail(npc)


def get_npc_loot(npc_id: int) -> list[dict] | None:
    try:
        npc = _queryset().only("id", "loottable_id").get(pk=npc_id)
    except QuarmNPC.DoesNotExist:
        return None
    return get_loot_for_table(npc.loottable_id)

def get_npc_names_for_zone(zone: str) -> list[str]:
    clean_zone = zone.strip()

    if not clean_zone:
        return []

    queryset = (
        _queryset()
        .filter(
            Q(zone_code__iexact=clean_zone)
            | Q(zone_name__iexact=clean_zone)
        )
        .only("name")
        .order_by("name")
    )

    names = {
        npc.display_name.strip()
        for npc in queryset
        if npc.display_name and npc.display_name.strip()
    }

    return sorted(
        names,
        key=str.casefold,
    )