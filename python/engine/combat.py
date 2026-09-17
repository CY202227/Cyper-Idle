import json
import random

from engine.power import calc_player_power


class CombatEngine:
    """全自动网络攻防：敌人表 + 威胁阶 + 可观看互打。"""

    def __init__(
        self,
        state,
        manager,
        update_ui_callback=None,
        mission_mgr=None,
        i18n=None,
        protocol_mgr=None,
    ):
        self.state = state
        self.manager = manager
        self.update_ui_callback = update_ui_callback
        self.mission_mgr = mission_mgr
        self.i18n = i18n
        self.protocol_mgr = protocol_mgr
        self.network_mgr = None
        self.enemy_defs = {}

        self.status = "idle"
        self.enemy = None
        self.enemy_hp = 0.0
        self.player_hp = 0.0
        self.player_max_hp = 100.0
        self.player_power = {}
        self.turn = 0
        self.log = []
        self.cooldown_remaining = 0.0
        self.pending_dungeon_fight = False
        self._pending_level = 1
        self._pending_boss = False
        self._pending_floor_elite = False
        self.last_rewards = {}
        self.vs_boss = False
        self.win_streak = 0
        self.dungeon = None
        # 待展示的战斗播报（main 消费后清空），例如区域攻克
        self.pending_notices = []

    def set_dungeon(self, dungeon):
        self.dungeon = dungeon

    def set_i18n(self, i18n):
        self.i18n = i18n

    def set_protocol_manager(self, protocol_mgr):
        self.protocol_mgr = protocol_mgr

    def set_network_manager(self, network_mgr):
        self.network_mgr = network_mgr

    def load_enemies(self, enemies_json):
        self.enemy_defs = json.loads(enemies_json)

    def _t(self, key, **kwargs):
        if self.i18n:
            return self.i18n.get(key, key, **kwargs)
        return key

    def _effects(self):
        if self.protocol_mgr:
            return self.protocol_mgr.aggregate_effects()
        return {}

    def _region_threat_floor(self):
        """当前区域的威胁阶下限（区域越深，起步越硬）。"""
        if self.network_mgr is None:
            return 0
        try:
            return int(self.network_mgr.threat_offset())
        except Exception:
            return 0

    @property
    def is_active(self):
        return self.status == "fighting"

    def set_mission_manager(self, mission_mgr):
        self.mission_mgr = mission_mgr

    def _buildings(self):
        return self.manager.definitions.get("buildings", {})

    def get_power(self, vs_boss=None):
        if vs_boss is None:
            vs_boss = self.vs_boss
        syn = {}
        if self.manager is not None and hasattr(self.manager, "synergy_effects"):
            syn = self.manager.synergy_effects()
        # 本层地牢修饰词中的我方修正（player_intrusion_pct / player_firewall_pct
        # 等）必须并入玩家侧效果，否则这些键永远不会生效。
        effects = dict(self._effects())
        if self.dungeon is not None:
            for k, v in self.dungeon.modifier_effects().items():
                effects[k] = effects.get(k, 0) + v
        return calc_player_power(
            self.state,
            self._buildings(),
            protocol_effects=effects,
            vs_boss=vs_boss,
            synergy_effects=syn,
        )

    def can_farm(self):
        return bool(getattr(self.state, "auto_combat", False))

    def queue_dungeon_fight(self, level, floor_elite=False):
        self.pending_dungeon_fight = True
        self._pending_level = level
        self._pending_boss = False
        self._pending_floor_elite = floor_elite

    def queue_boss_fight(self, level=None):
        self.pending_dungeon_fight = True
        self._pending_level = level or max(
            15, getattr(self.state, "max_dungeon_level", 1)
        )
        self._pending_boss = True
        self._pending_floor_elite = False

    def _pick_template(self, tier, force_id=None):
        if force_id and force_id in self.enemy_defs:
            return self.enemy_defs[force_id]
        pool = []
        allowed = None
        if self.network_mgr is not None:
            try:
                allowed = self.network_mgr.enemy_pool()
            except Exception:
                allowed = None
        for eid, defn in self.enemy_defs.items():
            if defn.get("boss"):
                continue
            if allowed is not None and eid not in allowed:
                continue
            tmin = defn.get("tier_min", 0)
            if tmin > tier:
                continue
            # 权重衰减：威胁阶远超怪物档位时，低级怪淡出
            weight = float(defn.get("weight", 1))
            decay = max(0.0, 1.0 - (tier - tmin) * 0.22)
            pool.append((defn, weight * decay))
        if not pool:
            # 区域过滤后没有可用敌人时，退回到全表，避免刷不出怪
            for eid, defn in self.enemy_defs.items():
                if defn.get("boss") or defn.get("tier_min", 0) > tier:
                    continue
                weight = float(defn.get("weight", 1))
                decay = max(0.0, 1.0 - (tier - defn.get("tier_min", 0)) * 0.22)
                pool.append((defn, weight * decay))
        if not pool:
            return self.enemy_defs.get("sentry") or {
                "id": "sentry",
                "name": "Sentry",
                "hp_mult": 1,
                "intrusion_mult": 1,
                "firewall_mult": 1,
                "speed_mult": 1,
                "reflect": 0,
                "loot": {},
            }
        total = sum(w for _, w in pool)
        if total <= 0:
            pool = [(d, 1.0) for d, _ in pool]
            total = float(len(pool))
        roll = random.random() * total
        acc = 0
        for defn, w in pool:
            acc += w
            if roll <= acc:
                return defn
        return pool[-1][0]

    def _region_boss_id(self):
        """当前区域的区域核心 id（回退到通用核心守卫）。"""
        if self.network_mgr is None:
            return None
        try:
            return self.network_mgr.boss_id()
        except Exception:
            return None

    def _region_id(self):
        if self.network_mgr is None:
            return None
        try:
            return self.network_mgr.current_region()
        except Exception:
            return None

    def _enemy_label(self, defn):
        lang = getattr(self.state, "language", "zh")
        if lang == "en" and defn.get("name_en"):
            return defn["name_en"]
        return defn.get("name") or defn.get("id", "enemy")

    def start_combat(
        self,
        enemy_type=None,
        level=1,
        force_id=None,
        is_boss=False,
        is_elite=False,
    ):
        tier = max(
            int(getattr(self.state, "threat_tier", 0)),
            min(5, level // 3),
            self._region_threat_floor(),
        )
        if is_boss:
            force_id = self._region_boss_id() or "core_guardian"
            is_boss = True
        elif is_elite:
            force_id = force_id or "elite"
        elif enemy_type and enemy_type in self.enemy_defs:
            force_id = enemy_type

        defn = self._pick_template(tier, force_id=force_id)
        self.vs_boss = bool(defn.get("boss") or is_boss)
        power = self.get_power(vs_boss=self.vs_boss)
        self.player_power = power
        self.status = "fighting"
        self.turn = 0

        # 地牢修饰词（若有）
        meff = {}
        if self.dungeon is not None:
            meff = self.dungeon.modifier_effects()

        # 拉长场次：常规约 8–20 tick，Boss 约 45–90 tick
        scale = 1.0 + tier * 0.15 + max(0, level - 1) * 0.06
        if self.vs_boss:
            scale *= 1.5
        base_hp = (95 + level * 28) * scale
        base_intrusion = (4.2 + level * 1.7) * (1 + tier * 0.05)
        base_firewall = (4 + level * 1.5) * (1 + tier * 0.05)
        base_speed = 6 + level * 1.0 + tier * 0.3
        if self.vs_boss:
            base_intrusion *= 0.85
            base_hp *= 1.25

        # 修饰词：敌方三维调整
        base_hp *= 1.0 + float(meff.get("enemy_hp_pct", 0))
        base_intrusion *= 1.0 + float(meff.get("enemy_intrusion_pct", 0))
        base_firewall *= 1.0 + float(meff.get("enemy_firewall_pct", 0))
        base_speed *= 1.0 + float(meff.get("all_speed_pct", 0)) + float(
            meff.get("enemy_speed_pct", 0)
        )

        label = self._enemy_label(defn)
        self.enemy = {
            "id": defn.get("id", "sentry"),
            "type": defn.get("id", enemy_type or "sentry"),
            "label": label,
            "level": level,
            "tier": tier,
            "boss": self.vs_boss,
            "region": self._region_id(),
            "max_hp": base_hp * float(defn.get("hp_mult", 1)),
            "intrusion": base_intrusion * float(defn.get("intrusion_mult", 1)),
            "firewall": base_firewall * float(defn.get("firewall_mult", 1)),
            "speed": base_speed * float(defn.get("speed_mult", 1)),
            "reflect": float(defn.get("reflect", 0)),
            "special": list(defn.get("special", [])),
            "loot_mult": dict(defn.get("loot", {})),
        }
        self.enemy_hp = float(self.enemy["max_hp"])
        self.player_max_hp = float(power["integrity"])
        self.player_hp = self.player_max_hp
        self.last_rewards = {}
        link_key = "combat_link_boss" if self.vs_boss else "combat_link"
        self.log = [self._t(link_key, enemy=label, level=level)]
        if defn.get("special"):
            # 词条预告：让玩家知道这怪有什么机制
            for sp in defn["special"]:
                self.log.append(self._t(f"enemy_special_{sp}"))
        return True

    def start_boss_raid(self):
        if self.status == "fighting":
            return False
        level = max(
            12,
            getattr(self.state, "max_dungeon_level", 1),
            max(1, self.state.hacking_level),
        )
        return self.start_combat(level=level, is_boss=True)

    def tick(self, delta_time, farm_level=1):
        if self.cooldown_remaining > 0:
            self.cooldown_remaining = max(0.0, self.cooldown_remaining - delta_time)
            if self.cooldown_remaining <= 0 and self.status == "cooldown":
                self.status = "idle"
            return

        if self.pending_dungeon_fight and self.status == "idle":
            level = self._pending_level
            is_boss = self._pending_boss
            is_elite = self._pending_floor_elite
            self.pending_dungeon_fight = False
            self._pending_boss = False
            self._pending_floor_elite = False
            self.start_combat(level=level, is_boss=is_boss, is_elite=is_elite)
            return

        if self.status == "idle" and self.can_farm():
            tier = int(getattr(self.state, "threat_tier", 0))
            level = max(farm_level, tier + 1)
            self.start_combat(level=level)
            return

        if self.status == "fighting":
            self.pulse()

    def pulse(self):
        if not self.enemy:
            self.status = "idle"
            return

        power = self.get_power()
        self.player_power = power
        self.turn += 1

        # 词条：护盾再生——每回合回 1.2% 最大生命
        if "shield_regen" in self.enemy.get("special", []):
            if self.enemy_hp > 0 and self.enemy_hp < self.enemy["max_hp"]:
                heal = self.enemy["max_hp"] * 0.012
                self.enemy_hp = min(self.enemy["max_hp"], self.enemy_hp + heal)

        # 词条：超频——血量低于 30% 时速度视为 +60%
        e_spd = self.enemy["speed"]
        if "overclock" in self.enemy.get("special", []):
            if self.enemy_hp < self.enemy["max_hp"] * 0.30:
                e_spd *= 1.6

        p_spd = power["speed"]
        player_actions = 2 if p_spd > e_spd * 1.25 else 1
        enemy_actions = 2 if e_spd > p_spd * 1.25 else 1
        order = ["player", "enemy"] if p_spd >= e_spd else ["enemy", "player"]

        for side in order:
            if self.player_hp <= 0 or self.enemy_hp <= 0:
                break
            if side == "player":
                for _ in range(player_actions):
                    if self.enemy_hp <= 0:
                        break
                    self._player_strike(power)
            else:
                for _ in range(enemy_actions):
                    if self.player_hp <= 0:
                        break
                    self._enemy_strike(power)

        self.log = self.log[-20:]

        if self.enemy_hp <= 0:
            self.end_combat(True)
        elif self.player_hp <= 0:
            self.end_combat(False)

    def _player_strike(self, power):
        e_fw = self.enemy.get("firewall", 0)
        mitigate = min(0.5, e_fw / (e_fw + 40))
        variance = 0.85 + random.random() * 0.3
        energy = self.state.resources.get("energy", 0)
        if energy < 20:
            variance *= 0.85
        damage = power["intrusion"] * (1.0 - mitigate) * variance
        self.enemy_hp = max(0.0, self.enemy_hp - damage)
        self.log.append(
            self._t(
                "combat_player_hit",
                dmg=int(damage),
                hp=int(self.enemy_hp),
            )
        )
        reflect = float(self.enemy.get("reflect", 0))
        if reflect > 0 and damage > 0:
            back = damage * reflect
            self.player_hp = max(0.0, self.player_hp - back)
            self.log.append(self._t("combat_reflect", dmg=int(back)))

    def _enemy_strike(self, power):
        fw = power["firewall"]
        mitigate = min(0.55, fw / (fw + 45))
        variance = 0.9 + random.random() * 0.25
        damage = self.enemy["intrusion"] * (1.0 - mitigate) * variance
        if self.vs_boss or self.enemy.get("boss"):
            damage *= 0.4
        if random.random() < min(0.25, fw / 200):
            self.log.append(self._t("combat_block"))
            return
        self.player_hp = max(0.0, self.player_hp - damage)
        self.log.append(
            self._t(
                "combat_enemy_hit",
                dmg=int(damage),
                hp=int(self.player_hp),
            )
        )
        # 词条：汲取——造成伤害的 30% 转为自身治疗
        if "leech" in self.enemy.get("special", []) and damage > 0:
            heal = damage * 0.30
            self.enemy_hp = min(self.enemy["max_hp"], self.enemy_hp + heal)
            self.log.append(self._t("enemy_leech", heal=int(heal)))

    def _handle_region_boss(self):
        """击败区域核心：首次攻克时记录并播报永久加成。"""
        if self.network_mgr is None:
            return
        try:
            bonus = self.network_mgr.on_region_boss_defeated(
                (self.enemy or {}).get("id")
            )
        except Exception:
            bonus = None
        if bonus is None:
            return
        rid = (self.enemy or {}).get("region") or ""
        self.log.append(self._t("region_cleared_log"))
        self.pending_notices.append(
            self._t("region_cleared_notice", name=self.network_mgr.name(rid))
        )

    def end_combat(self, victory):
        level = self.enemy["level"] if self.enemy else 1
        was_boss = bool(self.enemy and self.enemy.get("boss"))
        loot_m = (self.enemy or {}).get("loot_mult", {})
        effects = self._effects()
        loot_pct = 1.0 + float(effects.get("loot_pct", 0))

        if victory:
            self.win_streak += 1
            self.log.append(self._t("combat_win"))
            # 连击奖励：快速连续胜利最多 +30% 掉落
            streak_mult = 1.0 + min(0.30, (self.win_streak - 1) * 0.02)
            # 高层压制：等级差加成，鼓励打高级怪
            overkill = max(0, level - max(1, self.state.hacking_level))
            overkill_mult = 1.0 + min(0.50, overkill * 0.05)
            # 地牢修饰词：本层掉落/经验加成
            meff = {}
            if self.dungeon is not None:
                meff = self.dungeon.modifier_effects()
            loot_m_all = (
                loot_pct
                * streak_mult
                * overkill_mult
                * (1.0 + float(meff.get("loot_pct", 0)))
            )
            credits = int(
                (18 + level * 12) * loot_m.get("credits", 1) * loot_m_all
            )
            scraps = max(
                1,
                int((1 + level // 2) * loot_m.get("data_scraps", 1) * loot_m_all),
            )
            compute = max(
                1,
                int((1 + level // 3) * loot_m.get("compute", 1) * loot_m_all),
            )
            # 经验曲线：高等级击杀经验小幅加速 + 修饰词/区域经验加成
            hxp = int(
                (10 + level * 4 + (level * level) // 40)
                * loot_m.get("hacking_xp", 1)
                * loot_m_all
                * (1.0 + float(meff.get("xp_bonus_pct", 0)))
                * (1.0 + float(effects.get("xp_bonus_pct", 0)))
            )
            if was_boss:
                credits = int(credits * 1.5)
                hxp = int(hxp * 1.5)

            self.state.resources["credits"] = (
                self.state.resources.get("credits", 0) + credits
            )
            self.state.resources["data_scraps"] = (
                self.state.resources.get("data_scraps", 0) + scraps
            )
            self.state.resources["compute"] = (
                self.state.resources.get("compute", 0) + compute
            )
            self.state.resources["hacking_xp"] = (
                self.state.resources.get("hacking_xp", 0) + hxp
            )
            self.last_rewards = {
                "credits": credits,
                "data_scraps": scraps,
                "compute": compute,
                "hacking_xp": hxp,
            }
            self.log.append(
                self._t(
                    "combat_loot",
                    credits=credits,
                    scraps=scraps,
                    compute=compute,
                    hxp=hxp,
                )
            )
            self.state.combat_wins = getattr(self.state, "combat_wins", 0) + 1
            if was_boss:
                self.state.boss_kills = getattr(self.state, "boss_kills", 0) + 1
                self.log.append(self._t("combat_boss_down"))
                self._handle_region_boss()
            # 层事件封锁在任意胜利后解除
            if getattr(self.state, "pending_floor_boss", False):
                self.state.pending_floor_boss = False
            try:
                import sys

                main_module = sys.modules.get("__main__")
                if main_module and hasattr(main_module, "quest_mgr"):
                    main_module.quest_mgr.update_progress("combat")
            except Exception:
                pass

            cd = 0.8
            cd *= 1.0 + float(effects.get("combat_cooldown_pct", 0))
            self.cooldown_remaining = max(0.3, cd)
        else:
            self.win_streak = 0
            self.log.append(self._t("combat_lose"))
            penalty = 12
            self.state.resources["energy"] = max(
                0, self.state.resources.get("energy", 0) - penalty
            )
            self.log.append(self._t("combat_energy_loss", penalty=penalty))
            self.cooldown_remaining = 4.0
            if was_boss:
                # Boss 失败不清 pending，可再打
                pass

        self.enemy = None
        self.vs_boss = False
        self.status = "cooldown"
        if self.update_ui_callback:
            self.update_ui_callback()
