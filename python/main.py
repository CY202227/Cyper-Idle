import asyncio
import time
import sys
import os
from js import document, window, localStorage
from pyodide.ffi import create_proxy

# 将当前目录及其父目录添加到路径，以便导入
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "python"))

from engine.state import GameState
from engine.manager import GameManager
from engine.story import StoryManager
from utils.rng import SeededRNG
from utils.storage import save_to_local, load_from_local, export_save_string, import_save_string
from utils.i18n import I18nManager

# 初始化全局实例
state = GameState()
rng = SeededRNG()
manager = GameManager(state, rng)
story = StoryManager(state)
i18n = I18nManager(state)

async def load_game_data():
    """加载 JSON 配置文件"""
    lang = state.language
    try:
        # 加载公共 UI 翻译
        with open("data/ui.json", "r", encoding="utf-8") as f:
            ui_data = f.read()
        i18n.load_ui_translations(ui_data)

        # 加载特定语言的游戏内容
        with open(f"data/{lang}/resources.json", "r", encoding="utf-8") as f:
            res_data = f.read()
        with open(f"data/{lang}/events.json", "r", encoding="utf-8") as f:
            evt_data = f.read()
        with open(f"data/{lang}/story.json", "r", encoding="utf-8") as f:
            story_data = f.read()
            
        manager.load_definitions(res_data, evt_data)
        story.load_nodes(story_data)
    except Exception as e:
        print(f"配置文件加载失败 ({lang}): {e}")

def update_ui():
    """更新页面元素"""
    # 更新静态 UI 文本
    document.getElementById("btn-lang").innerText = i18n.get("switch_lang")
    document.getElementById("btn-export").innerText = i18n.get("export_save")
    document.getElementById("btn-import").innerText = i18n.get("import_save")
    document.querySelector("#resource-panel h2").innerText = i18n.get("core_assets")
    document.querySelector("#action-panel h2").innerText = i18n.get("system_ops")
    document.getElementById("status-text").innerText = i18n.get("status_ready")
    document.getElementById("version").innerText = f"{i18n.get('ver_prefix')} v0.1.0-ALPHA"

    # 更新资源显示
    res_list = document.getElementById("resources-list")
    res_list.innerHTML = ""
    for res_id, amount in state.resources.items():
        res_item = document.createElement("div")
        res_item.className = "resource-item"
        # 使用 i18n 获取资源名称
        display_name = i18n.get_res_name(res_id, manager.definitions["resources"])
        res_item.innerHTML = f"<span>{display_name}:</span> <span>{int(amount)}</span>"
        res_list.appendChild(res_item)

    # 更新剧情面板
    current_node = story.get_current_node()
    if current_node:
        log_div = document.getElementById("story-log")
        # 仅当节点改变时更新文本（简单实现）
        if not hasattr(update_ui, "last_node") or update_ui.last_node != state.current_story_node:
            entry = document.createElement("div")
            entry.className = "log-entry"
            entry.innerText = f"> {current_node['text']}"
            log_div.appendChild(entry)
            log_div.scrollTop = log_div.scrollHeight
            update_ui.last_node = state.current_story_node
            
            # 更新选项
            choice_div = document.getElementById("story-choices")
            choice_div.innerHTML = ""
            if "actions" in current_node:
                for cid, cdef in current_node["actions"].items():
                    btn = document.createElement("button")
                    btn.innerText = cdef.get("label", cid)
                    # 绑定点击事件
                    def make_handler(choice_id):
                        def handler(event):
                            if story.trigger_choice(choice_id):
                                update_ui()
                        return handler
                    
                    btn.onclick = create_proxy(make_handler(cid))
                    choice_div.appendChild(btn)

    # 更新状态栏
    document.getElementById("tick-timer").innerText = f"TICK: {state.tick_count}"

async def game_loop():
    """主游戏循环"""
    last_time = time.time()
    while True:
        current_time = time.time()
        delta_time = current_time - last_time
        last_time = current_time
        
        manager.tick(delta_time)
        update_ui()
        
        # 每 10 秒自动保存一次
        if state.tick_count % 10 == 0:
            save_to_local(state)
            
        await asyncio.sleep(1)

# --- 按钮绑定函数 (由 HTML 中的 py-click 调用) ---

async def switch_language(event=None):
    state.language = "en" if state.language == "zh" else "zh"
    await load_game_data()
    # 强制重置剧情显示以刷新翻译
    if hasattr(update_ui, "last_node"):
        delattr(update_ui, "last_node")
    update_ui()
    save_to_local(state)

def export_save(event=None):
    save_str = export_save_string(state)
    window.prompt(i18n.get("save_prompt"), save_str)

async def import_save_dialog(event=None):
    save_str = window.prompt(i18n.get("load_prompt"))
    if save_str:
        success, msg = import_save_string(state, save_str)
        if success:
            # 导入后可能语言变了，重新加载数据
            await load_game_data()
            # 强制重置剧情显示
            if hasattr(update_ui, "last_node"):
                delattr(update_ui, "last_node")
            update_ui()
        else:
            window.alert(msg)

# --- 初始化流程 ---

async def start_game():
    # 1. 加载配置
    await load_game_data()
    
    # 2. 尝试从本地加载存档
    if load_from_local(state):
        print("已恢复存档")
    else:
        print("开启新游戏")
        state.seed = rng.get_seed()

    # 3. 立即更新一次 UI，确保数据渲染
    update_ui()

    # 4. 移除加载遮罩，显示游戏界面
    loading_overlay = document.getElementById("loading-overlay")
    if loading_overlay:
        loading_overlay.style.display = "none"
    
    game_container = document.getElementById("game-container")
    if game_container:
        game_container.style.display = "flex"
    
    # 5. 启动循环
    await game_loop()

# 启动游戏
asyncio.ensure_future(start_game())
