import logging

from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone


from .models import RaidEvent, RecurringRaidSchedule

logger = logging.getLogger(__name__)


def scheduler_test(message: str = "Django Q2 scheduler is working") -> str:
    """
    Simple test task for verifying Django Q2.

    The returned value will be stored in the Django Q2
    successful task record.
    """
    current_time = timezone.now()
    result = f"{message} at {current_time.isoformat()}"

    logger.info(result)

    return result


# guild/tasks.py


def create_weekly_raids(reference_date=None, schedule_ids=None):
    """
    Create next week's raids from enabled RecurringRaidSchedule records.

    The job normally runs Sunday night and generates raids for the
    following Monday through Sunday.
    """
    current_timezone = timezone.get_current_timezone()

    if reference_date:
        if isinstance(reference_date, str):
            reference_date = date.fromisoformat(reference_date)
    else:
        reference_date = timezone.localdate()

    # Find the next Monday.
    days_until_monday = (7 - reference_date.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7

    next_monday = reference_date + timedelta(days=days_until_monday)

    schedules = RecurringRaidSchedule.objects.filter(enabled=True)

    if schedule_ids:
        schedules = schedules.filter(id__in=schedule_ids)

    created = []
    skipped = []

    with transaction.atomic():
        for schedule in schedules:
            raid_date = next_monday + timedelta(days=schedule.weekday)

            start_at = timezone.make_aware(
                datetime.combine(raid_date, schedule.start_time),
                current_timezone,
            )

            end_date = raid_date

            # Allow raids to end after midnight.
            if schedule.end_time <= schedule.start_time:
                end_date += timedelta(days=1)

            end_at = timezone.make_aware(
                datetime.combine(end_date, schedule.end_time),
                current_timezone,
            )

            day_start = timezone.make_aware(
                datetime.combine(raid_date, time.min),
                current_timezone,
            )
            next_day_start = day_start + timedelta(days=1)

            existing_raid = RaidEvent.objects.filter(
                recurring_schedule=schedule,
                start_at__gte=day_start,
                start_at__lt=next_day_start,
            ).first()

            if existing_raid:
                skipped.append(
                    {
                        "id": existing_raid.id,
                        "title": existing_raid.title,
                        "date": raid_date.isoformat(),
                    }
                )
                continue

            raid = RaidEvent(
                recurring_schedule=schedule,
                title=schedule.title,
                zone=schedule.zone,
                description=schedule.description,
                start_at=start_at,
                end_at=end_at,
                status=schedule.status,
                public=schedule.public,
            )

            raid.full_clean()
            raid.save()

            created.append(
                {
                    "id": raid.id,
                    "title": raid.title,
                    "date": raid_date.isoformat(),
                }
            )

    return {
        "created": created,
        "skipped": skipped,
        "created_count": len(created),
        "skipped_count": len(skipped),
    }