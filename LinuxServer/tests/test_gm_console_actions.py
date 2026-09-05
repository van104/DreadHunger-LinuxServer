from __future__ import annotations

import importlib.util
import http.client
import json
import math
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gm_module = load_module(
    "gm_console_actions_under_test",
    LINUX_SERVER_ROOT / "GM控制台" / "gm_console.py",
)


class GMActionTests(unittest.TestCase):
    def make_console(self, root: Path):
        runtime_dir = root / gm_module.GM_RUNTIME_DIR
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / gm_module.PLAYER_LIST_FILE).write_text(
            json.dumps(
                {
                    "timestamp": int(time.time() * 1000),
                    "count": 1,
                    "players": [
                        {
                            "name": "测试船长",
                            "role": "船长",
                            "role_id": "Captain",
                            "index": 0,
                            "is_thrall": False,
                            "has_pawn": True,
                            "is_dead": False,
                            "x": 10.5,
                            "y": -20.25,
                            "z": 300.0,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return gm_module.GMConsole(root, "test")

    def test_item_catalog_contains_normal_and_special_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            items = console.get_items()["items"]
            by_id = {item["id"]: item for item in items}

            self.assertEqual(len(items), 56)
            self.assertEqual(len(by_id), len(items))
            self.assertEqual(len({item["class_path"] for item in gm_module.ITEM_CATALOG}), len(items))
            self.assertIn("flintlock", by_id)
            self.assertIn("quest", by_id)
            self.assertIn("backpack", by_id)
            self.assertIn("human_body", by_id)
            self.assertIn("rabbit_head", by_id)
            self.assertIn("bone_charm", by_id)
            self.assertIn("pure_crystal", by_id)
            self.assertTrue(by_id["bone_charm"]["special"])
            self.assertTrue(by_id["bone_charm"]["requires_mod"])
            self.assertTrue(by_id["pure_crystal"]["requires_mod"])
            self.assertNotIn("animal_body_part", by_id)
            self.assertNotIn("ingot", by_id)

    def test_give_item_accepts_quantity_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            for quantity in (1, 20):
                with self.subTest(quantity=quantity):
                    params = console.normalize_action_params(
                        "give_item",
                        {"role": "Captain", "item": "flintlock", "quantity": quantity},
                    )
                    self.assertEqual(params["quantity"], quantity)
                    self.assertIn("BP_Flintlock_Inventory_C", params["item_class"])

    def test_give_item_accepts_all_online_players(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            params = console.normalize_action_params(
                "give_item", {"role": "all", "item": "coal", "quantity": 5}
            )
            self.assertEqual(params["role"], "all")
            self.assertEqual(params["quantity"], 5)

    def test_give_item_rejects_bad_quantity_item_and_role(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            invalid = [
                {"role": "Captain", "item": "flintlock", "quantity": 0},
                {"role": "Captain", "item": "flintlock", "quantity": 21},
                {"role": "Captain", "item": "flintlock", "quantity": 1.5},
                {"role": "Captain", "item": "missing", "quantity": 1},
                {"role": "Doctor", "item": "flintlock", "quantity": 1},
                {"role": "Unknown", "item": "flintlock", "quantity": 1},
            ]
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    console.normalize_action_params("give_item", payload)

    def test_teleport_rejects_non_finite_and_out_of_range_coordinates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            valid = console.normalize_action_params(
                "teleport_player",
                {"player": "测试船长", "x": 1.25, "y": -2, "z": 3},
            )
            self.assertEqual(valid["player"], "测试船长")
            self.assertEqual(valid["x"], 1.25)
            self.assertEqual(valid["y"], -2.0)

            for value in (math.nan, math.inf, -math.inf, gm_module.MAX_COORDINATE + 1, "12"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    console.normalize_action_params(
                        "teleport_player",
                        {"player": "测试船长", "x": value, "y": 0, "z": 0},
                    )

    def test_coordinate_teleport_targets_online_player_and_keeps_role_compatibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            by_player = console.normalize_action_params(
                "teleport_player", {"player": "测试船长", "x": 1, "y": 2, "z": 3}
            )
            by_role = console.normalize_action_params(
                "teleport_player", {"role": "Captain", "x": 1, "y": 2, "z": 3}
            )
            self.assertEqual(by_player["player"], "测试船长")
            self.assertEqual(by_role["role"], "Captain")
            with self.assertRaisesRegex(ValueError, "玩家当前不在线"):
                console.normalize_action_params(
                    "teleport_player", {"player": "离线玩家", "x": 1, "y": 2, "z": 3}
                )

    def test_revive_and_ship_teleport_keep_player_name_compatibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            revive = console.normalize_action_params("revive_player", {"player": "测试船长"})
            ship = console.normalize_action_params("teleport_to_ship", {"player": "all"})
            self.assertEqual(revive["player"], "测试船长")
            self.assertEqual(ship["player"], "all")

    def test_result_file_success_failure_and_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            success_path = console.result_dir / "success.json"
            success_path.write_text(
                json.dumps(
                    {
                        "id": "success",
                        "action": "give_item",
                        "result": {"success": True, "added": 2},
                    }
                ),
                encoding="utf-8",
            )
            success = console.wait_for_result("success", 0.1)
            self.assertEqual(success["result"]["added"], 2)
            self.assertFalse(success_path.exists())

            failure_path = console.result_dir / "failure.json"
            failure_path.write_text(
                json.dumps(
                    {
                        "id": "failure",
                        "action": "teleport_player",
                        "result": {"success": False, "error": "传送失败"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            failure = console.wait_for_result("failure", 0.1)
            self.assertEqual(failure["result"]["error"], "传送失败")
            self.assertIsNone(console.wait_for_result("missing", 0.01))

    def test_send_command_reports_actual_partial_failure_and_timeout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            partial = {
                "result": {
                    "success": True,
                    "requested": 20,
                    "added": 3,
                    "partial": True,
                    "message": "背包空间不足，实际加入 3 个",
                }
            }
            with mock.patch.object(console, "wait_for_result", return_value=partial):
                result = console.send_command(
                    "give_item", {"role": "Captain", "item": "coal", "quantity": 20}
                )
            self.assertTrue(result["success"])
            self.assertFalse(result["queued"])
            self.assertEqual(result["result"]["added"], 3)

            native_failure = {"result": {"success": False, "error": "背包已满"}}
            with mock.patch.object(console, "wait_for_result", return_value=native_failure):
                result = console.send_command(
                    "give_item", {"role": "Captain", "item": "coal", "quantity": 1}
                )
            self.assertFalse(result["success"])
            self.assertEqual(result["error"], "背包已满")

            with mock.patch.object(console, "wait_for_result", return_value=None):
                result = console.send_command("open_armory", {})
            self.assertTrue(result["queued"])
            self.assertIn("等待 Frida", result["message"])

    def test_stale_result_files_are_cleaned_after_ten_minutes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            stale = console.result_dir / "stale.json"
            fresh = console.result_dir / "fresh.json"
            stale.write_text("{}", encoding="utf-8")
            fresh.write_text("{}", encoding="utf-8")
            old_time = time.time() - gm_module.COMMAND_RESULT_MAX_AGE - 1
            os.utime(stale, (old_time, old_time))

            console._cleanup_results()

            self.assertFalse(stale.exists())
            self.assertTrue(fresh.exists())

    def test_teleport_presets_persist_update_remove_and_validate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = self.make_console(root)
            saved = console.save_teleport_preset({"name": "船长室", "x": 1, "y": 2.5, "z": -3})
            self.assertEqual(saved["preset"]["name"], "船长室")
            self.assertEqual(console.get_teleport_presets()["count"], 1)

            console.save_teleport_preset({"name": "船长室", "x": 10, "y": 20, "z": 30})
            reloaded = gm_module.GMConsole(root, "test").get_teleport_presets()
            self.assertEqual(reloaded["count"], 1)
            self.assertEqual(reloaded["presets"][0]["x"], 10.0)

            self.assertEqual(console.remove_teleport_preset({"name": "船长室"})["removed"], "船长室")
            self.assertEqual(console.get_teleport_presets()["count"], 0)
            for payload in (
                {"name": "", "x": 1, "y": 2, "z": 3},
                {"name": "坏点", "x": math.nan, "y": 2, "z": 3},
                {"name": "越界", "x": gm_module.MAX_COORDINATE + 1, "y": 2, "z": 3},
            ):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    console.save_teleport_preset(payload)

    def test_player_schema_preserves_live_coordinates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            player = console.get_players()["players"][0]
            self.assertEqual(player["role_id"], "Captain")
            self.assertEqual(player["x"], 10.5)
            self.assertTrue(player["has_pawn"])
            self.assertFalse(player["is_dead"])

    def test_winning_card_reward_config_persists_resolved_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = self.make_console(root)
            saved = console.save_winning_card_reward({
                "enabled": True,
                "mode": "fixed",
                "delay_seconds": 45,
                "backpack_slots": 12,
                "items": [
                    {"item": "coal", "quantity": 5},
                    {"item": "flintlock", "quantity": 1},
                ],
                "announcement": "{player} 获得 {rewards}",
            })["config"]

            self.assertEqual(saved["delay_seconds"], 45)
            self.assertEqual(saved["backpack_slots"], 12)
            self.assertIn("BP_Coal_Inventory_C", saved["items"][0]["item_class"])
            reloaded = gm_module.GMConsole(root, "test").get_winning_card_reward()["config"]
            self.assertEqual(reloaded, saved)

    def test_winning_card_reward_config_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            valid = {
                "enabled": True,
                "mode": "random",
                "delay_seconds": 0,
                "backpack_slots": 0,
                "items": [{"item": "coal", "quantity": 1}],
                "announcement": "奖励 {player}",
            }
            invalid = [
                {**valid, "mode": "all"},
                {**valid, "delay_seconds": 601},
                {**valid, "backpack_slots": 31},
                {**valid, "items": [{"item": "missing", "quantity": 1}]},
                {**valid, "items": [{"item": "coal", "quantity": 21}]},
                {**valid, "items": [], "backpack_slots": 0},
            ]
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    console.save_winning_card_reward(payload)


class GMPluginSourceTests(unittest.TestCase):
    def test_native_addresses_and_actions_are_registered(self):
        source = (LINUX_SERVER_ROOT / "Linux 插件" / "[服务端]GM控制台_Linux.js").read_text(encoding="utf-8")
        self.assertNotIn("controller.add(0x258).readPointer()", source)
        self.assertNotIn("base.add(0x2D6FA10)", source)
        self.assertIn("base.add(0x40A0430)", source)
        self.assertIn("base.add(0x284FEA0)", source)
        self.assertIn("gs.add(0x2A8).readPointer()", source)
        self.assertNotIn("gs.add(0x2B0).readPointer()", source)
        self.assertNotIn("warship.add(0x03BC)", source)
        self.assertIn("getShipReturnLocations", source)
        self.assertIn("gmSendTopMessage('军械库已开启')", source)
        self.assertIn("params.role === 'all'", source)
        self.assertIn("var PlayerPollMs     = 1000", source)
        self.assertIn("'give_item':", source)
        self.assertIn("'teleport_player':", source)
        self.assertIn("'execute_player':", source)

    def test_coordinate_teleport_ui_selects_player_name(self):
        source = (LINUX_SERVER_ROOT / "GM控制台" / "gm_console.py").read_text(encoding="utf-8")
        self.assertIn('v-model="formCoordinate.player"', source)
        self.assertIn("const formCoordinate = reactive({ player: ''", source)
        self.assertIn("params = { player: params.player", source)

    def test_winning_card_reward_ui_and_plugin_are_connected(self):
        console_source = (LINUX_SERVER_ROOT / "GM控制台" / "gm_console.py").read_text(encoding="utf-8")
        plugin_source = (LINUX_SERVER_ROOT / "Linux 插件" / "[服务端]赢牌对家开船_Linux.js").read_text(encoding="utf-8")
        self.assertIn('name="card-reward"', console_source)
        self.assertNotIn('label="随机在线玩家"', console_source)
        self.assertIn('<el-radio-button label="fixed">固定奖励（全部发放）</el-radio-button>', console_source)
        self.assertIn('<el-radio-button label="random">随机奖励（随机一种）</el-radio-button>', console_source)
        self.assertIn('grid-template-columns:minmax(0,1fr) 120px 78px', console_source)
        self.assertIn('@click="removeRewardItem(index)">删除</el-button>', console_source)
        self.assertIn("/api/gm/winning-card-reward", console_source)
        self.assertIn("gm_winning_card_reward.json", plugin_source)
        self.assertIn("UDH_InventoryManager_SetStorageLimit", plugin_source)
        self.assertIn("UDH_InventoryManager_AddInventory", plugin_source)
        self.assertIn("var wi = getPawnInfo(winner)", plugin_source)


class GMActionAPITests(unittest.TestCase):
    def test_new_api_statuses_and_item_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = GMActionTests().make_console(Path(temp_dir))
            server = gm_module.GMHTTPServer(("127.0.0.1", 0), gm_module.make_handler(console))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)

            def request(method, path, payload=None, token=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                body = json.dumps(payload).encode("utf-8") if payload is not None else None
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                data = json.loads(response.read().decode("utf-8"))
                return response.status, data

            try:
                status, login = request("POST", "/login", {"password": "test"})
                self.assertEqual(status, 200)
                token = login["token"]

                status, catalog = request("GET", "/api/gm/items", token=token)
                self.assertEqual(status, 200)
                self.assertEqual(catalog["count"], len(gm_module.ITEM_CATALOG))

                status, reward = request("GET", "/api/gm/winning-card-reward", token=token)
                self.assertEqual(status, 200)
                self.assertFalse(reward["config"]["enabled"])
                status, reward = request(
                    "POST", "/api/gm/winning-card-reward",
                    {
                        "enabled": True, "mode": "random", "delay_seconds": 10,
                        "backpack_slots": 10, "items": [{"item": "coal", "quantity": 3}],
                        "announcement": "{player}: {rewards}",
                    }, token,
                )
                self.assertEqual(status, 200)
                self.assertEqual(reward["config"]["items"][0]["item_name"], "煤炭")

                status, saved = request(
                    "POST", "/api/gm/teleport_presets/save",
                    {"name": "测试点", "x": 11, "y": 22, "z": 33}, token,
                )
                self.assertEqual(status, 200)
                self.assertEqual(saved["preset"]["name"], "测试点")
                status, presets = request("GET", "/api/gm/teleport_presets", token=token)
                self.assertEqual(status, 200)
                self.assertEqual(presets["presets"][0]["z"], 33.0)
                status, removed = request(
                    "POST", "/api/gm/teleport_presets/remove", {"name": "测试点"}, token,
                )
                self.assertEqual(status, 200)
                self.assertEqual(removed["removed"], "测试点")

                status, invalid = request(
                    "POST",
                    "/api/gm/give_item",
                    {"role": "Captain", "item": "coal", "quantity": 21},
                    token,
                )
                self.assertEqual(status, 400)
                self.assertIn("1 到 20", invalid["error"])

                with mock.patch.object(
                    console,
                    "wait_for_result",
                    return_value={"result": {"success": True, "added": 1, "partial": False}},
                ):
                    status, actual = request(
                        "POST",
                        "/api/gm/give_item",
                        {"role": "Captain", "item": "coal", "quantity": 1},
                        token,
                    )
                self.assertEqual(status, 200)
                self.assertEqual(actual["result"]["added"], 1)

                with mock.patch.object(
                    console,
                    "wait_for_result",
                    return_value={"result": {"success": False, "error": "原生调用失败"}},
                ):
                    status, failure = request(
                        "POST",
                        "/api/gm/teleport_player",
                        {"player": "测试船长", "x": 1, "y": 2, "z": 3},
                        token,
                    )
                self.assertEqual(status, 409)
                self.assertEqual(failure["error"], "原生调用失败")

                with mock.patch.object(console, "wait_for_result", return_value=None):
                    status, queued = request("POST", "/api/gm/open_armory", {}, token)
                self.assertEqual(status, 202)
                self.assertTrue(queued["queued"])
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
