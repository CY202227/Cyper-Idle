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
        # 1. 初始化全为墙壁 #
        self.grid = [["#" for _ in range(self.width)] for _ in range(self.height)]
        
        # 2. 随机漫步生成路径 (空地用空格 " " 表示)
        x, y = self.width // 2, self.height // 2
        self.player_pos = [x, y]
        
        # 路径步数随层数略微增加
        steps = (self.width * self.height) // 2 + (level_num * 2)
        
        walked_path = []
        for _ in range(steps):
            self.grid[y][x] = " " # 空地是空格，可以直接走
            walked_path.append((x, y))
            dx, dy = self.rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
            # 留出边界墙壁
            nx, ny = x + dx, y + dy
            if 1 <= nx < self.width - 1 and 1 <= ny < self.height - 1:
                x, y = nx, ny

        # 3. 在路径上随机散布符号
        # 过滤掉玩家初始位置
        spawn_pool = [p for p in walked_path if p != tuple(self.player_pos)]
        self.rng.rng.shuffle(spawn_pool)

        # 放置出口 E
        if spawn_pool:
            ex, ey = spawn_pool.pop()
            self.grid[ey][ex] = "E"

        # 放置其他符号
        symbols = {
            "!": 2, # 信息
            "?": 2, # 任务
            "*": 3, # 掉落
            "%": 3  # 敌人
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
                return "COLLISION", "撞到了防火墙。"
            
            # 更新位置
            self.player_pos = [nx, ny]
            
            if target == " ":
                return "MOVE", ""
            
            # 触发事件后清除该格子的符号
            self.grid[ny][nx] = " "
            
            if target == "!":
                return "INFO", "你发现了一段残留的系统日志。"
            elif target == "?":
                return "QUEST", "检测到未完成的任务协议。"
            elif target == "*":
                return "LOOT", "成功回收了一件丢弃的硬件碎片。"
            elif target == "%":
                return "ENEMY", "警告：遭遇安全防御程序！"
            elif target == "E":
                return "EXIT", "找到出口。准备进入下一层网络节点。"
                
        return "IDLE", ""

    def render(self):
        """渲染成字符串供 UI 显示"""
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
