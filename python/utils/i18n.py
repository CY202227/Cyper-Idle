import json


class I18nManager:
    def __init__(self, state):
        self.state = state
        self.translations = {}
        self.ui_data = {}

    def load_ui_translations(self, json_data):
        self.ui_data = json.loads(json_data)

    def get(self, key, default=None, **kwargs):
        lang = self.state.language
        text = self.ui_data.get(lang, {}).get(key)
        if text is None:
            # fallback to other language then key
            other = "en" if lang == "zh" else "zh"
            text = self.ui_data.get(other, {}).get(key, default or key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text

    def get_res_name(self, res_id, res_defs):
        res_def = res_defs.get(res_id, {})
        return res_def.get("name", res_id)

    def stat_label(self, stat_id):
        return self.get(f"stat_{stat_id}", stat_id)
