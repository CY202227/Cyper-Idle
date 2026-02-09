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
            "hacking_xp": 0
        }
        self.storage_caps = {
            "energy": 100,
            "data_scraps": 100,
            "credits": 1000,
            "compute": 50
        }
        self.buildings = {} # { "building_id": level }
        self.daemons = [] # 存储拥有的守护程序
        self.active_daemon_index = 0 # 当前选中的守护程序索引
        self.active_quests = [] # 存储当前接受的任务
        self.story_flags = []
        self.current_story_node = "start"
        self.seed = None
        self.tick_count = 0
        self.last_update = 0
        self.unlocked_actions = ["gather_energy"]
        self.language = "en"

    @property
    def hacking_level(self):
        # 简单的等级公式：等级 = floor(sqrt(xp / 100)) + 1
        import math
        return math.floor(math.sqrt(self.resources.get("hacking_xp", 0) / 100)) + 1

    def to_json(self):
        return json.dumps({
            "resources": self.resources,
            "storage_caps": self.storage_caps,
            "buildings": self.buildings,
            "daemons": self.daemons,
            "active_daemon_index": self.active_daemon_index,
            "active_quests": self.active_quests,
            "story_flags": self.story_flags,
            "current_story_node": self.current_story_node,
            "seed": self.seed,
            "tick_count": self.tick_count,
            "last_update": self.last_update,
            "unlocked_actions": self.unlocked_actions,
            "language": self.language
        })

    def from_json(self, json_str):
        data = json.loads(json_str)
        self.resources = data.get("resources", self.resources)
        self.storage_caps = data.get("storage_caps", self.storage_caps)
        self.buildings = data.get("buildings", {})
        self.daemons = data.get("daemons", [])
        self.active_daemon_index = data.get("active_daemon_index", 0)
        self.active_quests = data.get("active_quests", [])
        self.story_flags = data.get("story_flags", self.story_flags)
        self.current_story_node = data.get("current_story_node", self.current_story_node)
        self.seed = data.get("seed", self.seed)
        self.tick_count = data.get("tick_count", self.tick_count)
        self.last_update = data.get("last_update", self.last_update)
        self.unlocked_actions = data.get("unlocked_actions", self.unlocked_actions)
        self.language = data.get("language", "zh")
