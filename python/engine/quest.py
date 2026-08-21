import json

class QuestManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}

    def load_definitions(self, quests_json):
        self.definitions = json.loads(quests_json)

    def has_quest(self, quest_id):
        """是否已在进行中，或已领过奖（合同板应隐藏）。"""
        if not quest_id:
            return False
        if quest_id in getattr(self.state, "completed_quests", []):
            return True
        return any(q.get("id") == quest_id for q in self.state.active_quests)

    def accept_quest(self, quest_id):
        """接受一个任务"""
        if quest_id not in self.definitions or self.has_quest(quest_id):
            return False
        defn = self.definitions[quest_id]
        new_quest = {
            "id": quest_id,
            "progress": 0,
            "completed": False,
            "claimed": False,
        }
        # 如果是收集任务，初始化进度
        if defn["type"] == "collect":
            new_quest["progress"] = self.state.resources.get(defn["target_id"], 0)

        self.state.active_quests.append(new_quest)
        return True

    def update_progress(self, q_type, target_id=None, amount=1):
        """更新任务进度"""
        changed = False
        for quest in self.state.active_quests:
            if quest["completed"] or quest["claimed"]:
                continue
                
            defn = self.definitions.get(quest["id"])
            if not defn or defn["type"] != q_type:
                continue

            if q_type == "collect":
                if target_id == defn["target_id"]:
                    quest["progress"] = self.state.resources.get(target_id, 0)
                    changed = True
            elif q_type == "combat":
                quest["progress"] += amount
                changed = True
            elif q_type == "explore":
                quest["progress"] = max(quest["progress"], amount)
                changed = True
            elif q_type == "special":
                quest["progress"] += amount
                changed = True
            elif q_type == "protocol":
                quest["progress"] = len(getattr(self.state, "protocols", []))
                changed = True
            elif q_type == "boss":
                quest["progress"] = getattr(self.state, "boss_kills", 0)
                changed = True

            if quest["progress"] >= defn["target_amount"]:
                quest["completed"] = True
                changed = True
        return changed

    def claim_reward(self, quest_id):
        """领取任务奖励"""
        for i, quest in enumerate(self.state.active_quests):
            if quest["id"] == quest_id and quest["completed"] and not quest["claimed"]:
                defn = self.definitions[quest_id]
                
                # 发放奖励
                for res_id, amount in defn["reward"].items():
                    if res_id == "hacking_xp":
                        self.state.resources["hacking_xp"] += amount
                    else:
                        self.state.resources[res_id] = self.state.resources.get(res_id, 0) + amount
                
                quest["claimed"] = True
                self.state.active_quests.pop(i)
                done = getattr(self.state, "completed_quests", None)
                if done is None:
                    self.state.completed_quests = []
                    done = self.state.completed_quests
                if quest_id not in done:
                    done.append(quest_id)
                return True, defn["reward"]
        return False, None
