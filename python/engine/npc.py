import random

class NPCManager:
    def __init__(self, state, story_manager, i18n):
        self.state = state
        self.story = story_manager
        self.i18n = i18n
        self.npcs = {
            "K0_Echo": {
                "type": "important",
                "color": "#00eeff",
                "prefix": "[K0_Echo]",
                "bg_alpha": "0.1"
            },
            "System_Admin": {
                "type": "hostile",
                "color": "#ff003c",
                "prefix": "[SYS_ADMIN]",
                "bg_alpha": "0.15"
            },
            "Merchant_Bot": {
                "type": "neutral",
                "color": "#ffcc00",
                "prefix": "[MERCHANT]",
                "bg_alpha": "0.08"
            },
            "Ghost_Runner": {
                "type": "friendly",
                "color": "#00ff41",
                "prefix": "[GHOST]",
                "bg_alpha": "0.05"
            }
        }

    def get_npc_style(self, text):
        """根据文本前缀获取 NPC 样式"""
        for npc_id, config in self.npcs.items():
            if config["prefix"] in text:
                return config
        return None

    def trigger_random_chatter(self, pool, chance=0.1):
        """尝试触发随机闲聊"""
        if self.state.current_story_node != "energy_stable":
            return False
            
        if random.random() < chance:
            self.state.current_story_node = random.choice(pool)
            return True
        return False

    def check_reaction(self, event_type, context=None):
        """根据游戏事件触发 NPC 反应"""
        if self.state.current_story_node != "energy_stable":
            return False

        # 这里可以根据 event_type 扩展更多 NPC 的逻辑
        if event_type == "build_complete":
            if random.random() < 0.3:
                self.state.current_story_node = "echo_react_build"
                return True
        elif event_type == "dungeon_return":
            if random.random() < 0.3:
                self.state.current_story_node = "echo_react_dungeon"
                return True
        return False
