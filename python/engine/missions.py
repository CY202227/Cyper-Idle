import json
import time


class MissionManager:
    """网络行动：无宠物，占带宽槽，完成后领奖。"""

    def __init__(self, state):
        self.state = state
        self.definitions = {}
        self.protocol_mgr = None

    def set_protocol_manager(self, protocol_mgr):
        self.protocol_mgr = protocol_mgr

    def load_definitions(self, missions_json):
        self.definitions = json.loads(missions_json)

    def active_count(self):
        return sum(
            1
            for m in getattr(self.state, "missions", [])
            if not m.get("claimed", False)
        )

    def start_mission(self, mission_id):
        if mission_id not in self.definitions:
            return False, "mission_not_found"

        defn = self.definitions[mission_id]
        req_level = defn.get("req_level", 1)
        if self.state.hacking_level < req_level:
            return False, "level_too_low"

        if self.active_count() >= 3:
            return False, "mission_slots_full"

        # 可选启动消耗
        cost = defn.get("cost", {})
        for res, amount in cost.items():
            if self.state.resources.get(res, 0) < amount:
                return False, "insufficient_resources"
        for res, amount in cost.items():
            self.state.resources[res] -= amount

        duration = float(defn.get("duration", 60))
        if self.protocol_mgr:
            pe = self.protocol_mgr.aggregate_effects()
            duration *= 1.0 + float(pe.get("mission_duration_pct", 0))
        duration = max(15.0, duration)

        self.state.missions.append({
            "mission_id": mission_id,
            "elapsed": 0.0,
            "duration": duration,
            "completed": False,
            "claimed": False,
            "started_at": time.time(),
        })
        return True, "ok"

    def tick(self, delta_time):
        for m in self.state.missions:
            if m.get("claimed") or m.get("completed"):
                continue
            m["elapsed"] = m.get("elapsed", 0) + delta_time
            if m["elapsed"] >= m["duration"]:
                m["completed"] = True
                m["elapsed"] = m["duration"]

    def claim_mission(self, mission_index):
        if not (0 <= mission_index < len(self.state.missions)):
            return False, {}, "invalid"
        m = self.state.missions[mission_index]
        if not m.get("completed") or m.get("claimed"):
            return False, {}, "not_ready"

        defn = self.definitions.get(m["mission_id"], {})
        rewards = dict(defn.get("rewards", {}))
        if self.protocol_mgr:
            loot_pct = 1.0 + float(
                self.protocol_mgr.aggregate_effects().get("loot_pct", 0)
            )
            rewards = {k: int(v * loot_pct) for k, v in rewards.items()}

        for res, amount in rewards.items():
            self.state.resources[res] = self.state.resources.get(res, 0) + amount

        m["claimed"] = True
        self.state.missions = [x for x in self.state.missions if not x.get("claimed")]
        return True, rewards, "ok"

    def progress_ratio(self, mission):
        dur = max(1.0, float(mission.get("duration", 1)))
        return min(1.0, float(mission.get("elapsed", 0)) / dur)
