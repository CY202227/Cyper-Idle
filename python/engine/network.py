"""网络区域（Network Region）与网络跃迁（Network Migration）。

游戏原本只有一张「本地子网」。本模块把它扩展为多个区域：每个区域拥有
独立的敌人池、地牢修饰词池、掉落/经验偏移与固有正负修正。

三层资源模型：

- **区域效果** `region_effects()`：只在当前所在区域生效，通常正负并存。
- **攻克加成** `clear_bonus_effects()`：击杀该区域核心后永久生效，跨区域叠加。
- **网络跃迁** `migrate()`：切换到目标区域，重置当前一轮的地牢进度与在途行动，
  但保留转生、协议栈、架构/Trait、跃迁永久升级与里程碑。

区域效果与攻克加成都会通过 `aggregate_effects()` 合入
`ProtocolManager` 的既有全局修正通道，因此战斗/经济/任务各处无需新增分支。
"""

import json
import random

from engine.dungeon import _is_hazard as is_hazard_effect

# 解锁条件中按「数值比较」判定的键；`region` 单独处理（要求前置区域已攻克）
_NUMERIC_KEYS = ("prestige", "boss_kills", "dungeon_level", "ascension_count")

# 危害维度：由效果键自动推断，无需在数据里额外标注。
# 同一次跃迁内不抽两个同维度的危害修饰词——同维度惩罚会线性叠加成断崖
# （例如两个速度惩罚让玩家直接失去双动权），那不是设计意图中的取舍。
_HAZARD_DIMS = (
    ("speed", ("speed",)),
    ("intrusion", ("intrusion",)),
    ("hp", ("hp",)),
    ("firewall", ("firewall",)),
    ("integrity", ("integrity",)),
)


def hazard_dim(key):
    """效果键所属的危害维度；无法归类返回 None。"""
    for dim, toks in _HAZARD_DIMS:
        if any(t in key for t in toks):
            return dim
    return None


class NetworkManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}
        self.rules = {}
        self.regions = {}
        self.modifier_defs = {}

    # ---------- 加载 ----------
    def load_definitions(self, networks_json):
        data = json.loads(networks_json)
        self.definitions = data
        self.rules = data.get("rules", {})
        self.regions = data.get("regions", {})

    def load_modifiers(self, modifiers_json):
        """接入地牢修饰词表，用于解析挑战修饰词的效果与名称。"""
        self.modifier_defs = json.loads(modifiers_json)

    # ---------- 查询 ----------
    def ordered_ids(self):
        return sorted(
            self.regions.keys(),
            key=lambda rid: (int(self.regions[rid].get("order", 0)), rid),
        )

    def default_region(self):
        ids = self.ordered_ids()
        return ids[0] if ids else None

    def current_region(self):
        rid = getattr(self.state, "network_region", None)
        if rid in self.regions:
            return rid
        return self.default_region()

    def region_def(self, rid=None):
        key = rid if rid in self.regions else self.current_region()
        return self.regions.get(key) or {}

    def region_order(self, rid=None):
        return int(self.region_def(rid).get("order", 0))

    def threat_offset(self, rid=None):
        return int(self.region_def(rid).get("threat_offset", 0))

    def enemy_pool(self, rid=None):
        """当前区域允许刷出的敌人 id 集合；未配置则返回 None（不限）。"""
        pool = self.region_def(rid).get("enemy_pool")
        if not pool:
            return None
        return set(pool)

    def boss_id(self, rid=None):
        return self.region_def(rid).get("boss")

    def modifier_pool(self, rid=None):
        """当前区域允许 roll 到的地牢修饰词 id 集合；未配置则返回 None。"""
        pool = self.region_def(rid).get("modifiers")
        if not pool:
            return None
        return set(pool)

    def name(self, rid=None):
        d = self.region_def(rid)
        return d.get("name") or (rid or self.current_region() or "-")

    def desc(self, rid=None):
        return self.region_def(rid).get("desc", "")

    # ---------- 效果 ----------
    def region_effects(self, rid=None):
        return dict(self.region_def(rid).get("effects", {}))

    def cleared_regions(self):
        raw = getattr(self.state, "regions_cleared", None) or []
        return [rid for rid in raw if rid in self.regions]

    def is_cleared(self, rid):
        return rid in self.cleared_regions()

    def clear_bonus_effects(self):
        """已攻克区域的永久加成（跨区域叠加）。"""
        effects = {}
        for rid in self.cleared_regions():
            for k, v in self.region_def(rid).get("clear_bonus", {}).items():
                effects[k] = effects.get(k, 0) + float(v)
        return effects

    def aggregate_effects(self):
        effects = {}
        for src in (self.region_effects(), self.clear_bonus_effects()):
            for k, v in src.items():
                effects[k] = effects.get(k, 0) + v
        return effects

    # ---------- 挑战修饰词 ----------
    # 跃迁进区域时随机抽取，整个驻留期间持续生效，叠加在每层随机修饰词之上。
    # 注意：**不要**把挑战效果并进 aggregate_effects()——那条通道只通向玩家侧，
    # 会丢掉 enemy_* 这类敌方侧键，而且会和 combat 的 meff 通道重复计算。
    def challenge_pool(self, rid=None):
        """挑战修饰词候选池（只取地牢修饰词表里存在的 id）。"""
        raw = self.rules.get("challenge_pool")
        if not raw:
            return set(self.modifier_defs.keys())
        return {mid for mid in raw if mid in self.modifier_defs}

    def challenge_count(self, rid=None):
        """本次跃迁抽几个挑战修饰词；区域越深越可能抽到 2 个。"""
        count = int(self.rules.get("challenge_count", 1))
        chance = float(self.rules.get("challenge_extra_chance", 0.0))
        chance += float(self.rules.get("challenge_extra_per_order", 0.0)) * (
            self.region_order(rid)
        )
        if chance > 0 and random.random() < min(1.0, chance):
            count += 1
        cap = int(self.rules.get("challenge_max", 2))
        return max(0, min(cap, count))

    def primary_hazard(self, mid):
        """修饰词的主要危害维度：取危害项里绝对值最大的效果键所属维度。

        纯增益修饰词返回 None（不参与维度去重）。
        """
        defn = self.modifier_defs.get(mid) or {}
        best_dim, best_val = None, 0.0
        for k, v in defn.get("effects", {}).items():
            fv = float(v)
            if not is_hazard_effect(k, fv) or abs(fv) <= best_val:
                continue
            dim = hazard_dim(k)
            if dim:
                best_dim, best_val = dim, abs(fv)
        return best_dim

    def roll_challenges(self, rid=None):
        """重抽并写入 state；返回本次抽到的 id 列表。

        同一次跃迁内避免抽到两个同维度的危害修饰词：同维度惩罚会线性叠加
        成断崖（两个速度惩罚 → 玩家直接失去双动权），那不是取舍而是惩罚。
        维度池不足时按数量回填，保证抽数与产出加成稳定。
        """
        pool = sorted(self.challenge_pool(rid))
        count = self.challenge_count(rid)
        if not pool or count <= 0:
            self.state.region_challenges = []
            return []
        count = min(count, len(pool))
        picks, used, candidates = [], set(), list(pool)
        while len(picks) < count and candidates:
            mid = random.choice(candidates)
            candidates.remove(mid)
            dim = self.primary_hazard(mid)
            if dim and dim in used:
                continue
            picks.append(mid)
            if dim:
                used.add(dim)
        # 维度冲突导致抽不满时不回填：回填会绕过去重规则，把两个同类惩罚
        # 重新叠回来。少抽就少拿产出加成，代价与收益自洽。
        self.state.region_challenges = picks
        return picks

    def challenges(self):
        """当前生效的挑战修饰词 id 列表（过滤掉已失效的 id）。"""
        raw = getattr(self.state, "region_challenges", None) or []
        return [mid for mid in raw if mid in self.modifier_defs]

    def challenge_bonus(self):
        """挑战带来的额外产出加成（按数量累加）。"""
        per = float(self.rules.get("challenge_bonus_per", 0.0))
        return per * len(self.challenges())

    def challenge_effects(self):
        """挑战修饰词效果 + 挑战产出加成。敌方侧键由 combat 的 meff 通道消费。"""
        effects = {}
        for mid in self.challenges():
            defn = self.modifier_defs.get(mid) or {}
            for k, v in defn.get("effects", {}).items():
                effects[k] = effects.get(k, 0) + float(v)
        bonus = self.challenge_bonus()
        if bonus:
            effects["loot_pct"] = effects.get("loot_pct", 0) + bonus
            effects["xp_bonus_pct"] = effects.get("xp_bonus_pct", 0) + bonus
        return effects

    def challenge_names(self):
        return [
            (self.modifier_defs.get(mid) or {}).get("name", mid)
            for mid in self.challenges()
        ]

    # ---------- 解锁 ----------
    def _stat(self, key):
        mapping = {
            "prestige": int(getattr(self.state, "prestige", 0)),
            "boss_kills": int(getattr(self.state, "boss_kills", 0)),
            "dungeon_level": int(getattr(self.state, "max_dungeon_level", 1)),
            "ascension_count": int(getattr(self.state, "ascension_count", 0)),
        }
        return mapping.get(key, 0)

    def unlock_status(self, rid):
        """逐项检查解锁条件：{key: {"need": n, "have": n, "met": bool}}。"""
        req = self.region_def(rid).get("unlock") or {}
        out = {}
        prev = req.get("region")
        if prev:
            met = self.is_cleared(prev)
            out["region"] = {"need": prev, "have": 1 if met else 0, "met": met}
        for key in _NUMERIC_KEYS:
            if key not in req:
                continue
            need = int(req[key])
            have = self._stat(key)
            out[key] = {"need": need, "have": have, "met": have >= need}
        return out

    def locked_keys(self, rid):
        return [k for k, v in self.unlock_status(rid).items() if not v["met"]]

    def is_unlocked(self, rid):
        if rid not in self.regions:
            return False
        return not self.locked_keys(rid)

    # ---------- 跃迁费用 ----------
    def migrate_cost(self, rid):
        order = self.region_order(rid)
        r = self.rules
        return {
            "credits": int(r.get("migrate_credits_base", 2500))
            + int(r.get("migrate_credits_per_order", 4000)) * order,
            "compute": int(r.get("migrate_compute_base", 50))
            + int(r.get("migrate_compute_per_order", 70)) * order,
            "data_scraps": int(r.get("migrate_scraps_base", 900))
            + int(r.get("migrate_scraps_per_order", 1400)) * order,
        }

    def can_afford(self, rid):
        for res, amount in self.migrate_cost(rid).items():
            if self.state.resources.get(res, 0) < amount:
                return False
        return True

    def can_migrate(self, rid):
        """返回 (ok, reason)。reason ∈ network_unknown / network_same / network_locked / network_no_res。"""
        if rid not in self.regions:
            return False, "network_unknown"
        if rid == self.current_region():
            return False, "network_same"
        if not self.is_unlocked(rid):
            return False, "network_locked"
        if not self.can_afford(rid):
            return False, "network_no_res"
        return True, "ok"

    def migrate(self, rid):
        ok, reason = self.can_migrate(rid)
        if not ok:
            return False, reason
        for res, amount in self.migrate_cost(rid).items():
            self.state.resources[res] = max(
                0, self.state.resources.get(res, 0) - amount
            )
        self.state.network_migrate(rid, threat_floor=self.threat_offset(rid))
        # 跃迁即重抽挑战修饰词——每次跃迁都是一次手气
        self.roll_challenges(rid)
        return True, "ok"

    # ---------- 区域核心 ----------
    def on_region_boss_defeated(self, boss_id=None):
        """区域核心被击杀：首次攻克时返回该区域的永久加成，否则返回 None。"""
        rid = self.current_region()
        if not rid:
            return None
        boss = self.region_def(rid).get("boss")
        if not boss:
            return None
        if boss_id and boss_id != boss:
            return None
        if self.is_cleared(rid):
            return None
        cleared = list(getattr(self.state, "regions_cleared", None) or [])
        cleared.append(rid)
        self.state.regions_cleared = cleared
        flags = getattr(self.state, "story_flags", None)
        if isinstance(flags, list) and "region_first_cleared" not in flags:
            flags.append("region_first_cleared")
        return dict(self.region_def(rid).get("clear_bonus", {}))

    # ---------- 深度记录 ----------
    def record_depth(self, level=None):
        """记录当前区域到达过的最深楼层（仅用于展示与成就）。"""
        rid = self.current_region()
        if not rid:
            return
        lvl = int(
            level if level is not None else getattr(self.state, "max_dungeon_level", 1)
        )
        depths = dict(getattr(self.state, "region_depths", None) or {})
        if lvl > int(depths.get(rid, 0)):
            depths[rid] = lvl
            self.state.region_depths = depths

    def depth_of(self, rid):
        return int((getattr(self.state, "region_depths", None) or {}).get(rid, 0))

    # ---------- 迁移 / UI ----------
    def ensure_default(self):
        """旧存档迁移：缺少区域字段时落到默认区域。"""
        changed = False
        if getattr(self.state, "network_region", None) not in self.regions:
            rid = self.default_region()
            if rid:
                self.state.network_region = rid
                changed = True
        if not isinstance(getattr(self.state, "regions_cleared", None), list):
            self.state.regions_cleared = []
            changed = True
        if not isinstance(getattr(self.state, "region_depths", None), dict):
            self.state.region_depths = {}
            changed = True
        if not isinstance(getattr(self.state, "migrations", None), int):
            self.state.migrations = 0
            changed = True
        raw = getattr(self.state, "region_challenges", None)
        if not isinstance(raw, list):
            self.state.region_challenges = []
            changed = True
        elif raw and self.modifier_defs:
            kept = [m for m in raw if m in self.modifier_defs]
            if kept != raw:
                self.state.region_challenges = kept
                changed = True
        return changed

    def progress(self):
        """供 UI 渲染的区域列表。"""
        out = []
        for rid in self.ordered_ids():
            d = self.region_def(rid)
            out.append(
                {
                    "id": rid,
                    "name": d.get("name", rid),
                    "desc": d.get("desc", ""),
                    "order": int(d.get("order", 0)),
                    "current": rid == self.current_region(),
                    "cleared": self.is_cleared(rid),
                    "unlocked": self.is_unlocked(rid),
                    "threat_offset": self.threat_offset(rid),
                    "effects": self.region_effects(rid),
                    "clear_bonus": dict(d.get("clear_bonus", {})),
                    "cost": self.migrate_cost(rid),
                    "locked": self.locked_keys(rid),
                    "depth": self.depth_of(rid),
                    "challenges": (
                        self.challenges() if rid == self.current_region() else []
                    ),
                }
            )
        return out
