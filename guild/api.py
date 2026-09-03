from datetime import date, datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
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
from quarm_reference.routes import router as quarm_router
from quarm_reference.services.items import get_item_by_id
from .permissions import require_permission
from .services.attendance import get_attendance_summary

from quarm_reference.services.queries import (
    resolve_item_reference,
)

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




# def require_permission(request, permission):
#     if not request.auth or not request.auth.has_permission(permission):
#         raise HttpError(403, f"API key lacks permission: {permission}")


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


class RaidEventCreate(Schema):
    title: str
    zone: str = ""
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: str = ""
    status: str = RaidEvent.Status.SCHEDULED
    public: bool = True

    # Friendly input: allow specifying date + time in EST (e.g. for users)
    start_date: Optional[date] = None
    start_time_est: Optional[str] = None  # expected HH:MM or HH:MM:SS
    end_date: Optional[date] = None
    end_time_est: Optional[str] = None


class RaidEventUpdate(Schema):
    title: Optional[str] = None
    zone: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: Optional[str] = None
    status: Optional[str] = None
    public: Optional[bool] = None
    # Friendly input for updates as well
    start_date: Optional[date] = None
    start_time_est: Optional[str] = None
    end_date: Optional[date] = None
    end_time_est: Optional[str] = None


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


class AttendanceOverallPlayerOut(Schema):
    main_character: GuildMemberOut
    alts: list[GuildMemberOut]

    total_attendance_percent: float
    attendance_percentage: float

    total_raid_minutes: int
    attendance_percentage_raw_minutes: float


class AttendanceOverallOut(Schema):
    cutoff_date: datetime
    through_date: datetime

    total_raid_events: int
    total_raid_minutes_available: int

    players: list[AttendanceOverallPlayerOut]

class LootRecordCreateOut(Schema):
    raid_event_id: int
    member_id: int
    item_id: Optional[int] = None
    item_url: Optional[str] = None
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
    main_character = (
        record.member.main_character
        or record.member
    )

    return {
        "id": record.id,

        "raid_event_id": record.raid_event_id,
        "raid_event": record.raid_event.title,
        "raid_date": record.raid_date,
        "zone": record.raid_event.zone,

        "member_id": record.member_id,
        "member": record.member.character_name,

        "main_character_id": main_character.id,
        "main_character": main_character.character_name,

        "class_name": record.member.class_name,
        "class_name_display":
            record.member.get_class_name_display(),

        "attended": record.attended,
        "arrival_time": record.arrival_time,
        "is_late": record.is_late,

        "total_raid_minutes":
            record.total_raid_minutes,

        "attendance_percent":
            record.attendance_percent,

        "notes": record.notes,
    }

def serialize_loot(
    record,
    *,
    request=None,
):
    item_url = None

    if record.item_id:
        relative_url = (
            f"/api/v1/quarm/items/"
            f"{record.item_id}"
        )

        item_url = (
            #request.build_absolute_uri(relative_url) #for LSF API
            f"https://www.pqdi.cc/item/{record.item_id}" # for pqdi
            if request
            else relative_url
        )

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
        "item_id": record.item_id,
        "item_url": item_url,
        "item_name": record.item_name,
        "toon_type": record.toon_type,
        "toon_type_display": (
            record.get_toon_type_display()
        ),
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
    item_id: Optional[int] = None
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

class RaidAttendanceAdd(Schema):
    raid_event_id: int
    character_names: list[str]
    total_raid_minutes: Optional[dict[str, int]] = None
    attendance_percent: Optional[dict[str, float]] = None


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

@api.post(
    "/v1/raids/create",
    auth=api_key_auth,
    response={201: dict},
)
def create_raid(request, payload: RaidEventCreate):
    require_permission(request, "raids:create")

    data = payload.model_dump(exclude_unset=True)
    # Support user-friendly EST date+time inputs. If provided, combine
    # and convert to UTC for storage.
    def _combine_est(d: Optional[date], t: Optional[str], field_name: str):
        if d is None and t is None:
            return None
        if d is None or not t:
            raise HttpError(400, {field_name: ["Both date and time must be provided together."]})

        parsed_time = None
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(t, fmt).time()
                break
            except Exception:
                continue

        if parsed_time is None:
            raise HttpError(400, {field_name: ["Time must be in HH:MM or HH:MM:SS format."]})

        ny = ZoneInfo("America/New_York")
        naive_dt = datetime.combine(d, parsed_time)
        est_dt = naive_dt.replace(tzinfo=ny)
        return est_dt.astimezone(dt_timezone.utc)

    # start
    if "start_date" in data or "start_time_est" in data:
        start_dt = _combine_est(
            data.pop("start_date", None),
            data.pop("start_time_est", None),
            "start",
        )
        data["start_at"] = start_dt

    # end
    if "end_date" in data or "end_time_est" in data:
        end_dt = _combine_est(
            data.pop("end_date", None),
            data.pop("end_time_est", None),
            "end",
        )
        data["end_at"] = end_dt
    # Ensure we have start_at and end_at after processing friendly inputs
    if data.get("start_at") is None:
        raise HttpError(400, {"start_at": ["This field may not be blank."]})
    if data.get("end_at") is None:
        raise HttpError(400, {"end_at": ["This field may not be blank."]})
    title = data.get("title", "").strip()
    if not title:
        raise HttpError(400, {"title": ["This field may not be blank."]})

    data["title"] = title

    try:
        with transaction.atomic():
            event = RaidEvent(**data)
            event.full_clean()
            event.save()
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
        ) from exc

    return Status(201, serialize_raid(event))


@api.get("/v1/raids", auth=api_key_auth)
def list_raids(
    request,
    limit: int = 5000,
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

    changes = payload.model_dump(exclude_unset=True)

    # Support EST friendly inputs for updates as well
    def _combine_est_update(d: Optional[date], t: Optional[str], field_name: str):
        if d is None and t is None:
            return None
        if d is None or not t:
            raise HttpError(400, {field_name: ["Both date and time must be provided together."]})

        parsed_time = None
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(t, fmt).time()
                break
            except Exception:
                continue

        if parsed_time is None:
            raise HttpError(400, {field_name: ["Time must be in HH:MM or HH:MM:SS format."]})

        ny = ZoneInfo("America/New_York")
        naive_dt = datetime.combine(d, parsed_time)
        est_dt = naive_dt.replace(tzinfo=ny)
        return est_dt.astimezone(dt_timezone.utc)

    if "start_date" in changes or "start_time_est" in changes:
        start_dt = _combine_est_update(
            changes.pop("start_date", None),
            changes.pop("start_time_est", None),
            "start",
        )
        if start_dt is not None:
            changes["start_at"] = start_dt

    if "end_date" in changes or "end_time_est" in changes:
        end_dt = _combine_est_update(
            changes.pop("end_date", None),
            changes.pop("end_time_est", None),
            "end",
        )
        if end_dt is not None:
            changes["end_at"] = end_dt

    for field, value in changes.items():
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
    zone: Optional[str] = None,
    limit: int = 5000,
    offset: int = 0,
    
):
    require_permission(request, "attendance:read")
    limit, offset = bounded_page(limit, offset)

    queryset = RaidAttendance.objects.select_related(
        "raid_event",
        "member",
        "member__main_character",
    )

    if raid_event_id is not None:
        queryset = queryset.filter(raid_event_id=raid_event_id)
    if member_id is not None:
        queryset = queryset.filter(member_id=member_id)
    if attended is not None:
        queryset = queryset.filter(attended=attended)

    if zone:
        queryset = queryset.filter(
            raid_event__zone__iexact=zone.strip()
        )        

    return [
        serialize_attendance(record)
        for record in queryset[offset:offset + limit]
    ]
@api.get(
    "/v1/attendance/overall",
    auth=api_key_auth,
    response=AttendanceOverallOut,
    summary="Get Overall Raid Attendance",
    description="""
Returns rolled-up raid attendance.

### Attendance logic

- Future raids are excluded.
- Attendance from registered alts is credited to their main character.
- Main + alt attendance is combined per raid.
- Attendance for one raid is capped at 100%.
- Main + alt raid minutes are capped at the total duration of the raid.
- Missed scheduled raids count as 0%.

Overall attendance:

`sum of credited attendance percentages / total scheduled raids`

### Parameters

- `days` - Number of days to calculate attendance over. Default: 90.
- `main_character_id` - Optionally return one specific main character.
- `character_name` - Optionally search for a main character by name.
""",
)
def overall_attendance(
    request,
    days: int = 90,
    main_character_id: Optional[int] = None,
    character_name: Optional[str] = None,
):
    require_permission(
        request,
        "attendance:read",
    )

    # ---------------------------------------------------------
    # Validate days
    # ---------------------------------------------------------
    if days < 1:
        raise HttpError(
            400,
            "days must be greater than 0.",
        )

    if days > 3650:
        raise HttpError(
            400,
            "days cannot exceed 3650.",
        )

    # ---------------------------------------------------------
    # Shared attendance calculation
    # ---------------------------------------------------------
    summary = get_attendance_summary(
        days=days,
    )

    # ---------------------------------------------------------
    # Active main characters
    # ---------------------------------------------------------
    mains = (
        GuildMember.objects
        .filter(
            active=True,
            main_character__isnull=True,
        )
        .select_related("main_character")
    )

    # ---------------------------------------------------------
    # Optional main character ID filter
    # ---------------------------------------------------------
    if main_character_id is not None:
        mains = mains.filter(
            id=main_character_id
        )

    # ---------------------------------------------------------
    # Optional character name filter
    # ---------------------------------------------------------
    if character_name:
        mains = mains.filter(
            character_name__icontains=
                character_name.strip()
        )

    mains = list(
        mains.order_by("character_name")
    )

    # ---------------------------------------------------------
    # Main IDs
    # ---------------------------------------------------------
    main_ids = [
        main.id
        for main in mains
    ]

    # ---------------------------------------------------------
    # Registered alts
    # ---------------------------------------------------------
    alts = (
        GuildMember.objects
        .filter(
            main_character_id__in=main_ids,
        )
        .select_related("main_character")
        .order_by("character_name")
    )

    # ---------------------------------------------------------
    # Group alts by main
    # ---------------------------------------------------------
    alts_by_main = {}

    for alt in alts:
        alts_by_main.setdefault(
            alt.main_character_id,
            [],
        ).append(alt)

    # ---------------------------------------------------------
    # Build response
    # ---------------------------------------------------------
    players = []

    for main in mains:

        stats = summary["players"].get(
            main.id,
            {
                "total_attendance_percent": 0.0,
                "attendance_percentage": 0.0,
                "total_raid_minutes": 0,
                "attendance_percentage_raw_minutes": 0.0,
            },
        )

        players.append(
            {
                "main_character":
                    serialize_member(main),

                "alts": [
                    serialize_member(alt)
                    for alt in alts_by_main.get(
                        main.id,
                        [],
                    )
                ],

                "total_attendance_percent": round(
                    float(
                        stats.get(
                            "total_attendance_percent",
                            0.0,
                        )
                    ),
                    2,
                ),

                "attendance_percentage": round(
                    float(
                        stats.get(
                            "attendance_percentage",
                            0.0,
                        )
                    ),
                    2,
                ),

                "total_raid_minutes": int(
                    stats.get(
                        "total_raid_minutes",
                        0,
                    )
                ),

                "attendance_percentage_raw_minutes": round(
                    float(
                        stats.get(
                            "attendance_percentage_raw_minutes",
                            0.0,
                        )
                    ),
                    2,
                ),
            }
        )

    # ---------------------------------------------------------
    # Highest attendance first
    # ---------------------------------------------------------
    players.sort(
        key=lambda player: (
            -player["attendance_percentage"],
            player[
                "main_character"
            ]["character_name"].lower(),
        )
    )

    return {
        "cutoff_date":
            summary["cutoff_date"],

        "through_date":
            summary["through_date"],

        "total_raid_events":
            summary["total_raid_events"],

        "total_raid_minutes_available":
            summary[
                "total_raid_minutes_available"
            ],

        "players":
            players,
    }

@api.get("/v1/attendance/{int:attendance_id}", auth=api_key_auth)
def get_attendance(request, attendance_id: int):
    require_permission(request, "attendance:read")

    record = get_object_or_404(
        RaidAttendance.objects.select_related(
            "raid_event",
            "member",
        ),
        pk=attendance_id,
    )

    return serialize_attendance(record)

@api.patch("/v1/attendance/{int:attendance_id}", auth=api_key_auth)
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

@api.post(
    "/v1/attendance/add",
    auth=api_key_auth,
)
def add_raid_attendance(
    request,
    payload: RaidAttendanceAdd,
    summary="Add or update raid attendance",
    description="""
        Adds or updates attendance for a raid event.

        ### Behavior

        - New characters are added with `arrival_time` set to the current server time.
        - Characters missing from the current roster receive a `leave_time`.
        - Characters who rejoin have their `leave_time` cleared.
        - `total_raid_minutes` is optional raw per-character data supplied by the client.
        - `attendance_percent` is optional raw per-character data supplied by the client.
        - `total_raid_minutes` and `attendance_percent` are **not calculated by the API**.
        - An empty `character_names` list does not mark all members as having left.

        ### Example payload

        ```json
        {
        "raid_event_id": 10,
        "character_names": [
            "Paxxar",
            "SuccorPunch"
        ],
        "total_raid_minutes": {
            "Paxxar": 120,
            "SuccorPunch": 9
        },
        "attendance_percent": {
            "Paxxar": 100,
            "SuccorPunch": 7.5
        }
        }

        """,    
):
    require_permission(request, "attendance:update")

    raid_event = get_object_or_404(
        RaidEvent,
        pk=payload.raid_event_id,
    )

    now = timezone.now()

    # ---------------------------------------------------------
    # CURRENT RAID ROSTER
    # ---------------------------------------------------------

    requested_names = {
        name.strip().casefold()
        for name in payload.character_names
        if name and name.strip()
    }

    submitted_names = [
        name.strip()
        for name in payload.character_names
        if name and name.strip()
    ]

    # ---------------------------------------------------------
    # RAW TOTAL RAID MINUTES
    #
    # No calculation is performed.
    # Whatever the client sends is stored.
    # ---------------------------------------------------------

    minutes_by_name = {}

    if payload.total_raid_minutes:

        for name, minutes in payload.total_raid_minutes.items():

            clean_name = name.strip().casefold()

            if not clean_name:
                continue

            if minutes < 0:
                raise HttpError(
                    400,
                    (
                        "total_raid_minutes cannot be "
                        f"negative for '{name}'."
                    ),
                )

            minutes_by_name[clean_name] = minutes

    # ---------------------------------------------------------
    # RAW ATTENDANCE PERCENT
    #
    # No calculation is performed.
    # Whatever the client sends is stored.
    # ---------------------------------------------------------

    percent_by_name = {}

    if payload.attendance_percent:

        for name, percent in payload.attendance_percent.items():

            clean_name = name.strip().casefold()

            if not clean_name:
                continue

            if percent < 0 or percent > 100:
                raise HttpError(
                    400,
                    (
                        "attendance_percent must be between "
                        f"0 and 100 for '{name}'."
                    ),
                )

            percent_by_name[clean_name] = percent

    # ---------------------------------------------------------
    # RESOLVE CURRENT ROSTER NAMES
    # ---------------------------------------------------------

    members_by_name = {}

    if submitted_names:

        members_by_name = {
            member.character_name.casefold(): member
            for member in GuildMember.objects.filter(
                character_name__in=submitted_names
            )
        }

        # Fallback for case-sensitive database collations.
        missing_lookups = (
            requested_names
            - set(members_by_name)
        )

        if missing_lookups:

            for member in GuildMember.objects.all():

                normalized_name = (
                    member.character_name.casefold()
                )

                if normalized_name in missing_lookups:
                    members_by_name[
                        normalized_name
                    ] = member

    # ---------------------------------------------------------
    # VALID CURRENT RAID MEMBERS
    # ---------------------------------------------------------

    valid_members = [
        members_by_name[name]
        for name in requested_names
        if name in members_by_name
    ]

    current_member_ids = {
        member.id
        for member in valid_members
    }

    current_members_by_id = {
        member.id: member
        for member in valid_members
    }

    # ---------------------------------------------------------
    # GET ALL EXISTING ATTENDANCE FOR THIS RAID
    #
    # We need every attendance row so we can:
    #   - detect departures
    #   - detect rejoins
    #   - update minutes
    #   - update attendance percentage
    # ---------------------------------------------------------

    existing_records = list(
        RaidAttendance.objects
        .filter(raid_event=raid_event)
        .select_related("member")
    )

    existing_by_member_id = {
        record.member_id: record
        for record in existing_records
    }

    existing_member_ids = set(
        existing_by_member_id
    )

    # ---------------------------------------------------------
    # NEW ARRIVALS
    # ---------------------------------------------------------

    new_members = []
    new_records = []

    if requested_names:

        new_member_ids = (
            current_member_ids
            - existing_member_ids
        )

        new_members = [
            current_members_by_id[member_id]
            for member_id in new_member_ids
        ]

        new_records = [
            RaidAttendance(
                raid_event=raid_event,
                member=member,
                attended=True,
                arrival_time=now,
                leave_time=None,

                total_raid_minutes=(
                    minutes_by_name.get(
                        member.character_name.casefold()
                    )
                ),

                attendance_percent=(
                    percent_by_name.get(
                        member.character_name.casefold()
                    )
                ),
            )
            for member in new_members
        ]

    # ---------------------------------------------------------
    # MEMBERS WHO LEFT
    #
    # Only run leave detection when character_names contains
    # a roster. An empty roster will NOT mark everyone left.
    # ---------------------------------------------------------

    left_records = []

    if requested_names:

        for record in existing_records:

            if (
                record.member_id
                not in current_member_ids
                and record.leave_time is None
            ):
                record.leave_time = now
                left_records.append(record)

    # ---------------------------------------------------------
    # MEMBERS WHO REJOINED
    #
    # If they are back in the roster and previously had a
    # leave_time, clear leave_time.
    #
    # Original arrival_time remains unchanged.
    # ---------------------------------------------------------

    rejoined_records = []

    if requested_names:

        for member_id in (
            current_member_ids
            & existing_member_ids
        ):

            record = existing_by_member_id[
                member_id
            ]

            if record.leave_time is not None:
                record.leave_time = None
                rejoined_records.append(record)

    # ---------------------------------------------------------
    # RAW TOTAL RAID MINUTES
    #
    # Completely independent of roster add/remove logic.
    # ---------------------------------------------------------

    minutes_records = []

    if minutes_by_name:

        for record in existing_records:

            member_name = (
                record.member
                .character_name
                .casefold()
            )

            if member_name in minutes_by_name:

                record.total_raid_minutes = (
                    minutes_by_name[
                        member_name
                    ]
                )

                minutes_records.append(record)

    # ---------------------------------------------------------
    # RAW ATTENDANCE PERCENT
    #
    # Completely independent of roster add/remove logic.
    # ---------------------------------------------------------

    percent_records = []

    if percent_by_name:

        for record in existing_records:

            member_name = (
                record.member
                .character_name
                .casefold()
            )

            if member_name in percent_by_name:

                record.attendance_percent = (
                    percent_by_name[
                        member_name
                    ]
                )

                percent_records.append(record)

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------

    with transaction.atomic():

        if new_records:
            RaidAttendance.objects.bulk_create(
                new_records,
                ignore_conflicts=True,
            )

        if left_records:
            RaidAttendance.objects.bulk_update(
                left_records,
                ["leave_time"],
            )

        if rejoined_records:
            RaidAttendance.objects.bulk_update(
                rejoined_records,
                ["leave_time"],
            )

        if minutes_records:
            RaidAttendance.objects.bulk_update(
                minutes_records,
                ["total_raid_minutes"],
            )

        if percent_records:
            RaidAttendance.objects.bulk_update(
                percent_records,
                ["attendance_percent"],
            )

    # ---------------------------------------------------------
    # UNKNOWN CHARACTER NAMES FROM ROSTER
    # ---------------------------------------------------------

    unknown_names = sorted(
        original_name.strip()
        for original_name in payload.character_names
        if (
            original_name
            and original_name.strip()
            and original_name
            .strip()
            .casefold()
            not in members_by_name
        )
    )

    # ---------------------------------------------------------
    # EXISTING MEMBERS STILL PRESENT
    # ---------------------------------------------------------

    existing_present_ids = (
        current_member_ids
        & existing_member_ids
    )

    rejoined_member_ids = {
        record.member_id
        for record in rejoined_records
    }

    existing_present_ids -= rejoined_member_ids

    # ---------------------------------------------------------
    # NEW RECORDS THAT RECEIVED RAW VALUES
    # ---------------------------------------------------------

    new_minutes_members = {
        record.member.character_name
        for record in new_records
        if record.total_raid_minutes is not None
    }

    new_percent_members = {
        record.member.character_name
        for record in new_records
        if record.attendance_percent is not None
    }

    # ---------------------------------------------------------
    # RESPONSE
    # ---------------------------------------------------------

    return {
        "raid_event_id": raid_event.id,
        "raid_event": raid_event.title,

        "added_count": len(new_records),
        "existing_count": len(existing_present_ids),
        "left_count": len(left_records),
        "rejoined_count": len(rejoined_records),

        "minutes_updated_count": (
            len(minutes_records)
            + len(new_minutes_members)
        ),

        "attendance_percent_updated_count": (
            len(percent_records)
            + len(new_percent_members)
        ),

        "unknown_character_names": unknown_names,

        "added_members": sorted(
            member.character_name
            for member in new_members
        ),

        "left_members": sorted(
            record.member.character_name
            for record in left_records
        ),

        "rejoined_members": sorted(
            record.member.character_name
            for record in rejoined_records
        ),

        "minutes_updated_members": sorted(
            {
                record.member.character_name
                for record in minutes_records
            }
            | new_minutes_members
        ),

        "attendance_percent_updated_members": sorted(
            {
                record.member.character_name
                for record in percent_records
            }
            | new_percent_members
        ),
    }


# ---------------------------------------------------------------------------
# Loot records: select and update
# ---------------------------------------------------------------------------

@api.get("/v1/loot", auth=api_key_auth)
def list_loot(
    request,
    raid_event_id: Optional[int] = None,
    member_id: Optional[int] = None,
    limit: int = 5000,
    offset: int = 0,
):
    require_permission(request, "loot:read")
    limit, offset = bounded_page(limit, offset)

    queryset = (
        LootRecord.objects
        .select_related("member", "raid_event")
        .order_by("-awarded_at")
    )

    if raid_event_id is not None:
        queryset = queryset.filter(
            raid_event_id=raid_event_id
        )

    if member_id is not None:
        queryset = queryset.filter(
            member_id=member_id
        )

    return [
        serialize_loot(record)
        for record in queryset[offset:offset + limit]
    ]
@api.post(
    "/v1/loot/create",
    auth=api_key_auth,
    response={201: LootRecordCreateOut},
)
def create_loot(request, payload: LootCreate):
    require_permission(request, "loot:create")

    data = payload.model_dump(
        exclude_unset=True,
    )

    member_id = data.pop("member_id")
    raid_event_id = data.pop("raid_event_id")

    member = get_object_or_404(
        GuildMember,
        pk=member_id,
    )

    raid_event = get_object_or_404(
        RaidEvent,
        pk=raid_event_id,
    )

    submitted_item_name = data["item_name"].strip()
    submitted_zone = data.get("zone", "").strip()

    try:
        item_reference = resolve_item_reference(
            submitted_item_name,
            zone=submitted_zone,
        )
    except ValueError as error:
        raise HttpError(
            409,
            str(error),
        ) from error

    if item_reference is None:
        raise HttpError(
            422,
            (
                f"No Quarm item named "
                f"'{submitted_item_name}' was found "
                f"in zone '{submitted_zone}'."
            ),
        )

    # Store both the external ID and canonical name.
    data["item_id"] = item_reference["item_id"]
    data["item_name"] = item_reference["item_name"]

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
        ) from exc

    return Status(
        201,
        serialize_loot(
            loot,
            request=request,
        ),
    )

@api.get(
    "/v1/loot/character/{character_name}",
    auth=api_key_auth,
)
def get_loot_by_character_name(
    request,
    character_name: str,
):
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


@api.get(
    "/v1/loot/{int:record_id}",
    auth=api_key_auth,
)
def get_loot(request, record_id: int):
    require_permission(request, "loot:read")

    record = get_object_or_404(
        LootRecord.objects.select_related(
            "member",
            "raid_event",
        ),
        pk=record_id,
    )

    return serialize_loot(record)


@api.patch(
    "/v1/loot/{int:record_id}",
    auth=api_key_auth,
)
def update_loot(
    request,
    record_id: int,
    payload: LootRecordUpdate,
):
    require_permission(request, "loot:update")

    record = get_object_or_404(
        LootRecord,
        pk=record_id,
    )

    changes = payload.model_dump(
        exclude_unset=True
    )

    if "member_id" in changes:
        record.member = get_object_or_404(
            GuildMember,
            pk=changes.pop("member_id"),
        )

    if "raid_event_id" in changes:
        raid_id = changes.pop("raid_event_id")

        record.raid_event = (
            get_object_or_404(
                RaidEvent,
                pk=raid_id,
            )
            if raid_id is not None
            else None
        )

    for field, value in changes.items():
        setattr(record, field, value)

    try:
        record.full_clean()
        record.save()
        record.refresh_from_db()

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

    return serialize_loot(record)

# ---------------------------------------------------------------------------
# Guild news: select and update
# featured_image is read-only here; manage the actual image in Wagtail.
# ---------------------------------------------------------------------------

@api.get("/v1/news", auth=api_key_auth)
def list_news(
    request,
    published: Optional[bool] = None,
    limit: int = 5000,
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
    limit: int = 5000,
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


api.add_router(
    "/v1/quarm",
    quarm_router,
    auth=api_key_auth,  
)
