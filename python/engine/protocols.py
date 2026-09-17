import json


class ProtocolManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}
        # 架构/Trait 构筑聚合器（可选注入）
        self.arch_mgr = None
        # 内核跃迁永久升级聚合器（可选注入）
        self.asc_mgr = None
        # 网络区域聚合器（可选注入）
        self.net_mgr = None

    def set_architecture_manager(self, arch_mgr):
        self.arch_mgr = arch_mgr

    def set_ascension_manager(self, asc_mgr):
        self.asc_mgr = asc_mgr

    def set_network_manager(self, net_mgr):
        self.net_mgr = net_mgr

    def load_definitions(self, protocols_json):
        self.definitions = json.loads(protocols_json)

    def researched(self):
        return list(getattr(self.state, "protocols", []))

    def has(self, pid):
        return pid in self.researched()

    def aggregate_effects(self):
        effects = {}
        for pid in self.researched():
            defn = self.definitions.get(pid, {})
            for k, v in defn.get("effects", {}).items():
                effects[k] = effects.get(k, 0) + v
        # prestige bonuses
        p = getattr(self.state, "prestige", 0)
        if p > 0:
            effects["all_gen_pct"] = effects.get("all_gen_pct", 0) + 0.05 * p
            effects["intrusion_pct"] = effects.get("intrusion_pct", 0) + 0.03 * p
            # 转生掉落：第二圈起战利品与经验更丰厚，加速收束
            effects["loot_pct"] = effects.get("loot_pct", 0) + 0.10 * p
        # 架构范式 + Trait：走同一条全局修正通道
        if self.arch_mgr is not None:
            for k, v in self.arch_mgr.aggregate_effects().items():
                effects[k] = effects.get(k, 0) + v
        # 内核跃迁永久升级：同一条通道
        if self.asc_mgr is not None:
            for k, v in self.asc_mgr.aggregate_effects().items():
                effects[k] = effects.get(k, 0) + v
        # 网络区域效果 + 已攻克区域的永久加成：同一条通道
        if self.net_mgr is not None:
            for k, v in self.net_mgr.aggregate_effects().items():
                effects[k] = effects.get(k, 0) + v
        return effects

    def research(self, protocol_id):
        if not getattr(self.state, "protocols_unlocked", False):
            return False, "protocols_locked"
        if protocol_id not in self.definitions:
            return False, "not_found"
        if self.has(protocol_id):
            return False, "already"
        defn = self.definitions[protocol_id]
        req = defn.get("req")
        if req and not self.has(req):
            return False, "req_missing"
        cost = defn.get("cost", {})
        for res, amount in cost.items():
            if self.state.resources.get(res, 0) < amount:
                return False, "insufficient_resources"
        for res, amount in cost.items():
            self.state.resources[res] -= amount
        self.state.protocols.append(protocol_id)
        return True, "ok"

    def persistent_pool(self):
        """所有已研究且标记 persist 的协议 id。"""
        return [
            pid
            for pid in self.researched()
            if self.definitions.get(pid, {}).get("persist")
        ]

    def next_slots(self):
        """下一次重启可保留的槽位数（基于即将到达的转生次数）。"""
        from engine.architecture import protocol_slots

        bonus = 0
        if self.asc_mgr is not None:
            bonus = int(self.asc_mgr.protocol_slot_bonus())
        return protocol_slots(int(getattr(self.state, "prestige", 0)) + 1, bonus)

    def persist_plan(self):
        """计算本次重启实际保留的持久协议。

        规则：玩家手动锁定的协议优先，其余按 tier 从高到低补足，
        总数不超过下一次重启解锁的槽位数。
        """
        pool = self.persistent_pool()
        slots = self.next_slots()
        if slots <= 0:
            return []
        keep = [
            pid
            for pid in list(getattr(self.state, "protocol_keep", None) or [])
            if pid in pool
        ]
        rest = [pid for pid in pool if pid not in keep]
        rest.sort(key=lambda pid: (-int(self.definitions.get(pid, {}).get("tier", 1)), pid))
        plan = keep[:slots]
        for pid in rest:
            if len(plan) >= slots:
                break
            plan.append(pid)
        return plan

    def persistent_ids(self):
        return self.persist_plan()

    def toggle_keep(self, pid):
        """切换某个持久协议的「锁定保留」状态。"""
        if pid not in self.persistent_pool():
            return False, "not_persistent"
        keep = list(getattr(self.state, "protocol_keep", None) or [])
        if pid in keep:
            keep.remove(pid)
        else:
            keep.append(pid)
        self.state.protocol_keep = keep
        return True, "ok"
