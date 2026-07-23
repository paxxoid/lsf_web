from datetime import date, datetime
from typing import Optional

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from ninja import NinjaAPI, Schema, Status
from ninja.errors import HttpError
from ninja.security import APIKeyHeader
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from ninja.errors import HttpError


from .models import (
    ApiKey,
    GuildApplication,
    GuildMember,
    GuildNews,
    LootRecord,
    RaidAttendance,
    RaidEvent,
    EverQuestClass
)


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

        ApiKey.objects.filter(pk=api_key.pk).update(
            last_used_at=timezone.now()
        )
        return api_key


api_key_auth = GuildApiKeyAuth()

api = NinjaAPI(
    title="Loot and Some Fun API",
    version="1.1.0",
)


def require_permission(request, permission):
    if not request.auth or not request.auth.has_permission(permission):
        raise HttpError(403, f"API key lacks permission: {permission}")


def bounded_page(limit, offset):
    return min(max(limit, 1), 500), max(offset, 0)


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------
0

class GuildMemberUpdate(Schema):
    character_name: Optional[str] = None
    character_type: Optional[str] = None
    main_character_id: Optional[int] = None
    class_name: Optional[str] = None
    race: Optional[str] = None
    level: Optional[int] = None
    rank: Optional[str] = None
    active: Optional[bool] = None
    raider: Optional[bool] = None
    featured: Optional[bool] = None
    joined_at: Optional[date] = None
    bio: Optional[str] = None
    last_raid_attended: Optional[datetime] = None


class RaidEventUpdate(Schema):
    title: Optional[str] = None
    zone: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: Optional[str] = None
    status: Optional[str] = None
    public: Optional[bool] = None


class RaidAttendanceUpdate(Schema):
    raid_event_id: Optional[int] = None
    member_id: Optional[int] = None
    attended: Optional[bool] = None
    arrival_time: Optional[datetime] = None
    notes: Optional[str] = None


class LootRecordUpdate(Schema):
    raid_event_id: Optional[int] = None
    member_id: Optional[int] = None
    item_name: Optional[str] = None
    awarded_at: Optional[datetime] = None
    zone: Optional[str] = None
    npc: Optional[str] = None
    notes: Optional[str] = None


class GuildNewsUpdate(Schema):
    title: Optional[str] = None
    slug: Optional[str] = None
    summary: Optional[str] = None
    body: Optional[str] = None
    published_at: Optional[datetime] = None
    is_published: Optional[bool] = None
    featured: Optional[bool] = None


class GuildApplicationUpdate(Schema):
    character_name: Optional[str] = None
    class_name: Optional[str] = None
    level: Optional[int] = None
    discord_name: Optional[str] = None
    timezone_name: Optional[str] = None
    typical_play_times: Optional[str] = None
    experience: Optional[str] = None
    why_join: Optional[str] = None
    status: Optional[str] = None


class GuildMemberOut(Schema):
    id: int
    character_name: str
    character_type: str
    character_type_display: str

    main_character_id: Optional[int] = None
    main_character: Optional[str] = None

    class_name: str
    class_name_display: str
    race: str
    level: int

    rank: str
    rank_display: str

    active: bool
    raider: bool
    featured: bool

    joined_at: date
    bio: str
    last_raid_attended: Optional[datetime] = None

class LootRecordCreateOut(Schema):
    raid_event_id: int
    member_id: int
    item_name: str
    awarded_at: datetime
    zone: str
    npc: Optional[str] = None
    notes:Optional[str] = None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def serialize_member(member):
    return {
        "id": member.id,
        "character_name": member.character_name,
        "character_type": member.character_type,
        "character_type_display": member.get_character_type_display(),
        "main_character_id": member.main_character_id,
        "main_character": (
            member.main_character.character_name
            if member.main_character
            else None
        ),
        "class_name": member.class_name,
        "class_name_display": member.get_class_name_display(),
        "race": member.race,
        "level": member.level,
        "rank": member.rank,
        "rank_display": member.get_rank_display(),
        "active": member.active,
        "raider": member.raider,
        "featured": member.featured,
        "joined_at": member.joined_at,
        "bio": member.bio,
        "last_raid_attended": member.last_raid_attended,
    }

def serialize_raid(event):
    return {
        "id": event.id,
        "title": event.title,
        "zone": event.zone,
        "start_at": event.start_at,
        "end_at": event.end_at,
        "description": event.description,
        "status": event.status,
        "status_display": event.get_status_display(),
        "public": event.public,
    }


def serialize_attendance(record):
    return {
        "id": record.id,
        "raid_event_id": record.raid_event_id,
        "raid_event": record.raid_event.title,
        "raid_date": record.raid_date,
        "member_id": record.member_id,
        "member": record.member.character_name,
        "class_name": record.member.class_name,
        "class_name_display": record.member.get_class_name_display(),
        "attended": record.attended,
        "arrival_time": record.arrival_time,
        "is_late": record.is_late,
        "notes": record.notes,
    }


def serialize_loot(record):
    return {
        "id": record.id,
        "raid_event_id": record.raid_event_id,
        "raid_event": (
            record.raid_event.title
            if record.raid_event
            else None
        ),
        "member_id": record.member_id,
        "member": record.member.character_name,
        "item_name": record.item_name,
        "toon_type": record.toon_type,
        "toon_type_display": record.get_toon_type_display(),
        "zone": record.zone,
        "npc": record.npc,
        "notes": record.notes,
        "awarded_at": record.awarded_at,
    }


def serialize_news(story):
    return {
        "id": story.id,
        "title": story.title,
        "slug": story.slug,
        "summary": story.summary,
        "body": str(story.body),
        "featured_image_id": story.featured_image_id,
        "published_at": story.published_at,
        "is_published": story.is_published,
        "featured": story.featured,
        "created_at": story.created_at,
        "updated_at": story.updated_at,
        "url": story.get_absolute_url(),
    }


def serialize_application(application):
    return {
        "id": application.id,
        "character_name": application.character_name,
        "class_name": application.class_name,
        "class_name_display": application.get_class_name_display(),
        "level": application.level,
        "discord_name": application.discord_name,
        "timezone_name": application.timezone_name,
        "typical_play_times": application.typical_play_times,
        "experience": application.experience,
        "why_join": application.why_join,
        "status": application.status,
        "status_display": application.get_status_display(),
        "submitted_at": application.submitted_at,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api.get("/health", auth=None)
def health(request):
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Guild members: select and update
# ---------------------------------------------------------------------------


class LootCreate(Schema):
    raid_event_id: int
    member_id: int
    item_name: str
    awarded_at: datetime
    zone: str
    npc: Optional[str] = None
    notes:Optional[str] = None
        
        

class GuildMemberCreate(Schema):
    character_name: str
    character_type: str = GuildMember.CharacterType.MAIN
    main_character_id: Optional[int] = None
    class_name: str
    race: str = ""
    level: int = 1
    rank: str = GuildMember.Rank.MEMBER
    active: bool = True
    raider: bool = False
    featured: bool = False
    joined_at: Optional[date] = None
    bio: Optional[str] = ""




@api.post(
    "/v1/members/create",
    auth=api_key_auth,
    response={201: GuildMemberOut},
)
def create_member(request, payload: GuildMemberCreate):
    require_permission(request, "members:create")

    data = payload.model_dump(exclude_unset=True)

    character_name = data["character_name"].strip()

    if not character_name:
        raise HttpError(
            400,
            "character_name cannot be empty.",
        )

    if GuildMember.objects.filter(
        character_name__iexact=character_name,
    ).exists():
        raise HttpError(
            409,
            f"A guild member named '{character_name}' already exists.",
        )

    data["character_name"] = character_name

    character_type = data.get(
        "character_type",
        GuildMember.CharacterType.MAIN,
    )

    main_character_id = data.pop(
        "main_character_id",
        None,
    )

    if character_type == GuildMember.CharacterType.ALT:
        if not main_character_id:
            raise HttpError(
                400,
                "main_character_id is required for an alt.",
            )

        main_character = get_object_or_404(
            GuildMember,
            pk=main_character_id,
        )

    elif character_type == GuildMember.CharacterType.MAIN:
        main_character = None

    else:
        raise HttpError(
            400,
            "character_type must be either 'main' or 'alt'.",
        )

    if data.get("joined_at") is None:
        data.pop("joined_at", None)

    try:
        with transaction.atomic():
            member = GuildMember(
                main_character=main_character,
                **data,
            )

            member.full_clean()
            member.save()

            member = (
                GuildMember.objects
                .select_related("main_character")
                .get(pk=member.pk)
            )

            response_data = serialize_member(member)

    except ValidationError as exc:
        errors = getattr(
            exc,
            "message_dict",
            {"error": exc.messages},
        )

        if "character_name" in errors:
            raise HttpError(
                409,
                f"A guild member named '{character_name}' already exists.",
            )

        formatted_errors = {
            field: list(messages)
            for field, messages in errors.items()
        }

        raise HttpError(
            400,
            formatted_errors,
        )

    except IntegrityError:
        raise HttpError(
            409,
            f"A guild member named '{character_name}' already exists.",
        )

    return Status(
        201,
        serialize_member(member),
    )


@api.get("/v1/members", auth=api_key_auth)
def list_members(
    request,
    limit: int = 100,
    offset: int = 0,
    active: Optional[bool] = None,
):
    require_permission(request, "members:read")
    limit, offset = bounded_page(limit, offset)

    queryset = GuildMember.objects.select_related("main_character")
    if active is not None:
        queryset = queryset.filter(active=active)

    return [
        serialize_member(member)
        for member in queryset[offset:offset + limit]
    ]


@api.get("/v1/members/{member_id}", auth=api_key_auth)
def get_member(request, member_id: int):
    require_permission(request, "members:read")
    member = get_object_or_404(
        GuildMember.objects.select_related("main_character"),
        pk=member_id,
    )
    return serialize_member(member)

@api.get(
    "/v1/members/class/{class_name}",
    auth=api_key_auth,
)
def get_members_by_class(request, class_name: str):
    require_permission(request, "members:read")

    requested_class = class_name.strip().lower()

    class_lookup = {
        value.lower(): value
        for value, label in EverQuestClass.choices
    }

    class_lookup.update({
        label.lower(): value
        for value, label in EverQuestClass.choices
    })

    class_value = class_lookup.get(requested_class)

    if class_value is None:
        valid_classes = [
            value
            for value, label in EverQuestClass.choices
        ]

        raise HttpError(
            400,
            {
                "message": f"Invalid class: {class_name}",
                "valid_classes": valid_classes,
            },
        )

    members = (
        GuildMember.objects
        .filter(class_name=class_value)
        .select_related("main_character")
        .order_by("character_name")
    )

    return [
        serialize_member(member)
        for member in members
    ]
    


@api.patch("/v1/members/{member_id}", auth=api_key_auth)
def update_member(request, member_id: int, payload: GuildMemberUpdate):
    require_permission(request, "members:update")
    member = get_object_or_404(GuildMember, pk=member_id)
    changes = payload.model_dump(exclude_unset=True)

    if "main_character_id" in changes:
        main_id = changes.pop("main_character_id")
        member.main_character = (
            get_object_or_404(GuildMember, pk=main_id)
            if main_id is not None
            else None
        )

    for field, value in changes.items():
        setattr(member, field, value)

    member.full_clean()
    member.save()
    member.refresh_from_db()
    return serialize_member(member)


# ---------------------------------------------------------------------------
# Raid events: select and update
# ---------------------------------------------------------------------------

@api.get("/v1/raids", auth=api_key_auth)
def list_raids(
    request,
    limit: int = 100,
    offset: int = 0,
    public: Optional[bool] = None,
    status: Optional[str] = None,
):
    require_permission(request, "raids:read")
    limit, offset = bounded_page(limit, offset)

    queryset = RaidEvent.objects.all()
    if public is not None:
        queryset = queryset.filter(public=public)
    if status:
        queryset = queryset.filter(status=status)

    return [
        serialize_raid(event)
        for event in queryset[offset:offset + limit]
    ]


@api.get("/v1/raids/{raid_id}", auth=api_key_auth)
def get_raid(request, raid_id: int):
    require_permission(request, "raids:read")
    return serialize_raid(get_object_or_404(RaidEvent, pk=raid_id))


@api.patch("/v1/raids/{raid_id}", auth=api_key_auth)
def update_raid(request, raid_id: int, payload: RaidEventUpdate):
    require_permission(request, "raids:update")
    event = get_object_or_404(RaidEvent, pk=raid_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)

    event.full_clean()
    event.save()
    return serialize_raid(event)


# ---------------------------------------------------------------------------
# Raid attendance: select and update
# ---------------------------------------------------------------------------

@api.get("/v1/attendance", auth=api_key_auth)
def list_attendance(
    request,
    raid_event_id: Optional[int] = None,
    member_id: Optional[int] = None,
    attended: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "attendance:read")
    limit, offset = bounded_page(limit, offset)

    queryset = RaidAttendance.objects.select_related(
        "raid_event",
        "member",
    )

    if raid_event_id is not None:
        queryset = queryset.filter(raid_event_id=raid_event_id)
    if member_id is not None:
        queryset = queryset.filter(member_id=member_id)
    if attended is not None:
        queryset = queryset.filter(attended=attended)

    return [
        serialize_attendance(record)
        for record in queryset[offset:offset + limit]
    ]


@api.get("/v1/attendance/{attendance_id}", auth=api_key_auth)
def get_attendance(request, attendance_id: int):
    require_permission(request, "attendance:read")
    record = get_object_or_404(
        RaidAttendance.objects.select_related("raid_event", "member"),
        pk=attendance_id,
    )
    return serialize_attendance(record)


@api.patch("/v1/attendance/{attendance_id}", auth=api_key_auth)
def update_attendance(
    request,
    attendance_id: int,
    payload: RaidAttendanceUpdate,
):
    require_permission(request, "attendance:update")
    record = get_object_or_404(RaidAttendance, pk=attendance_id)
    changes = payload.model_dump(exclude_unset=True)

    if "raid_event_id" in changes:
        record.raid_event = get_object_or_404(
            RaidEvent,
            pk=changes.pop("raid_event_id"),
        )

    if "member_id" in changes:
        record.member = get_object_or_404(
            GuildMember,
            pk=changes.pop("member_id"),
        )

    for field, value in changes.items():
        setattr(record, field, value)

    record.full_clean()
    record.save()



    record.refresh_from_db()
    return serialize_attendance(record)


# ---------------------------------------------------------------------------
# Loot records: select and update
# ---------------------------------------------------------------------------

@api.get("/v1/loot", auth=api_key_auth)
def list_loot(
    request,
    raid_event_id: Optional[int] = None,
    member_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "loot:read")
    limit, offset = bounded_page(limit, offset)

    queryset = LootRecord.objects.select_related("member", "raid_event")
    if raid_event_id is not None:
        queryset = queryset.filter(raid_event_id=raid_event_id)
    if member_id is not None:
        queryset = queryset.filter(member_id=member_id)

    return [
        serialize_loot(record)
        for record in queryset[offset:offset + limit]
    ]



@api.get(
    "/v1/loot/character/{character_name}",
    auth=api_key_auth,
)
def get_loot_by_character_name(request, character_name: str):
    require_permission(request, "loot:read")

    member = get_object_or_404(
        GuildMember,
        character_name__iexact=character_name.strip(),
    )

    records = (
        LootRecord.objects
        .filter(member=member)
        .select_related(
            "member",
            "raid_event",
        )
        .order_by("-awarded_at")
    )

    return [
        serialize_loot(record)
        for record in records
    ]


@api.get("/v1/loot/{record_id}", auth=api_key_auth)
def get_loot(request, record_id: int):
    require_permission(request, "loot:read")
    record = get_object_or_404(
        LootRecord.objects.select_related("member", "raid_event"),
        pk=record_id,
    )
    return serialize_loot(record)


@api.patch("/v1/loot/{record_id}", auth=api_key_auth)
def update_loot(request, record_id: int, payload: LootRecordUpdate):
    require_permission(request, "loot:update")
    record = get_object_or_404(LootRecord, pk=record_id)
    changes = payload.model_dump(exclude_unset=True)

    if "member_id" in changes:
        record.member = get_object_or_404(
            GuildMember,
            pk=changes.pop("member_id"),
        )

    if "raid_event_id" in changes:
        raid_id = changes.pop("raid_event_id")
        record.raid_event = (
            get_object_or_404(RaidEvent, pk=raid_id)
            if raid_id is not None
            else None
        )

    for field, value in changes.items():
        setattr(record, field, value)

    record.full_clean()
    record.save()
    record.refresh_from_db()
    return serialize_loot(record)

@api.post(
    "/v1/loot/create",
    auth=api_key_auth,
    response={201: LootRecordCreateOut},
)
def create_loot(request, payload: LootCreate):
    require_permission(request, "loot:create")

    data = payload.model_dump(exclude_unset=True)

    member_id = data.pop("member_id")
    raid_event_id = data.pop("raid_event_id")

    try:
        member = GuildMember.objects.get(pk=member_id)
    except GuildMember.DoesNotExist:
        raise HttpError(
            404,
            f"Guild member ID {member_id} was not found.",
        )

    try:
        raid_event = RaidEvent.objects.get(pk=raid_event_id)
    except RaidEvent.DoesNotExist:
        raise HttpError(
            404,
            f"Raid event ID {raid_event_id} was not found.",
        )

    try:
        with transaction.atomic():
            loot = LootRecord(
                member=member,
                raid_event=raid_event,
                **data,
            )

            loot.full_clean()
            loot.save()

            loot = (
                LootRecord.objects
                .select_related(
                    "member",
                    "raid_event",
                )
                .get(pk=loot.pk)
            )

    except ValidationError as exc:
        errors = getattr(
            exc,
            "message_dict",
            {"error": exc.messages},
        )

        raise HttpError(
            400,
            {
                field: list(messages)
                for field, messages in errors.items()
            },
        )

    return Status(
        201,
        serialize_loot(loot),
    )


# ---------------------------------------------------------------------------
# Guild news: select and update
# featured_image is read-only here; manage the actual image in Wagtail.
# ---------------------------------------------------------------------------

@api.get("/v1/news", auth=api_key_auth)
def list_news(
    request,
    published: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "news:read")
    limit, offset = bounded_page(limit, offset)

    queryset = GuildNews.objects.all()
    if published is not None:
        queryset = queryset.filter(is_published=published)

    return [
        serialize_news(story)
        for story in queryset[offset:offset + limit]
    ]


@api.get("/v1/news/{news_id}", auth=api_key_auth)
def get_news(request, news_id: int):
    require_permission(request, "news:read")
    return serialize_news(get_object_or_404(GuildNews, pk=news_id))


@api.patch("/v1/news/{news_id}", auth=api_key_auth)
def update_news(request, news_id: int, payload: GuildNewsUpdate):
    require_permission(request, "news:update")
    story = get_object_or_404(GuildNews, pk=news_id)
    changes = payload.model_dump(exclude_unset=True)

    if "title" in changes and "slug" not in changes and not story.slug:
        changes["slug"] = slugify(changes["title"])

    for field, value in changes.items():
        setattr(story, field, value)

    story.full_clean()
    story.save()
    return serialize_news(story)


# ---------------------------------------------------------------------------
# Guild applications: select and update
# ---------------------------------------------------------------------------

@api.get("/v1/applications", auth=api_key_auth)
def list_applications(
    request,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    require_permission(request, "applications:read")
    limit, offset = bounded_page(limit, offset)

    queryset = GuildApplication.objects.all()
    if status:
        queryset = queryset.filter(status=status)

    return [
        serialize_application(application)
        for application in queryset[offset:offset + limit]
    ]


@api.get("/v1/applications/{application_id}", auth=api_key_auth)
def get_application(request, application_id: int):
    require_permission(request, "applications:read")
    application = get_object_or_404(
        GuildApplication,
        pk=application_id,
    )
    return serialize_application(application)


@api.patch("/v1/applications/{application_id}", auth=api_key_auth)
def update_application(
    request,
    application_id: int,
    payload: GuildApplicationUpdate,
):
    require_permission(request, "applications:update")
    application = get_object_or_404(
        GuildApplication,
        pk=application_id,
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(application, field, value)

    application.full_clean()
    application.save()
    return serialize_application(application)