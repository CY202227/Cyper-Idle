import json

class I18nManager:
    def __init__(self, state):
        self.state = state
        self.translations = {}
        self.ui_data = {}

    def load_ui_translations(self, json_data):
        self.ui_data = json.loads(json_data)

    def get(self, key, default=None):
        lang = self.state.language
        return self.ui_data.get(lang, {}).get(key, default or key)

    def get_res_name(self, res_id, res_defs):
        lang = self.state.language
        res_def = res_defs.get(res_id, {})
        # 如果定义中有直接翻译则使用，否则回退
        return res_def.get("name", res_id)
