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
    cutoff_date = timezone.now() - timedelta(days=90)

    # -------------------------------------------------
    # Raid totals for the last 90 days
    # -------------------------------------------------
    raids = (
        RaidAttendance.objects
        .filter(raid_event__start_at__gte=cutoff_date)
        .values("raid_event_id")
        .annotate(max_raid_minutes=Max("total_raid_minutes"))
    )

    total_raid_events = RaidEvent.objects.filter(
        start_at__gte=cutoff_date
    ).count()

    total_raid_minutes_available = (
        raids.aggregate(total=Sum("max_raid_minutes"))["total"] or 0
    )

    available_minutes_for_calc = max(total_raid_minutes_available, 1)
    raid_events_for_calc = max(total_raid_events, 1)

    # Need each raid's total duration so main + alt minutes
    # cannot exceed the total duration of that raid.
    raid_max_minutes = {
        row["raid_event_id"]: row["max_raid_minutes"] or 0
        for row in raids
    }

    # -------------------------------------------------
    # Roll MAIN + registered ALT attendance together
    # -------------------------------------------------
    #
    # If member is an alt:
    #     credit attendance to main_character_id
    #
    # If member is a main:
    #     credit attendance to member_id
    #
    # Group PER RAID first so main + alt can be capped at
    # 100% for an individual raid.
    # -------------------------------------------------
    rolled_up_attendance = (
        RaidAttendance.objects
        .filter(
            raid_event__start_at__gte=cutoff_date
        )
        .annotate(
            credited_member_id=Coalesce(
                F("member__main_character_id"),
                F("member_id"),
                output_field=IntegerField(),
            )
        )
        .values(
            "credited_member_id",
            "raid_event_id",
        )
        .annotate(
            raid_minutes=Coalesce(
                Sum("total_raid_minutes"),
                Value(0),
                output_field=IntegerField(),
            ),
            raid_percent=Coalesce(
                Sum("attendance_percent"),
                Value(0.0),
                output_field=FloatField(),
            ),
        )
    )

    # -------------------------------------------------
    # Build rolled-up totals for each MAIN character
    # -------------------------------------------------
    main_percent_totals = {}
    main_minute_totals = {}

    for row in rolled_up_attendance:
        member_id = row["credited_member_id"]
        raid_event_id = row["raid_event_id"]

        raid_percent = float(row["raid_percent"] or 0.0)
        raid_minutes = int(row["raid_minutes"] or 0)

        # Main + alt can never exceed 100% of one raid
        raid_percent = min(raid_percent, 100.0)

        # Main + alt minutes cannot exceed the raid duration
        max_raid_minutes = raid_max_minutes.get(
            raid_event_id,
            0,
        )

        if max_raid_minutes > 0:
            raid_minutes = min(
                raid_minutes,
                max_raid_minutes,
            )

        main_percent_totals[member_id] = (
            main_percent_totals.get(member_id, 0.0)
            + raid_percent
        )

        main_minute_totals[member_id] = (
            main_minute_totals.get(member_id, 0)
            + raid_minutes
        )

    # -------------------------------------------------
    # Existing individual member totals
    #
    # KEEP THESE so alt rows can still display their
    # own individual attendance.
    # -------------------------------------------------
    members = (
        GuildMember.objects
        .filter(active=True)
        .select_related("main_character")
        .annotate(
            total_raid_minutes=Coalesce(
                Sum(
                    "raid_attendances__total_raid_minutes",
                    filter=Q(
                        raid_attendances__raid_event__start_at__gte=cutoff_date
                    ),
                ),
                Value(0),
                output_field=IntegerField(),
            ),

            total_attendance_percent=Coalesce(
                Sum(
                    "raid_attendances__attendance_percent",
                    filter=Q(
                        raid_attendances__raid_event__start_at__gte=cutoff_date
                    ),
                ),
                Value(0.0),
                output_field=FloatField(),
            ),
        )
        .annotate(
            # Attendance based on actual minutes
            attendance_percentage_raw_minutes=ExpressionWrapper(
                F("total_raid_minutes")
                * Value(100.0)
                / Value(float(available_minutes_for_calc)),
                output_field=FloatField(),
            ),

            # Attendance based on summed per-raid %
            attendance_percentage=ExpressionWrapper(
                F("total_attendance_percent")
                / Value(float(raid_events_for_calc)),
                output_field=FloatField(),
            ),
        )
    )

    # -------------------------------------------------
    # Existing filters - unchanged
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

    # QuerySet must be evaluated before overriding the
    # MAIN characters with their rolled-up totals.
    members = list(members)

    # -------------------------------------------------
    # Replace MAIN totals with MAIN + ALT totals
    # -------------------------------------------------
    for member in members:

        # Only override main characters.
        # Alts keep their own individual stats.
        if member.main_character_id is None:

            total_percent = main_percent_totals.get(
                member.id,
                0.0,
            )

            total_minutes = main_minute_totals.get(
                member.id,
                0,
            )

            member.total_attendance_percent = (
                total_percent
            )

            member.total_raid_minutes = (
                total_minutes
            )

            member.attendance_percentage = (
                total_percent
                / raid_events_for_calc
            )

            member.attendance_percentage_raw_minutes = (
                total_minutes
                * 100.0
                / available_minutes_for_calc
            )

    # -------------------------------------------------
    # Sort AFTER main + alt totals have been calculated
    # -------------------------------------------------
    members.sort(
        key=lambda member: (
            -float(member.attendance_percentage or 0),
            member.character_name.lower(),
        )
    )

    # -------------------------------------------------
    # Existing context - unchanged
    # -------------------------------------------------
    context = {
        "members": members,
        "selected_class": selected_class,
        "selected_character_type": selected_character_type,
        "player_name": player_name,
        "total_raid_minutes_available": total_raid_minutes_available,
        "total_raid_events": total_raid_events,
        "class_choices": GuildMember._meta.get_field(
            "class_name"
        ).choices,
        "character_type_choices": GuildMember._meta.get_field(
            "character_type"
        ).choices,
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
        GuildMember.objects.select_related("main_character"),
        id=member_id,
    )

    cutoff_date = timezone.now() - timedelta(days=90)

    # -------------------------------------------------
    # Determine the MAIN character
    # -------------------------------------------------
    # If viewing an alt:
    #     main_character = its registered main
    #
    # If viewing a main:
    #     main_character = itself
    # -------------------------------------------------
    main_character = member.main_character or member

    # -------------------------------------------------
    # Get all registered alts for this main
    # -------------------------------------------------
    known_alts = (
        GuildMember.objects
        .filter(main_character=main_character)
        .order_by("character_name")
    )

    # -------------------------------------------------
    # Character IDs belonging to this player
    #
    # Main + all registered alts
    # -------------------------------------------------
    credited_member_ids = [
        main_character.id,
        *known_alts.values_list("id", flat=True),
    ]

    # -------------------------------------------------
    # Raid history
    #
    # Show raids attended by the main OR any registered alt.
    # -------------------------------------------------
    attended_raids = (
        RaidAttendance.objects
        .select_related(
            "raid_event",
            "member",
        )
        .filter(
            member_id__in=credited_member_ids,
            attended=True,
        )
        .order_by(
            "-raid_event__start_at",
            "member__character_name",
        )
    )

    # -------------------------------------------------
    # Total scheduled raids in the last 90 days
    # -------------------------------------------------
    total_raid_events = RaidEvent.objects.filter(
        start_at__gte=cutoff_date
    ).count()

    # -------------------------------------------------
    # Main + alt attendance, grouped PER RAID
    #
    # Example:
    #
    # Paxxar = 40%
    # Paxxor = 60%
    #
    # Same raid = 100%, not two separate raids.
    # -------------------------------------------------
    raid_attendance = (
        RaidAttendance.objects
        .filter(
            member_id__in=credited_member_ids,
            raid_event__start_at__gte=cutoff_date,
        )
        .values("raid_event_id")
        .annotate(
            combined_percent=Coalesce(
                Sum("attendance_percent"),
                Value(0.0),
                output_field=FloatField(),
            )
        )
    )

    # -------------------------------------------------
    # Sum player attendance
    #
    # Cap each individual raid at 100%.
    # -------------------------------------------------
    total_attendance_percent = 0.0

    for raid in raid_attendance:
        raid_percent = float(
            raid["combined_percent"] or 0.0
        )

        total_attendance_percent += min(
            raid_percent,
            100.0,
        )

    # -------------------------------------------------
    # Overall attendance %
    #
    # SUM(main + alt raid percentages)
    # --------------------------------
    # total scheduled raids
    # -------------------------------------------------
    if total_raid_events > 0:
        attendance_percentage = (
            total_attendance_percent
            / total_raid_events
        )
    else:
        attendance_percentage = 0.0

    # -------------------------------------------------
    # Loot records
    #
    # Leaving this as the SELECTED character's loot.
    # This preserves your existing behavior.
    # -------------------------------------------------
    loot_records = (
        LootRecord.objects
        .filter(member=member)
        .order_by("-awarded_at")
    )

    context = {
        "member": member,
        "main_character": main_character,
        "known_alts": known_alts,

        "attended_raids": attended_raids,
        "loot_records": loot_records,

        "attendance_count": attended_raids.count(),
        "loot_count": loot_records.count(),

        "attendance_percentage": attendance_percentage,
        "total_attendance_percent": total_attendance_percent,
        "total_raid_events": total_raid_events,
    }

    return render(
        request,
        "guild/member_summary.html",
        context,
    )