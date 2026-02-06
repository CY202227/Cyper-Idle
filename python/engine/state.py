import json

class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {
            "energy": 0,
            "data_scraps": 0,
            "credits": 0
        }
        self.story_flags = []
        self.current_story_node = "start"
        self.seed = None
        self.tick_count = 0
        self.last_update = 0
        self.unlocked_actions = ["gather_energy"]
        self.language = "en"

    def to_json(self):
        return json.dumps({
            "resources": self.resources,
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
        self.story_flags = data.get("story_flags", self.story_flags)
        self.current_story_node = data.get("current_story_node", self.current_story_node)
        self.seed = data.get("seed", self.seed)
        self.tick_count = data.get("tick_count", self.tick_count)
        self.last_update = data.get("last_update", self.last_update)
        self.unlocked_actions = data.get("unlocked_actions", self.unlocked_actions)
        self.language = data.get("language", "zh")
