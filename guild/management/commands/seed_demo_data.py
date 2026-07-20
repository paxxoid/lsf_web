from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from guild.models import GuildMember, GuildNews, LootRecord, RaidEvent


CLASS_COUNTS = {
    "warrior": 12,
    "cleric": 9,
    "paladin": 7,
    "ranger": 8,
    "shadowknight": 6,
    "necromancer": 6,
    "wizard": 7,
    "enchanter": 5,
    "bard": 5,
    "druid": 4,
}


class Command(BaseCommand):
    help = "Add example content so the starter homepage is populated."

    def handle(self, *args, **options):
        members = []
        for class_name, count in CLASS_COUNTS.items():
            for number in range(1, count + 1):
                member, _ = GuildMember.objects.get_or_create(
                    character_name=f"{class_name.title()}{number}",
                    defaults={
                        "class_name": class_name,
                        "level": 60,
                        "rank": "raider" if number <= 3 else "member",
                        "raider": number <= 3,
                        "featured": number == 1,
                    },
                )
                members.append(member)

        now = timezone.localtime()
        schedule = [
            (1, time(19, 0), time(22, 0), "Kunark Raids"),
            (3, time(19, 0), time(22, 0), "Velious Raids"),
            (5, time(15, 0), time(18, 0), "Open World / Missions"),
            (6, time(19, 0), time(22, 0), "Tier / Event Raids"),
        ]
        for weekday, start_time, end_time, title in schedule:
            days_ahead = (weekday - now.weekday()) % 7
            event_date = now.date() + timedelta(days=days_ahead)
            start_at = timezone.make_aware(datetime.combine(event_date, start_time))
            end_at = timezone.make_aware(datetime.combine(event_date, end_time))
            RaidEvent.objects.get_or_create(
                title=title,
                start_at=start_at,
                defaults={"end_at": end_at, "public": True},
            )

        news = [
            ("Vex Thal progression continues", "Great work, everyone — progression continues this week."),
            ("Welcome our newest members", "Please welcome several new adventurers to the guild."),
            ("Plane of Fear turnout", "Great turnout for the Plane of Fear event this weekend."),
        ]
        for title, summary in news:
            GuildNews.objects.get_or_create(title=title, defaults={"summary": summary})

        if members:
            LootRecord.objects.get_or_create(
                member=members[0],
                item_name="Example Raid Item",
                defaults={"zone": "Vex Thal", "npc": "Example Boss"},
            )

        self.stdout.write(self.style.SUCCESS("Demo content created."))
