"""内核跃迁（Kernel Ascension）——第二层、更深一层的转生。

层级设计（参考 Evolve 的多层递进重置）：

- **第 1 层 协议重启**：清空资源与建筑，保留转生加成与持久协议（有限槽位）。
- **第 2 层 内核跃迁**：在协议重启之上再清空**全部协议研究**（含持久槽位）并把
  转生计数归零，换取永久货币 **架构点**。

架构点只能用于本模块定义的永久升级，效果通过 `aggregate_effects()` 合入
`ProtocolManager` 的全局修正通道，因此不需要在战斗/经济/任务各处新增分支。

两个「元升级」（`special` 字段）会反向影响第 1 层与架构系统：
- `protocol_slots` → 增加持久协议槽位上限
- `trait_budget`   → 增加架构 Trait 预算上限
"""

import json


class AscensionManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}
        self.rules = {}
        self.upgrades = {}

    # ---------- 加载 ----------
    def load_definitions(self, ascension_json):
        data = json.loads(ascension_json)
        self.definitions = data
        self.rules = data.get("rules", {})
        self.upgrades = data.get("upgrades", {})

    # ---------- 等级 / 费用 ----------
    def level(self, uid):
        levels = getattr(self.state, "ascension_upgrades", None) or {}
        return int(levels.get(uid, 0))

    def max_level(self, uid):
        return int(self.upgrades.get(uid, {}).get("max_level", 0))

    def is_maxed(self, uid):
        return self.level(uid) >= self.max_level(uid)

    def next_cost(self, uid):
        """下一级所需架构点；已满级返回 None。"""
        defn = self.upgrades.get(uid)
        if not defn:
            return None
        lvl = self.level(uid)
        costs = list(defn.get("cost", []))
        if lvl >= int(defn.get("max_level", 0)) or lvl >= len(costs):
            return None
        return int(costs[lvl])

    def total_spent(self):
        spent = 0
        for uid, defn in self.upgrades.items():
            costs = list(defn.get("cost", []))
            for i in range(min(self.level(uid), len(costs))):
                spent += int(costs[i])
        return spent

    # ---------- 购买 ----------
    def can_purchase(self, uid):
        if uid not in self.upgrades:
            return False, "asc_unknown"
        if self.is_maxed(uid):
            return False, "asc_maxed"
        cost = self.next_cost(uid)
        if cost is None:
            return False, "asc_maxed"
        if int(getattr(self.state, "arch_points", 0)) < cost:
            return False, "asc_no_points"
        return True, "ok"

    def purchase(self, uid):
        ok, reason = self.can_purchase(uid)
        if not ok:
            return False, reason
        cost = self.next_cost(uid)
        self.state.arch_points = int(getattr(self.state, "arch_points", 0)) - cost
        levels = dict(getattr(self.state, "ascension_upgrades", None) or {})
        levels[uid] = self.level(uid) + 1
        self.state.ascension_upgrades = levels
        return True, "ok"

    # ---------- 效果 ----------
    def aggregate_effects(self):
        """永久升级效果（按等级线性叠加）。"""
        effects = {}
        for uid, defn in self.upgrades.items():
            lvl = self.level(uid)
            if lvl <= 0:
                continue
            for k, v in defn.get("effects", {}).items():
                effects[k] = effects.get(k, 0) + float(v) * lvl
        return effects

    def _special_levels(self, special):
        total = 0
        for uid, defn in self.upgrades.items():
            if defn.get("special") == special:
                total += self.level(uid)
        return total

    def protocol_slot_bonus(self):
        """额外持久协议槽位（来自「深层槽位」）。"""
        return self._special_levels("protocol_slots")

    def trait_budget_bonus(self):
        """额外 Trait 预算（来自「构筑容量」）。"""
        return self._special_levels("trait_budget")

    # ---------- 跃迁条件与收益 ----------
    def requirements(self):
        return {
            "prestige": int(self.rules.get("unlock_prestige", 3)),
            "boss_kills": int(self.rules.get("unlock_boss_kills", 3)),
            "dungeon_level": int(self.rules.get("unlock_dungeon_level", 20)),
        }

    def unlock_status(self):
        """逐项检查解锁条件，返回 {key: {"need": n, "have": n, "met": bool}}。"""
        req = self.requirements()
        have = {
            "prestige": int(getattr(self.state, "prestige", 0)),
            "boss_kills": int(getattr(self.state, "boss_kills", 0)),
            "dungeon_level": int(getattr(self.state, "max_dungeon_level", 1)),
        }
        out = {}
        for key, need in req.items():
            out[key] = {"need": need, "have": have[key], "met": have[key] >= need}
        return out

    def can_ascend(self):
        status = self.unlock_status()
        missing = [k for k, v in status.items() if not v["met"]]
        return (not missing), missing

    def gain_for(self, state=None):
        """本次跃迁可得架构点。"""
        st = state or self.state
        r = self.rules
        gain = (
            float(r.get("gain_base", 1))
            + float(r.get("gain_per_prestige", 2)) * int(getattr(st, "prestige", 0))
            + float(r.get("gain_per_depth", 0.25))
            * int(getattr(st, "max_dungeon_level", 1))
            + float(r.get("gain_per_boss_kill", 1)) * int(getattr(st, "boss_kills", 0))
            + float(r.get("gain_per_protocol", 0.5)) * len(getattr(st, "protocols", []))
        )
        return max(1, int(gain))

    def threat_floor(self):
        """跃迁次数带来的起始威胁阶（越跃迁越硬，但掉落更好）。"""
        per = int(self.rules.get("threat_per_ascension", 2))
        return min(5, int(getattr(self.state, "ascension_count", 0)) * per)
