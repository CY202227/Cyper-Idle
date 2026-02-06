import math

class DaemonManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}

    def load_definitions(self, daemons_json):
        import json
        self.definitions = json.loads(daemons_json)

    def create_daemon(self, daemon_id, level=1):
        """创建一个新的守护程序实例"""
        if daemon_id not in self.definitions:
            return None
        
        defn = self.definitions[daemon_id]
        daemon = {
            "id": daemon_id,
            "name": defn["name"],
            "level": level,
            "xp": 0,
            "xp_to_next": self.calculate_xp_requirement(level),
            "stats": self.calculate_stats(daemon_id, level)
        }
        return daemon

    def calculate_xp_requirement(self, level):
        """计算升级所需经验值"""
        return int(100 * (level ** 1.5))

    def calculate_stats(self, daemon_id, level):
        """根据等级计算属性"""
        defn = self.definitions[daemon_id]
        base = defn["base_stats"]
        growth = defn["growth"]
        
        stats = {}
        for stat, base_val in base.items():
            # 基础值 + (等级-1) * 成长值
            stats[stat] = base_val + (level - 1) * growth.get(stat, 0)
        return stats

    def add_xp(self, daemon_index, amount):
        """为指定的守护程序增加经验值"""
        if 0 <= daemon_index < len(self.state.daemons):
            daemon = self.state.daemons[daemon_index]
            daemon["xp"] += amount
            
            leveled_up = False
            while daemon["xp"] >= daemon["xp_to_next"]:
                daemon["xp"] -= daemon["xp_to_next"]
                daemon["level"] += 1
                daemon["xp_to_next"] = self.calculate_xp_requirement(daemon["level"])
                daemon["stats"] = self.calculate_stats(daemon["id"], daemon["level"])
                leveled_up = True
            
            return leveled_up
        return False

    def get_active_daemon(self):
        """获取当前出战的守护程序"""
        if not self.state.daemons:
            return None
        idx = self.state.active_daemon_index
        if 0 <= idx < len(self.state.daemons):
            return self.state.daemons[idx]
        return None
