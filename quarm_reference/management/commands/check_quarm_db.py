from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from quarm_reference.database import get_database_alias


EXPECTED_TABLES = {
    "NPC": {
        "ID",
        "Name",
        "Zone_Code",
        "Level",
        "HP",
        "MR",
        "Loottable_ID",
        "Special_Abilities",
    },
    "NPC_Drops": {
        "Item_ID",
        "Item_Name",
        "Drop_Chance",
        "Loottable_ID",
    },
    "NPC_Factions": {"NPC_ID", "Faction_ID", "Faction_Hit"},
    "NPC_RespawnTimers": {
        "Mob_Name",
        "Zone_Code",
        "Min_RespawnTimer",
        "Max_RespawnTimer",
    },
    "NPC_Wares": {"MerchantID", "Slot", "Item_ID", "Item_Name"},
    "Zones": {"ID", "Zone_ID", "Name", "Code"},
}


class Command(BaseCommand):
    help = "Verify Quarm DB access, required columns, and row counts."

    def handle(self, *args, **options):
        alias = get_database_alias()
        connection = connections[alias]
        failures: list[str] = []

        self.stdout.write(f"Database alias: {alias}")
        try:
            with connection.cursor() as cursor:
                for table_name, expected_columns in EXPECTED_TABLES.items():
                    try:
                        cursor.execute(
                            f"SELECT * FROM `{table_name}` LIMIT 0"
                        )
                        actual_columns = {
                            column[0] for column in cursor.description
                        }
                        missing = expected_columns - actual_columns
                        if missing:
                            failures.append(
                                f"{table_name}: missing columns "
                                f"{', '.join(sorted(missing))}"
                            )
                            continue

                        cursor.execute(
                            f"SELECT COUNT(*) FROM `{table_name}`"
                        )
                        count = int(cursor.fetchone()[0])
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  {table_name}: {count:,} rows"
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{table_name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                f"Could not connect to database alias '{alias}': {exc}"
            ) from exc

        if failures:
            formatted = "\n".join(
                f"  - {failure}" for failure in failures
            )
            raise CommandError(
                f"Quarm database check failed:\n{formatted}"
            )

        self.stdout.write(
            self.style.SUCCESS("Quarm reference database check passed.")
        )
