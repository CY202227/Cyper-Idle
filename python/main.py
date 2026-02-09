import asyncio
import time
import sys
import os
from js import document, window, localStorage
from pyodide.ffi import create_proxy

# 将当前目录添加到路径，以便导入
import os
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "python"))

from engine.state import GameState
from engine.manager import GameManager
from engine.story import StoryManager
from engine.dungeon import DungeonEngine
from engine.daemon import DaemonManager
from engine.combat import CombatEngine
from engine.quest import QuestManager
from utils.rng import SeededRNG
from utils.storage import save_to_local, load_from_local, export_save_string, import_save_string
from utils.i18n import I18nManager

# 初始化全局实例
state = GameState()
rng = SeededRNG()
manager = GameManager(state, rng)
story = StoryManager(state)
i18n = I18nManager(state)
dungeon = DungeonEngine(state, rng)
daemon_mgr = DaemonManager(state)

def on_combat_ui_update():
    update_ui()

combat_eng = CombatEngine(state, daemon_mgr, on_combat_ui_update)
quest_mgr = QuestManager(state)

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
        
        # 加载特定语言的守护程序定义
        with open(f"data/{lang}/daemons.json", "r", encoding="utf-8") as f:
            daemon_data = f.read()
        
        # 加载特定语言的任务定义
        with open(f"data/{lang}/quests.json", "r", encoding="utf-8") as f:
            quest_data = f.read()
            
        manager.load_definitions(res_data, evt_data)
        story.load_nodes(story_data)
        daemon_mgr.load_definitions(daemon_data)
        quest_mgr.load_definitions(quest_data)
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
    document.querySelector("#quest-panel h2").innerText = i18n.get("active_contracts")
    document.getElementById("status-text").innerText = i18n.get("status_ready")
    document.getElementById("version").innerText = f"{i18n.get('ver_prefix')} v0.1.0-ALPHA"
    
    # 显示黑客等级
    status_bar = document.getElementById("status-bar")
    level_span = document.getElementById("level-display")
    if not level_span:
        level_span = document.createElement("span")
        level_span.id = "level-display"
        status_bar.insertBefore(level_span, status_bar.firstChild)
    level_span.innerText = f"{i18n.get('hacking_level')}: {state.hacking_level} | "

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

    # 更新守护程序显示
    daemon_list_div = document.getElementById("daemons-list")
    if daemon_list_div:
        daemon_list_div.innerHTML = ""
        for i, daemon in enumerate(state.daemons):
            d_item = document.createElement("div")
            d_item.className = "daemon-item"
            if i == state.active_daemon_index:
                d_item.className += " active"
            
            name = daemon["name"] 
            d_item.innerHTML = f"""
                <div class="daemon-header">
                    <span class="daemon-name">{name}</span>
                    <span class="daemon-level">Lv.{daemon['level']}</span>
                </div>
                <div class="daemon-xp-bar">
                    <div class="daemon-xp-fill" style="width: {(daemon['xp']/daemon['xp_to_next'])*100}%"></div>
                </div>
                <div class="daemon-stats">
                    INT:{int(daemon['stats']['intrusion'])} | SHD:{int(daemon['stats']['shielding'])}
                </div>
            """
            # 绑定点击切换
            def make_switch_handler(idx):
                def handler(event):
                    state.active_daemon_index = idx
                    update_ui()
                return handler
            
            d_item.onclick = create_proxy(make_switch_handler(i))
            daemon_list_div.appendChild(d_item)

            # 添加“重构”按钮
            refactor_btn = document.createElement("button")
            refactor_btn.innerText = "重构 (SP: " + str(daemon.get('sp', 0)) + ")"
            refactor_btn.className = "refactor-btn-mini"
            def make_refactor_handler(idx):
                def handler(event):
                    event.stopPropagation()
                    show_refactor_ui(idx)
                return handler
            refactor_btn.onclick = create_proxy(make_refactor_handler(i))
            d_item.appendChild(refactor_btn)

    # 更新任务显示
    quest_list_div = document.getElementById("quests-list")
    if quest_list_div:
        quest_list_div.innerHTML = ""
        for quest in state.active_quests:
            defn = quest_mgr.definitions.get(quest["id"])
            if not defn: continue
            
            q_item = document.createElement("div")
            q_item.className = "quest-item"
            if quest["completed"]:
                q_item.className += " completed"
            
            name = defn["name"]
            desc = defn["desc"]
            progress_pct = min(100, (quest["progress"] / defn["target_amount"]) * 100)
            
            q_item.innerHTML = f"""
                <div class="quest-header">
                    <span>{name}</span>
                    <span>{int(quest['progress'])}/{defn['target_amount']}</span>
                </div>
                <div class="quest-desc">{desc}</div>
                <div class="quest-progress-bar">
                    <div class="quest-progress-fill" style="width: {progress_pct}%"></div>
                </div>
            """
            
            if quest["completed"]:
                btn = document.createElement("button")
                btn.className = "quest-reward-btn"
                btn.innerText = i18n.get("claim_reward")
                
                def make_claim_handler(qid):
                    def handler(event):
                        success, rewards = quest_mgr.claim_reward(qid)
                        if success:
                            # 显示奖励消息
                            reward_msg = ", ".join([f"+{v} {k}" for k, v in rewards.items()])
                            log_div = document.getElementById("story-log")
                            entry = document.createElement("div")
                            entry.className = "log-entry"
                            entry.innerText = f"> 任务完成！获得奖励: {reward_msg}"
                            log_div.appendChild(entry)
                            log_div.scrollTop = log_div.scrollHeight
                            update_ui()
                    return handler
                
                btn.onclick = create_proxy(make_claim_handler(quest["id"]))
                q_item.appendChild(btn)
                
            quest_list_div.appendChild(q_item)

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
                    def make_handler(node_id, choice_id):
                        def handler(event):
                            # 检查是否有任务接受逻辑
                            current_node = story.story_nodes.get(node_id)
                            if current_node:
                                action = current_node["actions"].get(choice_id)
                                if action and "quest_id" in action:
                                    quest_mgr.accept_quest(action["quest_id"])
                                    # 特殊逻辑：如果是黑市购买守护程序
                                    if action["quest_id"] == "unlock_data_ghost":
                                        new_daemon = daemon_mgr.create_daemon("data_ghost", level=1)
                                        if new_daemon:
                                            state.daemons.append(new_daemon)
                                            quest_mgr.update_progress("special", amount=1)
                            
                            if story.trigger_choice(choice_id):
                                update_ui()
                        return handler
                    
                    btn.onclick = create_proxy(make_handler(state.current_story_node, cid))
                    choice_div.appendChild(btn)

    # 更新状态栏
    document.getElementById("tick-timer").innerText = f"TICK: {state.tick_count}"

    # 更新地牢显示
    if state.current_story_node == "dungeon_start" and not combat_eng.is_active:
        document.getElementById("dungeon-container").style.display = "flex"
        document.getElementById("dungeon-grid").innerText = dungeon.render()
    else:
        document.getElementById("dungeon-container").style.display = "none"

    # 更新战斗显示
    combat_scene = document.getElementById("combat-scene")
    if combat_eng.is_active:
        combat_scene.style.display = "flex"
        
        # 更新敌人信息
        document.getElementById("enemy-intent").innerText = f"NEXT: [{combat_eng.enemy_intent['name'].upper()}]"
        document.getElementById("enemy-hp-fill").style.width = f"{(combat_eng.enemy_hp / combat_eng.enemy['max_hp']) * 100}%"
        
        # 更新玩家信息
        active_daemon = daemon_mgr.get_active_daemon()
        if active_daemon:
            document.getElementById("active-daemon-name").innerText = active_daemon["name"].get(state.language)
            document.getElementById("player-hp-fill").style.width = f"{(combat_eng.player_hp / combat_eng.player_max_hp) * 100}%"
            document.getElementById("player-bw-fill").style.width = f"{combat_eng.player_bw}%"
            
        # 更新战斗日志
        log_area = document.getElementById("combat-log-area")
        log_area.innerHTML = "".join([f"<div>{l}</div>" for l in combat_eng.log])
        log_area.scrollTop = log_area.scrollHeight
        
        # 更新动作按钮
        actions_div = document.getElementById("combat-actions")
        actions_div.innerHTML = ""
        
        # 基础动作
        base_actions = [("attack", "基础攻击 (20% BW)"), ("defend", "防御 (恢复 BW)"), ("reset", "重置 (大恢复)")]
        
        # 技能动作 (仅显示已挂载的技能)
        equipped_ids = active_daemon.get("equipped_skills", [])
        defn = daemon_mgr.definitions[active_daemon["id"]]
        all_actions = base_actions.copy()
        
        for sid in equipped_ids:
            skill_defn = next((s for s in defn["skill_tree"] if s["id"] == sid), None)
            if skill_defn:
                all_actions.append((sid, f"{skill_defn['name']} ({skill_defn['bw_cost']}% BW)"))

        for aid, label in all_actions:
            btn = document.createElement("button")
            btn.innerText = label
            def make_combat_handler(action_id):
                def handler(event):
                    combat_eng.execute_player_action(action_id)
                    update_ui()
                return handler
            btn.onclick = create_proxy(make_combat_handler(aid))
            actions_div.appendChild(btn)
    else:
        combat_scene.style.display = "none"

async def game_loop():
    """主游戏循环"""
    last_time = time.time()
    while True:
        current_time = time.time()
        delta_time = current_time - last_time
        last_time = current_time
        
        manager.tick(delta_time)
        
        # 每秒检查一次收集任务进度
        quest_mgr.update_progress("collect", "data_scraps")
        
        update_ui()
        
        # 每 10 秒自动保存一次
        if state.tick_count % 10 == 0:
            save_to_local(state)
            
        await asyncio.sleep(1)

# --- 按钮绑定函数 (由 HTML 中的 py-click 调用) ---

def move_up(event=None):
    handle_move(0, -1)

def move_down(event=None):
    handle_move(0, 1)

def move_left(event=None):
    handle_move(-1, 0)

def move_right(event=None):
    handle_move(1, 0)

def handle_move(dx, dy):
    result, msg = dungeon.move_player(dx, dy)
    if msg:
        log_div = document.getElementById("story-log")
        entry = document.createElement("div")
        entry.className = "log-entry"
        entry.innerText = f"> {msg}"
        log_div.appendChild(entry)
        log_div.scrollTop = log_div.scrollHeight
    
    # 根据结果给予奖励
    if result == "LOOT":
        state.resources["credits"] += 20
        state.resources["data_scraps"] += 1
        quest_mgr.update_progress("collect", "data_scraps")
    elif result == "ENEMY":
        # 切换到战斗模式
        combat_eng.start_combat("SECURITY_NODE", dungeon.current_level)
        update_ui()
        return # 战斗逻辑由 CombatEngine 接管
    elif result == "INFO":
        state.resources["hacking_xp"] += 10
    elif result == "QUEST":
        state.resources["compute"] += 2
    elif result == "EXIT":
        dungeon.generate_level(dungeon.current_level + 1)
        quest_mgr.update_progress("explore", amount=dungeon.current_level)
    
    update_ui()

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

# --- 重构界面逻辑 ---

def show_refactor_ui(daemon_idx):
    state.current_refactor_idx = daemon_idx
    daemon = state.daemons[daemon_idx]
    defn = daemon_mgr.definitions[daemon["id"]]
    
    document.getElementById("refactor-overlay").style.display = "flex"
    document.getElementById("refactor-daemon-name").innerText = daemon["name"]
    document.getElementById("ref_level").innerText = str(daemon["level"])
    document.getElementById("ref_sp").innerText = str(daemon["sp"])
    
    container = document.getElementById("skill-tree-container")
    container.innerHTML = ""
    
    for skill in defn["skill_tree"]:
        node = document.createElement("div")
        node.className = "skill-node"
        
        is_learned = skill["id"] in daemon["learned_skills"]
        is_locked = skill["req"] and skill["req"] not in daemon["learned_skills"]
        
        if is_learned: node.className += " learned"
        if is_locked: node.className += " locked"
        
        node.innerHTML = f"""
            <div class="skill-info">
                <h4>{skill['name']} (SP: {skill['sp_cost']})</h4>
                <p>{skill['desc']}</p>
            </div>
        """
        
        if not is_learned and not is_locked:
            btn = document.createElement("button")
            btn.innerText = "学习"
            def make_learn_handler(sid):
                def handler(event):
                    success, msg = daemon_mgr.learn_skill(state.current_refactor_idx, sid)
                    if success:
                        show_refactor_ui(state.current_refactor_idx)
                        update_ui()
                    else:
                        window.alert(msg)
                return handler
            btn.onclick = create_proxy(make_learn_handler(skill["id"]))
            node.appendChild(btn)
        elif is_learned:
            status = document.createElement("span")
            status.innerText = "[已激活]"
            node.appendChild(status)
            
        container.appendChild(node)

def close_refactor_ui(event=None):
    document.getElementById("refactor-overlay").style.display = "none"
    state.current_refactor_idx = None

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
        
        # 初始赠送一个守护程序 (改为新职业 ID)
        initial_daemon = daemon_mgr.create_daemon("vanguard", level=1)
        if initial_daemon:
            state.daemons.append(initial_daemon)

    # 初始化地牢
    dungeon.generate_level(1)

    # 3. 移除加载遮罩，显示游戏界面
    document.getElementById("loading-overlay").style.display = "none"
    document.getElementById("game-container").style.display = "flex"
    
    # 4. 启动循环
    await game_loop()

# 启动游戏
asyncio.ensure_future(start_game())
