from django.db import connections

from quarm_reference.database import get_database_alias


def get_item_by_id(item_id: int) -> dict | None:
    if item_id < 1:
        return None

    sql = """
        SELECT DISTINCT
            `Item_ID` AS item_id,
            `Item_Name` AS item_name
        FROM `NPC_Drops`
        WHERE `Item_ID` = %s
        ORDER BY `Item_Name`
        LIMIT 1
    """

    with connections[get_database_alias()].cursor() as cursor:
        cursor.execute(sql, [item_id])
        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "item_id": int(row[0]),
        "item_name": row[1] or "",
    }