"""Cyber-Idle — PyScript browser entry (GitHub Pages / static hosting).

Do NOT run this file with desktop Python (`python python/main.py`).
`js` / `document` / `pyodide` only exist inside the browser PyScript runtime.

Local play (from repo root):
  python -m http.server 8000
  open http://localhost:8000

Online: enable GitHub Pages on this repo and open the Pages URL.
"""

import asyncio
import time
import sys
import os

try:
    from js import document, window
    from pyodide.ffi import create_proxy
except ImportError:
    raise SystemExit(
        "Cyber-Idle is a PyScript web game - do not run main.py with CPython.\n"
        "From the repo root:\n"
        "  python -m http.server 8000\n"
        "Then open http://localhost:8000 in a browser.\n"
        "Or push to GitHub and enable Pages (serves index.html + PyScript)."
    )

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "python"))

from engine.state import GameState
from engine.manager import GameManager
from engine.story import StoryManager
from engine.dungeon import DungeonEngine
from engine.combat import CombatEngine
from engine.quest import QuestManager
from engine.missions import MissionManager
from engine.progress import ProgressManager
from engine.protocols import ProtocolManager
from engine.power import calc_player_power
from utils.rng import SeededRNG
from utils.storage import save_to_local, load_from_local, export_save_string, import_save_string
from utils.i18n import I18nManager

state = GameState()
rng = SeededRNG()
manager = GameManager(state, rng)
story = StoryManager(state)
i18n = I18nManager(state)
dungeon = DungeonEngine(state, rng)
mission_mgr = MissionManager(state)
protocol_mgr = ProtocolManager(state)
progress_mgr = ProgressManager(state)
combat_eng = CombatEngine(state, manager, None, mission_mgr, i18n, protocol_mgr)
quest_mgr = QuestManager(state)

manager.set_protocol_manager(protocol_mgr)
mission_mgr.set_protocol_manager(protocol_mgr)
combat_eng.set_protocol_manager(protocol_mgr)


def _ensure_glitch_layers(el):
    """保证动态 glitch 节点有前景层和两层虚影。"""
    main = el.querySelector(".glitch-main")
    if main:
        return main
    el.innerHTML = ""
    el.classList.add("glitch-layered")
    for class_name in ("glitch-layer glitch-layer-a", "glitch-layer glitch-layer-b"):
        span = document.createElement("span")
        span.className = class_name
        span.setAttribute("aria-hidden", "true")
        el.appendChild(span)
    main = document.createElement("span")
    main.className = "glitch-main"
    el.appendChild(main)
    return main


def set_glitch_text(el, text):
    """写入可见文字，并同步两层 glitch 虚影。"""
    if not el:
        return
    text = "" if text is None else str(text)
    if el.classList.contains("glitch-layered") or el.id == "enemy-visual":
        main = _ensure_glitch_layers(el)
        main.textContent = text
        for layer in el.querySelectorAll(".glitch-layer"):
            layer.textContent = text
    else:
        el.textContent = text
    el.setAttribute("data-text", text)


def sync_glitch_texts():
    """兜底：所有 .glitch-text 的虚影与正文保持一致。"""
    for el in document.querySelectorAll(".glitch-text"):
        main = el.querySelector(".glitch-main")
        if main:
            set_glitch_text(el, main.textContent or "")
            continue
        text = el.textContent or ""
        if el.getAttribute("data-text") != text:
            el.setAttribute("data-text", text)


def reset_story_view_state(clear_text=False):
    if hasattr(update_ui, "last_node"):
        delattr(update_ui, "last_node")
    if clear_text and hasattr(update_ui, "last_story_text"):
        delattr(update_ui, "last_story_text")


def append_story_log(msg):
    log_div = document.getElementById("story-log")
    if not log_div:
        return
    entry = document.createElement("div")
    entry.className = "log-entry"
    entry.innerText = f"> {msg}"
    log_div.appendChild(entry)
    log_div.scrollTop = log_div.scrollHeight


async def load_game_data():
    lang = state.language
    try:
        with open("data/ui.json", "r", encoding="utf-8") as f:
            i18n.load_ui_translations(f.read())
        with open(f"data/{lang}/resources.json", "r", encoding="utf-8") as f:
            res_data = f.read()
        with open(f"data/{lang}/events.json", "r", encoding="utf-8") as f:
            evt_data = f.read()
        with open(f"data/{lang}/story.json", "r", encoding="utf-8") as f:
            story_data = f.read()
        with open(f"data/{lang}/quests.json", "r", encoding="utf-8") as f:
            quest_data = f.read()
        with open(f"data/{lang}/buildings.json", "r", encoding="utf-8") as f:
            buildings_data = f.read()
        with open(f"data/{lang}/artifacts.json", "r", encoding="utf-8") as f:
            artifacts_data = f.read()
        with open(f"data/{lang}/missions.json", "r", encoding="utf-8") as f:
            missions_data = f.read()
        with open(f"data/{lang}/milestones.json", "r", encoding="utf-8") as f:
            milestones_data = f.read()
        with open(f"data/{lang}/enemies.json", "r", encoding="utf-8") as f:
            enemies_data = f.read()
        with open(f"data/{lang}/protocols.json", "r", encoding="utf-8") as f:
            protocols_data = f.read()

        manager.load_definitions(res_data, evt_data, buildings_data, artifacts_data)
        story.load_nodes(story_data)
        quest_mgr.load_definitions(quest_data)
        mission_mgr.load_definitions(missions_data)
        progress_mgr.load_definitions(milestones_data)
        protocol_mgr.load_definitions(protocols_data)
        combat_eng.load_enemies(enemies_data)
        combat_eng.set_i18n(i18n)
        manager.update_storage_caps()
    except Exception as e:
        print(f"配置文件加载失败 ({lang}): {e}")


def apply_dungeon_result(result, msg):
    if msg:
        append_story_log(i18n.get(msg, msg))

    pe = protocol_mgr.aggregate_effects()
    loot_pct = 1.0 + float(pe.get("loot_pct", 0))
    floor = dungeon.current_level

    if result == "LOOT":
        credits = int((40 + floor * 8) * loot_pct)
        scraps = max(1, int((2 + floor // 2) * loot_pct))
        state.resources["credits"] = state.resources.get("credits", 0) + credits
        state.resources["data_scraps"] = (
            state.resources.get("data_scraps", 0) + scraps
        )
        quest_mgr.update_progress("collect", "data_scraps")
    elif result == "ENEMY":
        combat_eng.queue_dungeon_fight(dungeon.current_level)
    elif result == "INFO":
        state.resources["hacking_xp"] = (
            state.resources.get("hacking_xp", 0) + 20 + floor * 2
        )
    elif result == "QUEST":
        state.resources["compute"] = state.resources.get("compute", 0) + 6 + floor // 2
    elif result == "EXIT":
        next_level = dungeon.current_level + 1
        dungeon.generate_level(next_level)
        state.max_dungeon_level = max(
            getattr(state, "max_dungeon_level", 1), next_level
        )
        quest_mgr.update_progress("explore", amount=next_level)
        # 每 5 层精英 / 15 层核心
        if next_level % 5 == 0:
            state.pending_floor_boss = True
            state.auto_explore = False
            if next_level >= 15 and getattr(state, "boss_available", False):
                append_story_log(i18n.get("dungeon_core_spawn", level=next_level))
                combat_eng.queue_boss_fight(next_level)
            else:
                append_story_log(i18n.get("dungeon_floor_boss", level=next_level))
                combat_eng.queue_dungeon_fight(next_level, floor_elite=True)


def set_locked(el, locked, title=None):
    """统一灰显不可用控件。不禁用点击，以便给出游戏内提示。"""
    if not el:
        return
    if locked:
        el.classList.add("is-locked")
        if title:
            el.title = title
    else:
        el.classList.remove("is-locked")
        el.removeAttribute("title")


_notice_token = 0
_notice_hide_proxy = None


def notify(msg):
    """游戏内提示，替代浏览器弹窗。"""
    global _notice_token, _notice_hide_proxy
    if not msg:
        return
    el = document.getElementById("game-notice")
    if not el:
        el = document.createElement("div")
        el.id = "game-notice"
        el.setAttribute("role", "status")
        document.body.appendChild(el)
    _notice_token += 1
    token = _notice_token
    el.innerText = str(msg)
    el.classList.add("is-on")

    def hide(*_args):
        if token == _notice_token:
            el.classList.remove("is-on")

    _notice_hide_proxy = create_proxy(hide)
    window.setTimeout(_notice_hide_proxy, 2600)


def update_status_bar():
    status_map = {
        "idle": i18n.get("status_idle"),
        "fighting": i18n.get("status_fighting"),
        "cooldown": i18n.get("status_cooldown"),
    }
    bits = [
        f"{i18n.get('combat_status')}: {status_map.get(combat_eng.status, combat_eng.status)}",
    ]
    if state.auto_combat:
        bits.append(f"{i18n.get('auto_combat')}:{i18n.get('toggle_on')}")
    if state.auto_explore and state.current_story_node == "dungeon_start":
        bits.append(f"{i18n.get('auto_explore')}:{i18n.get('toggle_on')}")
    if getattr(state, "protocols_unlocked", False):
        bits.append(
            f"{i18n.get('protocols_title')}:{len(getattr(state, 'protocols', []))}"
        )
    document.getElementById("status-text").innerText = " · ".join(bits)


def update_ui():
    document.getElementById("btn-lang").innerText = i18n.get("switch_lang")
    document.getElementById("btn-export").innerText = i18n.get("export_save")
    document.getElementById("btn-import").innerText = i18n.get("import_save")
    document.querySelector("#resource-panel h2").innerText = i18n.get("core_assets")
    document.querySelector("#action-panel h2").innerText = i18n.get("system_ops")
    document.querySelector("#quest-panel h2").innerText = i18n.get("active_contracts")
    infra_h2 = document.querySelector("#infrastructure-panel > h2")
    if infra_h2:
        infra_h2.innerText = i18n.get("infra_title")
    archives_h2 = document.querySelector("#archives-panel h2")
    if archives_h2:
        archives_h2.innerText = i18n.get("archives")
    document.getElementById("version").innerText = f"{i18n.get('ver_prefix')} v0.4.0-ALPHA"

    vs = document.getElementById("vs-divider")
    if vs:
        vs.innerText = i18n.get("vs_label")

    # 侧栏标签
    tab_labels = {
        "assets": "tab_assets",
        "progress": "tab_progress",
        "infra": "tab_infra",
        "ops": "tab_ops",
        "quests": "tab_quests",
        "archives": "tab_archives",
    }
    for btn in document.querySelectorAll(".side-tab-btn"):
        tid = btn.getAttribute("data-tab")
        key = tab_labels.get(tid)
        if key:
            btn.innerText = i18n.get(key)

    tabs = document.querySelectorAll("#infrastructure-tabs .tab-btn")
    if len(tabs) >= 2:
        tabs[0].innerText = i18n.get("tab_hardware")
        tabs[1].innerText = i18n.get("tab_software")

    sec_label = document.getElementById("sec-stability-label")
    if sec_label:
        sec_label.innerText = i18n.get("sec_stability")
    node_label = document.getElementById("node-stability-label")
    if node_label:
        node_label.innerText = i18n.get("node_stability")
    force_btn = document.getElementById("btn-force-fight")
    if force_btn:
        force_btn.innerText = i18n.get("force_fight")

    status_bar = document.getElementById("status-bar")
    level_span = document.getElementById("level-display")
    if not level_span:
        level_span = document.createElement("span")
        level_span.id = "level-display"
        status_bar.insertBefore(level_span, status_bar.firstChild)
    level_span.innerText = (
        f"{i18n.get('hacking_level')}: {state.hacking_level} · "
        f"{i18n.get('floor_label')}: {dungeon.current_level}"
    )
    update_status_bar()

    res_list = document.getElementById("resources-list")
    if res_list:
        res_list.innerHTML = ""
        for res_id, amount in state.resources.items():
            name = i18n.get_res_name(res_id, manager.definitions["resources"])
            cap = state.storage_caps.get(res_id)
            cap_str = f" / {int(cap)}" if cap is not None else ""
            item = document.createElement("div")
            item.className = "resource-item"
            item.innerText = f"{name}: {int(amount)}{cap_str}"
            res_list.appendChild(item)

    side = document.getElementById("side-content")
    side_top = side.scrollTop if side else 0

    update_power_ui()
    update_progress_ui()
    update_protocols_ui()
    update_missions_ui()
    update_idle_combat_ui()
    update_infrastructure_ui()
    update_archives_ui()
    update_actions_ui()
    update_quests_ui()
    update_story_ui()
    update_dungeon_ui()
    sync_glitch_texts()

    if side:
        side.scrollTop = side_top

    document.getElementById("tick-timer").innerText = (
        f"{i18n.get('tick_prefix')}: {state.tick_count}"
    )


def update_power_ui():
    panel = document.getElementById("node-power-panel")
    if not panel:
        return
    title = document.getElementById("node-power-title")
    if title:
        title.innerText = i18n.get("node_power")
    power = calc_player_power(
        state,
        manager.definitions.get("buildings", {}),
        protocol_effects=protocol_mgr.aggregate_effects(),
    )
    panel.innerHTML = f"""
        <div class="power-stat">{i18n.get('stat_intrusion')}: {int(power['intrusion'])}</div>
        <div class="power-stat">{i18n.get('stat_firewall')}: {int(power['firewall'])}</div>
        <div class="power-stat">{i18n.get('stat_integrity')}: {int(power['integrity'])}</div>
        <div class="power-stat">{i18n.get('stat_speed')}: {int(power['speed'])}</div>
        <div class="power-meta">{i18n.get('power_mult')}: x{power['mult']:.2f}</div>
        <div class="power-meta">{i18n.get('ops_penalty')}: -{int(power['ops_penalty']*100)}%</div>
    """


def update_progress_ui():
    title = document.getElementById("progress-title")
    if title:
        title.innerText = i18n.get("progress_title")
    panel = document.getElementById("progress-content")
    if not panel:
        return
    panel.innerHTML = ""

    mid, defn = progress_mgr.current_target()
    meta = document.createElement("div")
    meta.className = "progress-meta"
    meta.innerText = (
        f"{i18n.get('progress_prestige')}: {getattr(state, 'prestige', 0)} | "
        f"{i18n.get('progress_threat')}: {getattr(state, 'threat_tier', 0)}"
    )
    panel.appendChild(meta)

    if not mid:
        done = document.createElement("div")
        done.className = "empty-msg"
        done.innerText = i18n.get("progress_done")
        panel.appendChild(done)
    else:
        card = document.createElement("div")
        card.className = "progress-card"
        card.innerHTML = f"""
            <div class="quest-name">{defn.get('name', mid)}</div>
            <div class="quest-desc">{defn.get('desc', '')}</div>
            <div class="quest-progress">{i18n.get('progress_hint')}: {defn.get('hint', '')}</div>
        """
        panel.appendChild(card)

    if getattr(state, "boss_available", False):
        boss_btn = document.createElement("button")
        boss_btn.innerText = i18n.get("progress_boss_btn")
        busy = combat_eng.status == "fighting" or combat_eng.cooldown_remaining > 0
        set_locked(boss_btn, busy, i18n.get("status_fighting") if busy else None)

        def do_boss(event):
            if combat_eng.status == "fighting" or combat_eng.cooldown_remaining > 0:
                return
            combat_eng.start_boss_raid()
            update_ui()

        boss_btn.onclick = create_proxy(do_boss)
        panel.appendChild(boss_btn)
    else:
        hint = document.createElement("div")
        hint.className = "empty-msg is-locked"
        hint.innerText = i18n.get("boss_locked")
        panel.appendChild(hint)

    if getattr(state, "boss_kills", 0) >= 1 and "milestone_breach" in state.story_flags:
        reboot_btn = document.createElement("button")
        reboot_btn.innerText = i18n.get("progress_reboot_btn")

        def do_reboot_ui(event):
            state.current_story_node = "protocol_reboot"
            reset_story_view_state()
            update_ui()

        reboot_btn.onclick = create_proxy(do_reboot_ui)
        panel.appendChild(reboot_btn)


def update_protocols_ui():
    title = document.getElementById("protocols-title")
    if title:
        title.innerText = i18n.get("protocols_title")
    list_div = document.getElementById("protocols-list")
    if not list_div:
        return
    list_div.innerHTML = ""

    if not getattr(state, "protocols_unlocked", False):
        empty = document.createElement("div")
        empty.className = "empty-msg is-locked"
        empty.innerText = i18n.get("protocols_locked")
        list_div.appendChild(empty)
        return

    items = sorted(
        protocol_mgr.definitions.items(),
        key=lambda kv: (kv[1].get("tier", 1), kv[0]),
    )
    for pid, pdef in items:
        item = document.createElement("div")
        item.className = "mission-item"
        cost = pdef.get("cost", {})
        cost_str = ", ".join(
            f"{i18n.get_res_name(k, manager.definitions.get('resources', {}))}:{v}"
            for k, v in cost.items()
        )
        item.innerHTML = f"""
            <div class="mission-name">{pdef.get('name', pid)}</div>
            <div class="mission-desc">{pdef.get('desc', '')}</div>
            <div class="mission-meta">{i18n.get('protocol_tier', tier=pdef.get('tier', 1))} | {cost_str}</div>
        """
        if protocol_mgr.has(pid):
            done = document.createElement("div")
            done.className = "mission-meta"
            done.innerText = i18n.get("protocol_done")
            item.appendChild(done)
        else:
            btn = document.createElement("button")
            btn.innerText = i18n.get("protocol_research")
            can = True
            lock_reason = ""
            req = pdef.get("req")
            if req and not protocol_mgr.has(req):
                can = False
                lock_reason = i18n.get("protocol_req")
            else:
                for res, amount in cost.items():
                    if state.resources.get(res, 0) < amount:
                        can = False
                        lock_reason = i18n.get("protocol_no_res")
                        break
            set_locked(btn, not can, lock_reason)
            if not can:
                item.classList.add("is-locked")

            def make_research(protocol_id):
                def handler(event):
                    ok, msg = protocol_mgr.research(protocol_id)
                    if not ok:
                        alerts = {
                            "protocols_locked": i18n.get("protocols_locked"),
                            "req_missing": i18n.get("protocol_req"),
                            "insufficient_resources": i18n.get("protocol_no_res"),
                            "already": i18n.get("protocol_done"),
                        }
                        notify(alerts.get(msg, msg))
                    else:
                        quest_mgr.update_progress("protocol")
                        manager.update_storage_caps()
                    update_ui()
                return handler

            btn.onclick = create_proxy(make_research(pid))
            item.appendChild(btn)
        list_div.appendChild(item)


def update_missions_ui():
    title = document.getElementById("missions-title")
    if title:
        title.innerText = i18n.get("network_ops")

    list_div = document.getElementById("missions-list")
    if not list_div:
        return
    list_div.innerHTML = ""

    for mid, mdef in mission_mgr.definitions.items():
        item = document.createElement("div")
        item.className = "mission-item"
        rewards = mdef.get("rewards", {})
        reward_str = ", ".join(
            f"{i18n.get_res_name(k, manager.definitions['resources'])}:{v}"
            if k in manager.definitions.get("resources", {})
            else f"{k}:{v}"
            for k, v in rewards.items()
        )
        cost = mdef.get("cost", {})
        if cost:
            cost_str = ", ".join(
                f"{i18n.get_res_name(k, manager.definitions['resources'])}:{v}"
                for k, v in cost.items()
            )
        else:
            cost_str = i18n.get("op_cost_none")
        req_level = mdef.get("req_level", 1)
        item.innerHTML = f"""
            <div class="mission-name">{mdef.get('name', mid)}</div>
            <div class="mission-desc">{mdef.get('desc', '')}</div>
            <div class="mission-meta">{i18n.get('op_meta', level=req_level, duration=int(mdef.get('duration', 0)), cost=cost_str)}</div>
            <div class="mission-meta">{reward_str}</div>
        """
        btn = document.createElement("button")
        btn.innerText = i18n.get("launch_op")

        locked = False
        lock_reason = ""
        if state.hacking_level < req_level:
            locked = True
            lock_reason = i18n.get("op_level_low")
        elif mission_mgr.active_count() >= 3:
            locked = True
            lock_reason = i18n.get("op_slots_full")
        else:
            for res, amount in cost.items():
                if state.resources.get(res, 0) < amount:
                    locked = True
                    lock_reason = i18n.get("op_no_res")
                    break
        set_locked(btn, locked, lock_reason)
        if locked:
            item.classList.add("is-locked")

        def make_dispatch(mission_id):
            def handler(event):
                ok, msg = mission_mgr.start_mission(mission_id)
                if not ok:
                    alerts = {
                        "level_too_low": i18n.get("op_level_low"),
                        "mission_slots_full": i18n.get("op_slots_full"),
                        "insufficient_resources": i18n.get("op_no_res"),
                        "mission_not_found": i18n.get("mission_not_found"),
                    }
                    notify(alerts.get(msg, msg))
                update_ui()
            return handler

        btn.onclick = create_proxy(make_dispatch(mid))
        item.appendChild(btn)
        list_div.appendChild(item)

    active_div = document.getElementById("active-missions-list")
    if not active_div:
        return
    active_div.innerHTML = ""
    if not state.missions:
        empty = document.createElement("div")
        empty.className = "empty-msg"
        empty.innerText = i18n.get("no_ops")
        active_div.appendChild(empty)
        return

    for idx, m in enumerate(state.missions):
        defn = mission_mgr.definitions.get(m["mission_id"], {})
        ratio = mission_mgr.progress_ratio(m)
        status = i18n.get("mission_done") if m.get("completed") else i18n.get("mission_running")
        item = document.createElement("div")
        item.className = "mission-item active-mission"
        item.innerHTML = f"""
            <div class="mission-name">{defn.get('name', m['mission_id'])}</div>
            <div class="mission-meta">{status} ({int(ratio*100)}%)</div>
            <div class="daemon-xp-bar"><div class="daemon-xp-fill" style="width:{ratio*100}%"></div></div>
        """
        if m.get("completed") and not m.get("claimed"):
            claim_btn = document.createElement("button")
            claim_btn.innerText = i18n.get("claim_mission")

            def make_claim(mission_id):
                def handler(event):
                    for i, am in enumerate(state.missions):
                        if am.get("mission_id") == mission_id and not am.get("claimed"):
                            ok, rewards, _ = mission_mgr.claim_mission(i)
                            if ok:
                                parts = []
                                for k, v in rewards.items():
                                    name = i18n.get_res_name(
                                        k, manager.definitions.get("resources", {})
                                    )
                                    parts.append(f"+{v} {name}")
                                append_story_log(
                                    i18n.get("op_loot", rewards=", ".join(parts))
                                )
                            break
                    update_ui()
                return handler

            claim_btn.onclick = create_proxy(make_claim(m["mission_id"]))
            item.appendChild(claim_btn)
        active_div.appendChild(item)


def update_idle_combat_ui():
    panel = document.getElementById("combat-scene")
    if not panel:
        return
    panel.style.display = "flex"

    in_dungeon = state.current_story_node == "dungeon_start"
    engaged = (
        combat_eng.status in ("fighting", "cooldown")
        or bool(combat_eng.enemy)
        or combat_eng.pending_dungeon_fight
    )
    # 空闲时压缩；地牢开启且未交火时进一步压缩，避免挤占剧情
    if not engaged:
        panel.classList.add("combat-compact")
    else:
        panel.classList.remove("combat-compact")
    story_panel = document.getElementById("story-panel")
    if story_panel:
        if in_dungeon:
            story_panel.classList.add("in-dungeon")
        else:
            story_panel.classList.remove("in-dungeon")

    title = document.getElementById("idle-combat-title")
    if title:
        title.innerText = i18n.get("combat_idle_title")

    status_map = {
        "idle": i18n.get("status_idle"),
        "fighting": i18n.get("status_fighting"),
        "cooldown": i18n.get("status_cooldown"),
    }
    document.getElementById("combat-status-text").innerText = (
        f"{i18n.get('combat_status')}: {status_map.get(combat_eng.status, combat_eng.status)}"
    )
    document.getElementById("combat-wins-text").innerText = (
        f"{i18n.get('combat_wins')}: {getattr(state, 'combat_wins', 0)}"
    )

    document.getElementById("player-node-label").innerText = i18n.get("your_node")
    if combat_eng.player_max_hp > 0:
        pct = max(0, (combat_eng.player_hp / combat_eng.player_max_hp) * 100)
        document.getElementById("player-hp-fill").style.width = f"{pct}%"
        document.getElementById("player-hp-text").innerText = (
            f"{int(combat_eng.player_hp)}/{int(combat_eng.player_max_hp)}"
        )
    else:
        power = calc_player_power(
            state,
            manager.definitions.get("buildings", {}),
            protocol_effects=protocol_mgr.aggregate_effects(),
        )
        document.getElementById("player-hp-fill").style.width = "100%"
        document.getElementById("player-hp-text").innerText = f"{int(power['integrity'])}"

    if combat_eng.enemy and combat_eng.enemy.get("max_hp"):
        label = combat_eng.enemy.get("label") or i18n.get("enemy_security")
        enemy_text = f"{label} Lv.{combat_eng.enemy.get('level', 1)}"
        set_glitch_text(document.getElementById("enemy-visual"), enemy_text)
        ep = max(0, (combat_eng.enemy_hp / combat_eng.enemy["max_hp"]) * 100)
        document.getElementById("enemy-hp-fill").style.width = f"{ep}%"
        document.getElementById("enemy-hp-text").innerText = (
            f"{int(combat_eng.enemy_hp)}/{int(combat_eng.enemy['max_hp'])}"
        )
    else:
        set_glitch_text(
            document.getElementById("enemy-visual"),
            i18n.get("idle_scan"),
        )
        document.getElementById("enemy-hp-fill").style.width = "0%"
        document.getElementById("enemy-hp-text").innerText = "—"

    log_area = document.getElementById("combat-log-area")
    log_area.innerHTML = "".join([f"<div>{l}</div>" for l in combat_eng.log[-12:]])
    log_area.scrollTop = log_area.scrollHeight

    auto_btn = document.getElementById("btn-auto-combat")
    if auto_btn:
        on = i18n.get("toggle_on") if state.auto_combat else i18n.get("toggle_off")
        auto_btn.innerText = f"{i18n.get('auto_combat')}: {on}"

    force_btn = document.getElementById("btn-force-fight")
    if force_btn:
        busy = combat_eng.status == "fighting" or combat_eng.cooldown_remaining > 0
        set_locked(force_btn, busy, i18n.get("status_fighting") if busy else None)


def update_dungeon_ui():
    container = document.getElementById("dungeon-container")
    if state.current_story_node == "dungeon_start":
        container.style.display = "flex"
        document.getElementById("dungeon-grid").innerText = dungeon.render()
        auto_btn = document.getElementById("btn-auto-explore")
        if auto_btn:
            on = i18n.get("toggle_on") if state.auto_explore else i18n.get("toggle_off")
            auto_btn.innerText = f"{i18n.get('auto_explore')}: {on}"
    else:
        container.style.display = "none"


def update_actions_ui():
    actions_div = document.getElementById("actions-list")
    if not actions_div:
        return
    actions_div.innerHTML = ""
    btn = document.createElement("button")
    btn.innerText = i18n.get("gather_energy")

    def gather(event):
        manager.perform_action("gather_energy")
        update_ui()

    btn.onclick = create_proxy(gather)
    actions_div.appendChild(btn)


def update_quests_ui():
    quest_list_div = document.getElementById("quests-list")
    if not quest_list_div:
        return
    quest_list_div.innerHTML = ""
    if not state.active_quests:
        empty = document.createElement("div")
        empty.className = "empty-msg"
        empty.innerText = i18n.get("no_contracts")
        quest_list_div.appendChild(empty)
        return

    for quest in state.active_quests:
        defn = quest_mgr.definitions.get(quest["id"], {})
        q_item = document.createElement("div")
        q_item.className = "quest-item"
        progress = quest.get("progress", 0)
        target = defn.get("target_amount", 1)
        q_item.innerHTML = f"""
            <div class="quest-name">{defn.get('name', quest.get('id'))}</div>
            <div class="quest-desc">{defn.get('desc', '')}</div>
            <div class="quest-progress">{int(progress)}/{target}</div>
        """
        if progress >= target:
            btn = document.createElement("button")
            btn.className = "quest-reward-btn"
            btn.innerText = i18n.get("claim_reward")

            def make_claim_handler(qid):
                def handler(event):
                    success, rewards = quest_mgr.claim_reward(qid)
                    if success:
                        parts = []
                        for k, v in rewards.items():
                            name = i18n.get_res_name(
                                k, manager.definitions.get("resources", {})
                            )
                            parts.append(f"+{v} {name}")
                        append_story_log(
                            i18n.get(
                                "quest_complete",
                                rewards=", ".join(parts),
                            )
                        )
                        update_ui()
                return handler

            btn.onclick = create_proxy(make_claim_handler(quest["id"]))
            q_item.appendChild(btn)
        quest_list_div.appendChild(q_item)


def _story_choice_hidden(cdef):
    """合同已接/已完成，或一次性 flag 用尽时隐藏选项。"""
    block_flag = cdef.get("requires_not_flag")
    if block_flag and block_flag in state.story_flags:
        return True
    quest_id = cdef.get("quest_id")
    if quest_id and quest_mgr.has_quest(quest_id):
        return True
    return False


def _story_choice_fingerprint(node):
    if not node:
        return ""
    parts = []
    for cid, cdef in node.get("actions", {}).items():
        if _story_choice_hidden(cdef):
            parts.append(f"{cid}:hidden")
            continue
        ok, reason = story.can_take_action(cdef, quest_mgr)
        parts.append(f"{cid}:{ok}:{reason}")
    return "|".join(parts)


def _build_story_choices(current_node):
    choice_div = document.getElementById("story-choices")
    if not choice_div:
        return
    choice_div.innerHTML = ""
    if "actions" not in current_node:
        return
    for cid, cdef in current_node["actions"].items():
        if _story_choice_hidden(cdef):
            continue

        btn = document.createElement("button")
        btn.innerText = cdef.get("label", cid)
        btn.setAttribute("data-choice-id", cid)
        ok, reason = story.can_take_action(cdef, quest_mgr)
        reason_text = {
            "insufficient_resources": i18n.get("story_need_res"),
            "already_done": i18n.get("story_already_done"),
            "flag_locked": i18n.get("story_choice_locked"),
        }.get(reason, i18n.get("story_choice_locked"))
        set_locked(btn, not ok, reason_text if not ok else None)

        def make_handler(node_id, choice_id):
            def handler(event):
                current = story.story_nodes.get(node_id)
                if current:
                    action = current["actions"].get(choice_id)
                    if action and "quest_id" in action:
                        qid = action["quest_id"]
                        accepted = quest_mgr.accept_quest(qid)
                        if not accepted:
                            notify(i18n.get("story_already_done"))
                            update_ui()
                            return
                        qname = quest_mgr.definitions.get(qid, {}).get(
                            "name", qid
                        )
                        tip = i18n.get("quest_accept", name=qname)
                        notify(tip)
                        append_story_log(tip)
                        if qid in (
                            "unlock_attack_suite",
                            "unlock_data_ghost",
                        ):
                            quest_mgr.update_progress("special", amount=1)
                    if choice_id == "do_reboot" and node_id == "protocol_reboot":
                        persist = protocol_mgr.persistent_ids()
                        state.prestige_reset(persist)
                        dungeon.generate_level(1)
                        manager.update_storage_caps()
                        append_story_log(i18n.get("progress_reboot_btn"))
                ok, reason = story.trigger_choice(choice_id)
                if ok:
                    update_ui()
                else:
                    alerts = {
                        "insufficient_resources": i18n.get("story_need_res"),
                        "already_done": i18n.get("story_already_done"),
                        "flag_locked": i18n.get("story_choice_locked"),
                    }
                    notify(alerts.get(reason, reason))
            return handler

        btn.onclick = create_proxy(make_handler(state.current_story_node, cid))
        choice_div.appendChild(btn)


def update_story_ui():
    current_node = story.get_current_node()
    if not current_node:
        return

    current_el = document.getElementById("story-current")
    log_label = document.getElementById("story-log-label")
    if log_label:
        log_label.innerText = i18n.get("story_log_label")

    node_changed = (
        not hasattr(update_ui, "last_node")
        or update_ui.last_node != state.current_story_node
    )
    if node_changed:
        prev_text = getattr(update_ui, "last_story_text", None)
        if prev_text:
            append_story_log(prev_text)

        text = current_node.get("text", "")
        update_ui.last_story_text = text
        update_ui.last_node = state.current_story_node
        if current_el:
            current_el.innerText = text
        _build_story_choices(current_node)
        update_ui.last_choice_fp = _story_choice_fingerprint(current_node)
    else:
        if current_el and not current_el.innerText:
            current_el.innerText = current_node.get("text", "")
        fp = _story_choice_fingerprint(current_node)
        if getattr(update_ui, "last_choice_fp", None) != fp:
            _build_story_choices(current_node)
            update_ui.last_choice_fp = fp


async def game_loop():
    last_time = time.time()
    while True:
        current_time = time.time()
        delta_time = current_time - last_time
        last_time = current_time

        manager.tick(delta_time)
        mission_mgr.tick(delta_time)

        farm_level = max(
            state.hacking_level,
            int(getattr(state, "threat_tier", 0)) + 1,
        )
        combat_eng.tick(delta_time, farm_level=farm_level)

        if (
            state.auto_explore
            and state.current_story_node == "dungeon_start"
            and combat_eng.status == "idle"
            and combat_eng.cooldown_remaining <= 0
            and not combat_eng.pending_dungeon_fight
            and not getattr(state, "pending_floor_boss", False)
        ):
            result, msg = dungeon.auto_step()
            apply_dungeon_result(result, msg)

        # 层精英打完后清除封锁
        if getattr(state, "pending_floor_boss", False):
            if combat_eng.status == "idle" and not combat_eng.pending_dungeon_fight:
                # 若仍 pending 且无战斗排队，可能刚胜利已在 end_combat 清掉
                pass

        newly = progress_mgr.check(dungeon=dungeon, protocol_mgr=protocol_mgr)
        for mid in newly:
            append_story_log(
                i18n.get(
                    "milestone_log",
                    name=progress_mgr.definitions.get(mid, {}).get("name", mid),
                )
            )
            story_map = {
                "first_purge": "milestone_purge_story",
                "protocol_t1": "milestone_protocol_story",
                "depth_10": "milestone_depth_story",
                "core_breach": "protocol_reboot",
                "echo_stable": "echo_finale",
            }
            if mid in story_map:
                state.current_story_node = story_map[mid]
                reset_story_view_state()

        quest_mgr.update_progress("collect", "data_scraps")
        quest_mgr.update_progress("protocol")
        quest_mgr.update_progress("boss")
        update_ui()

        if state.tick_count % 10 == 0:
            save_to_local(state)

        await asyncio.sleep(1)


def move_up(event=None):
    handle_move(0, -1)


def move_down(event=None):
    handle_move(0, 1)


def move_left(event=None):
    handle_move(-1, 0)


def move_right(event=None):
    handle_move(1, 0)


def handle_move(dx, dy):
    if state.current_story_node != "dungeon_start":
        return
    if combat_eng.status == "fighting":
        return
    result, msg = dungeon.move_player(dx, dy)
    apply_dungeon_result(result, msg)
    update_ui()


def toggle_auto_combat(event=None):
    state.auto_combat = not state.auto_combat
    update_ui()


def toggle_auto_explore(event=None):
    state.auto_explore = not state.auto_explore
    update_ui()


def force_fight(event=None):
    if combat_eng.status == "idle" and combat_eng.cooldown_remaining <= 0:
        level = max(state.hacking_level, int(getattr(state, "threat_tier", 0)) + 1)
        combat_eng.start_combat(level=level)
        update_ui()


async def switch_language(event=None):
    state.language = "en" if state.language == "zh" else "zh"
    await load_game_data()
    reset_story_view_state(clear_text=True)
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
            await load_game_data()
            reset_story_view_state(clear_text=True)
            update_ui()
        else:
            notify(msg)


_SIDE_TAB_MAP = {
    "assets": "resource-panel",
    "progress": "progress-panel",
    "infra": "infrastructure-panel",
    "ops": "action-panel",
    "quests": "quest-panel",
    "archives": "archives-panel",
}
_side_scroll_proxy = None
_side_jumping = False


def _highlight_side_tab(tab_id):
    for btn in document.querySelectorAll(".side-tab-btn"):
        if btn.getAttribute("data-tab") == tab_id:
            btn.classList.add("active")
        else:
            btn.classList.remove("active")
    target_id = _SIDE_TAB_MAP.get(tab_id)
    for panel_id in _SIDE_TAB_MAP.values():
        el = document.getElementById(panel_id)
        if el:
            if panel_id == target_id:
                el.classList.add("active")
            else:
                el.classList.remove("active")


def _side_tab_from_scroll():
    container = document.getElementById("side-content")
    if not container:
        return None
    marker = container.getBoundingClientRect().top + 16
    current = "assets"
    for tab_id, panel_id in _SIDE_TAB_MAP.items():
        el = document.getElementById(panel_id)
        if el and el.getBoundingClientRect().top <= marker:
            current = tab_id
    return current


def _on_side_scroll(event=None):
    if _side_jumping:
        return
    tab_id = _side_tab_from_scroll()
    if tab_id:
        _highlight_side_tab(tab_id)


def bind_side_panel():
    global _side_scroll_proxy
    container = document.getElementById("side-content")
    if not container or _side_scroll_proxy is not None:
        return
    _side_scroll_proxy = create_proxy(_on_side_scroll)
    container.addEventListener("scroll", _side_scroll_proxy)


def _scroll_side_to(target):
    global _side_jumping
    container = document.getElementById("side-content")
    if not container or not target:
        return
    _side_jumping = True
    c_rect = container.getBoundingClientRect()
    t_rect = target.getBoundingClientRect()
    container.scrollTop = max(
        0, float(container.scrollTop) + float(t_rect.top) - float(c_rect.top)
    )
    _side_jumping = False


def show_side_tab(tab_id, event=None):
    target_id = _SIDE_TAB_MAP.get(tab_id)
    target = document.getElementById(target_id) if target_id else None
    _highlight_side_tab(tab_id)
    _scroll_side_to(target)


def update_infrastructure_ui():
    for category in ["hardware", "software"]:
        list_div = document.getElementById(f"{category}-list")
        if not list_div:
            continue

        list_div.innerHTML = ""
        buildings_def = manager.definitions.get("buildings", {}).get(category, {})

        if not buildings_def:
            empty_msg = document.createElement("div")
            empty_msg.className = "empty-msg"
            empty_msg.innerText = i18n.get("no_infra")
            list_div.appendChild(empty_msg)
        else:
            for b_id, b_def in buildings_def.items():
                locked_art = False
                if "requires_artifact" in b_def:
                    if b_def["requires_artifact"] not in state.artifacts:
                        locked_art = True

                level = state.buildings.get(b_id, 0)
                multiplier = b_def.get("cost_multiplier", 1.5)

                costs = []
                can_afford = True
                for res, base_amount in b_def["cost"].items():
                    actual_cost = int(base_amount * (multiplier ** level))
                    res_name = i18n.get_res_name(res, manager.definitions["resources"])
                    costs.append(f"{actual_cost} {res_name}")
                    if state.resources.get(res, 0) < actual_cost:
                        can_afford = False

                combat = b_def.get("effects", {}).get("combat", {})
                combat_str = ""
                if combat:
                    bits = []
                    for k, v in combat.items():
                        bits.append(
                            f"{i18n.stat_label(k)}{v:+g}{i18n.get('per_level')}"
                        )
                    combat_str = " | " + ", ".join(bits)

                item = document.createElement("div")
                item.className = "infra-item"
                lock_note = ""
                if locked_art:
                    item.classList.add("is-locked")
                    lock_note = f"<div class='infra-cost'>{i18n.get('err_artifact_missing')}</div>"
                item.innerHTML = f"""
                    <div class="infra-header">
                        <span>{b_def['name']}</span>
                        <span>Lv.{level}</span>
                    </div>
                    <div class="infra-desc">{b_def['desc']}{combat_str}</div>
                    <div class="infra-cost">{i18n.get('cost')}: {', '.join(costs)}</div>
                    {lock_note}
                """

                btn = document.createElement("button")
                btn.className = "infra-build-btn"
                btn.innerText = i18n.get("upgrade") if level > 0 else i18n.get("build")
                locked = locked_art or not can_afford
                reason = (
                    i18n.get("err_artifact_missing")
                    if locked_art
                    else i18n.get("op_no_res")
                )
                set_locked(btn, locked, reason if locked else None)

                def make_build_handler(bid):
                    def handler(event):
                        success, msg = manager.build(bid)
                        if success:
                            update_ui()
                        else:
                            if isinstance(msg, tuple):
                                key, amount, res = msg
                                res_name = i18n.get_res_name(
                                    res, manager.definitions.get("resources", {})
                                )
                                notify(
                                    i18n.get(key, amount=amount, res=res_name)
                                )
                            else:
                                notify(i18n.get(msg, msg))
                    return handler

                btn.onclick = create_proxy(make_build_handler(b_id))
                item.appendChild(btn)
                list_div.appendChild(item)


def show_infra_tab(category, event=None):
    document.getElementById("hardware-list").style.display = "none"
    document.getElementById("software-list").style.display = "none"
    document.getElementById(f"{category}-list").style.display = "flex"

    tabs = document.querySelectorAll("#infrastructure-tabs .tab-btn")
    for tab in tabs:
        click_attr = tab.getAttribute("py-click") or ""
        if f"'{category}'" in click_attr or f'"{category}"' in click_attr:
            tab.classList.add("active")
        else:
            tab.classList.remove("active")


def update_archives_ui():
    list_div = document.getElementById("artifacts-list")
    if not list_div:
        return

    list_div.innerHTML = ""
    archives_title = i18n.get("archives")
    document.querySelector("#archives-panel h2").innerText = archives_title

    if not state.artifacts:
        empty_msg = document.createElement("div")
        empty_msg.className = "empty-msg"
        empty_msg.innerText = i18n.get("no_artifacts")
        list_div.appendChild(empty_msg)
    else:
        for art_id in state.artifacts:
            art_def = manager.definitions.get("artifacts", {}).get(art_id)
            if not art_def:
                continue

            item = document.createElement("div")
            item.className = "artifact-item"
            item.innerHTML = f"""
                <div class="artifact-name">{art_def['name']}</div>
                <div class="artifact-desc">{art_def['desc']}</div>
                <div class="artifact-content">{art_def['content']}</div>
            """

            def make_toggle_handler(target_item):
                def handler(event):
                    target_item.classList.toggle("expanded")
                return handler

            item.onclick = create_proxy(make_toggle_handler(item))
            list_div.appendChild(item)


async def start_game():
    await load_game_data()

    if load_from_local(state):
        print("已恢复存档")
        manager.update_storage_caps()
    else:
        print("开启新游戏")
        state.seed = rng.get_seed()

    start_floor = max(1, getattr(state, "max_dungeon_level", 1))
    dungeon.generate_level(start_floor)

    if not getattr(state, "guide_shown", False):
        append_story_log(i18n.get("guide_step"))
        state.guide_shown = True

    document.getElementById("loading-overlay").style.display = "none"
    document.getElementById("game-container").style.display = "flex"
    bind_side_panel()

    await game_loop()


asyncio.ensure_future(start_game())
