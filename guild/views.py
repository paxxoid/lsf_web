from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import render


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

    context = {
        "news_items": GuildNews.objects.filter(published=True)[:3],
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


def roster(request):
    members = GuildMember.objects.filter(active=True).select_related("main_character")
    selected_class = request.GET.get("class", "").strip()
    if selected_class:
        members = members.filter(class_name=selected_class)
    return render(
        request,
        "guild/roster.html",
        {"members": members, "selected_class": selected_class},
    )


def raids(request):
    events = RaidEvent.objects.filter(public=True, end_at__gte=timezone.now())
    return render(request, "guild/raids.html", {"events": events})


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
    items = GuildNews.objects.filter(published=True)
    return render(request, "guild/news.html", {"news_items": items})


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
