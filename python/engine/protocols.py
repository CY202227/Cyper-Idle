import json


class ProtocolManager:
    def __init__(self, state):
        self.state = state
        self.definitions = {}

    def load_definitions(self, protocols_json):
        self.definitions = json.loads(protocols_json)

    def researched(self):
        return list(getattr(self.state, "protocols", []))

    def has(self, pid):
        return pid in self.researched()

    def aggregate_effects(self):
        effects = {}
        for pid in self.researched():
            defn = self.definitions.get(pid, {})
            for k, v in defn.get("effects", {}).items():
                effects[k] = effects.get(k, 0) + v
        # prestige bonuses
        p = getattr(self.state, "prestige", 0)
        if p > 0:
            effects["all_gen_pct"] = effects.get("all_gen_pct", 0) + 0.05 * p
            effects["intrusion_pct"] = effects.get("intrusion_pct", 0) + 0.03 * p
        return effects

    def research(self, protocol_id):
        if not getattr(self.state, "protocols_unlocked", False):
            return False, "protocols_locked"
        if protocol_id not in self.definitions:
            return False, "not_found"
        if self.has(protocol_id):
            return False, "already"
        defn = self.definitions[protocol_id]
        req = defn.get("req")
        if req and not self.has(req):
            return False, "req_missing"
        cost = defn.get("cost", {})
        for res, amount in cost.items():
            if self.state.resources.get(res, 0) < amount:
                return False, "insufficient_resources"
        for res, amount in cost.items():
            self.state.resources[res] -= amount
        self.state.protocols.append(protocol_id)
        return True, "ok"

    def persistent_ids(self):
        return [
            pid
            for pid in self.researched()
            if self.definitions.get(pid, {}).get("persist")
        ]
