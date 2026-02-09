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

        # 如果动作包含任务接受
        if "quest_id" in action:
            # 这里需要访问全局的 quest_mgr，或者通过某种方式传递
            # 简单起见，我们在 main.py 中处理这个逻辑
            pass

        # 应用奖励/后果
        if "reward" in action:
            for res, amount in action["reward"].items():
                if res in self.state.resources:
                    self.state.resources[res] = self.state.resources.get(res, 0) + amount
                elif res == "daemon_id" or res == "quest_id":
                    # 已经在 main.py 中特殊处理，这里跳过
                    pass
                else:
                    # 如果是其他未定义的资源，也尝试增加
                    self.state.resources[res] = self.state.resources.get(res, 0) + amount

        # 扣除消耗 (Requirements)
        # 或者在 action 中增加一个 "consume" 字段。
        if "requirements" in action:
            # 默认情况下，requirements 只是检查。
            # 但如果我们在 action 中定义了 "consume": true，则扣除。
            if action.get("consume", False):
                for res, amount in action["requirements"].items():
                    self.state.resources[res] = max(0, self.state.resources.get(res, 0) - amount)

        # 特殊处理：如果 reward 中有负数，它实际上就是消耗
        
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
