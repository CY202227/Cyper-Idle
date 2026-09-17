"""玩家节点战斗力：黑客等级 + 建筑 combat + 资源库存加成 + 协议 + 行动带宽惩罚。"""


def _building_combat_bonus(state, buildings_def):
    bonus = {"intrusion": 0.0, "firewall": 0.0, "integrity": 0.0, "speed": 0.0}
    if not buildings_def:
        return bonus
    for category in ("hardware", "software"):
        cat = buildings_def.get(category, {})
        for b_id, b_def in cat.items():
            level = state.buildings.get(b_id, 0)
            if level <= 0:
                continue
            combat = b_def.get("effects", {}).get("combat", {})
            for stat, per_level in combat.items():
                if stat in bonus:
                    bonus[stat] += per_level * level
    return bonus


def _resource_multiplier(state):
    """电力/算力库存各最多 +15% 全属性倍率。"""
    mult = 1.0
    energy = state.resources.get("energy", 0)
    compute = state.resources.get("compute", 0)
    energy_cap = max(1, state.storage_caps.get("energy", 500))
    compute_cap = max(1, state.storage_caps.get("compute", 200))
    if energy >= energy_cap * 0.3:
        mult += 0.15 * min(1.0, energy / energy_cap)
    if compute >= compute_cap * 0.3:
        mult += 0.15 * min(1.0, compute / compute_cap)
    return mult


def _ops_intrusion_penalty(state, protocol_effects=None):
    """每条进行中的网络行动 -5% intrusion，最多 -15%；幽灵协议减半。"""
    active = 0
    for m in getattr(state, "missions", []):
        if not m.get("claimed", False) and not m.get("completed", False):
            active += 1
        elif m.get("completed") and not m.get("claimed", False):
            active += 1
    penalty = min(0.15, active * 0.05)
    if penalty > 0 and protocol_effects:
        reduction = float(protocol_effects.get("ops_penalty_reduction", 0))
        if reduction > 0:
            penalty *= max(0.0, 1.0 - reduction)
    return penalty


def calc_player_power(
    state, buildings_def=None, protocol_effects=None, vs_boss=False,
    synergy_effects=None,
):
    """返回 intrusion / firewall / integrity / speed。"""
    effects = protocol_effects or {}
    syn = synergy_effects or {}
    level = max(1, state.hacking_level)
    base_intrusion = 8 + level * 3
    base_firewall = 5 + level * 2
    base_integrity = 100 + level * 30
    base_speed = 8 + level * 1.5

    bonus = _building_combat_bonus(state, buildings_def)
    mult = _resource_multiplier(state)
    penalty = _ops_intrusion_penalty(state, effects)

    intrusion = (base_intrusion + bonus["intrusion"]) * mult * (1.0 - penalty)
    firewall = (base_firewall + bonus["firewall"]) * mult
    integrity = (base_integrity + bonus["integrity"]) * mult
    speed = (base_speed + bonus["speed"]) * mult

    # 协议/架构效果与地牢修饰词都可能给出 player_* 前缀的同类修正
    # （例如修饰词 data_tide 的 player_intrusion_pct、mirror_static 的
    #  player_firewall_pct），两者与 intrusion_pct / firewall_pct 同义累加。
    intrusion *= (
        1.0
        + float(effects.get("intrusion_pct", 0))
        + float(effects.get("player_intrusion_pct", 0))
    )
    firewall *= (
        1.0
        + float(effects.get("firewall_pct", 0))
        + float(effects.get("player_firewall_pct", 0))
    )
    integrity *= (
        1.0
        + float(effects.get("integrity_pct", 0))
        + float(effects.get("player_integrity_pct", 0))
    )
    speed *= (
        1.0
        + float(effects.get("speed_pct", 0))
        + float(effects.get("player_speed_pct", 0))
    )
    if vs_boss:
        intrusion *= 1.0 + float(effects.get("boss_intrusion_pct", 0))

    # 建筑协同战斗加成
    intrusion *= 1.0 + float(syn.get("intrusion_pct", 0))
    firewall *= 1.0 + float(syn.get("firewall_pct", 0))
    integrity *= 1.0 + float(syn.get("integrity_pct", 0))
    speed *= 1.0 + float(syn.get("speed_pct", 0))

    return {
        "intrusion": intrusion,
        "firewall": firewall,
        "integrity": integrity,
        "speed": speed,
        "mult": mult,
        "ops_penalty": penalty,
    }
