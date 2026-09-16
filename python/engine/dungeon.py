import json
import random
from collections import deque


class DungeonEngine:
    def __init__(self, state, rng, width=20, height=10):
        self.state = state
        self.rng = rng
        self.width = width
        self.height = height
        self.grid = []
        self.player_pos = [0, 0]
        self.current_level = 1
        self.log = []
        # 地牢修饰词
        self.modifier_defs = {}
        self.active_modifier = None

    def load_modifiers(self, modifiers_json):
        self.modifier_defs = json.loads(modifiers_json)

    def modifier_effects(self):
        """当前层修饰词效果（无修饰词返回空 dict）。"""
        if not self.active_modifier:
            return {}
        defn = self.modifier_defs.get(self.active_modifier)
        return dict(defn.get("effects", {})) if defn else {}

    def _roll_modifier(self, level_num):
        """按权重 roll 本层修饰词；浅层（<3）不出修饰词。"""
        if level_num < 3 or not self.modifier_defs:
            return None
        pool = [
            (mid, float(defn.get("weight", 1)))
            for mid, defn in self.modifier_defs.items()
        ]
        total = sum(w for _, w in pool)
        roll = self.rng.rng.random() * total
        acc = 0.0
        for mid, w in pool:
            acc += w
            if roll <= acc:
                return mid
        return pool[-1][0]

    def generate_level(self, level_num=1):
        self.current_level = level_num
        self.active_modifier = self._roll_modifier(level_num)
        self.grid = [["#" for _ in range(self.width)] for _ in range(self.height)]

        x, y = self.width // 2, self.height // 2
        self.player_pos = [x, y]

        steps = (self.width * self.height) // 2 + (level_num * 2)

        walked_path = []
        for _ in range(steps):
            self.grid[y][x] = " "
            walked_path.append((x, y))
            dx, dy = self.rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
            nx, ny = x + dx, y + dy
            if 1 <= nx < self.width - 1 and 1 <= ny < self.height - 1:
                x, y = nx, ny

        spawn_pool = [p for p in walked_path if p != tuple(self.player_pos)]
        self.rng.rng.shuffle(spawn_pool)

        if spawn_pool:
            ex, ey = spawn_pool.pop()
            self.grid[ey][ex] = "E"

        # 修饰词影响 POI 分布：静默区砍敌人格，其他保持
        eff = self.modifier_effects()
        enemy_scale = 1.0 + float(eff.get("enemy_spawn_pct", 0))
        enemy_count = max(1, int(round(3 * max(0.0, enemy_scale))))

        symbols = {
            "!": 2,
            "?": 2,
            "*": 3,
            "%": enemy_count,
        }

        for sym, count in symbols.items():
            for _ in range(count):
                if spawn_pool:
                    sx, sy = spawn_pool.pop()
                    self.grid[sy][sx] = sym

    def move_player(self, dx, dy):
        nx, ny = self.player_pos[0] + dx, self.player_pos[1] + dy

        if 0 <= nx < self.width and 0 <= ny < self.height:
            target = self.grid[ny][nx]

            if target == "#":
                return "COLLISION", "dungeon_wall"

            self.player_pos = [nx, ny]

            if target == " ":
                return "MOVE", ""

            self.grid[ny][nx] = " "

            if target == "!":
                return "INFO", "dungeon_info"
            elif target == "?":
                return "QUEST", "dungeon_quest"
            elif target == "*":
                return "LOOT", "dungeon_loot"
            elif target == "%":
                return "ENEMY", "dungeon_enemy"
            elif target == "E":
                return "EXIT", "dungeon_exit"

        return "IDLE", ""

    def find_exit(self):
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == "E":
                    return (x, y)
        return None

    def find_nearest_poi(self):
        """寻找最近的有趣格子或出口。"""
        px, py = self.player_pos
        best = None
        best_dist = 10**9
        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if cell in ("!", "?", "*", "%", "E"):
                    dist = abs(x - px) + abs(y - py)
                    if dist < best_dist and dist > 0:
                        best_dist = dist
                        best = (x, y)
        return best

    def _bfs_step_toward(self, target):
        """BFS 求一步走向目标的最短路。返回 (dx, dy) 或 None。"""
        px, py = self.player_pos
        tx, ty = target
        if (px, py) == (tx, ty):
            return None
        start = (px, py)
        prev = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur == (tx, ty):
                # 回溯到起点后的第一步
                step = cur
                while prev[step] is not None and prev[step] != start:
                    step = prev[step]
                if prev[step] is None:
                    return None
                return (step[0] - px, step[1] - py)
            cx, cy = cur
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nxt = (cx + dx, cy + dy)
                if nxt in prev:
                    continue
                if 0 <= nxt[0] < self.width and 0 <= nxt[1] < self.height:
                    if self.grid[nxt[1]][nxt[0]] != "#":
                        prev[nxt] = cur
                        q.append(nxt)
        return None

    def auto_step(self):
        """自动探索一步：BFS 走向最近 POI/出口，否则随机可行方向。"""
        target = self.find_nearest_poi()

        if target:
            step = self._bfs_step_toward(target)
            if step:
                result, msg = self.move_player(step[0], step[1])
                if result != "COLLISION":
                    return result, msg

        dirs = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        self.rng.rng.shuffle(dirs)
        for dx, dy in dirs:
            result, msg = self.move_player(dx, dy)
            if result != "COLLISION":
                return result, msg
        return "IDLE", ""

    def render(self):
        lines = []
        for y in range(self.height):
            line = ""
            for x in range(self.width):
                if [x, y] == self.player_pos:
                    line += "@"
                else:
                    line += self.grid[y][x]
            lines.append(line)
        return "\n".join(lines)
