import random

class CombatEngine:
    def __init__(self, state, daemon_mgr, update_ui_callback):
        self.state = state
        self.daemon_mgr = daemon_mgr
        self.update_ui_callback = update_ui_callback
        
        self.is_active = False
        self.enemy = None
        self.player_bw = 100
        self.player_hp = 100
        self.enemy_hp = 100
        self.enemy_intent = None
        self.turn_count = 0
        self.log = []

    def start_combat(self, enemy_type, level):
        self.is_active = True
        self.turn_count = 1
        self.log = [f"--- 遭遇安全程序: {enemy_type} (Lv.{level}) ---"]
        
        # 初始化敌人
        self.enemy = {
            "type": enemy_type,
            "level": level,
            "hp": 50 + level * 20,
            "max_hp": 50 + level * 20,
            "intrusion": 5 + level * 3,
            "speed": 5 + level * 2
        }
        self.enemy_hp = self.enemy["max_hp"]
        
        # 初始化玩家状态
        active_daemon = self.daemon_mgr.get_active_daemon()
        if active_daemon:
            self.player_hp = active_daemon["stats"]["stability"]
            self.player_max_hp = active_daemon["stats"]["stability"]
        else:
            self.player_hp = 50
            self.player_max_hp = 50
            
        self.player_bw = 100 # 带宽初始 100%
        self.generate_enemy_intent()
        
    def generate_enemy_intent(self):
        """预知机制：生成敌人下一回合的动作"""
        actions = [
            {"id": "attack", "name": "攻击", "power": 1.0, "chance": 0.8},
            {"id": "heavy_attack", "name": "强力攻击", "power": 1.5, "chance": 0.6},
            {"id": "scan", "name": "系统扫描", "power": 0, "chance": 1.0}
        ]
        self.enemy_intent = random.choice(actions)

    def execute_player_action(self, action_id):
        if not self.is_active: return
        
        active_daemon = self.daemon_mgr.get_active_daemon()
        if not active_daemon: return

        msg = ""
        # 1. 玩家行动消耗与效果
        if action_id == "attack":
            cost = 20
            if self.player_bw >= cost:
                damage = active_daemon["stats"]["intrusion"]
                self.enemy_hp -= damage
                self.player_bw -= cost
                msg = f"> 你执行了 [基础攻击]，造成 {int(damage)} 点伤害。"
            else:
                msg = "> 带宽不足！强制执行 [重置]，本回合无法行动。"
                self.player_bw = min(100, self.player_bw + 40)
        
        elif action_id == "defend":
            self.player_bw = min(100, self.player_bw + 20)
            msg = "> 你执行了 [防御]，带宽恢复 20%，本回合受损减半。"
            
        elif action_id == "reset":
            self.player_bw = min(100, self.player_bw + 50)
            msg = "> 你执行了 [系统重置]，带宽恢复 50%。"
        
        else:
            # 处理自定义技能 (从职业定义中获取技能数据)
            defn = self.daemon_mgr.definitions[active_daemon["id"]]
            skill = next((s for s in defn["skill_tree"] if s["id"] == action_id), None)
            
            if skill:
                cost = skill.get("bw_cost", 0)
                if self.player_bw >= cost:
                    damage = active_daemon["stats"]["intrusion"] * skill.get("power", 1.0)
                    self.enemy_hp -= damage
                    self.player_bw -= cost
                    msg = f"> 你释放了 [{skill['name']}]，造成 {int(damage)} 点伤害。"
                    
                    # 特殊效果处理
                    if action_id == "kernel_panic":
                        self.player_bw = 0
                else:
                    msg = f"> 带宽不足以释放 [{skill['name']}]！"
                    return # 不消耗回合

        self.log.append(msg)
        
        # 2. 检查敌人是否死亡
        if self.enemy_hp <= 0:
            self.end_combat(True)
            return

        # 3. 敌人行动
        self.execute_enemy_action(action_id == "defend")
        
        # 4. 检查玩家是否死亡
        if self.player_hp <= 0:
            self.end_combat(False)
            return

        # 5. 回合结束准备
        self.turn_count += 1
        self.generate_enemy_intent()
        self.update_ui_callback()

    def execute_enemy_action(self, player_defending):
        intent = self.enemy_intent
        msg = f"> 敌人执行了 [{intent['name']}]。"
        
        if intent["id"] in ["attack", "heavy_attack"]:
            damage = self.enemy["intrusion"] * intent["power"]
            if player_defending:
                damage /= 2
            
            # 命中判定
            if random.random() < intent["chance"]:
                self.player_hp -= damage
                msg += f" 命中！造成 {int(damage)} 点伤害。"
            else:
                msg += " 未命中。"
        elif intent["id"] == "scan":
            msg += " 你的系统漏洞被标记，敌人下次攻击更准。"
            
        self.log.append(msg)

    def end_combat(self, victory):
        self.is_active = False
        if victory:
            self.log.append("--- 战斗胜利！系统威胁已清除 ---")
            # 结算奖励
            xp_gain = 20 + self.enemy["level"] * 5
            leveled_up = self.daemon_mgr.add_xp(self.state.active_daemon_index, xp_gain)
            
            # 尝试更新任务进度
            try:
                import sys
                main_module = sys.modules['__main__']
                if hasattr(main_module, 'quest_mgr'):
                    main_module.quest_mgr.update_progress("combat")
            except:
                pass
            
            # 捕获逻辑
            if random.random() < 0.15:
                new_id = random.choice(list(self.daemon_mgr.definitions.keys()))
                new_daemon = self.daemon_mgr.create_daemon(new_id, level=self.enemy["level"])
                self.state.daemons.append(new_daemon)
        else:
            self.log.append("--- 战斗失败！系统崩溃，强制断开 ---")
            self.state.resources["energy"] = max(0, self.state.resources["energy"] - 30)
        
        # 触发一次 UI 更新以显示最终日志，然后在 main.py 的逻辑中会自动因为 is_active=False 切换回地图
        self.update_ui_callback()
