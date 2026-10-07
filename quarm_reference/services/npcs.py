from django.db.models import Q, QuerySet

from quarm_reference.database import get_database_alias
from quarm_reference.models import QuarmNPC
from .names import normalize_npc_name, stored_npc_name_variants
from .queries import (
    get_factions_for_npc, get_loot_for_table, get_merchant_wares,
    get_npc_metadata, get_respawn_timers, npc_ids_for_zone,
)
from .special_abilities import crowd_control_summary, parse_special_abilities


NPC_CLASS_NAMES = {
    0: "Unknown", 1: "Warrior", 2: "Cleric", 3: "Paladin", 4: "Ranger",
    5: "Shadow Knight", 6: "Druid", 7: "Monk", 8: "Bard", 9: "Rogue",
    10: "Shaman", 11: "Necromancer", 12: "Wizard", 13: "Magician",
    14: "Enchanter", 15: "Beastlord", 16: "Berserker",
    20: "Warrior Guildmaster", 21: "Cleric Guildmaster", 22: "Paladin Guildmaster",
    23: "Ranger Guildmaster", 24: "Shadow Knight Guildmaster", 25: "Druid Guildmaster",
    26: "Monk Guildmaster", 27: "Bard Guildmaster", 28: "Rogue Guildmaster",
    29: "Shaman Guildmaster", 30: "Necromancer Guildmaster", 31: "Wizard Guildmaster",
    32: "Magician Guildmaster", 33: "Enchanter Guildmaster", 34: "Beastlord Guildmaster",
    35: "Berserker Guildmaster", 40: "Banker", 41: "Merchant",
}


def _queryset() -> QuerySet[QuarmNPC]:
    return QuarmNPC.objects.using(get_database_alias()).all()


def _with_metadata(queryset):
    npcs = list(queryset)
    metadata = get_npc_metadata([npc.id for npc in npcs])
    for npc in npcs:
        npc.__dict__["reference_metadata"] = metadata.get(npc.id, {})
    return npcs


def _filter_zone(queryset, zone):
    if zone and zone.strip():
        return queryset.filter(pk__in=npc_ids_for_zone(zone))
    return queryset


def get_npc_class_name(class_id: int | None) -> str:
    if class_id is None:
        return "Unknown"
    return NPC_CLASS_NAMES.get(class_id, f"Unknown Class ({class_id})")


def _summary(npc: QuarmNPC) -> dict:
    return {
        "id": npc.id, "name": npc.display_name, "stored_name": npc.name or "",
        "zone_code": npc.zone_code, "zone_name": npc.zone_name,
        "level": npc.level, "max_level": npc.max_level, "race": npc.race,
        "npc_class_id": npc.npc_class_id,
        "npc_class_name": get_npc_class_name(npc.npc_class_id),
    }


def _detail(npc: QuarmNPC) -> dict:
    payload = _summary(npc)
    payload.update({
        "combat": {
            "hp": npc.hp, "mana": npc.mana, "ac": npc.ac,
            "min_damage": npc.min_damage, "max_damage": npc.max_damage,
            "attack_count": npc.attack_count, "attack_delay": npc.attack_delay,
            "run_speed": npc.run_speed, "hp_regen": npc.combat_hp_regen,
            "mana_regen": npc.combat_mana_regen,
        },
        "resistances": {
            "magic": npc.magic_resist, "fire": npc.fire_resist,
            "cold": npc.cold_resist, "disease": npc.disease_resist,
            "poison": npc.poison_resist,
        },
        "visibility": {
            "sees_invisible": bool(npc.see_invis),
            "sees_invisible_undead": bool(npc.see_invis_undead),
            "sees_sneak": bool(npc.see_sneak),
            "sees_improved_hide": bool(npc.see_improved_hide),
        },
        "is_quest_npc": bool(npc.is_quest_npc),
        "unique_spawn_by_name": bool(npc.unique_spawn_by_name),
        "primary_faction": npc.primary_faction,
        "npc_faction_id": npc.npc_faction_id,
        "merchant_id": npc.merchant_id, "loottable_id": npc.loottable_id,
        "npc_spells_id": npc.npc_spells_id,
        "raw_special_abilities": npc.special_abilities or "",
        "special_abilities": parse_special_abilities(npc.special_abilities),
        "crowd_control": crowd_control_summary(npc.special_abilities, npc.slow_mitigation),
        "loot": get_loot_for_table(npc.loottable_id),
        "faction_hits": get_factions_for_npc(npc.id),
        # Match the NPC ID, so same-name NPCs do not inherit one another's timers.
        # All its configured zones are included; zone is a search constraint only.
        "respawn_timers": get_respawn_timers(None, None, npc_id=npc.id),
        "merchant_wares": get_merchant_wares(npc.merchant_id),
    })
    return payload


def search_npcs(*, name=None, zone=None, minimum_level=None, maximum_level=None,
                limit=50, offset=0) -> tuple[int, list[dict]]:
    queryset = _queryset()
    if name:
        normalized = normalize_npc_name(name).lstrip("#")
        if normalized:
            queryset = queryset.filter(name__icontains=normalized)
    queryset = _filter_zone(queryset, zone)
    if minimum_level is not None:
        queryset = queryset.filter(level__gte=minimum_level)
    if maximum_level is not None:
        queryset = queryset.filter(level__lte=maximum_level)
    total = queryset.count()
    npcs = _with_metadata(queryset.order_by("name", "id")[offset:offset + limit])
    return total, [_summary(npc) for npc in npcs]


def get_npcs_by_name(name, *, zone=None, maximum_matches=20) -> list[dict]:
    normal, marked = stored_npc_name_variants(name)
    queryset = _queryset().filter(Q(name__iexact=normal) | Q(name__iexact=marked))
    queryset = _filter_zone(queryset, zone)
    npcs = _with_metadata(queryset.order_by("id")[:maximum_matches])
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
    if not (zone or "").strip():
        return []
    queryset = _filter_zone(_queryset(), zone).only("name").order_by("name")
    return sorted({npc.display_name.strip() for npc in queryset if npc.display_name.strip()},
                  key=str.casefold)
