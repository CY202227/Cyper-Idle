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

    def can_take_action(self, action):
        """检查选项是否可点：资源门槛、一次性标记等。"""
        if not action:
            return False, "missing"
        need_flag = action.get("requires_flag")
        if need_flag and need_flag not in self.state.story_flags:
            return False, "flag_locked"
        block_flag = action.get("requires_not_flag")
        if block_flag and block_flag in self.state.story_flags:
            return False, "already_done"
        for res, amount in action.get("requirements", {}).items():
            if self.state.resources.get(res, 0) < amount:
                return False, "insufficient_resources"
        return True, "ok"

    def trigger_choice(self, choice_id):
        node = self.get_current_node()
        if not node or "actions" not in node:
            return False, "missing"

        action = node["actions"].get(choice_id)
        if not action:
            return False, "missing"

        ok, reason = self.can_take_action(action)
        if not ok:
            return False, reason

        # 消耗：显式 consume，或 requirements 里标了 cost 语义
        if action.get("consume"):
            for res, amount in action.get("requirements", {}).items():
                self.state.resources[res] = max(
                    0, self.state.resources.get(res, 0) - amount
                )

        if "reward" in action:
            for res, amount in action["reward"].items():
                if res in ("daemon_id", "quest_id"):
                    continue
                self.state.resources[res] = self.state.resources.get(res, 0) + amount
                if self.state.resources[res] < 0:
                    self.state.resources[res] = 0

        set_flag = action.get("set_flag")
        if set_flag and set_flag not in self.state.story_flags:
            self.state.story_flags.append(set_flag)

        if "next_node" in action:
            self.state.current_story_node = action["next_node"]

        return True, "ok"

    def check_availability(self, node_id):
        node = self.story_nodes.get(node_id)
        if not node:
            return False

        if "requirements" in node:
            for res, amount in node["requirements"].items():
                if self.state.resources.get(res, 0) < amount:
                    return False

        return True
