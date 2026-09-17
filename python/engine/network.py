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

# 解锁条件中按「数值比较」判定的键；`region` 单独处理（要求前置区域已攻克）
_NUMERIC_KEYS = ("prestige", "boss_kills", "dungeon_level", "ascension_count")


class NetworkManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}
        self.rules = {}
        self.regions = {}

    # ---------- 加载 ----------
    def load_definitions(self, networks_json):
        data = json.loads(networks_json)
        self.definitions = data
        self.rules = data.get("rules", {})
        self.regions = data.get("regions", {})

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
                }
            )
        return out
