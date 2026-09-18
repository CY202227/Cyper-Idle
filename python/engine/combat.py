import json
import math
import random

from engine.power import calc_player_power

# 防火墙减伤曲线：低于拐点时用 value/(value+const)，
# 高于拐点后不再硬截断，而是平滑趋近 asymptote。
# 原来的 min(0.55, fw/(fw+45)) 在 fw>=55 后完全失效，
# 导致「堆防火墙」和 firewall_pct 类修饰词在中期以后毫无作用。
_PLAYER_FW = (45.0, 55.0, 0.75, 90.0)   # const, knee, asymptote, span
_ENEMY_FW = (40.0, 40.0, 0.70, 80.0)

# 敌人池权重衰减：低于池内最高档位的敌人按指数淡出。
#
# 历史：最初是 max(0, 1-(tier-tmin)*0.22)（无下限），tier 在 15 层封顶后
# 池逐字节冻结；改成 max(0.06, ...) 后解决了冻结，但**硬下限本身有缺陷**：
# ref（池内最高档）是无上界的，而 gap*0.22 一旦超过 (1-0.06)/0.22 ≈ 4.3，
# 该怪就永久钉死在下限。实测深度 27 时池总权重从 104.9 崩到 41.7、
# tmin<=4 的敌人全部落到 0.06，池的「档位梯度」被抹平 —— 于是新增 3 只
# 深层敌人后它们独占 44.9% 的份额，把 kernel_warden 从 11.9% 压到 4.6%。
# 指数衰减没有这个悬崖：它单调、永不归零、任意深度都保留梯度。
_POOL_DECAY = 0.30

# 护盾再生：回补「上一回合受到的伤害」的 35%，而不是最大生命的固定比例。
# 1.2%*max_hp 会随层数线性增长，而玩家输出与层数无关（战力只由 hacking_xp
# 的平方根决定），于是净 DPS 会在某层转负、敌人变得数学上不可击杀：
# 实测 quarantine_bulwark 在 26 层净 DPS=-0.6，35 层时 6/6 带此词条的敌人
# 都不可击杀（含 tier_min=5 的区域核心 kernel_sovereign，会卡死区域攻克）。
# 改成伤害比例后净 DPS 恒 >= 65% 玩家输出，永不出现僵局。
_SHIELD_REGEN_RATE = 0.35


def pool_decay(tier_min, ref_tier):
    """敌人在池内的权重衰减系数（指数，单调递减，永不为 0）。

    语义：衰减衡量这只怪比「池内最深档位」落后多少。

    **注意 ref_tier 在指数形式下是公共因子**：
        exp(-(ref - t) * k) == exp(-ref * k) * exp(t * k)
    所以 ref 取任何值都不改变池的成分，只等比缩放总权重，而 _pick_template
    会归一化。等价说法：池成分 = 按 tier_min 的静态权重 `w * exp(k * tier_min)`。
    参数保留只是让「越深的怪越常见」这层语义显式
    （旧公式带硬下限时 ref 是**必须**取池内最高档的，换 exp 后这个约束消失）。

    为什么用 exp 而不是 max(floor, 1-gap*k)：后者的下限是个悬崖，gap 一旦
    越过 (1-floor)/k，所有浅层怪就被压成同一个数、池的梯度消失，新增深层
    内容会一次性夺走全部份额。实测深度 27 时池总权重从 104.9 崩到 41.7、
    tmin<=4 全部落到 0.06，3 只新怪独占 44.9%，kernel_warden 从 11.9% 压到 4.6%。
    exp 在 gap 小的时候与原式几乎一致（gap=0 -> 1.00，gap=1 -> 0.74 vs 0.78，
    gap=2 -> 0.55 vs 0.56），在 gap 大时温和得多（gap=6 -> 0.17 vs 0.06），
    因此对「新增更深档位」不敏感。实测加入 3 只深层敌人后新怪份额 45% -> 25%，
    8/8 个采样格子的难度偏差都更接近基线。

    推论：池成分只在 pool_tier 跨过某个 tier_min（新怪解锁）时改变；一旦
    pool_tier >= 池内最高档位，成分就固定（层 27 之后逐字节相同）。
    这是档位制设计的固有性质，要靠**加内容**推进，不要靠调 ref。
    """
    gap = max(0, int(ref_tier) - int(tier_min))
    return math.exp(-gap * _POOL_DECAY)


def mitigation(value, const, knee, asymptote, span):
    """防火墙减伤率：拐点前沿用 value/(value+const)，拐点后平滑趋近 asymptote。"""
    value = max(0.0, float(value))
    if value <= knee:
        return value / (value + const)
    base = knee / (knee + const)
    over = value - knee
    return base + (asymptote - base) * over / (over + span)


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
        # 本回合敌人累计受到的伤害，供 shield_regen 结算（每回合清空）
        self._enemy_damage_taken = 0.0
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

    def _region_challenge_effects(self):
        """当前区域挑战修饰词的效果（含挑战产出加成）。

        与地牢修饰词走同一条 meff 通道：这样 enemy_* 这类敌方侧键才会生效。
        不要把它并进 _effects()/aggregate_effects()——那条通道只通向玩家侧。

        挑战同样吃 modifier_resist，与地牢修饰词保持一致；否则同一个修饰词
        作为地牢修饰词时被抗性削弱、作为挑战时却不受影响。
        产出加成（loot_pct / xp_bonus_pct 正值）是增益项，不会被缩放。
        """
        if self.network_mgr is None:
            return {}
        try:
            eff = dict(self.network_mgr.challenge_effects())
        except Exception:
            return {}
        if self.dungeon is not None:
            eff = self.dungeon.scale_hazards(eff)
        return eff

    def _layer_effects(self):
        """本层生效的全部修饰词效果 = 地牢本层修饰词 + 当前区域挑战修饰词。"""
        effects = {}
        if self.dungeon is not None:
            for k, v in self.dungeon.modifier_effects().items():
                effects[k] = effects.get(k, 0) + float(v)
        for k, v in self._region_challenge_effects().items():
            effects[k] = effects.get(k, 0) + float(v)
        return effects

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
        # 本层地牢修饰词与区域挑战修饰词中的我方修正
        # （player_intrusion_pct / player_firewall_pct 等）必须并入玩家侧效果，
        # 否则这些键永远不会生效。
        effects = dict(self._effects())
        for k, v in self._layer_effects().items():
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

    def _pool_candidates(self, tier, allowed):
        """筛出当前池威胁阶下可用的敌人：排除 boss、未解锁档位与区域外敌人。"""
        out = []
        for eid, defn in self.enemy_defs.items():
            if defn.get("boss"):
                continue
            if allowed is not None and eid not in allowed:
                continue
            if defn.get("tier_min", 0) > tier:
                continue
            out.append(defn)
        return out

    def _pick_template(self, tier, force_id=None):
        if force_id and force_id in self.enemy_defs:
            return self.enemy_defs[force_id]
        allowed = None
        if self.network_mgr is not None:
            try:
                allowed = self.network_mgr.enemy_pool()
            except Exception:
                allowed = None
        cands = self._pool_candidates(tier, allowed)
        if not cands:
            # 区域过滤后没有可用敌人时，退回到全表，避免刷不出怪
            cands = self._pool_candidates(tier, None)
        if not cands:
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
        # 以池内最高档位为衰减基准，保证「越深的怪越常见」在任意深度都成立
        best = max(int(d.get("tier_min", 0)) for d in cands)
        pool = [
            (d, float(d.get("weight", 1)) * pool_decay(d.get("tier_min", 0), best))
            for d in cands
        ]
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
        # 敌人池的威胁阶与数值威胁阶必须分开：
        #   tier      -> 敌人数值缩放，绑在 threat_tier / 区域基线上，封顶 5；
        #   pool_tier -> 敌人池成分，必须随层数继续推进，不封顶。
        # 两者共用一个变量时，min(5, level//3) 会让 15 层之后的池彻底冻结，
        # 而且 tier_min=6 的 null_crawler 永远刷不出来（6 > 5 被直接排除）。
        pool_tier = max(tier, level // 3)
        if is_boss:
            force_id = self._region_boss_id() or "core_guardian"
            is_boss = True
        elif is_elite:
            force_id = force_id or "elite"
        elif enemy_type and enemy_type in self.enemy_defs:
            force_id = enemy_type

        defn = self._pick_template(pool_tier, force_id=force_id)
        self.vs_boss = bool(defn.get("boss") or is_boss)
        power = self.get_power(vs_boss=self.vs_boss)
        self.player_power = power
        self.status = "fighting"
        self.turn = 0
        self._enemy_damage_taken = 0.0

        # 地牢修饰词（若有）
        meff = {}
        if self.dungeon is not None:
            meff = self.dungeon.modifier_effects()
        # 区域挑战修饰词与地牢修饰词同通道生效（含敌方侧键）
        for k, v in self._region_challenge_effects().items():
            meff[k] = meff.get(k, 0) + float(v)

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
        # all_speed_pct 是「所有单位」：敌方这一半在此生效，
        # 玩家那一半在 power.py 的 calc_player_power 里生效。
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
            "pool_tier": pool_tier,
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

        # 词条：护盾再生——回补上一回合受到伤害的 35%
        # （按伤害而非最大生命，见文件头 _SHIELD_REGEN_RATE 的说明）
        if "shield_regen" in self.enemy.get("special", []):
            if self.enemy_hp > 0 and self._enemy_damage_taken > 0:
                heal = self._enemy_damage_taken * _SHIELD_REGEN_RATE
                self.enemy_hp = min(self.enemy["max_hp"], self.enemy_hp + heal)
            self._enemy_damage_taken = 0.0

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
        mitigate = mitigation(e_fw, *_ENEMY_FW)
        variance = 0.85 + random.random() * 0.3
        energy = self.state.resources.get("energy", 0)
        if energy < 20:
            variance *= 0.85
        damage = power["intrusion"] * (1.0 - mitigate) * variance
        hp_before = self.enemy_hp
        self.enemy_hp = max(0.0, self.enemy_hp - damage)
        # 只累计实际打掉的血量，避免溢出伤害被 shield_regen 当成治疗量
        self._enemy_damage_taken += hp_before - self.enemy_hp
        self.log.append(
            self._t(
                "combat_player_hit",
                dmg=int(damage),
                hp=int(self.enemy_hp),
            )
        )
        reflect = float(self.enemy.get("reflect", 0))
        if reflect > 0 and damage > 0:
            # 反伤是「玩家受到的伤害」，必须和敌人普攻走同一条减伤通道。
            # 原来直接扣 player_hp、完全绕过防火墙，有两个后果：
            #   1) 唯一的防御属性对它无效，没有 counter-play；
            #   2) 整场反伤总量 = reflect × 敌人最大生命 —— 玩家输出 D 在
            #      「回合数 T = H/D」与「每回合 r*D」里约掉，与 D 无关，
            #      所以它是按敌人血量计价的固定税，∝ 层数^2，而玩家生命只
            #      随 sqrt(XP) 增长，深层必然反超。
            # 实测：17/26 只怪带反射；去掉反射后层 30 胜率 +48~63pt
            # （轨道中继 L25 20.0% -> 83.3%），是深层难度的最大单一来源。
            # 接入减伤后解析税从「L45 = 158% 玩家生命（单独就能致死）」
            # 降到 57.4%，各等级全部 < 100%，「单独致死」被消除。
            # 注意：这不等于它是一个有效的「构筑区分器」——firewall 的等级
            # 基底（5+level*2）在 L25 左右已越过减伤曲线的拐点，可达区间在
            # 深层塌缩到 ~0.06（L45 满堆防御 vs 零防御的反伤税只差 4~5pt）。
            # 反伤仍带「按敌人血量计价的固定税」性质（L15 46% -> L60 65%
            # 玩家生命）；若要它真正惩罚高爆发，需改为按单次伤害占比计价。
            back = damage * reflect * (1.0 - mitigation(power["firewall"], *_PLAYER_FW))
            self.player_hp = max(0.0, self.player_hp - back)
            self.log.append(self._t("combat_reflect", dmg=int(back)))

    def _enemy_strike(self, power):
        fw = power["firewall"]
        mitigate = mitigation(fw, *_PLAYER_FW)
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
            # 区域挑战修饰词同样影响掉落/经验（含挑战产出加成）
            for k, v in self._region_challenge_effects().items():
                meff[k] = meff.get(k, 0) + float(v)
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
