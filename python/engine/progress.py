import json


class ProgressManager:
    """里程碑检测与当前目标。"""

    def __init__(self, state):
        self.state = state
        self.definitions = {}
        # 有序列表（完成顺序）
        self.order = []

    def load_definitions(self, milestones_json):
        data = json.loads(milestones_json)
        self.definitions = data.get("milestones", data)
        self.order = data.get(
            "order",
            list(self.definitions.keys()),
        )

    def is_done(self, mid):
        return mid in getattr(self.state, "milestones_done", [])

    def check(self, dungeon=None, protocol_mgr=None):
        """检查并完成可达成的里程碑，返回新完成的 id 列表。"""
        newly = []
        for mid in self.order:
            if self.is_done(mid):
                continue
            defn = self.definitions.get(mid)
            if not defn:
                continue
            if self._met(defn.get("require", {}), dungeon, protocol_mgr):
                self.state.milestones_done.append(mid)
                newly.append(mid)
                # 应用解锁标记
                unlock = defn.get("unlock", {})
                if unlock.get("story_flag"):
                    flag = unlock["story_flag"]
                    if flag not in self.state.story_flags:
                        self.state.story_flags.append(flag)
                if unlock.get("set_threat_tier") is not None:
                    self.state.threat_tier = max(
                        self.state.threat_tier, int(unlock["set_threat_tier"])
                    )
                if unlock.get("boss_available"):
                    self.state.boss_available = True
                if unlock.get("protocols_unlocked"):
                    self.state.protocols_unlocked = True
        return newly

    def _met(self, req, dungeon, protocol_mgr):
        if "story_node" in req:
            if self.state.current_story_node != req["story_node"]:
                # 也接受已经离开该节点但做过的标记
                if req["story_node"] not in self.state.story_flags:
                    # energy_stable: 当前或曾经到达
                    if req.get("story_reached"):
                        if req["story_reached"] not in self.state.story_flags and (
                            self.state.current_story_node
                            not in (
                                req["story_reached"],
                                req.get("story_node"),
                            )
                        ):
                            return False
                    elif self.state.current_story_node != req["story_node"]:
                        # soft: if require story_node as "at or past"
                        nodes_ok = req.get("story_any", [])
                        if nodes_ok:
                            if self.state.current_story_node not in nodes_ok:
                                return False
                        else:
                            return False
        if "story_flag" in req:
            if req["story_flag"] not in self.state.story_flags:
                return False
        if "combat_wins" in req:
            if getattr(self.state, "combat_wins", 0) < req["combat_wins"]:
                return False
        if "dungeon_level" in req:
            lvl = dungeon.current_level if dungeon else 0
            lvl = max(lvl, getattr(self.state, "max_dungeon_level", 0))
            if lvl < req["dungeon_level"]:
                return False
        if "hacking_level" in req:
            if self.state.hacking_level < req["hacking_level"]:
                return False
        if "hacking_xp" in req:
            if self.state.resources.get("hacking_xp", 0) < req["hacking_xp"]:
                return False
        if "protocols_researched" in req:
            count = len(getattr(self.state, "protocols", []))
            if count < req["protocols_researched"]:
                return False
        if "boss_kills" in req:
            if getattr(self.state, "boss_kills", 0) < req["boss_kills"]:
                return False
        if "prestige" in req:
            if getattr(self.state, "prestige", 0) < req["prestige"]:
                return False
        if "milestone" in req:
            if not self.is_done(req["milestone"]):
                return False
        return True

    def current_target(self):
        """返回当前未完成的第一个里程碑定义。"""
        for mid in self.order:
            if not self.is_done(mid):
                defn = self.definitions.get(mid, {})
                return mid, defn
        return None, None
