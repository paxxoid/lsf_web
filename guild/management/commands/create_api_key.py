from django.core.management.base import BaseCommand, CommandError

from guild.models import ApiKey


class Command(BaseCommand):
    help = "Issue an API key and display the raw value once."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument(
            "--permission",
            action="append",
            default=[],
            dest="permissions",
            help="Permission such as loot:read, loot:create, members:read, raids:read, or admin.",
        )
        parser.add_argument("--expires-days", type=int, default=None)

    def handle(self, *args, **options):
        if options["expires_days"] is not None and options["expires_days"] < 1:
            raise CommandError("--expires-days must be at least 1")

        api_key, raw_key = ApiKey.issue(
            name=options["name"],
            permissions=options["permissions"],
            expires_in_days=options["expires_days"],
        )

        self.stdout.write(self.style.SUCCESS(f"Created API key: {api_key.name}"))
        self.stdout.write("Store this value now; it will not be shown again:")
        self.stdout.write(self.style.WARNING(raw_key))
