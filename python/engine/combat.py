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

    def set_i18n(self, i18n):
        self.i18n = i18n

    def set_protocol_manager(self, protocol_mgr):
        self.protocol_mgr = protocol_mgr

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
        return calc_player_power(
            self.state,
            self._buildings(),
            protocol_effects=self._effects(),
            vs_boss=vs_boss,
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
        for eid, defn in self.enemy_defs.items():
            if defn.get("boss"):
                continue
            if defn.get("tier_min", 0) <= tier:
                pool.append((defn, defn.get("weight", 1)))
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
        roll = random.random() * total
        acc = 0
        for defn, w in pool:
            acc += w
            if roll <= acc:
                return defn
        return pool[-1][0]

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
        )
        if is_boss:
            force_id = "core_guardian"
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

        label = self._enemy_label(defn)
        self.enemy = {
            "id": defn.get("id", "sentry"),
            "type": defn.get("id", enemy_type or "sentry"),
            "label": label,
            "level": level,
            "tier": tier,
            "boss": self.vs_boss,
            "max_hp": base_hp * float(defn.get("hp_mult", 1)),
            "intrusion": base_intrusion * float(defn.get("intrusion_mult", 1)),
            "firewall": base_firewall * float(defn.get("firewall_mult", 1)),
            "speed": base_speed * float(defn.get("speed_mult", 1)),
            "reflect": float(defn.get("reflect", 0)),
            "loot_mult": dict(defn.get("loot", {})),
        }
        self.enemy_hp = float(self.enemy["max_hp"])
        self.player_max_hp = float(power["integrity"])
        self.player_hp = self.player_max_hp
        self.last_rewards = {}
        link_key = "combat_link_boss" if self.vs_boss else "combat_link"
        self.log = [self._t(link_key, enemy=label, level=level)]
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

        p_spd = power["speed"]
        e_spd = self.enemy["speed"]
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

    def end_combat(self, victory):
        level = self.enemy["level"] if self.enemy else 1
        was_boss = bool(self.enemy and self.enemy.get("boss"))
        loot_m = (self.enemy or {}).get("loot_mult", {})
        effects = self._effects()
        loot_pct = 1.0 + float(effects.get("loot_pct", 0))

        if victory:
            self.log.append(self._t("combat_win"))
            credits = int((18 + level * 12) * loot_m.get("credits", 1) * loot_pct)
            scraps = max(
                1, int((1 + level // 2) * loot_m.get("data_scraps", 1) * loot_pct)
            )
            compute = max(
                1, int((1 + level // 3) * loot_m.get("compute", 1) * loot_pct)
            )
            hxp = int((10 + level * 4) * loot_m.get("hacking_xp", 1) * loot_pct)
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
