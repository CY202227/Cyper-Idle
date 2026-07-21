import random


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

    def generate_level(self, level_num=1):
        self.current_level = level_num
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

        symbols = {
            "!": 2,
            "?": 2,
            "*": 3,
            "%": 3,
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

    def auto_step(self):
        """自动探索一步：朝 POI/出口移动，否则随机可行方向。"""
        target = self.find_nearest_poi()
        px, py = self.player_pos

        if target:
            tx, ty = target
            dx = 0 if tx == px else (1 if tx > px else -1)
            dy = 0 if ty == py else (1 if ty > py else -1)
            # 优先横移
            if dx != 0:
                result, msg = self.move_player(dx, 0)
                if result != "COLLISION":
                    return result, msg
            if dy != 0:
                result, msg = self.move_player(0, dy)
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
