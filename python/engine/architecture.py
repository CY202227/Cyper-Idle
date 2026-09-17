"""架构范式（Architecture Paradigm）与 Trait 构筑。

设计参考 Evolve 的 Genus / Trait 体系，但收敛到 Cyber-Idle 的单层转生：

- **架构范式**：每轮只能选 1 个，决定内核的固有偏向（正负效果并存）。
- **Trait**：在范式的 Trait 预算内自由挑选。正面 Trait 消耗预算，
  缺陷（flaw）返还预算，因此「强 build」必须用真实弱点去换。
- **互斥轴**：同一轴最多选 `limit` 个，避免同类效果叠加。

所有效果最终合并进 `ProtocolManager.aggregate_effects()`，复用既有的
全局修正通道，因此不需要在战斗/经济/任务各处新增分支。
"""

import json

# 持久协议槽位：按「重启次数」递增，第 1/2/4 次重启分别解锁 2/3/4 个槽位。
_SLOT_TABLE = ((1, 2), (3, 3), (5, 4))


def protocol_slots(prestige, bonus=0):
    """返回给定转生次数下可保留的持久协议数量。

    基础表上限 5；`bonus` 来自内核跃迁的「深层槽位」永久升级，
    因此总上限可超过 5。
    """
    p = int(prestige or 0)
    bonus = max(0, int(bonus or 0))
    base = 0
    if p > 0:
        base = 5
        for cap, slots in _SLOT_TABLE:
            if p <= cap:
                base = slots
                break
    return base + bonus


class ArchitectureManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}
        self.rules = {}
        self.axes = {}
        self.paradigms = {}
        self.traits = {}
        # 内核跃迁管理器（可选）：提供额外的 Trait 预算
        self.asc_mgr = None

    def set_ascension_manager(self, asc_mgr):
        self.asc_mgr = asc_mgr

    def trait_budget_bonus(self):
        if self.asc_mgr is None:
            return 0
        try:
            return int(self.asc_mgr.trait_budget_bonus())
        except Exception:
            return 0

    # ---------- 加载 ----------
    def load_definitions(self, architectures_json):
        data = json.loads(architectures_json)
        self.definitions = data
        self.rules = data.get("rules", {})
        self.axes = data.get("axes", {})
        self.paradigms = data.get("paradigms", {})
        self.traits = data.get("traits", {})

    def default_paradigm(self):
        return "standard" if "standard" in self.paradigms else None

    # ---------- 当前构筑 ----------
    def current_paradigm(self):
        pid = getattr(self.state, "architecture", None)
        if pid in self.paradigms:
            return pid
        return None

    def current_traits(self):
        out = []
        for tid in list(getattr(self.state, "traits", None) or []):
            if tid in self.traits and tid not in out:
                out.append(tid)
        return out

    def paradigm_effects(self):
        pid = self.current_paradigm()
        if not pid:
            return {}
        return dict(self.paradigms[pid].get("effects", {}))

    def trait_effects(self):
        effects = {}
        for tid in self.current_traits():
            for k, v in self.traits[tid].get("effects", {}).items():
                effects[k] = effects.get(k, 0) + v
        return effects

    def aggregate_effects(self):
        """合并范式 + Trait 效果，供 ProtocolManager 统一聚合。"""
        effects = {}
        for src in (self.paradigm_effects(), self.trait_effects()):
            for k, v in src.items():
                effects[k] = effects.get(k, 0) + v
        return effects

    # ---------- 预算 / 校验 ----------
    def budget_total(self, paradigm_id=None):
        pid = paradigm_id or self.current_paradigm()
        if not pid:
            return 0
        base = int(self.paradigms.get(pid, {}).get("trait_budget", 0))
        return base + self.trait_budget_bonus()

    def budget_used(self, traits=None):
        tids = self.current_traits() if traits is None else list(traits or [])
        return sum(int(self.traits.get(t, {}).get("val", 0)) for t in tids)

    def max_traits(self):
        return int(self.rules.get("max_traits", 5))

    def axis_counts(self, traits):
        counts = {}
        for tid in traits or []:
            axis = self.traits.get(tid, {}).get("axis")
            if axis:
                counts[axis] = counts.get(axis, 0) + 1
        return counts

    def axis_violations(self, traits):
        """返回超出 limit 的轴 id 列表。"""
        bad = []
        for axis, n in self.axis_counts(traits).items():
            limit = int(self.axes.get(axis, {}).get("limit", 1))
            if n > limit:
                bad.append(axis)
        return bad

    def validate(self, paradigm_id, traits):
        if paradigm_id not in self.paradigms:
            return False, "arch_unknown"
        tids = []
        for t in traits or []:
            if t in tids:
                continue
            if t not in self.traits:
                return False, "trait_unknown"
            tids.append(t)
        if len(tids) > self.max_traits():
            return False, "trait_too_many"
        if self.axis_violations(tids):
            return False, "trait_axis_conflict"
        if self.budget_used(tids) > self.budget_total(paradigm_id):
            return False, "budget_exceeded"
        return True, "ok"

    # ---------- 重选费用 ----------
    def respec_cost(self):
        """首次选择免费；之后按转生数与已选 Trait 数量计价。

        `architecture_chosen` 记录玩家是否主动构筑过——旧存档被
        `ensure_default()` 迁移到 standard 时该标记为 False，
        因此第一次真正的构筑依然免费。
        """
        if not getattr(self.state, "architecture_chosen", False):
            return {}
        p = int(getattr(self.state, "prestige", 0))
        r = self.rules
        credits = (
            int(r.get("respec_credits_base", 200))
            + int(r.get("respec_credits_per_prestige", 150)) * p
            + int(r.get("respec_credits_per_trait", 100)) * len(self.current_traits())
        )
        compute = int(r.get("respec_compute_base", 20)) + int(
            r.get("respec_compute_per_prestige", 10)
        ) * p
        return {"credits": credits, "compute": compute}

    def can_afford(self):
        for res, amount in self.respec_cost().items():
            if self.state.resources.get(res, 0) < amount:
                return False
        return True

    def select(self, paradigm_id, traits, charge=True):
        ok, reason = self.validate(paradigm_id, traits)
        if not ok:
            return False, reason
        tids = []
        for t in traits or []:
            if t not in tids:
                tids.append(t)
        cost = self.respec_cost() if charge else {}
        for res, amount in cost.items():
            if self.state.resources.get(res, 0) < amount:
                return False, "insufficient_resources"
        for res, amount in cost.items():
            self.state.resources[res] = max(
                0, self.state.resources.get(res, 0) - amount
            )
        self.state.architecture = paradigm_id
        self.state.traits = tids
        self.state.architecture_chosen = True
        return True, "ok"

    def ensure_default(self):
        """旧存档迁移：没有架构时落到默认范式（standard），不消耗资源。

        不设置 `architecture_chosen`，因此迁移后的首次构筑仍然免费。
        """
        if self.current_paradigm() is not None:
            return False
        pid = self.default_paradigm()
        if not pid:
            return False
        self.state.architecture = pid
        if not isinstance(getattr(self.state, "traits", None), list):
            self.state.traits = []
        return True
