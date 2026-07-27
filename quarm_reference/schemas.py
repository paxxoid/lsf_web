from ninja import Schema


class ErrorSchema(Schema):
    detail: str


class HealthSchema(Schema):
    status: str
    database_alias: str
    npc_count: int
    loot_row_count: int


class NPCSummarySchema(Schema):
    id: int
    name: str
    stored_name: str
    zone_code: str | None = None
    zone_name: str | None = None
    level: int | None = None
    max_level: int | None = None
    race: str | None = None
    npc_class_id: int | None = None


class CombatSchema(Schema):
    hp: int | None = None
    mana: int | None = None
    ac: int | None = None
    min_damage: int | None = None
    max_damage: int | None = None
    attack_count: int | None = None
    attack_delay: int | None = None
    run_speed: float | None = None
    hp_regen: int | None = None
    mana_regen: int | None = None


class ResistanceSchema(Schema):
    magic: int | None = None
    fire: int | None = None
    cold: int | None = None
    disease: int | None = None
    poison: int | None = None


class VisibilitySchema(Schema):
    sees_invisible: bool
    sees_invisible_undead: bool
    sees_sneak: bool
    sees_improved_hide: bool


class SpecialAbilitySchema(Schema):
    id: int
    name: str
    enabled: bool
    parameters: list[int | float | str]


class CrowdControlSchema(Schema):
    slow_immune: bool
    slow_mitigation_percent: int
    slow_status: str
    mez_immune: bool
    mez_status: str
    charm_immune: bool
    stun_immune: bool
    snare_immune: bool
    fear_immune: bool
    pacify_immune: bool


class LootDropSchema(Schema):
    item_id: int | None = None
    item_name: str
    drop_chance: float | None = None


class FactionHitSchema(Schema):
    faction_id: int | None = None
    faction_name: str | None = None
    faction_hit: int | None = None
    sort_order: int | None = None


class RespawnTimerSchema(Schema):
    min_seconds: float | None = None
    max_seconds: float | None = None
    stored_name: str | None = None
    zone_code: str | None = None
    zone_id: str | None = None


class MerchantWareSchema(Schema):
    slot: int | None = None
    item_id: int | None = None
    item_name: str | None = None


class NPCDetailSchema(NPCSummarySchema):
    combat: CombatSchema
    resistances: ResistanceSchema
    visibility: VisibilitySchema
    is_quest_npc: bool
    unique_spawn_by_name: bool
    primary_faction: str | None = None
    npc_faction_id: int | None = None
    merchant_id: int | None = None
    loottable_id: int | None = None
    npc_spells_id: int | None = None
    raw_special_abilities: str
    special_abilities: list[SpecialAbilitySchema]
    crowd_control: CrowdControlSchema
    loot: list[LootDropSchema]
    faction_hits: list[FactionHitSchema]
    respawn_timers: list[RespawnTimerSchema]
    merchant_wares: list[MerchantWareSchema]


class NPCSearchResponseSchema(Schema):
    total: int
    limit: int
    offset: int
    results: list[NPCSummarySchema]


class NPCNameLookupResponseSchema(Schema):
    count: int
    results: list[NPCDetailSchema]


class ItemDropSourceSchema(Schema):
    item_id: int | None = None
    item_name: str | None = None
    drop_chance: float | None = None
    npc_id: int | None = None
    npc_name: str
    zone_code: str | None = None
    zone_name: str | None = None


class ItemSearchResponseSchema(Schema):
    total: int
    limit: int
    offset: int
    results: list[ItemDropSourceSchema]


class ZoneSchema(Schema):
    id: int | None = None
    zone_id: int | None = None
    name: str | None = None
    code: str | None = None
    is_dungeon: bool
    is_outdoor: bool
    has_reduced_spawn_timers: bool
    zem: float | None = None
