import pybase64
import json
from js import window, localStorage

SAVE_KEY = "CYBER_IDLE_SAVE"

def save_to_local(state):
    """保存游戏状态到 localStorage"""
    json_str = state.to_json()
    localStorage.setItem(SAVE_KEY, json_str)

def load_from_local(state):
    """从 localStorage 加载游戏状态"""
    save_data = localStorage.getItem(SAVE_KEY)
    if save_data:
        try:
            state.from_json(save_data)
            return True
        except Exception as e:
            print(f"加载存档失败: {e}")
    return False

def export_save_string(state):
    """导出 Base64 加密的存档字符串"""
    json_str = state.to_json()
    # 仿 Evolve 风格，增加一个简单的校验前缀
    data_bytes = json_str.encode('utf-8')
    b64_str = pybase64.b64encode(data_bytes).decode('utf-8')
    return f"CYBER-{b64_str}"

def import_save_string(state, save_str):
    """从 Base64 字符串导入存档"""
    if not save_str.startswith("CYBER-"):
        return False, "无效的存档格式"
    
    try:
        b64_part = save_str[6:]
        json_bytes = pybase64.b64decode(b64_part)
        json_str = json_bytes.decode('utf-8')
        state.from_json(json_str)
        return True, "存档加载成功"
    except Exception as e:
        return False, f"解析存档失败: {e}"
