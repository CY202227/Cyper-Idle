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
            "sp": 0, # 初始技能点
            "total_sp": 0, # 总技能点
            "stats": self.calculate_stats(daemon_id, level),
            "learned_skills": [], # 已解锁的技能 ID 列表
            "equipped_skills": [] # 战斗中挂载的技能 ID 列表 (最多 4 个)
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
            stats[stat] = base_val + (level - 1) * growth.get(stat, 0)
        
        # 应用被动技能加成 (后续实现)
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
                daemon["sp"] += 1 # 每升一级获得 1 SP
                daemon["total_sp"] += 1
                daemon["xp_to_next"] = self.calculate_xp_requirement(daemon["level"])
                daemon["stats"] = self.calculate_stats(daemon["id"], daemon["level"])
                leveled_up = True
            
            return leveled_up
        return False

    def learn_skill(self, daemon_index, skill_id):
        """学习/解锁一个技能"""
        if 0 <= daemon_index < len(self.state.daemons):
            daemon = self.state.daemons[daemon_index]
            defn = self.definitions[daemon["id"]]
            
            # 找到技能定义
            skill_defn = next((s for s in defn["skill_tree"] if s["id"] == skill_id), None)
            if not skill_defn: return False, "技能不存在"
            
            # 检查是否已学习
            if skill_id in daemon["learned_skills"]: return False, "技能已学习"
            
            # 检查 SP
            if daemon["sp"] < skill_defn["sp_cost"]: return False, "SP 不足"
            
            # 检查前提条件
            if skill_defn["req"] and skill_defn["req"] not in daemon["learned_skills"]:
                return False, f"需要先解锁 {skill_defn['req']}"
            
            # 扣除 SP 并学习
            daemon["sp"] -= skill_defn["sp_cost"]
            daemon["learned_skills"].append(skill_id)
            
            # 如果是主动技能，默认挂载（如果槽位够）
            if skill_defn["type"] == "active" and len(daemon["equipped_skills"]) < 4:
                daemon["equipped_skills"].append(skill_id)
            
            # 重新计算属性（以防有被动加成）
            daemon["stats"] = self.calculate_stats(daemon["id"], daemon["level"])
            return True, "学习成功"
        return False, "守护程序不存在"

    def equip_skill(self, daemon_index, skill_id):
        """挂载技能到战斗槽位"""
        if 0 <= daemon_index < len(self.state.daemons):
            daemon = self.state.daemons[daemon_index]
            if skill_id not in daemon["learned_skills"]: return False, "尚未学习该技能"
            if skill_id in daemon["equipped_skills"]: return False, "已挂载"
            if len(daemon["equipped_skills"]) >= 4: return False, "槽位已满"
            
            daemon["equipped_skills"].append(skill_id)
            return True, "挂载成功"
        return False, "失败"

    def get_active_daemon(self):
        """获取当前出战的守护程序"""
        if not self.state.daemons:
            return None
        idx = self.state.active_daemon_index
        if 0 <= idx < len(self.state.daemons):
            return self.state.daemons[idx]
        return None
