"""Read the raw Quarm world tables. No SQL writes or legacy-table fallbacks."""
from collections import defaultdict
from math import prod
from typing import Any

from django.db import connections

from quarm_reference.database import get_database_alias
from .names import display_npc_name


def _dict_fetchall(cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _select(sql, params=(), *, alias=None):
    with connections[alias or get_database_alias()].cursor() as cursor:
        cursor.execute(sql, params)
        return _dict_fetchall(cursor)


def _marks(values):
    return ", ".join(["%s"] * len(values))


def _like(value):
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


# One row per NPC/zone, regardless of the number of individual spawn points.
_LOCATIONS = """
    SELECT DISTINCT se.npcID AS npc_id, s.zone AS zone_code,
           z.long_name AS zone_name
    FROM spawnentry AS se
    JOIN spawn2 AS s ON s.spawngroupID = se.spawngroupID
    LEFT JOIN zone AS z ON z.short_name = s.zone
    WHERE s.enabled = 1 AND se.chance > 0
"""


def get_npc_metadata(npc_ids, *, alias=None):
    ids = list(dict.fromkeys(npc_ids))
    if not ids:
        return {}
    rows = _select(f"""
        SELECT n.id, r.name AS race, f.name AS primary_faction
        FROM npc_types AS n
        LEFT JOIN (SELECT id, MIN(name) AS name FROM races GROUP BY id) AS r
            ON r.id = n.race
        LEFT JOIN npc_faction AS nf ON nf.id = n.npc_faction_id
        LEFT JOIN faction_list AS f ON f.id = nf.primaryfaction
        WHERE n.id IN ({_marks(ids)})
    """, ids, alias=alias)
    result = {row["id"]: {**row, "zone_code": None, "zone_name": None} for row in rows}
    locations = _select(f"""
        SELECT * FROM ({_LOCATIONS}) AS loc
        WHERE loc.npc_id IN ({_marks(ids)})
        ORDER BY loc.npc_id, loc.zone_code, loc.zone_name
    """, ids, alias=alias)
    grouped = defaultdict(dict)
    for row in locations:
        grouped[row["npc_id"]][row["zone_code"]] = row["zone_name"]
    for npc_id, zones in grouped.items():
        if npc_id in result:
            # Preserve a string field for NPCs appearing in multiple zones.
            codes = sorted(code for code in zones if code)
            result[npc_id]["zone_code"] = "^".join(codes) or None
            result[npc_id]["zone_name"] = "^".join(zones[code] or code for code in codes) or None
    return result


def npc_ids_for_zone(zone):
    clean_zone = (zone or "").strip()
    if not clean_zone:
        return []
    return [row["npc_id"] for row in _select(f"""
        SELECT DISTINCT npc_id FROM ({_LOCATIONS}) AS loc
        WHERE LOWER(zone_code) = LOWER(%s) OR LOWER(zone_name) = LOWER(%s)
    """, [clean_zone, clean_zone])]


def database_health() -> dict:
    alias = get_database_alias()
    counts = _select("""
        SELECT (SELECT COUNT(*) FROM npc_types) AS npc_count,
               (SELECT COUNT(*) FROM loottable_entries AS lt
                JOIN lootdrop_entries AS ld ON ld.lootdrop_id = lt.lootdrop_id
                JOIN items AS i ON i.id = ld.item_id) AS loot_row_count
    """, alias=alias)[0]
    return {"status": "ok", "database_alias": alias, **counts}


def get_factions_for_npc(npc_id: int) -> list[dict]:
    return _select("""
        SELECT fe.faction_id, fl.name AS faction_name,
               fe.value AS faction_hit, fe.sort_order
        FROM npc_types AS n
        JOIN npc_faction_entries AS fe ON fe.npc_faction_id = n.npc_faction_id
        LEFT JOIN faction_list AS fl ON fl.id = fe.faction_id
        WHERE n.id = %s
        ORDER BY fe.sort_order, fl.name, fe.faction_id
    """, [npc_id])


def get_respawn_timers(stored_name, zone_code, *, npc_id=None) -> list[dict]:
    """Base spawn2 timers; not a live countdown or an instance override."""
    params = []
    if npc_id is not None:
        where = "n.id = %s"
        params.append(npc_id)
    elif stored_name:
        base_name = stored_name.lstrip("#")
        where = "(n.name = %s OR n.name = %s)"
        params.extend([base_name, f"#{base_name}"])
    else:
        return []
    codes = [part.strip() for part in (zone_code or "").split("^") if part.strip()]
    if codes:
        where += f" AND s.zone IN ({_marks(codes)})"
        params.extend(codes)
    rows = _select(f"""
        SELECT n.name AS stored_name, s.zone AS zone_code,
               z.zoneidnumber AS zone_id, s.respawntime, s.variance,
               s.id AS spawn_point_id, se.spawngroupID AS spawn_group_id,
               se.chance AS spawn_weight,
               (SELECT SUM(other.chance) FROM spawnentry AS other
                WHERE other.spawngroupID = se.spawngroupID AND other.chance > 0
               ) AS total_weight
        FROM npc_types AS n
        JOIN spawnentry AS se ON se.npcID = n.id
        JOIN spawn2 AS s ON s.spawngroupID = se.spawngroupID
        LEFT JOIN zone AS z ON z.short_name = s.zone
        WHERE {where} AND s.enabled = 1 AND se.chance > 0
        ORDER BY s.zone, s.respawntime, s.variance, s.id, n.id
    """, params)
    for row in rows:
        seconds = float(row.pop("respawntime"))
        half_variance = float(row.pop("variance")) / 2.0
        # EQMacEmu Spawn2::resetTimer randomizes in milliseconds and clamps
        # variable timers to a minimum of 100 ms.
        floor = 0.1 if half_variance else 0.0
        row["min_seconds"] = max(floor, seconds - half_variance)
        row["max_seconds"] = max(floor, seconds + half_variance)
        row["zone_id"] = str(row["zone_id"]) if row["zone_id"] is not None else None
        total = float(row.pop("total_weight") or 0)
        weight = float(row.pop("spawn_weight"))
        row["spawn_chance_percent"] = round(100 * weight / total, 4) if total else None
    return rows


def get_merchant_wares(merchant_id: int | None) -> list[dict]:
    if not merchant_id:
        return []
    return _select("""
        SELECT m.slot, m.item AS item_id, i.Name AS item_name
        FROM merchantlist AS m
        LEFT JOIN items AS i ON i.id = m.item
        WHERE m.merchantid = %s
        ORDER BY m.slot, i.Name, m.item
    """, [merchant_id])


def list_zones() -> list[dict]:
    rows = _select("""
        SELECT id, zoneidnumber AS zone_id, long_name AS name, short_name AS code,
               castdungeon AS is_dungeon, castoutdoor AS is_outdoor,
               reducedspawntimers AS has_reduced_spawn_timers,
               zone_exp_multiplier AS zem
        FROM zone ORDER BY long_name, short_name, id
    """)
    for row in rows:
        for field in ("is_dungeon", "is_outdoor", "has_reduced_spawn_timers"):
            row[field] = bool(row[field])
        row["zem"] = float(row["zem"]) if row["zem"] is not None else None
    return rows


def _conditional_drop(row):
    return (
        float(row["min_expansion"]) != -1
        or float(row["max_expansion"]) != -1
        or bool(row["content_flags"] or row["content_flags_disabled"])
    )


def _drop_group_probabilities(rows):
    """Base probability of at least one copy per group invocation.

    Unknown runtime content filters make a group's probability unknown.
    Configured drops are still returned in that case, with null probability.
    """
    if any(_conditional_drop(row) for row in rows):
        return {row["item_id"]: None for row in rows}
    first = rows[0]
    limit, minimum = int(first["droplimit"]), int(first["mindrop"])
    if limit == 0 and minimum == 0:
        return {
            row["item_id"]: 1 - (1 - min(100, max(0, float(row["chance"]))) / 100)
            ** max(0, int(row["item_multiplier"]))
            for row in rows
        }
    if len(rows) > 100 and limit == 0:
        limit = 10
    limit = max(limit, minimum)
    total = sum(max(0, float(row["chance"])) for row in rows)
    if total <= 0:
        return {row["item_id"]: 0.0 for row in rows}
    optional_roll = 1 - prod(1 - min(100, max(0, float(row["chance"]))) / 100 for row in rows)
    return {
        row["item_id"]: 1 - (1 - max(0, float(row["chance"])) / total) ** minimum
        * (1 - optional_roll * max(0, float(row["chance"])) / total) ** (limit - minimum)
        for row in rows
    }


def _loot_for_tables(loottable_ids):
    ids = sorted({int(value) for value in loottable_ids if value})
    if not ids:
        return {}
    rows = _select(f"""
        SELECT lt.loottable_id, lt.lootdrop_id, lt.probability,
               lt.multiplier AS table_multiplier, lt.multiplier_min,
               lt.droplimit, lt.mindrop, ld.item_id, i.Name AS item_name,
               ld.chance, ld.multiplier AS item_multiplier,
               ld.min_expansion, ld.max_expansion,
               ld.content_flags, ld.content_flags_disabled
        FROM loottable_entries AS lt
        JOIN lootdrop_entries AS ld ON ld.lootdrop_id = lt.lootdrop_id
        JOIN items AS i ON i.id = ld.item_id
        WHERE lt.loottable_id IN ({_marks(ids)})
        ORDER BY lt.loottable_id, lt.lootdrop_id, ld.item_id
    """, ids)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["loottable_id"], row["lootdrop_id"])].append(row)
    result = defaultdict(dict)
    for (table_id, _), entries in groups.items():
        first = entries[0]
        probabilities = _drop_group_probabilities(entries)
        multiplier = max(0, int(first["table_multiplier"]))
        guaranteed = min(multiplier, max(0, int(first["multiplier_min"])))
        table_probability = min(100, max(0, float(first["probability"]))) / 100
        for entry in entries:
            item_id = entry["item_id"]
            probability = probabilities[item_id]
            if multiplier == 0 or table_probability == 0:
                no_drop = 1.0
            elif probability is None:
                no_drop = None
            else:
                no_drop = ((1 - probability) ** guaranteed
                           * (1 - table_probability * probability) ** (multiplier - guaranteed))
            item = result[table_id].setdefault(item_id, {
                "item_id": item_id, "item_name": entry["item_name"] or "", "no_drop": 1.0,
            })
            # A guaranteed source remains guaranteed even if another is conditional.
            if item["no_drop"] == 0 or no_drop == 0:
                item["no_drop"] = 0.0
            elif item["no_drop"] is None or no_drop is None:
                item["no_drop"] = None
            else:
                item["no_drop"] *= no_drop
    output = {}
    for table_id, items in result.items():
        for item in items.values():
            no_drop = item.pop("no_drop")
            item["drop_chance"] = round(100 * (1 - no_drop), 4) if no_drop is not None else None
        output[table_id] = sorted(items.values(), key=lambda row: (
            row["drop_chance"] is None, -(row["drop_chance"] or 0), row["item_name"], row["item_id"],
        ))
    return output


def get_loot_for_table(loottable_id: int | None) -> list[dict]:
    return _loot_for_tables([loottable_id]).get(loottable_id, [])


_ITEM_SOURCES = f"""
    SELECT DISTINCT i.id AS item_id, i.Name AS item_name,
           lt.loottable_id, n.id AS npc_id, n.name AS stored_npc_name,
           loc.zone_code, loc.zone_name
    FROM items AS i
    JOIN lootdrop_entries AS ld ON ld.item_id = i.id
    JOIN loottable_entries AS lt ON lt.lootdrop_id = ld.lootdrop_id
    LEFT JOIN npc_types AS n ON n.loottable_id = lt.loottable_id
    LEFT JOIN ({_LOCATIONS}) AS loc ON loc.npc_id = n.id
"""


def _format_sources(rows):
    loot = _loot_for_tables([row["loottable_id"] for row in rows])
    chance = {(tid, item["item_id"]): item["drop_chance"]
              for tid, items in loot.items() for item in items}
    for row in rows:
        table_id = row.pop("loottable_id")
        row["npc_name"] = display_npc_name(row.pop("stored_npc_name") or "")
        row["drop_chance"] = chance.get((table_id, row["item_id"]))
    return rows


def search_items(name, *, zone=None, limit=50, offset=0):
    where = ["i.Name LIKE %s ESCAPE '!'"]
    params = [f"%{_like(name.strip())}%"]
    if zone and zone.strip():
        where.append("(LOWER(loc.zone_code) = LOWER(%s) OR LOWER(loc.zone_name) = LOWER(%s))")
        params.extend([zone.strip(), zone.strip()])
    base = _ITEM_SOURCES + " WHERE " + " AND ".join(where)
    total = int(_select(f"SELECT COUNT(*) AS total FROM ({base}) AS sources", params)[0]["total"])
    rows = _select(base + " ORDER BY i.Name, n.id, loc.zone_code, lt.loottable_id LIMIT %s OFFSET %s",
                   [*params, limit, offset])
    return total, _format_sources(rows)


def resolve_item_reference(item_name, *, zone=None):
    clean_name = item_name.strip()
    if not clean_name:
        return None
    params = [clean_name]
    sql = "SELECT DISTINCT i.id AS item_id, i.Name AS item_name FROM items AS i WHERE LOWER(i.Name) = LOWER(%s)"
    if zone and zone.strip():
        sql = """
            SELECT DISTINCT i.id AS item_id, i.Name AS item_name
            FROM items AS i
            JOIN lootdrop_entries AS ld ON ld.item_id = i.id
            JOIN loottable_entries AS lt ON lt.lootdrop_id = ld.lootdrop_id
            JOIN npc_types AS n ON n.loottable_id = lt.loottable_id
            JOIN spawnentry AS se ON se.npcID = n.id
            JOIN spawn2 AS s ON s.spawngroupID = se.spawngroupID
            LEFT JOIN zone AS z ON z.short_name = s.zone
            WHERE LOWER(i.Name) = LOWER(%s) AND s.enabled = 1 AND se.chance > 0
              AND (LOWER(s.zone) = LOWER(%s) OR LOWER(z.long_name) = LOWER(%s))
        """
        params.extend([zone.strip(), zone.strip()])
    rows = _select(sql + " ORDER BY i.id", params)
    if not rows:
        return None
    if len(rows) > 1:
        raise ValueError(f"Multiple Quarm item IDs match '{clean_name}' in zone '{zone}': "
                         f"{[row['item_id'] for row in rows]}")
    return rows[0]


def get_item_reference(item_id: int):
    items = _select("SELECT id AS item_id, Name AS item_name FROM items WHERE id = %s", [item_id])
    if not items:
        return None
    rows = _format_sources(_select(_ITEM_SOURCES + " WHERE i.id = %s ORDER BY loc.zone_name, n.name, lt.loottable_id",
                                   [item_id]))
    return {**items[0], "drops": [{key: row[key] for key in (
        "npc_id", "npc_name", "zone_code", "zone_name", "drop_chance",
    )} for row in rows]}
