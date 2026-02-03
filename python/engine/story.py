import json

class StoryManager:
    def __init__(self, state):
        self.state = state
        self.story_nodes = {}

    def load_nodes(self, json_data):
        self.story_nodes = json.loads(json_data)

    def get_current_node(self):
        node_id = self.state.current_story_node
        return self.story_nodes.get(node_id)

    def trigger_choice(self, choice_id):
        node = self.get_current_node()
        if not node or "actions" not in node:
            return False
        
        action = node["actions"].get(choice_id)
        if not action:
            return False

        # 应用奖励/后果
        if "reward" in action:
            for res, amount in action["reward"].items():
                self.state.resources[res] = self.state.resources.get(res, 0) + amount

        # 跳转节点
        if "next_node" in action:
            self.state.current_story_node = action["next_node"]
            
        return True

    def check_availability(self, node_id):
        node = self.story_nodes.get(node_id)
        if not node:
            return False
            
        if "requirements" in node:
            for res, amount in node["requirements"].items():
                if self.state.resources.get(res, 0) < amount:
                    return False
        
        return True
