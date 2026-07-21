import json


class GameManager:
    BASE_CAPS = {
        "energy": 500,
        "data_scraps": 500,
        "credits": 5000,
        "compute": 200,
    }

    def __init__(self, state, rng):
        self.state = state
        self.rng = rng
        self.protocol_mgr = None
        self.definitions = {
            "resources": {},
            "actions": {},
            "events": [],
            "buildings": {},
            "artifacts": {},
        }

    def set_protocol_manager(self, protocol_mgr):
        self.protocol_mgr = protocol_mgr

    def _proto_effects(self):
        if self.protocol_mgr:
            return self.protocol_mgr.aggregate_effects()
        return {}

    def load_definitions(
        self, resources_json, events_json, buildings_json=None, artifacts_json=None
    ):
        self.definitions["resources"] = json.loads(resources_json)
        self.definitions["events"] = json.loads(events_json)
        if buildings_json:
            self.definitions["buildings"] = json.loads(buildings_json)
        if artifacts_json:
            self.definitions["artifacts"] = json.loads(artifacts_json)

    def tick(self, delta_time):
        """主循环逻辑，计算资源产出"""
        self.state.tick_count += 1

        for res_id, res_def in self.definitions["resources"].items():
            if "auto_gen" in res_def:
                amount = res_def["auto_gen"] * delta_time
                self.state.resources[res_id] = self.state.resources.get(res_id, 0) + amount

        # 核心架构升级：永久小幅电力加成
        if "core_upgraded" in self.state.story_flags:
            self.state.resources["energy"] = (
                self.state.resources.get("energy", 0) + 0.4 * delta_time
            )

        self.apply_building_effects(delta_time)
        self.apply_storage_caps()
        self.check_story_triggers()

        if self.state.tick_count % 60 == 0:
            self.check_random_events()

    def set_npc_manager(self, npc_mgr):
        self.npc_mgr = npc_mgr

    def check_story_triggers(self):
        if self.state.tick_count % 5 != 0:
            return

        if self.state.current_story_node == "energy_stable":
            if (
                "project_genesis_log" in self.state.artifacts
                and "echo_genesis_warned" not in self.state.story_flags
            ):
                self.state.current_story_node = "echo_genesis_warning"
                self.state.story_flags.append("echo_genesis_warned")
                return

            if (
                self.state.resources.get("compute", 0) >= 500
                and "echo_high_compute_triggered" not in self.state.story_flags
            ):
                self.state.current_story_node = "echo_high_compute"
                self.state.story_flags.append("echo_high_compute_triggered")
                return

            if hasattr(self, "npc_mgr"):
                idle_pool = ["echo_idle_1", "echo_idle_2", "echo_idle_3"]
                self.npc_mgr.trigger_random_chatter(idle_pool, chance=0.01)

    def apply_building_effects(self, delta_time):
        """建筑产出；资源不足时该建筑本 tick 停产。"""
        for category in ["hardware", "software"]:
            if category not in self.definitions["buildings"]:
                continue
            for b_id, b_def in self.definitions["buildings"][category].items():
                level = self.state.buildings.get(b_id, 0)
                if level <= 0:
                    continue

                effects = b_def.get("effects", {})
                consume = effects.get("consume", {})
                can_run = True
                for res, rate in consume.items():
                    need = rate * level * delta_time
                    if self.state.resources.get(res, 0) < need:
                        can_run = False
                        break

                if not can_run:
                    continue

                for res, rate in consume.items():
                    self.state.resources[res] = max(
                        0,
                        self.state.resources.get(res, 0) - (rate * level * delta_time),
                    )

                if "auto_gen" in effects:
                    pe = self._proto_effects()
                    gen_mult = 1.0 + float(pe.get("all_gen_pct", 0))
                    for res, rate in effects["auto_gen"].items():
                        rmult = gen_mult
                        if res == "credits":
                            rmult *= 1.0 + float(pe.get("credits_gen_pct", 0))
                        self.state.resources[res] = (
                            self.state.resources.get(res, 0)
                            + (rate * level * delta_time * rmult)
                        )

    def apply_storage_caps(self):
        for res_id, cap in self.state.storage_caps.items():
            if res_id in self.state.resources:
                if self.state.resources[res_id] > cap:
                    self.state.resources[res_id] = cap

    def update_storage_caps(self):
        new_caps = self.BASE_CAPS.copy()

        for category in ["hardware", "software"]:
            if category not in self.definitions["buildings"]:
                continue
            for b_id, b_def in self.definitions["buildings"][category].items():
                level = self.state.buildings.get(b_id, 0)
                if level <= 0:
                    continue
                storage_effects = b_def.get("effects", {}).get("storage", {})
                for res, bonus in storage_effects.items():
                    new_caps[res] = new_caps.get(res, 0) + (bonus * level)

        pe = self._proto_effects()
        storage_pct = 1.0 + float(pe.get("storage_pct", 0))
        self.state.storage_caps = {
            k: int(v * storage_pct) for k, v in new_caps.items()
        }

    def build(self, building_id):
        b_def = None
        for cat in ["hardware", "software"]:
            if building_id in self.definitions["buildings"].get(cat, {}):
                b_def = self.definitions["buildings"][cat][building_id]
                break

        if not b_def:
            return False, "err_building_missing"

        if "requires_artifact" in b_def:
            if b_def["requires_artifact"] not in self.state.artifacts:
                return False, "err_artifact_missing"

        current_level = self.state.buildings.get(building_id, 0)
        multiplier = b_def.get("cost_multiplier", 1.5)

        actual_costs = {}
        for res, base_amount in b_def["cost"].items():
            actual_costs[res] = base_amount * (multiplier ** current_level)

        for res, amount in actual_costs.items():
            if self.state.resources.get(res, 0) < amount:
                return False, ("err_resource_short", int(amount), res)

        for res, amount in actual_costs.items():
            self.state.resources[res] -= amount

        self.state.buildings[building_id] = current_level + 1
        self.update_storage_caps()
        return True, "build_ok"

    def check_random_events(self):
        available_events = []
        for event in self.definitions["events"]:
            met = True
            if "requirements" in event:
                for res, amount in event["requirements"].items():
                    if self.state.resources.get(res, 0) < amount:
                        met = False
                        break
            if met:
                available_events.append((event, event.get("weight", 1)))

        if available_events:
            event = self.rng.weighted_choice(available_events)
            self.trigger_event(event)

    def trigger_event(self, event):
        if "effect" in event:
            for res, amount in event["effect"].items():
                self.state.resources[res] = self.state.resources.get(res, 0) + amount
        return event.get("description", "发生了一个未知的网络波动。")

    def perform_action(self, action_id):
        if action_id == "gather_energy":
            self.state.resources["energy"] += 5
            return True
        return False
