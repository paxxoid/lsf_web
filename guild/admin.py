from django.contrib import admin

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


@admin.register(RaidAttendance)
class RaidAttendanceAdmin(admin.ModelAdmin):
    list_display = ("raid_event", "member", "attended")
    list_filter = ("attended",)
    search_fields = ("raid_event__title", "member__character_name")


@admin.register(GuildNews)
class GuildNewsAdmin(admin.ModelAdmin):
    list_display = ("title", "published_at", "published", "pinned")
    list_filter = ("published", "pinned", "published_at")
    search_fields = ("title", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Screenshot)
class ScreenshotAdmin(admin.ModelAdmin):
    list_display = ("title", "uploaded_at", "featured")
    list_filter = ("featured", "uploaded_at")


@admin.register(GuildApplication)
class GuildApplicationAdmin(admin.ModelAdmin):
    list_display = ("character_name", "class_name", "level", "discord_name", "status", "submitted_at")
    list_filter = ("status", "class_name", "submitted_at")
    search_fields = ("character_name", "discord_name", "why_join")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "active", "created_at", "expires_at", "last_used_at")
    list_filter = ("active", "created_at", "expires_at")
    search_fields = ("name", "prefix")
    readonly_fields = ("prefix", "key_hash", "created_at", "last_used_at")

    def has_add_permission(self, request):
        # Issue keys with: python manage.py create_api_key "Client name" --permission loot:read
        return False
