from typing import Any

from django.db import connections

from quarm_reference.database import get_database_alias
from .names import display_npc_name


def _dict_fetchall(cursor) -> list[dict[str, Any]]:
    columns = [column[0] for column in cursor.description]
    return [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]


def database_health() -> dict:
    alias = get_database_alias()
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM `NPC`")
        npc_count = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT(*) FROM `NPC_Drops`")
        loot_row_count = int(cursor.fetchone()[0])

    return {
        "status": "ok",
        "database_alias": alias,
        "npc_count": npc_count,
        "loot_row_count": loot_row_count,
    }


def get_loot_for_table(loottable_id: int | None) -> list[dict]:
    if not loottable_id:
        return []

    sql = """
        SELECT
            `Item_ID` AS item_id,
            `Item_Name` AS item_name,
            `Drop_Chance` AS drop_chance
        FROM `NPC_Drops`
        WHERE `Loottable_ID` = %s
        ORDER BY
            `Drop_Chance` DESC,
            `Item_Name` ASC,
            `Item_ID` ASC
    """

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql, [loottable_id])
        rows = _dict_fetchall(cursor)

    for row in rows:
        row["item_name"] = row["item_name"] or ""
        if row["drop_chance"] is not None:
            row["drop_chance"] = round(float(row["drop_chance"]), 4)
    return rows


def get_factions_for_npc(npc_id: int) -> list[dict]:
    sql = """
        SELECT
            `Faction_ID` AS faction_id,
            `Faction_Name` AS faction_name,
            `Faction_Hit` AS faction_hit,
            `Sort_Order` AS sort_order
        FROM `NPC_Factions`
        WHERE `NPC_ID` = %s
        ORDER BY `Sort_Order` ASC, `Faction_Name` ASC
    """

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql, [npc_id])
        return _dict_fetchall(cursor)


def get_respawn_timers(
    stored_name: str | None,
    zone_code: str | None,
) -> list[dict]:
    if not stored_name:
        return []

    sql = """
        SELECT
            `Min_RespawnTimer` AS min_seconds,
            `Max_RespawnTimer` AS max_seconds,
            `Mob_Name` AS stored_name,
            `Zone_Code` AS zone_code,
            `Zone_ID` AS zone_id
        FROM `NPC_RespawnTimers`
        WHERE (`Mob_Name` = %s OR `Mob_Name` = %s)
    """
    base_name = stored_name.lstrip("#")
    params: list[Any] = [base_name, f"#{base_name}"]

    if zone_code:
        escaped_zone = (
            zone_code.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )
        sql += (
            " AND (`Zone_Code` = %s "
            "OR `Zone_Code` LIKE %s ESCAPE '!')"
        )
        params.extend([zone_code, f"{escaped_zone}^%"])

    sql += " ORDER BY `Min_RespawnTimer`, `Max_RespawnTimer`"

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql, params)
        rows = _dict_fetchall(cursor)

    for row in rows:
        if row["min_seconds"] is not None:
            row["min_seconds"] = float(row["min_seconds"])
        if row["max_seconds"] is not None:
            row["max_seconds"] = float(row["max_seconds"])
    return rows


def get_merchant_wares(merchant_id: int | None) -> list[dict]:
    if not merchant_id:
        return []

    sql = """
        SELECT
            `Slot` AS slot,
            `Item_ID` AS item_id,
            `Item_Name` AS item_name
        FROM `NPC_Wares`
        WHERE `MerchantID` = %s
        ORDER BY `Slot` ASC, `Item_Name` ASC
    """

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql, [merchant_id])
        return _dict_fetchall(cursor)


def list_zones() -> list[dict]:
    sql = """
        SELECT
            `ID` AS id,
            `Zone_ID` AS zone_id,
            `Name` AS name,
            `Code` AS code,
            `IsDungeon` AS is_dungeon,
            `IsOutdoor` AS is_outdoor,
            `HasReducedSpawnTimers` AS has_reduced_spawn_timers,
            `ZEM` AS zem
        FROM `Zones`
        ORDER BY `Name` ASC, `Code` ASC
    """

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql)
        rows = _dict_fetchall(cursor)

    for row in rows:
        row["is_dungeon"] = bool(row["is_dungeon"])
        row["is_outdoor"] = bool(row["is_outdoor"])
        row["has_reduced_spawn_timers"] = bool(
            row["has_reduced_spawn_timers"]
        )
        if row["zem"] is not None:
            row["zem"] = float(row["zem"])
    return rows


def search_items(
    name: str,
    *,
    zone: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    where = ["d.`Item_Name` LIKE %s"]
    params: list[Any] = [f"%{name.strip()}%"]

    if zone:
        where.append(
            "(n.`Zone_Code` = %s OR n.`Zone_Name` = %s)"
        )
        clean_zone = zone.strip()
        params.extend([clean_zone, clean_zone])

    where_sql = " AND ".join(where)
    count_sql = f"""
        SELECT COUNT(*)
        FROM `NPC_Drops` AS d
        LEFT JOIN `NPC` AS n
            ON n.`Loottable_ID` = d.`Loottable_ID`
        WHERE {where_sql}
    """
    data_sql = f"""
        SELECT
            d.`Item_ID` AS item_id,
            d.`Item_Name` AS item_name,
            d.`Drop_Chance` AS drop_chance,
            n.`ID` AS npc_id,
            n.`Name` AS stored_npc_name,
            n.`Zone_Code` AS zone_code,
            n.`Zone_Name` AS zone_name
        FROM `NPC_Drops` AS d
        LEFT JOIN `NPC` AS n
            ON n.`Loottable_ID` = d.`Loottable_ID`
        WHERE {where_sql}
        ORDER BY
            d.`Item_Name` ASC,
            d.`Drop_Chance` DESC,
            n.`Name` ASC,
            n.`Zone_Code` ASC
        LIMIT %s OFFSET %s
    """

    alias = get_database_alias()
    with connections[alias].cursor() as cursor:
        cursor.execute(count_sql, params)
        total = int(cursor.fetchone()[0])
        cursor.execute(data_sql, [*params, limit, offset])
        rows = _dict_fetchall(cursor)

    for row in rows:
        row["npc_name"] = display_npc_name(
            row.pop("stored_npc_name")
        )
        if row["drop_chance"] is not None:
            row["drop_chance"] = round(float(row["drop_chance"]), 4)
    return total, rows
