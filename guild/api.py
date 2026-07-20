from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import APIKeyHeader

from .models import ApiKey, GuildMember, LootRecord, RaidEvent


class GuildApiKeyAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        if not key or not key.startswith("lasf_"):
            return None

        try:
            api_key = ApiKey.objects.get(prefix=key[:16], active=True)
        except ApiKey.DoesNotExist:
            return None

        if api_key.expired or not api_key.matches(key):
            return None

        ApiKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        return api_key


api_key_auth = GuildApiKeyAuth()
api = NinjaAPI(title="Loot and Some Fun API", version="1.0.0")


class LootCreate(Schema):
    member_id: int
    item_name: str
    zone: str = ""
    npc: str = ""
    notes: str = ""


class LootUpdate(Schema):
    member_id: int | None = None
    item_name: str | None = None
    zone: str | None = None
    npc: str | None = None
    notes: str | None = None


def require_permission(request, permission):
    if not request.auth.has_permission(permission):
        raise HttpError(403, f"API key lacks permission: {permission}")


def serialize_loot(record):
    return {
        "id": record.id,
        "member_id": record.member_id,
        "member": record.member.character_name,
        "item_name": record.item_name,
        "zone": record.zone,
        "npc": record.npc,
        "notes": record.notes,
        "awarded_at": record.awarded_at,
    }


@api.get("/health", auth=None)
def health(request):
    return {"status": "healthy"}


@api.get("/v1/members", auth=api_key_auth)
def list_members(request):
    require_permission(request, "members:read")
    return [
        {
            "id": member.id,
            "character_name": member.character_name,
            "class_name": member.class_name,
            "level": member.level,
            "rank": member.rank,
            "active": member.active,
        }
        for member in GuildMember.objects.all()
    ]


@api.get("/v1/raids", auth=api_key_auth)
def list_raids(request):
    require_permission(request, "raids:read")
    return [
        {
            "id": event.id,
            "title": event.title,
            "zone": event.zone,
            "start_at": event.start_at,
            "end_at": event.end_at,
            "status": event.status,
        }
        for event in RaidEvent.objects.filter(public=True)
    ]


@api.get("/v1/loot", auth=api_key_auth)
def list_loot(request, limit: int = 100):
    require_permission(request, "loot:read")
    limit = min(max(limit, 1), 500)
    return [
        serialize_loot(record)
        for record in LootRecord.objects.select_related("member")[:limit]
    ]


@api.post("/v1/loot", auth=api_key_auth)
def create_loot(request, payload: LootCreate):
    require_permission(request, "loot:create")
    member = get_object_or_404(GuildMember, pk=payload.member_id)
    record = LootRecord.objects.create(
        member=member,
        item_name=payload.item_name,
        zone=payload.zone,
        npc=payload.npc,
        notes=payload.notes,
    )
    return 201, serialize_loot(record)


@api.patch("/v1/loot/{record_id}", auth=api_key_auth)
def update_loot(request, record_id: int, payload: LootUpdate):
    require_permission(request, "loot:update")
    record = get_object_or_404(LootRecord.objects.select_related("member"), pk=record_id)
    changes = payload.model_dump(exclude_unset=True)

    if "member_id" in changes:
        record.member = get_object_or_404(GuildMember, pk=changes.pop("member_id"))

    for field, value in changes.items():
        setattr(record, field, value)

    record.save()
    record.refresh_from_db()
    return serialize_loot(record)


@api.delete("/v1/loot/{record_id}", auth=api_key_auth)
def delete_loot(request, record_id: int):
    require_permission(request, "loot:delete")
    record = get_object_or_404(LootRecord, pk=record_id)
    record.delete()
    return 204, None
