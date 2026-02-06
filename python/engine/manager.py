import json

class GameManager:
    def __init__(self, state, rng):
        self.state = state
        self.rng = rng
        self.definitions = {
            "resources": {},
            "actions": {},
            "events": []
        }

    def load_definitions(self, resources_json, events_json):
        self.definitions["resources"] = json.loads(resources_json)
        self.definitions["events"] = json.loads(events_json)

    def tick(self, delta_time):
        """主循环逻辑，计算资源产出"""
        self.state.tick_count += 1
        
        # 基础产出计算 (示例)
        # 在实际游戏中，这里会遍历已解锁的设施或升级
        for res_id, res_def in self.definitions["resources"].items():
            if "auto_gen" in res_def:
                amount = res_def["auto_gen"] * delta_time
                self.state.resources[res_id] = self.state.resources.get(res_id, 0) + amount

        # 检查收集类任务进度
        # 注意：这里需要一个引用到 quest_mgr 的方式，或者在 main.py 中处理
        # 暂时在 main.py 的循环中处理更方便

        # 随机事件检查
        if self.state.tick_count % 60 == 0: # 约每分钟检查一次（假设 1 tick/sec）
            self.check_random_events()

    def check_random_events(self):
        # 简单的权重随机事件系统
        available_events = []
        for event in self.definitions["events"]:
            # 检查事件触发条件
            met = True
            if "requirements" in event:
                for res, amount in event["requirements"].items():
                    if self.state.resources.get(res, 0) < amount:
                        met = False
                        break
            if met:
                available_events.append((event, event.get("weight", 1)))
        
        if available_events:
            event = self.rng.weighted_choice(available_events)
            self.trigger_event(event)

    def trigger_event(self, event):
        # 处理事件效果
        if "effect" in event:
            for res, amount in event["effect"].items():
                self.state.resources[res] = self.state.resources.get(res, 0) + amount
        # 记录到日志 (通过状态或某种方式传递给 UI)
        return event.get("description", "发生了一个未知的网络波动。")

    def perform_action(self, action_id):
        # 基础动作，如手动收集
        if action_id == "gather_energy":
            self.state.resources["energy"] += 1
            return True
        return False
