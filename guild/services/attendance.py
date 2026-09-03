from collections import defaultdict
from datetime import timedelta

from django.db.models import (
    F,
    FloatField,
    IntegerField,
    Max,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import RaidAttendance, RaidEvent


def get_attendance_summary(days=90, now=None):
    """
    Calculate guild attendance for the requested rolling period.

    Logic:
        - Include raids between cutoff and now.
        - Future raids are excluded.
        - Alt attendance is credited to main_character.
        - Main + alt attendance is combined PER RAID.
        - Per-raid attendance is capped at 100%.
        - Per-raid minutes are capped at the raid's available minutes.
    """

    now = now or timezone.now()
    cutoff_date = now - timedelta(days=days)

    # ---------------------------------------------------------
    # Total scheduled raid events
    # ---------------------------------------------------------
    total_raid_events = RaidEvent.objects.filter(
        start_at__gte=cutoff_date,
        start_at__lte=now,
    ).count()

    # ---------------------------------------------------------
    # Maximum available minutes per raid
    # ---------------------------------------------------------
    raids = list(
        RaidAttendance.objects
        .filter(
            raid_event__start_at__gte=cutoff_date,
            raid_event__start_at__lte=now,
        )
        .values("raid_event_id")
        .annotate(
            max_raid_minutes=Max("total_raid_minutes")
        )
    )

    raid_max_minutes = {
        row["raid_event_id"]: int(
            row["max_raid_minutes"] or 0
        )
        for row in raids
    }

    total_raid_minutes_available = sum(
        raid_max_minutes.values()
    )

    # ---------------------------------------------------------
    # Main + alt attendance grouped PER RAID
    #
    # If member is an alt:
    #     use main_character_id
    #
    # Otherwise:
    #     use member_id
    # ---------------------------------------------------------
    rollups = (
        RaidAttendance.objects
        .filter(
            raid_event__start_at__gte=cutoff_date,
            raid_event__start_at__lte=now,
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
            raid_percent=Coalesce(
                Sum("attendance_percent"),
                Value(0.0),
                output_field=FloatField(),
            ),
            raid_minutes=Coalesce(
                Sum("total_raid_minutes"),
                Value(0),
                output_field=IntegerField(),
            ),
        )
    )

    players = defaultdict(
        lambda: {
            "total_attendance_percent": 0.0,
            "total_raid_minutes": 0,
        }
    )

    # ---------------------------------------------------------
    # Roll each raid into player totals
    # ---------------------------------------------------------
    for row in rollups:
        main_id = row["credited_member_id"]
        raid_id = row["raid_event_id"]

        raid_percent = float(
            row["raid_percent"] or 0
        )

        raid_minutes = int(
            row["raid_minutes"] or 0
        )

        # Main + alts cannot exceed 100% for one raid.
        raid_percent = min(
            raid_percent,
            100.0,
        )

        # Main + alts cannot exceed raid duration.
        max_minutes = raid_max_minutes.get(
            raid_id,
            0,
        )

        if max_minutes > 0:
            raid_minutes = min(
                raid_minutes,
                max_minutes,
            )

        players[main_id][
            "total_attendance_percent"
        ] += raid_percent

        players[main_id][
            "total_raid_minutes"
        ] += raid_minutes

    # ---------------------------------------------------------
    # Calculate final player percentages
    # ---------------------------------------------------------
    for stats in players.values():

        if total_raid_events > 0:
            stats["attendance_percentage"] = (
                stats["total_attendance_percent"]
                / total_raid_events
            )
        else:
            stats["attendance_percentage"] = 0.0

        if total_raid_minutes_available > 0:
            stats[
                "attendance_percentage_raw_minutes"
            ] = (
                stats["total_raid_minutes"]
                * 100.0
                / total_raid_minutes_available
            )
        else:
            stats[
                "attendance_percentage_raw_minutes"
            ] = 0.0

    return {
        "cutoff_date": cutoff_date,
        "through_date": now,
        "total_raid_events": total_raid_events,
        "total_raid_minutes_available":
            total_raid_minutes_available,
        "players": dict(players),
    }