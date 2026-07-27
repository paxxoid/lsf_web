from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="QuarmNPC",
            fields=[
                ("ac", models.IntegerField(db_column="AC", null=True)),
                (
                    "cold_resist",
                    models.IntegerField(db_column="CR", null=True),
                ),
                (
                    "disease_resist",
                    models.IntegerField(db_column="DR", null=True),
                ),
                ("fire_resist", models.IntegerField(db_column="FR", null=True)),
                (
                    "magic_resist",
                    models.IntegerField(db_column="MR", null=True),
                ),
                (
                    "poison_resist",
                    models.IntegerField(db_column="PR", null=True),
                ),
                ("hp", models.IntegerField(db_column="HP", null=True)),
                (
                    "id",
                    models.IntegerField(
                        db_column="ID",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("mana", models.IntegerField(db_column="Mana", null=True)),
                (
                    "name",
                    models.TextField(
                        blank=True, db_column="Name", null=True
                    ),
                ),
                (
                    "race",
                    models.TextField(
                        blank=True, db_column="Race", null=True
                    ),
                ),
                (
                    "npc_class_id",
                    models.IntegerField(
                        db_column="NPC_Class_ID", null=True
                    ),
                ),
                ("greed", models.IntegerField(db_column="Greed", null=True)),
                ("level", models.IntegerField(db_column="Level", null=True)),
                (
                    "max_damage",
                    models.IntegerField(db_column="MaxDmg", null=True),
                ),
                (
                    "min_damage",
                    models.IntegerField(db_column="MinDmg", null=True),
                ),
                (
                    "is_quest_npc",
                    models.IntegerField(
                        db_column="IsQuestNPC", null=True
                    ),
                ),
                ("max_level", models.IntegerField(db_column="MaxLevel", null=True)),
                ("run_speed", models.FloatField(db_column="RunSpeed", null=True)),
                (
                    "zone_code",
                    models.TextField(
                        blank=True, db_column="Zone_Code", null=True
                    ),
                ),
                (
                    "zone_name",
                    models.TextField(
                        blank=True, db_column="Zone_Name", null=True
                    ),
                ),
                (
                    "merchant_id",
                    models.IntegerField(
                        db_column="Merchant_ID", null=True
                    ),
                ),
                (
                    "attack_count",
                    models.IntegerField(
                        db_column="Attack_Count", null=True
                    ),
                ),
                (
                    "attack_delay",
                    models.IntegerField(
                        db_column="Attack_Delay", null=True
                    ),
                ),
                (
                    "loottable_id",
                    models.IntegerField(
                        db_column="Loottable_ID", null=True
                    ),
                ),
                (
                    "npc_spells_id",
                    models.IntegerField(
                        db_column="NPC_Spells_ID", null=True
                    ),
                ),
                (
                    "mitigates_slow",
                    models.IntegerField(
                        db_column="Mitigates_Slow", null=True
                    ),
                ),
                (
                    "npc_faction_id",
                    models.IntegerField(
                        db_column="NPC_Faction_ID", null=True
                    ),
                ),
                (
                    "combat_hp_regen",
                    models.IntegerField(
                        db_column="Combat_HP_Regen", null=True
                    ),
                ),
                (
                    "combat_mana_regen",
                    models.IntegerField(
                        db_column="Combat_Mana_Regen", null=True
                    ),
                ),
                (
                    "primary_faction",
                    models.TextField(
                        blank=True,
                        db_column="Primary_Faction",
                        null=True,
                    ),
                ),
                (
                    "slow_mitigation",
                    models.IntegerField(
                        db_column="Slow_Mitigation", null=True
                    ),
                ),
                ("see_invis", models.IntegerField(db_column="See_Invis", null=True)),
                (
                    "see_invis_undead",
                    models.IntegerField(
                        db_column="See_Invis_Undead", null=True
                    ),
                ),
                ("see_sneak", models.IntegerField(db_column="See_Sneak", null=True)),
                (
                    "see_improved_hide",
                    models.IntegerField(
                        db_column="See_Improved_Hidee", null=True
                    ),
                ),
                (
                    "special_abilities",
                    models.TextField(
                        blank=True,
                        db_column="Special_Abilities",
                        null=True,
                    ),
                ),
                (
                    "unique_spawn_by_name",
                    models.IntegerField(
                        db_column="Unique_Spawn_By_Name", null=True
                    ),
                ),
                (
                    "instance_spawn_timer",
                    models.IntegerField(
                        db_column="Instance_Spawn_Timer", null=True
                    ),
                ),
                (
                    "zone_name_guess",
                    models.TextField(
                        blank=True, db_column="Zone_Name_Guess", null=True
                    ),
                ),
                (
                    "zone_code_guess",
                    models.TextField(
                        blank=True, db_column="Zone_Code_Guess", null=True
                    ),
                ),
            ],
            options={
                "db_table": "NPC",
                "ordering": ["name", "zone_code", "id"],
                "managed": False,
            },
        ),
    ]
