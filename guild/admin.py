import hashlib
import secrets
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.html import format_html
from django import forms

from .models import (
    ApiKey,
    GuildApplication,
    GuildMember,
    GuildNews,
    LootRecord,
    RaidEvent,
    Screenshot,
    RaidAttendance
)

API_PERMISSION_CHOICES = [
    ("members:read", "Members — View"),
    ("members:update", "Members — Update"),

    ("raids:read", "Raids — View"),
    ("raids:update", "Raids — Update"),

    ("attendance:read", "Attendance — View"),
    ("attendance:update", "Attendance — Update"),

    ("loot:read", "Loot — View"),
    ("loot:update", "Loot — Update"),

    ("news:read", "Guild News — View"),
    ("news:update", "Guild News — Update"),

    ("applications:read", "Applications — View"),
    ("applications:update", "Applications — Update"),

    ("admin", "Administrator — All permissions"),
]




@admin.register(GuildMember)
class GuildMemberAdmin(admin.ModelAdmin):
    list_display = ("character_name", "class_name", "level", "rank", "character_type", "active")
    list_filter = ("active", "rank", "class_name", "character_type", "raider")
    search_fields = ("character_name", "race", "bio")


@admin.register(RaidEvent)
class RaidEventAdmin(admin.ModelAdmin):
    list_display = ("title", "zone", "start_at", "end_at", "status", "public")
    list_filter = ("status", "public", "start_at")
    search_fields = ("title", "zone", "description")


@admin.register(LootRecord)
class LootRecordAdmin(admin.ModelAdmin):
    list_display = ("item_name", "member", "zone", "npc", "awarded_at")
    list_filter = ("zone", "awarded_at")
    search_fields = ("item_name", "member__character_name", "zone", "npc")
    autocomplete_fields = ("member",)
    list_display = (
        "item_name",
        "member",
        "raid_event",
        "awarded_at",
        "zone",
    )

    list_filter = (
        "raid_event",
        "zone",
        "awarded_at",
    )

    search_fields = (
        "item_name",
        "member__character_name",
        "raid_event__title",
        "npc",
    )

@admin.register(RaidAttendance)
class RaidAttendanceAdmin(admin.ModelAdmin):
    list_display = ("raid_event", "member", "attended")
    list_filter = ("attended",)
    search_fields = ("raid_event__title", "member__character_name")


@admin.register(GuildNews)
class GuildNewsAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "published_at",
        "is_published",
        "featured",
    )

    list_filter = (
        "is_published",
        "featured",
        "published_at",
    )

    search_fields = (
        "title",
        "summary",
        "body",
    )

    prepopulated_fields = {
        "slug": ("title",),
    }

    ordering = (
        "-published_at",
    )

@admin.register(Screenshot)
class ScreenshotAdmin(admin.ModelAdmin):
    list_display = ("title", "uploaded_at", "featured")
    list_filter = ("featured", "uploaded_at")


@admin.register(GuildApplication)
class GuildApplicationAdmin(admin.ModelAdmin):
    list_display = ("character_name", "class_name", "level", "discord_name", "status", "submitted_at")
    list_filter = ("status", "class_name", "submitted_at")
    search_fields = ("character_name", "discord_name", "why_join")



class ApiKeyAdminForm(forms.ModelForm):
    permissions = forms.MultipleChoiceField(
        label="Permissions",
        choices=API_PERMISSION_CHOICES,
        required=False,
        widget=FilteredSelectMultiple(
            verbose_name="permissions",
            is_stacked=False,
        ),
        help_text=(
            "Move permissions from Available permissions to "
            "Chosen permissions. Selecting Administrator grants "
            "access to every API operation."
        ),
    )

    class Meta:
        model = ApiKey
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            existing_permissions = self.instance.permissions or []

            # Preserve any older/custom permissions that are not currently
            # listed in API_PERMISSION_CHOICES.
            known_values = {
                value
                for value, label in API_PERMISSION_CHOICES
            }

            custom_choices = [
                (permission, f"{permission} — Custom/legacy")
                for permission in existing_permissions
                if permission not in known_values
            ]

            if custom_choices:
                self.fields["permissions"].choices = (
                    API_PERMISSION_CHOICES + custom_choices
                )

            self.fields["permissions"].initial = existing_permissions

    def clean_permissions(self):
        permissions = list(
            self.cleaned_data.get("permissions", [])
        )

        # Administrator already grants everything, so other entries
        # are unnecessary when it is selected.
        if "admin" in permissions:
            return ["admin"]

        return permissions
@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    form = ApiKeyAdminForm

    list_display = (
        "name",
        "prefix",
        "active",
        "permission_summary",
        "created_at",
        "expires_at",
        "last_used_at",
        "is_expired",
    )

    list_filter = (
        "active",
        "created_at",
        "expires_at",
    )

    search_fields = (
        "name",
        "prefix",
    )

    readonly_fields = (
        "prefix",
        "key_hash",
        "created_at",
        "last_used_at",
    )

    fieldsets = (
        (
            "API key",
            {
                "fields": (
                    "name",
                    "active",
                    "permissions",
                ),
            },
        ),
        (
            "Expiration",
            {
                "fields": (
                    "expires_at",
                    "last_used_at",
                ),
            },
        ),
        (
            "Stored key information",
            {
                "fields": (
                    "prefix",
                    "key_hash",
                    "created_at",
                ),
                "classes": (
                    "collapse",
                ),
            },
        ),
    )

    @admin.display(
        boolean=True,
        description="Expired",
    )
    def is_expired(self, obj):
        return obj.expired

    @admin.display(description="Permissions")
    def permission_summary(self, obj):
        permissions = obj.permissions or []

        if "admin" in permissions:
            return "Administrator"

        if not permissions:
            return "None"

        return ", ".join(permissions)

    def save_model(self, request, obj, form, change):
        raw_key = None

        if not change and not obj.key_hash:
            raw_key = (
                f"lasf_{secrets.token_urlsafe(32)}"
            )

            obj.prefix = raw_key[:16]

            obj.key_hash = hashlib.sha256(
                raw_key.encode("utf-8")
            ).hexdigest()

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        if raw_key:
            messages.warning(
                request,
                format_html(
                    "API key created. Copy it now because it "
                    "cannot be displayed again:<br><br>"
                    "<code style='font-size:1.1rem; "
                    "user-select:all;'>{}</code>",
                    raw_key,
                ),
            )
# class ApiKeyAdmin(admin.ModelAdmin):
#     list_display = ("name", "prefix", "active", "created_at", "expires_at", "last_used_at")
#     list_filter = ("active", "created_at", "expires_at")
#     search_fields = ("name", "prefix")
#     readonly_fields = ("prefix", "key_hash", "created_at", "last_used_at")

#     def has_add_permission(self, request):
#         # Issue keys with: python manage.py create_api_key "Client name" --permission loot:read
#         return False
