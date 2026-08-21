import json


class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {
            "energy": 100,
            "data_scraps": 0,
            "credits": 0,
            "compute": 0,
            "hacking_xp": 0,
        }
        self.storage_caps = {
            "energy": 500,
            "data_scraps": 500,
            "credits": 5000,
            "compute": 200,
        }
        self.buildings = {}
        self.artifacts = []
        self.active_quests = []
        self.completed_quests = []
        self.story_flags = []
        self.current_story_node = "start"
        self.seed = None
        self.tick_count = 0
        self.last_update = 0
        self.unlocked_actions = ["gather_energy"]
        self.language = "zh"
        self.auto_combat = False
        self.auto_explore = False
        self.missions = []
        self.combat_wins = 0
        self.milestones_done = []
        self.prestige = 0
        self.threat_tier = 0
        self.protocols = []
        self.protocols_unlocked = False
        self.boss_available = False
        self.boss_kills = 0
        self.pending_floor_boss = False
        self.guide_shown = False
        self.max_dungeon_level = 1

    @property
    def hacking_level(self):
        import math
        return math.floor(math.sqrt(self.resources.get("hacking_xp", 0) / 100)) + 1

    def prestige_reset(self, persist_protocols):
        """协议重启：清空进度，保留转生与持久协议。"""
        self.prestige += 1
        self.resources = {
            "energy": 120,
            "data_scraps": 0,
            "credits": 50 * self.prestige,
            "compute": 10 * self.prestige,
            "hacking_xp": 50 * self.prestige,
        }
        self.buildings = {}
        self.missions = []
        self.active_quests = []
        self.completed_quests = []
        self.auto_combat = False
        self.auto_explore = False
        self.combat_wins = 0
        self.threat_tier = min(2, self.prestige)
        self.boss_available = False
        self.pending_floor_boss = False
        self.max_dungeon_level = 1
        self.protocols = list(persist_protocols)
        self.protocols_unlocked = True
        self.storage_caps = {
            "energy": 500,
            "data_scraps": 500,
            "credits": 5000,
            "compute": 200,
        }
        if "protocol_reboot_done" not in self.story_flags:
            self.story_flags.append("protocol_reboot_done")

    def to_json(self):
        return json.dumps({
            "resources": self.resources,
            "storage_caps": self.storage_caps,
            "buildings": self.buildings,
            "artifacts": self.artifacts,
            "active_quests": self.active_quests,
            "completed_quests": getattr(self, "completed_quests", []),
            "story_flags": self.story_flags,
            "current_story_node": self.current_story_node,
            "seed": self.seed,
            "tick_count": self.tick_count,
            "last_update": self.last_update,
            "unlocked_actions": self.unlocked_actions,
            "language": self.language,
            "auto_combat": self.auto_combat,
            "auto_explore": self.auto_explore,
            "missions": self.missions,
            "combat_wins": self.combat_wins,
            "milestones_done": self.milestones_done,
            "prestige": self.prestige,
            "threat_tier": self.threat_tier,
            "protocols": self.protocols,
            "protocols_unlocked": self.protocols_unlocked,
            "boss_available": self.boss_available,
            "boss_kills": self.boss_kills,
            "pending_floor_boss": self.pending_floor_boss,
            "guide_shown": self.guide_shown,
            "max_dungeon_level": self.max_dungeon_level,
        })

    def from_json(self, json_str):
        data = json.loads(json_str)
        self.resources = data.get("resources", self.resources)
        self.storage_caps = data.get("storage_caps", self.storage_caps)
        self.buildings = data.get("buildings", {})
        self.artifacts = data.get("artifacts", [])
        self.active_quests = data.get("active_quests", [])
        self.completed_quests = data.get("completed_quests", [])
        self.story_flags = data.get("story_flags", self.story_flags)
        self.current_story_node = data.get(
            "current_story_node", self.current_story_node
        )
        self.seed = data.get("seed", self.seed)
        self.tick_count = data.get("tick_count", self.tick_count)
        self.last_update = data.get("last_update", self.last_update)
        self.unlocked_actions = data.get(
            "unlocked_actions", self.unlocked_actions
        )
        self.language = data.get("language", "zh")
        self.auto_combat = data.get("auto_combat", False)
        self.auto_explore = data.get("auto_explore", False)
        raw_missions = data.get("missions", [])
        self.missions = []
        for m in raw_missions:
            if "daemon_index" in m and "mission_id" not in m:
                continue
            cleaned = {
                "mission_id": m.get("mission_id"),
                "elapsed": m.get("elapsed", 0),
                "duration": m.get("duration", 60),
                "completed": m.get("completed", False),
                "claimed": m.get("claimed", False),
            }
            if cleaned["mission_id"]:
                self.missions.append(cleaned)
        self.combat_wins = data.get("combat_wins", 0)
        self.milestones_done = data.get("milestones_done", [])
        self.prestige = data.get("prestige", 0)
        self.threat_tier = data.get("threat_tier", 0)
        self.protocols = data.get("protocols", [])
        self.protocols_unlocked = data.get("protocols_unlocked", False)
        self.boss_available = data.get("boss_available", False)
        self.boss_kills = data.get("boss_kills", 0)
        self.pending_floor_boss = data.get("pending_floor_boss", False)
        self.guide_shown = data.get("guide_shown", False)
        self.max_dungeon_level = data.get("max_dungeon_level", 1)
