from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator

from datetime import timedelta
from django.db.models import Max, Sum, Q, Value, IntegerField, FloatField, F, ExpressionWrapper
from django.db.models.functions import Coalesce

from .services.attendance import get_attendance_summary

from .forms import GuildApplicationForm
from .models import (
    EverQuestClass,
    GuildMember,
    GuildNews,
    LootRecord,
    RaidEvent,
    Screenshot,
    RaidAttendance,
)


def home(request):
    class_labels = dict(EverQuestClass.choices)
    class_counts = [
        {
            "slug": row["class_name"],
            "label": class_labels[row["class_name"]],
            "total": row["total"],
        }
        for row in (
            GuildMember.objects.filter(active=True)
            .values("class_name")
            .annotate(total=Count("id"))
            .order_by("class_name")
        )
    ]
    latest_news = (
        GuildNews.objects
        .filter(
            is_published=True,
            published_at__lte=timezone.now(),
        )
        .order_by("-published_at")[:3]
    )

    context = {
        "latest_news": latest_news,
        "news_items": GuildNews.objects.filter(is_published=True)[:3],
        "raid_events": RaidEvent.objects.filter(
            public=True,
            status=RaidEvent.Status.SCHEDULED,
            end_at__gte=timezone.now(),
        )[:4],
        "class_counts": class_counts,
    }
    return render(request, "guild/home.html", context)


def about(request):
    return render(request, "guild/about.html")

def raid_detail(request, raid_id):
    raid = get_object_or_404(
        RaidEvent,
        pk=raid_id,
    )

    attendance_records = (
        raid.attendances
        .select_related("member")
        .order_by("member__character_name")
    )

    loot_records = (
        raid.loot_records
        .select_related("member")
        .order_by("-awarded_at")
    )

    return render(
        request,
        "guild/raid_detail.html",
        {
            "raid": raid,
            "attendance_records": attendance_records,
            "loot_records": loot_records,
        },
    ) 

def roster(request):
    # -------------------------------------------------
    # Shared attendance calculation
    # -------------------------------------------------
    attendance_summary = get_attendance_summary(days=90)

    total_raid_events = attendance_summary[
        "total_raid_events"
    ]

    total_raid_minutes_available = attendance_summary[
        "total_raid_minutes_available"
    ]

    player_stats = attendance_summary[
        "players"
    ]

    # -------------------------------------------------
    # Members
    # -------------------------------------------------
    members = (
        GuildMember.objects
        .filter(active=True)
        .select_related("main_character")
    )

    # -------------------------------------------------
    # Filters
    # -------------------------------------------------
    selected_class = request.GET.get(
        "class",
        "",
    ).strip()

    selected_character_type = request.GET.get(
        "character_type",
        "",
    ).strip()

    player_name = request.GET.get(
        "player_name",
        "",
    ).strip()

    if selected_class:
        members = members.filter(
            class_name=selected_class
        )

    if selected_character_type:
        members = members.filter(
            character_type=selected_character_type
        )

    if player_name:
        members = members.filter(
            character_name__icontains=player_name
        )

    # We are going to attach calculated fields,
    # so evaluate the QuerySet.
    members = list(members)

    # -------------------------------------------------
    # Attach attendance values
    # -------------------------------------------------
    for member in members:

        # MAIN
        if member.main_character_id is None:

            stats = player_stats.get(
                member.id,
                {},
            )

            member.total_raid_minutes = (
                stats.get(
                    "total_raid_minutes",
                    0,
                )
            )

            member.total_attendance_percent = (
                stats.get(
                    "total_attendance_percent",
                    0.0,
                )
            )

            member.attendance_percentage = (
                stats.get(
                    "attendance_percentage",
                    0.0,
                )
            )

            member.attendance_percentage_raw_minutes = (
                stats.get(
                    "attendance_percentage_raw_minutes",
                    0.0,
                )
            )

        # ALT
        else:
            # Keep the alt's own individual statistics
            # for the roster alt rows.
            alt_summary = (
                RaidAttendance.objects
                .filter(
                    member=member,
                    raid_event__start_at__gte=
                        attendance_summary["cutoff_date"],
                    raid_event__start_at__lte=
                        attendance_summary["through_date"],
                )
                .aggregate(
                    total_minutes=Coalesce(
                        Sum("total_raid_minutes"),
                        Value(0),
                        output_field=IntegerField(),
                    ),
                    total_percent=Coalesce(
                        Sum("attendance_percent"),
                        Value(0.0),
                        output_field=FloatField(),
                    ),
                )
            )

            member.total_raid_minutes = (
                alt_summary["total_minutes"]
                or 0
            )

            member.total_attendance_percent = float(
                alt_summary["total_percent"]
                or 0.0
            )

            if total_raid_events > 0:
                member.attendance_percentage = (
                    member.total_attendance_percent
                    / total_raid_events
                )
            else:
                member.attendance_percentage = 0.0

            if total_raid_minutes_available > 0:
                member.attendance_percentage_raw_minutes = (
                    member.total_raid_minutes
                    * 100.0
                    / total_raid_minutes_available
                )
            else:
                member.attendance_percentage_raw_minutes = 0.0

    # -------------------------------------------------
    # Sort by attendance %
    # -------------------------------------------------
    members.sort(
        key=lambda member: (
            -float(
                member.attendance_percentage
                or 0
            ),
            member.character_name.lower(),
        )
    )

    # -------------------------------------------------
    # Context
    # -------------------------------------------------
    context = {
        "members": members,

        "selected_class": selected_class,
        "selected_character_type":
            selected_character_type,
        "player_name": player_name,

        "total_raid_minutes_available":
            total_raid_minutes_available,

        "total_raid_events":
            total_raid_events,

        "class_choices":
            GuildMember._meta
            .get_field("class_name")
            .choices,

        "character_type_choices":
            GuildMember._meta
            .get_field("character_type")
            .choices,
    }

    return render(
        request,
        "guild/roster.html",
        context,
    )

def raids(request):
    now = timezone.now()

    upcoming_events = (
        RaidEvent.objects
        .filter(start_at__gte=now)
        .order_by("start_at")
    )

    past_events = (
        RaidEvent.objects
        .filter(start_at__lt=now)
        .order_by("-start_at")
    )

    paginator = Paginator(past_events, 5)
    page_number = request.GET.get("page")
    past_page = paginator.get_page(page_number)

    return render(
        request,
        "guild/raids.html",
        {
            "upcoming_events": upcoming_events,
            "past_page": past_page,
        },
    )

def loot(request):
    search_query = request.GET.get("q", "").strip()

    records = LootRecord.objects.select_related("member")

    if search_query:
        records = records.filter(
             Q(member__character_name__icontains=search_query)
            | Q(item_name__icontains=search_query)
            | Q(zone__icontains=search_query)
            | Q(npc__icontains=search_query)
            | Q(notes__icontains=search_query)
            | Q(toon_type__icontains=search_query)
        )

    records = records[:250]

    return render(
        request,
        "guild/loot.html",
        {
            "records": records,
            "search_query": search_query,
        },
    )

def attendance(request):
    search_query = request.GET.get("q", "").strip()

    records = RaidAttendance.objects.select_related("member", "raid_event")

    if search_query:
        records = records.filter(
             Q(member__character_name__icontains=search_query)
            | Q(raid_event__title__icontains=search_query)
            | Q(raid_event__zone__icontains=search_query)
        )

    records = records[:250]

    return render(
        request,
        "guild/attendance.html",
        {
            "records": records,
            "search_query": search_query,
        },
    )

def screenshots(request):
    images = Screenshot.objects.all()
    return render(request, "guild/screenshots.html", {"images": images})


def news(request):
    stories = (
        GuildNews.objects
        .filter(
            is_published=True,
            published_at__lte=timezone.now(),
        )
        .order_by("-published_at")
    )

    return render(
        request,
        "guild/news.html",
        {
            "stories": stories,
        },
    )
def news_detail(request, slug):
    story = get_object_or_404(
        GuildNews,
        slug=slug,
        is_published=True,
        published_at__lte=timezone.now(),
    )

    return render(
        request,
        "guild/news_detail.html",
        {
            "story": story,
        },
    )

def apply(request):
    if request.method == "POST":
        form = GuildApplicationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Application submitted. An officer will contact you on Discord.")
            return redirect("guild:application_success")
    else:
        form = GuildApplicationForm()

    return render(request, "guild/apply.html", {"form": form})


def application_success(request):
    return render(request, "guild/application_success.html")

def build_class_roster_counts() -> list[dict]:
    counts = {
        row["class_name"]: row["member_count"]
        for row in (
            GuildMember.objects
            .filter(active=True)
            .values("class_name")
            .annotate(member_count=Count("id"))
        )
    }

    return [
        {
            "value": class_value,
            "name": class_label,
            "image": f"{class_value}.png",
            "count": counts.get(class_value, 0),
        }
        for class_value, class_label in EverQuestClass.choices
    ]

def member_summary(request, member_id):
    member = get_object_or_404(
        GuildMember.objects.select_related(
            "main_character"
        ),
        id=member_id,
    )

    # -------------------------------------------------
    # Determine main character
    # -------------------------------------------------
    main_character = (
        member.main_character
        or member
    )

    # -------------------------------------------------
    # Registered alts
    # -------------------------------------------------
    known_alts = (
        GuildMember.objects
        .filter(
            main_character=main_character
        )
        .order_by(
            "character_name"
        )
    )

    # -------------------------------------------------
    # IDs for main + all registered alts
    # -------------------------------------------------
    credited_member_ids = [
        main_character.id,
        *known_alts.values_list(
            "id",
            flat=True,
        ),
    ]

    # -------------------------------------------------
    # Shared attendance calculation
    # -------------------------------------------------
    attendance_summary = (
        get_attendance_summary(days=90)
    )

    player_stats = (
        attendance_summary[
            "players"
        ].get(
            main_character.id,
            {},
        )
    )

    attendance_percentage = (
        player_stats.get(
            "attendance_percentage",
            0.0,
        )
    )

    total_attendance_percent = (
        player_stats.get(
            "total_attendance_percent",
            0.0,
        )
    )

    total_raid_minutes = (
        player_stats.get(
            "total_raid_minutes",
            0,
        )
    )

    total_raid_events = (
        attendance_summary[
            "total_raid_events"
        ]
    )

    total_raid_minutes_available = (
        attendance_summary[
            "total_raid_minutes_available"
        ]
    )

    # -------------------------------------------------
    # Raid history
    #
    # Show actual character used:
    # Paxxar / Paxxor / etc.
    # -------------------------------------------------
    attended_raids = (
        RaidAttendance.objects
        .select_related(
            "raid_event",
            "member",
            "member__main_character",
        )
        .filter(
            member_id__in=
                credited_member_ids,
            attended=True,
        )
        .order_by(
            "-raid_event__start_at",
            "member__character_name",
        )
    )

    # -------------------------------------------------
    # Loot
    #
    # Still only selected character, preserving
    # your existing behavior.
    # -------------------------------------------------
    loot_records = (
        LootRecord.objects
        .filter(member=member)
        .order_by("-awarded_at")
    )

    context = {
        "member": member,

        "main_character":
            main_character,

        "known_alts":
            known_alts,

        "attended_raids":
            attended_raids,

        "loot_records":
            loot_records,

        "attendance_count":
            attended_raids.count(),

        "loot_count":
            loot_records.count(),

        "attendance_percentage":
            attendance_percentage,

        "total_attendance_percent":
            total_attendance_percent,

        "total_raid_minutes":
            total_raid_minutes,

        "total_raid_events":
            total_raid_events,

        "total_raid_minutes_available":
            total_raid_minutes_available,
    }

    return render(
        request,
        "guild/member_summary.html",
        context,
    )