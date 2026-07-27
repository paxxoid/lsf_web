from django.conf import settings


DEFAULT_DATABASE_ALIAS = "quarm"


def get_database_alias() -> str:
    """Return the Django database alias used by this app."""
    return getattr(
        settings,
        "QUARM_REFERENCE_DATABASE_ALIAS",
        DEFAULT_DATABASE_ALIAS,
    )
