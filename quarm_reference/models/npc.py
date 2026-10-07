from django.db import models
from django.utils.functional import cached_property


class QuarmNPC(models.Model):
    """Read-only mapping of the world table refreshed by the Quarm sync."""

    id = models.IntegerField(db_column="id", primary_key=True)
    name = models.TextField(db_column="name")
    special_abilities = models.TextField(db_column="special_abilities", null=True, blank=True)
    run_speed = models.FloatField(db_column="runspeed")
    ac = models.IntegerField(db_column="AC")
    cold_resist = models.IntegerField(db_column="CR")
    disease_resist = models.IntegerField(db_column="DR")
    fire_resist = models.IntegerField(db_column="FR")
    magic_resist = models.IntegerField(db_column="MR")
    poison_resist = models.IntegerField(db_column="PR")
    hp = models.IntegerField(db_column="hp")
    mana = models.IntegerField(db_column="mana")
    npc_class_id = models.IntegerField(db_column="class")
    greed = models.IntegerField(db_column="greed")
    level = models.IntegerField(db_column="level")
    max_damage = models.IntegerField(db_column="maxdmg")
    min_damage = models.IntegerField(db_column="mindmg")
    is_quest_npc = models.IntegerField(db_column="isquest")
    max_level = models.IntegerField(db_column="maxlevel")
    merchant_id = models.IntegerField(db_column="merchant_id")
    attack_count = models.IntegerField(db_column="attack_count")
    attack_delay = models.IntegerField(db_column="attack_delay")
    loottable_id = models.IntegerField(db_column="loottable_id")
    npc_spells_id = models.IntegerField(db_column="npc_spells_id")
    npc_faction_id = models.IntegerField(db_column="npc_faction_id")
    combat_hp_regen = models.IntegerField(db_column="combat_hp_regen")
    combat_mana_regen = models.IntegerField(db_column="combat_mana_regen")
    slow_mitigation = models.IntegerField(db_column="slow_mitigation")
    see_invis = models.IntegerField(db_column="see_invis")
    see_invis_undead = models.IntegerField(db_column="see_invis_undead")
    see_sneak = models.IntegerField(db_column="see_sneak")
    see_improved_hide = models.IntegerField(db_column="see_improved_hide")
    unique_spawn_by_name = models.IntegerField(db_column="unique_spawn_by_name")
    instance_spawn_timer = models.IntegerField(db_column="instance_spawn_timer_override")
    race_id = models.IntegerField(db_column="race")

    class Meta:
        managed = False
        db_table = "npc_types"
        app_label = "quarm_reference"
        ordering = ["name", "id"]

    @cached_property
    def reference_metadata(self):
        # Services preload this for lists; direct model callers get a lazy lookup.
        from quarm_reference.services.queries import get_npc_metadata
        return get_npc_metadata([self.pk], alias=self._state.db).get(self.pk, {})

    @property
    def race(self):
        return self.reference_metadata.get("race") or str(self.race_id)

    @property
    def zone_code(self):
        return self.reference_metadata.get("zone_code")

    @property
    def zone_name(self):
        return self.reference_metadata.get("zone_name")

    @property
    def primary_faction(self):
        return self.reference_metadata.get("primary_faction")

    @property
    def mitigates_slow(self):
        return int(bool(self.slow_mitigation))

    @property
    def zone_code_guess(self):
        return self.zone_code

    @property
    def zone_name_guess(self):
        return self.zone_name

    @property
    def display_name(self) -> str:
        return (self.name or "").lstrip("#").replace("_", " ")

    def save(self, *args, **kwargs):
        raise RuntimeError("QuarmNPC is read-only.")

    def delete(self, *args, **kwargs):
        raise RuntimeError("QuarmNPC is read-only.")

    def __str__(self) -> str:
        return f"{self.display_name} ({self.zone_code or 'unknown zone'})"
