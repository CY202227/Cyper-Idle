# Cyber-Idle | 赛博放置

基于 Python 的赛博朋克放置游戏，通过 **PyScript 在浏览器中运行**（与 GitHub Pages 同一套方式）。

[English](README.md) | [简体中文](README.zh-CN.md)

---

## 怎么运行（重要）

本项目是**静态网页游戏**，和 GitHub Pages 部署方式一致：

| 正确 | 错误 |
|------|------|
| 用 HTTP 提供**仓库根目录**，浏览器打开 `index.html` | 执行 `python python/main.py` |
| 使用浏览器里 PyScript 提供的 `js` / `document` | `pip install js`（那是另一个无关包） |

### 在线（GitHub Pages）

1. 推送到 GitHub。
2. **Settings → Pages**，选分支根目录部署。
3. 打开 `https://<用户名>.github.io/<仓库名>/`。

Pages 会提供 [`index.html`](index.html)，其中用 `<script type="py" …>` 加载 [`python/main.py`](python/main.py)。

### 本地（与 Pages 相同模型）

在**仓库根目录**执行：

```bash
python -m http.server 8000
```

浏览器打开 **http://localhost:8000**。

---

## 特性

- **纯前端**：PyScript，无游戏后端。
- **赛博 UI**：CRT / Glitch。
- **存档**：`localStorage` + Base64 导入导出。
- **双语**：中英文 JSON。
- **剧情**：资源条件分支。
- **地牢**：程序化子网 + **自动探索**。
- **网络攻防**：全自动交火，血条逐 tick 下降。
- **网络行动**：计时带宽任务（无 Daemon 抓宠）。
- **仅在线挂机**：无离线收益补算。

## 结构

```text
/
├── index.html          # 入口（PyScript 加载 main.py）
├── pyscript.json       # 浏览器运行时预取文件
├── css/style.css
├── data/
└── python/             # 游戏逻辑（在浏览器跑，不是 CLI）
```

## 许可证

MIT
