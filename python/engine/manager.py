import json

class GameManager:
    def __init__(self, state, rng):
        self.state = state
        self.rng = rng
        self.definitions = {
            "resources": {},
            "actions": {},
            "events": [],
            "buildings": {}
        }

    def load_definitions(self, resources_json, events_json, buildings_json=None):
        self.definitions["resources"] = json.loads(resources_json)
        self.definitions["events"] = json.loads(events_json)
        if buildings_json:
            self.definitions["buildings"] = json.loads(buildings_json)

    def tick(self, delta_time):
        """主循环逻辑，计算资源产出"""
        self.state.tick_count += 1
        
        # 1. 基础产出 (来自资源定义)
        for res_id, res_def in self.definitions["resources"].items():
            if "auto_gen" in res_def:
                amount = res_def["auto_gen"] * delta_time
                self.state.resources[res_id] = self.state.resources.get(res_id, 0) + amount

        # 2. 建筑产出与消耗
        self.apply_building_effects(delta_time)

        # 3. 强制执行存储上限
        self.apply_storage_caps()

        # 4. 随机事件检查
        if self.state.tick_count % 60 == 0:
            self.check_random_events()

    def apply_building_effects(self, delta_time):
        """计算所有建筑的产出、消耗和存储加成"""
        # 重置存储上限为基础值 (这里需要一个基础值定义，或者在 state.reset 中定义)
        # 简单起见，我们假设基础值已经在 state.storage_caps 中，我们每次 tick 根据建筑重新计算它
        # 或者更高效的做法是：只在建筑升级时更新 storage_caps。
        
        for category in ["hardware", "software"]:
            if category not in self.definitions["buildings"]: continue
            for b_id, b_def in self.definitions["buildings"][category].items():
                level = self.state.buildings.get(b_id, 0)
                if level <= 0: continue
                
                effects = b_def.get("effects", {})
                
                # 处理自动产出
                if "auto_gen" in effects:
                    for res, rate in effects["auto_gen"].items():
                        self.state.resources[res] = self.state.resources.get(res, 0) + (rate * level * delta_time)
                
                # 处理消耗 (如果资源不足，建筑可能停止工作，这里简单处理：允许负数或直接扣除)
                if "consume" in effects:
                    for res, rate in effects["consume"].items():
                        self.state.resources[res] = max(0, self.state.resources.get(res, 0) - (rate * level * delta_time))

    def apply_storage_caps(self):
        """确保资源不超过上限"""
        for res_id, cap in self.state.storage_caps.items():
            if res_id in self.state.resources:
                if self.state.resources[res_id] > cap:
                    self.state.resources[res_id] = cap

    def update_storage_caps(self):
        """根据建筑等级重新计算存储上限 (仅在升级时调用)"""
        # 基础上限 (这里应该从某个地方读取，暂时硬编码或从 state 获取初始值)
        base_caps = {
            "energy": 100,
            "data_scraps": 100,
            "credits": 1000,
            "compute": 50
        }
        new_caps = base_caps.copy()
        
        for category in ["hardware", "software"]:
            if category not in self.definitions["buildings"]: continue
            for b_id, b_def in self.definitions["buildings"][category].items():
                level = self.state.buildings.get(b_id, 0)
                if level <= 0: continue
                
                storage_effects = b_def.get("effects", {}).get("storage", {})
                for res, bonus in storage_effects.items():
                    new_caps[res] = new_caps.get(res, 0) + (bonus * level)
        
        self.state.storage_caps = new_caps

    def build(self, building_id):
        """尝试建造或升级建筑"""
        # 查找建筑定义
        b_def = None
        for cat in ["hardware", "software"]:
            if building_id in self.definitions["buildings"].get(cat, {}):
                b_def = self.definitions["buildings"][cat][building_id]
                break
        
        if not b_def: return False, "建筑不存在"
        
        current_level = self.state.buildings.get(building_id, 0)
        multiplier = b_def.get("cost_multiplier", 1.5)
        
        # 计算当前等级的成本
        actual_costs = {}
        for res, base_amount in b_def["cost"].items():
            actual_costs[res] = base_amount * (multiplier ** current_level)
        
        # 检查资源
        for res, amount in actual_costs.items():
            if self.state.resources.get(res, 0) < amount:
                return False, f"资源不足: 需要 {int(amount)} {res}"
        
        # 扣除资源
        for res, amount in actual_costs.items():
            self.state.resources[res] -= amount
        
        # 升级
        self.state.buildings[building_id] = current_level + 1
        
        # 更新上限
        self.update_storage_caps()
        
        return True, "升级成功"

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
