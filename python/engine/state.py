import json


class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.resources = {
            "energy": 100,
            "data_scraps": 0,
            "credits": 0,
            "compute": 0,
            "hacking_xp": 0,
        }
        self.storage_caps = {
            "energy": 500,
            "data_scraps": 500,
            "credits": 5000,
            "compute": 200,
        }
        self.buildings = {}
        self.artifacts = []
        self.active_quests = []
        self.completed_quests = []
        self.story_flags = []
        self.current_story_node = "start"
        self.seed = None
        self.tick_count = 0
        self.last_update = 0
        self.unlocked_actions = ["gather_energy"]
        self.language = "zh"
        self.auto_combat = False
        self.auto_explore = False
        self.missions = []
        self.combat_wins = 0
        self.milestones_done = []
        self.prestige = 0
        self.threat_tier = 0
        self.protocols = []
        self.protocols_unlocked = False
        self.boss_available = False
        self.boss_kills = 0
        self.pending_floor_boss = False
        self.guide_shown = False
        self.max_dungeon_level = 1
        self.active_floor_modifier = None
        # 架构范式 + Trait 构筑（跨转生保留）
        self.architecture = None
        self.architecture_chosen = False
        self.traits = []
        # 玩家手动锁定、转生后必定保留的持久协议（受槽位上限约束）
        self.protocol_keep = []
        # 内核跃迁（第 2 层转生）：永久货币与永久升级等级
        self.arch_points = 0
        self.ascension_upgrades = {}
        self.ascension_count = 0
        # 网络区域（第 3 层）：当前所在区域、已攻克区域与各区域最深记录
        self.network_region = "local"
        self.regions_cleared = []
        self.region_depths = {}
        self.migrations = 0

    @property
    def hacking_level(self):
        import math
        return math.floor(math.sqrt(self.resources.get("hacking_xp", 0) / 100)) + 1

    def prestige_reset(self, persist_protocols):
        """协议重启：清空进度，保留转生、架构构筑与持久协议（受槽位上限约束）。"""
        self.prestige += 1
        self.resources = {
            "energy": 120,
            "data_scraps": 0,
            "credits": 50 * self.prestige,
            "compute": 10 * self.prestige,
            "hacking_xp": 50 * self.prestige,
        }
        self.buildings = {}
        self.missions = []
        self.active_quests = []
        self.completed_quests = []
        self.auto_combat = False
        self.auto_explore = False
        self.combat_wins = 0
        self.threat_tier = min(2, self.prestige)
        # boss_available 由 depth_10 里程碑授予；里程碑不会重复触发，
        # 因此这里不能清掉，否则第一次重启后核心突袭将永久失效。
        self.pending_floor_boss = False
        self.max_dungeon_level = 1
        self.active_floor_modifier = None
        self.protocols = list(persist_protocols)
        self.protocols_unlocked = True
        self.storage_caps = {
            "energy": 500,
            "data_scraps": 500,
            "credits": 5000,
            "compute": 200,
        }
        if "protocol_reboot_done" not in self.story_flags:
            self.story_flags.append("protocol_reboot_done")

    def ascension_reset(self, gain=0, threat_floor=0):
        """内核跃迁：比协议重启更深一层。

        代价：**清空全部协议研究**（包括持久槽位）并把转生计数归零——
        放弃这一轮积累的协议栈。
        保留：架构构筑、Trait、已购永久升级、里程碑与剧情标记
        （里程碑不会重复触发，清掉会造成解锁死锁）。
        """
        self.ascension_count = int(getattr(self, "ascension_count", 0)) + 1
        self.arch_points = int(getattr(self, "arch_points", 0)) + max(0, int(gain))
        self.prestige = 0
        # 跃迁代价：协议全清
        self.protocols = []
        self.protocol_keep = []
        self.resources = {
            "energy": 150,
            "data_scraps": 0,
            "credits": 0,
            "compute": 0,
            "hacking_xp": 0,
        }
        self.buildings = {}
        self.missions = []
        self.active_quests = []
        self.completed_quests = []
        self.auto_combat = False
        self.auto_explore = False
        self.combat_wins = 0
        self.boss_kills = 0
        self.pending_floor_boss = False
        self.max_dungeon_level = 1
        self.active_floor_modifier = None
        # 跃迁次数抬升起始威胁阶：越跃迁越硬，但掉落更好
        self.threat_tier = max(0, int(threat_floor))
        self.storage_caps = {
            "energy": 500,
            "data_scraps": 500,
            "credits": 5000,
            "compute": 200,
        }
        if "kernel_ascended" not in self.story_flags:
            self.story_flags.append("kernel_ascended")

    def network_migrate(self, target, threat_floor=0):
        """网络跃迁：把节点迁往目标区域（第 3 层推进，不是转生）。

        代价：跃迁费用（由 NetworkManager 在调用前扣除），并放弃当前一轮的
        地牢进度与在途行动——新网络要从第 1 层重新爬。
        保留：转生次数、协议栈、架构/Trait、跃迁永久升级、里程碑、剧情标记
        以及所有区域的攻克记录（这是跨区域累积的永久进度）。
        """
        self.network_region = target
        self.migrations = int(getattr(self, "migrations", 0)) + 1
        # 只重置「这一轮」的进度，不动资源/建筑/协议/转生
        self.missions = []
        self.combat_wins = 0
        self.pending_floor_boss = False
        self.max_dungeon_level = 1
        self.active_floor_modifier = None
        # 目标区域的威胁基线：越深的区域起步越硬
        self.threat_tier = max(int(getattr(self, "threat_tier", 0)), int(threat_floor))
        if "network_migrated" not in self.story_flags:
            self.story_flags.append("network_migrated")

    def to_json(self):
        return json.dumps({
            "resources": self.resources,
            "storage_caps": self.storage_caps,
            "buildings": self.buildings,
            "artifacts": self.artifacts,
            "active_quests": self.active_quests,
            "completed_quests": getattr(self, "completed_quests", []),
            "story_flags": self.story_flags,
            "current_story_node": self.current_story_node,
            "seed": self.seed,
            "tick_count": self.tick_count,
            "last_update": self.last_update,
            "unlocked_actions": self.unlocked_actions,
            "language": self.language,
            "auto_combat": self.auto_combat,
            "auto_explore": self.auto_explore,
            "missions": self.missions,
            "combat_wins": self.combat_wins,
            "milestones_done": self.milestones_done,
            "prestige": self.prestige,
            "threat_tier": self.threat_tier,
            "protocols": self.protocols,
            "protocols_unlocked": self.protocols_unlocked,
            "boss_available": self.boss_available,
            "boss_kills": self.boss_kills,
            "pending_floor_boss": self.pending_floor_boss,
            "guide_shown": self.guide_shown,
            "max_dungeon_level": self.max_dungeon_level,
            "active_floor_modifier": self.active_floor_modifier,
            "architecture": self.architecture,
            "architecture_chosen": self.architecture_chosen,
            "traits": self.traits,
            "protocol_keep": self.protocol_keep,
            "arch_points": self.arch_points,
            "ascension_upgrades": self.ascension_upgrades,
            "ascension_count": self.ascension_count,
            "network_region": self.network_region,
            "regions_cleared": self.regions_cleared,
            "region_depths": self.region_depths,
            "migrations": self.migrations,
        })

    def from_json(self, json_str):
        data = json.loads(json_str)
        self.resources = data.get("resources", self.resources)
        self.storage_caps = data.get("storage_caps", self.storage_caps)
        self.buildings = data.get("buildings", {})
        self.artifacts = data.get("artifacts", [])
        self.active_quests = data.get("active_quests", [])
        self.completed_quests = data.get("completed_quests", [])
        self.story_flags = data.get("story_flags", self.story_flags)
        self.current_story_node = data.get(
            "current_story_node", self.current_story_node
        )
        self.seed = data.get("seed", self.seed)
        self.tick_count = data.get("tick_count", self.tick_count)
        self.last_update = data.get("last_update", self.last_update)
        self.unlocked_actions = data.get(
            "unlocked_actions", self.unlocked_actions
        )
        self.language = data.get("language", "zh")
        self.auto_combat = data.get("auto_combat", False)
        self.auto_explore = data.get("auto_explore", False)
        raw_missions = data.get("missions", [])
        self.missions = []
        for m in raw_missions:
            if "daemon_index" in m and "mission_id" not in m:
                continue
            cleaned = {
                "mission_id": m.get("mission_id"),
                "elapsed": m.get("elapsed", 0),
                "duration": m.get("duration", 60),
                "completed": m.get("completed", False),
                "claimed": m.get("claimed", False),
            }
            if cleaned["mission_id"]:
                self.missions.append(cleaned)
        self.combat_wins = data.get("combat_wins", 0)
        self.milestones_done = data.get("milestones_done", [])
        self.prestige = data.get("prestige", 0)
        self.threat_tier = data.get("threat_tier", 0)
        self.protocols = data.get("protocols", [])
        self.protocols_unlocked = data.get("protocols_unlocked", False)
        self.boss_available = data.get("boss_available", False)
        self.boss_kills = data.get("boss_kills", 0)
        self.pending_floor_boss = data.get("pending_floor_boss", False)
        self.guide_shown = data.get("guide_shown", False)
        self.max_dungeon_level = data.get("max_dungeon_level", 1)
        self.active_floor_modifier = data.get("active_floor_modifier")
        # 旧存档没有架构字段：留 None，由 ArchitectureManager.ensure_default() 迁移
        self.architecture = data.get("architecture")
        self.architecture_chosen = bool(data.get("architecture_chosen", False))
        raw_traits = data.get("traits", [])
        self.traits = list(raw_traits) if isinstance(raw_traits, list) else []
        raw_keep = data.get("protocol_keep", [])
        self.protocol_keep = list(raw_keep) if isinstance(raw_keep, list) else []
        self.arch_points = int(data.get("arch_points", 0) or 0)
        raw_ups = data.get("ascension_upgrades", {})
        self.ascension_upgrades = dict(raw_ups) if isinstance(raw_ups, dict) else {}
        self.ascension_count = int(data.get("ascension_count", 0) or 0)
        # 旧存档没有区域字段：留默认值，由 NetworkManager.ensure_default() 迁移
        self.network_region = data.get("network_region", "local")
        raw_cleared = data.get("regions_cleared", [])
        self.regions_cleared = (
            list(raw_cleared) if isinstance(raw_cleared, list) else []
        )
        raw_depths = data.get("region_depths", {})
        self.region_depths = dict(raw_depths) if isinstance(raw_depths, dict) else {}
        self.migrations = int(data.get("migrations", 0) or 0)
