import re


_SEPARATOR_PATTERN = re.compile(r"[\s_]+")


def normalize_npc_name(value: str) -> str:
    """Convert a display name to the underscore form stored in the DB."""
    return _SEPARATOR_PATTERN.sub("_", value.strip())


def stored_npc_name_variants(value: str) -> tuple[str, str]:
    """Return ordinary and EQ database-marker variants of a name."""
    base_name = normalize_npc_name(value).lstrip("#")
    return base_name, f"#{base_name}"


def display_npc_name(value: str | None) -> str:
    """Convert a stored NPC name to a human-friendly display name."""
    return (value or "").lstrip("#").replace("_", " ")
