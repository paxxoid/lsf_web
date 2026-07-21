import hashlib
import secrets
from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse

from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField




class EverQuestClass(models.TextChoices):
    BARD = "bard", "Bard"
    BEASTLORD = "beastlord", "Beastlord"
    CLERIC = "cleric", "Cleric"
    DRUID = "druid", "Druid"
    ENCHANTER = "enchanter", "Enchanter"
    MAGICIAN = "magician", "Magician"
    MONK = "monk", "Monk"
    NECROMANCER = "necromancer", "Necromancer"
    PALADIN = "paladin", "Paladin"
    RANGER = "ranger", "Ranger"
    ROGUE = "rogue", "Rogue"
    SHADOWKNIGHT = "shadowknight", "Shadowknight"
    SHAMAN = "shaman", "Shaman"
    WARRIOR = "warrior", "Warrior"
    WIZARD = "wizard", "Wizard"
    
    



class RaidAttendance(models.Model):
    raid_event = models.ForeignKey("RaidEvent", on_delete=models.CASCADE, related_name="attendances")
    member = models.ForeignKey("GuildMember", on_delete=models.CASCADE, related_name="raid_attendances")
    attended = models.BooleanField(default=False)
    arrival_time = models.DateTimeField(
        null=True,
        blank=True,
    )    
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("raid_event", "member")
        ordering = ["raid_event__start_at", "member__character_name"]

    @property
    def is_late(self):
        if not self.attended or self.arrival_time is None:
            return False

        late_cutoff = self.raid_event.start_at + timedelta(minutes=5)

        return self.arrival_time > late_cutoff
    
    def __str__(self):
        return f"{self.member} @ {self.raid_event}"

class GuildMember(models.Model):
    class CharacterType(models.TextChoices):
        MAIN = "main", "Main"
        ALT = "alt", "Alt"

    class Rank(models.TextChoices):
        RECRUIT = "recruit", "Recruit"
        MEMBER = "member", "Member"
        RAIDER = "raider", "Raider"
        OFFICER = "officer", "Officer"
        LEADER = "leader", "Guild Leader"

    character_name = models.CharField(max_length=64, unique=True)
    character_type = models.CharField(
        max_length=8,
        choices=CharacterType.choices,
        default=CharacterType.MAIN,
    )
    main_character = models.ForeignKey(
        "self",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="alternate_characters",
    )
    class_name = models.CharField(max_length=24, choices=EverQuestClass.choices)
    race = models.CharField(max_length=40, blank=True)
    level = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(65)],
    )
    rank = models.CharField(max_length=16, choices=Rank.choices, default=Rank.MEMBER)
    active = models.BooleanField(default=True)
    raider = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    joined_at = models.DateField(default=timezone.localdate)
    bio = models.TextField(blank=True)

    class Meta:
        ordering = ["character_name"]

    def __str__(self):
        return self.character_name


class RaidEvent(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    title = models.CharField(max_length=120)
    zone = models.CharField(max_length=120, blank=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED)
    public = models.BooleanField(default=True)

    class Meta:
        ordering = ["start_at"]

    def __str__(self):
        return f"{self.title} — {self.start_at:%Y-%m-%d}"


class LootRecord(models.Model):
    awarded_at = models.DateTimeField(default=timezone.now)
    member = models.ForeignKey(GuildMember, on_delete=models.PROTECT, related_name="loot_records")
    item_name = models.CharField(max_length=160)
   # toon_type = models.CharField(max_length=8, choices=GuildMember.CharacterType.choices)
    toon_type = models.CharField(
        max_length=8,
        choices=GuildMember.CharacterType.choices,
        editable=False,
        #default=GuildMember.CharacterType.,
    )   
    zone = models.CharField(max_length=120, blank=True)
    npc = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-awarded_at"]
        indexes = [
            models.Index(fields=["-awarded_at"]),
            models.Index(fields=["item_name"]),
            models.Index(fields=["member"]),
            models.Index(fields=["toon_type"]),
        ]
    def save(self, *args, **kwargs):
        if self._state.adding and self.member_id:
            self.toon_type = self.member.character_type

        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.item_name} → {self.member}"

class GuildNews(models.Model):
    title = models.CharField(
        max_length=200,
    )

    slug = models.SlugField(
        max_length=220,
        unique=True,
        help_text="Used in the public news story URL.",
    )

    summary = models.CharField(
        max_length=400,
        blank=True,
        help_text="Short description shown on the homepage and news listing.",
    )

    body = RichTextField(
        blank=True,
    )

    featured_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    published_at = models.DateTimeField(
        default=timezone.now,
    )

    is_published = models.BooleanField(
        default=False,
    )

    featured = models.BooleanField(
        default=False,
        help_text="Show this story more prominently on the homepage.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("summary"),
        FieldPanel("featured_image"),
        FieldPanel("body"),
        FieldPanel("published_at"),
        FieldPanel("is_published"),
        FieldPanel("featured"),
    ]

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "Guild news story"
        verbose_name_plural = "Guild news stories"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse(
            "guild:news_detail",
            kwargs={"slug": self.slug},
        )

class Screenshot(models.Model):
    title = models.CharField(max_length=120)
    image = models.ImageField(upload_to="screenshots/%Y/%m/")
    caption = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["-featured", "-uploaded_at"]

    def __str__(self):
        return self.title


class GuildApplication(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWING = "reviewing", "Reviewing"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    character_name = models.CharField(max_length=64)
    class_name = models.CharField(max_length=24, choices=EverQuestClass.choices)
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(65)]
    )
    discord_name = models.CharField(max_length=80)
    timezone_name = models.CharField(max_length=80, default="Eastern Time")
    typical_play_times = models.CharField(max_length=200)
    experience = models.TextField(blank=True)
    why_join = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.character_name} ({self.get_status_display()})"


class ApiKey(models.Model):
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=16, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    permissions = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["name"]

    @classmethod
    def issue(cls, *, name, permissions=None, expires_in_days=None):
        raw_key = f"lasf_{secrets.token_urlsafe(32)}"
        expires_at = None
        if expires_in_days:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        instance = cls.objects.create(
            name=name,
            prefix=raw_key[:16],
            key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            permissions=permissions or [],
            expires_at=expires_at,
        )
        return instance, raw_key

    def matches(self, raw_key):
        candidate = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return secrets.compare_digest(self.key_hash, candidate)

    def has_permission(self, permission):
        return "admin" in self.permissions or permission in self.permissions

    @property
    def expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def __str__(self):
        return self.name
