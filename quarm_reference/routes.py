from ninja import Router
from ninja.errors import HttpError

from guild.permissions import require_permission

from .schemas import (
    ErrorSchema,
    HealthSchema,
    ItemSearchResponseSchema,
    LootDropSchema,
    NPCDetailSchema,
    NPCNameLookupResponseSchema,
    NPCSearchResponseSchema,
    ZoneSchema,
)
from .services.npcs import (
    get_npc_detail,
    get_npc_loot,
    get_npcs_by_name,
    get_npc_names_for_zone,
    search_npcs,
)
from .services.queries import database_health, list_zones, search_items, get_item_reference


router = Router(tags=["Quarm Reference"])


def _validate_paging(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100:
        raise HttpError(422, "limit must be between 1 and 100")
    if offset < 0:
        raise HttpError(422, "offset cannot be negative")


@router.get(
    "/health",
    response=HealthSchema,
    summary="Check Quarm database access",
)
def health(request):
    return database_health()


@router.get(
    "/npcs",
    response=NPCSearchResponseSchema,
    summary="Search NPCs",
)
def npc_search(
    request,
    name: str | None = None,
    zone: str | None = None,
    minimum_level: int | None = None,
    maximum_level: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    _validate_paging(limit, offset)

    if minimum_level is not None and minimum_level < 1:
        raise HttpError(422, "minimum_level must be at least 1")
    if maximum_level is not None and maximum_level < 1:
        raise HttpError(422, "maximum_level must be at least 1")
    if (
        minimum_level is not None
        and maximum_level is not None
        and minimum_level > maximum_level
    ):
        raise HttpError(
            422,
            "minimum_level cannot be greater than maximum_level",
        )

    total, results = search_npcs(
        name=name,
        zone=zone,
        minimum_level=minimum_level,
        maximum_level=maximum_level,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }


@router.get(
    "/npcs/by-name",
    response={200: NPCNameLookupResponseSchema, 404: ErrorSchema},
    summary="Get full NPC records by exact name",
)
def npc_by_name(
    request,
    name: str,
    zone: str | None = None,
):
    if not name.strip():
        raise HttpError(422, "name cannot be blank")

    results = get_npcs_by_name(name, zone=zone)
    if not results:
        raise HttpError(404, f"No NPC named '{name}' was found.")
    return {"count": len(results), "results": results}


@router.get(
    "/npcs/{int:npc_id}",
    response={200: NPCDetailSchema, 404: ErrorSchema},
    summary="Get one NPC with loot, abilities, and stats",
)
def npc_detail(request, npc_id: int):
    result = get_npc_detail(npc_id)
    if result is None:
        raise HttpError(404, f"NPC {npc_id} was not found.")
    return result


@router.get(
    "/npcs/{int:npc_id}/loot",
    response={200: list[LootDropSchema], 404: ErrorSchema},
    summary="Get only an NPC's loot",
)
def npc_loot(request, npc_id: int):
    result = get_npc_loot(npc_id)
    if result is None:
        raise HttpError(404, f"NPC {npc_id} was not found.")
    return result


@router.get(
    "/items",
    response=ItemSearchResponseSchema,
    summary="Find items and the NPCs that drop them",
)
def item_search(
    request,
    name: str,
    zone: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    _validate_paging(limit, offset)
    if not name.strip():
        raise HttpError(422, "name cannot be blank")

    total, results = search_items(
        name,
        zone=zone,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }

@router.get("/items/{int:item_id}")
def item_by_id(
    request,
    item_id: int,
):
    require_permission(
        request,
        "quarm:npcs:read",
    )

    item = get_item_reference(item_id)

    if item is None:
        raise HttpError(
            404,
            f"Quarm item {item_id} was not found.",
        )

    return item


@router.get(
    "/zones",
    response=list[ZoneSchema],
    summary="List zones",
)
def zones(request):
    return list_zones()


@router.get("/npcs-simple")
def list_npcs(
    request,
    zone: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "quarm:npcs:read")
    _validate_paging(limit, offset)

    clean_zone = zone.strip()

    if not clean_zone:
        raise HttpError(
            422,
            "zone cannot be blank",
        )

    names = get_npc_names_for_zone(
        clean_zone,
    )

    return {
        "zone": clean_zone,
        "count": len(names),
        "names": names,
    }