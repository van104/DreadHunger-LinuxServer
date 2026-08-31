from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gm_module = load_module(
    "gm_console_blacklist_under_test",
    LINUX_SERVER_ROOT / "GM控制台" / "gm_console.py",
)


class BlacklistTests(unittest.TestCase):
    def make_console(self, root: Path):
        game_log = root / "DreadHunger" / "Saved" / "Logs" / "DreadHunger.log"
        game_log.parent.mkdir(parents=True)
        game_log.write_text(
            "[2026.08.30-05.25.08:873][953]LogNet: Login request: "
            "?Name=景岗山王二 userId: "
            "EOSPlus:76561198661845743_+_|0002307d0c5f4e97911fe1d0a47231fe "
            "platform: EOSPlus\n",
            encoding="utf-8",
        )
        runtime_dir = root / gm_module.GM_RUNTIME_DIR
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / gm_module.PLAYER_LIST_FILE).write_text(
            json.dumps(
                {"timestamp": 1, "count": 1, "players": [{"name": "景岗山王二", "role": "厨师", "index": 0}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return gm_module.GMConsole(root, "test")

    def test_player_identity_is_enriched_from_login_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            player = console.get_players()["players"][0]
            self.assertEqual(player["steam_id"], "76561198661845743")
            self.assertEqual(player["eos_id"], "0002307d0c5f4e97911fe1d0a47231fe")
            self.assertEqual(
                player["user_id"],
                "76561198661845743_+_|0002307d0c5f4e97911fe1d0a47231fe",
            )

    def test_add_check_and_remove_blacklist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            added = console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "quit_after_death", "reason": ""}
            )
            self.assertEqual(added["entry"]["reason"], "死一次退")
            self.assertTrue((Path(temp_dir) / gm_module.BLACKLIST_FILE).is_file())

            check = console.check_lobby_blacklist()
            self.assertEqual(check["match_count"], 1)
            self.assertEqual(check["matches"][0]["name"], "景岗山王二")
            self.assertEqual(check["matches"][0]["reason"], "死一次退")

            removed = console.remove_blacklist({"user_id": added["entry"]["user_id"]})
            self.assertEqual(removed["entry"]["name"], "景岗山王二")
            self.assertEqual(console.get_blacklist()["count"], 0)

    def test_custom_reason_overrides_preset_and_duplicate_updates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "cheating", "reason": "录像确认开挂"}
            )
            console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "griefing", "reason": ""}
            )
            blacklist = console.get_blacklist()
            self.assertEqual(blacklist["count"], 1)
            self.assertEqual(blacklist["entries"][0]["reason"], "恶意摆烂")

    def test_manual_add_offline_with_separate_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = self.make_console(root)
            (root / gm_module.GM_RUNTIME_DIR / gm_module.PLAYER_LIST_FILE).write_text(
                json.dumps({"timestamp": 2, "count": 0, "players": []}),
                encoding="utf-8",
            )
            entry = console.add_blacklist(
                {
                    "manual": True,
                    "player": "离线玩家",
                    "steam_id": "76561198661845743",
                    "user_id": "0002307d0c5f4e97911fe1d0a47231fe",
                    "reason_code": "cheating",
                    "reason": "录像确认开挂",
                }
            )["entry"]
            self.assertEqual(entry["user_id"], "76561198661845743_+_|0002307d0c5f4e97911fe1d0a47231fe")
            self.assertEqual(entry["platform"], "EOSPlus")
            self.assertEqual(console.get_blacklist()["count"], 1)

    def test_manual_add_accepts_full_id_and_merges_partial_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            first = console.add_blacklist(
                {
                    "manual": True,
                    "player": "旧名字",
                    "steam_id": "76561198661845743",
                    "reason_code": "griefing",
                    "reason": "",
                }
            )["entry"]
            second = console.add_blacklist(
                {
                    "manual": True,
                    "player": "新名字",
                    "user_id": "EOSPlus:76561198661845743_+_|0002307d0c5f4e97911fe1d0a47231fe",
                    "reason_code": "cheating",
                    "reason": "确认作弊",
                }
            )["entry"]
            self.assertEqual(console.get_blacklist()["count"], 1)
            self.assertEqual(second["created_at"], first["created_at"])
            self.assertEqual(second["eos_id"], "0002307d0c5f4e97911fe1d0a47231fe")
            self.assertIn("旧名字", second["aliases"])

    def test_manual_add_rejects_missing_malformed_and_conflicting_ids(self):
        invalid_payloads = [
            {"manual": True, "player": "离线玩家", "reason_code": "other", "reason": "测试"},
            {"manual": True, "player": "离线玩家", "steam_id": "123", "reason_code": "other", "reason": "测试"},
            {"manual": True, "player": "离线玩家", "user_id": "not-an-id", "reason_code": "other", "reason": "测试"},
            {"manual": True, "player": "离线玩家", "steam_id": 76561198661845743, "reason_code": "other", "reason": "测试"},
            {
                "manual": True,
                "player": "离线玩家",
                "steam_id": "76561198000000000",
                "user_id": "76561198661845743_+_|0002307d0c5f4e97911fe1d0a47231fe",
                "reason_code": "other",
                "reason": "测试",
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temp_dir:
                console = self.make_console(Path(temp_dir))
                with self.assertRaises(ValueError):
                    console.add_blacklist(payload)
                self.assertEqual(console.get_blacklist()["count"], 0)

    def test_read_only_check_token_is_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            token = console.get_blacklist()["check_token"]
            self.assertTrue(token)
            self.assertTrue(console.valid_blacklist_check_token(token))
            self.assertFalse(console.valid_blacklist_check_token("invalid"))
            self.assertTrue((Path(temp_dir) / gm_module.BLACKLIST_CHECK_TOKEN_FILE).is_file())

    def test_historical_entry_can_be_edited_without_player_online(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            console = self.make_console(root)
            added = console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "quit_after_death", "reason": ""}
            )["entry"]
            (root / gm_module.GM_RUNTIME_DIR / gm_module.PLAYER_LIST_FILE).write_text(
                json.dumps({"timestamp": 2, "count": 0, "players": []}),
                encoding="utf-8",
            )

            updated = console.update_blacklist(
                {
                    "user_id": added["user_id"],
                    "name": "景岗山王二（录像）",
                    "reason_code": "cheating",
                    "reason": "录像确认使用外挂",
                }
            )["entry"]
            self.assertEqual(updated["name"], "景岗山王二（录像）")
            self.assertEqual(updated["reason"], "录像确认使用外挂")
            self.assertIn("景岗山王二", updated["aliases"])
            self.assertEqual(console.get_blacklist()["count"], 1)

    def test_preflight_checks_local_identity_before_joining(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            entry = console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "cheating", "reason": "测试本人拦截"}
            )["entry"]
            result = console.check_blacklist_preflight({"user_id": entry["user_id"]})
            self.assertTrue(result["local_identity_available"])
            self.assertEqual(result["local_match"]["steam_id"], "76561198661845743")
            self.assertEqual(result["local_match"]["reason"], "测试本人拦截")

    def test_preflight_still_checks_lobby_without_local_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            console = self.make_console(Path(temp_dir))
            console.add_blacklist(
                {"player": "景岗山王二", "reason_code": "griefing", "reason": ""}
            )
            result = console.check_blacklist_preflight({"user_id": ""})
            self.assertFalse(result["local_identity_available"])
            self.assertIsNone(result["local_match"])
            self.assertEqual(result["lobby_match_count"], 1)


if __name__ == "__main__":
    unittest.main()
