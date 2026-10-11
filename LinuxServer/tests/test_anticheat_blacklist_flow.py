from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loader = load_module("anticheat_blacklist_loader", ROOT / "app/frida_loader.py")
gm = load_module("anticheat_blacklist_console", ROOT / "app/GM控制台/gm_console.py")


class AntiCheatBlacklistFlowTests(unittest.TestCase):
    def deliver(self, root, **overrides):
        payload = {"type": "anti_cheat_blacklist", "player": "同名玩家",
                   "user_id": "EOSPlus:76561198000000000_+_|0123456789ABCDEF0123456789ABCDEF",
                   "reason": "非法图腾建造", **overrides}
        loader.on_message("[服务端]反作弊物资_v2_Linux.js", {"type": "send", "payload": payload}, None, root)
        return root / ".gm_runtime/anti_cheat_blacklist"

    def test_delivery_survives_restart_and_uses_exact_account(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.deliver(root)
            self.assertEqual(len(list(directory.glob("*.json"))), 1)
            self.assertEqual(list(directory.glob("*.tmp")), [])
            console = gm.GMConsole(root, "test")
            # 故意让昵称日志指向另一个账号，自动拉黑只使用原生账号快照。
            console._recent_player_identities = lambda: {"同名玩家": {"steam_id": "76561198000000001"}}
            result = console.get_blacklist()
            self.assertEqual(result["count"], 1)
            entry = result["entries"][0]
            self.assertEqual(entry["steam_id"], "76561198000000000")
            self.assertEqual(entry["eos_id"], "0123456789abcdef0123456789abcdef")
            self.assertEqual(entry["reason_code"], "cheating")
            self.assertEqual(entry["reason"], "非法图腾建造")
            self.assertEqual(list(directory.glob("*.json")), [])
            reopened = gm.GMConsole(root, "test")
            self.assertTrue(reopened.check_blacklist_preflight({"user_id": entry["user_id"]})["local_match"])

    def test_service_loop_processes_without_web_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            server = gm.GMHTTPServer(("127.0.0.1", 0), gm.make_handler(console))
            saved = threading.Event()
            original = gm.atomic_write_json
            def record_save(path, value):
                original(path, value)
                if path == console.blacklist_path:
                    saved.set()
            with mock.patch.object(gm, "atomic_write_json", side_effect=record_save):
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
                thread.start()
                try:
                    self.deliver(root)
                    self.assertTrue(saved.wait(2), "blacklist did not save without HTTP traffic")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            self.assertEqual(json.loads(console.blacklist_path.read_text(encoding="utf-8"))["entries"][0]["reason"], "非法图腾建造")

    def test_duplicate_preserves_manual_record_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            original = console.add_blacklist({"manual": True, "player": "管理员已确认",
                "steam_id": "76561198000000000", "reason": "录像证据", "reason_code": "cheating"})["entry"]
            self.deliver(root)
            self.deliver(root, reason="无限弹药")
            entries = console.get_blacklist()["entries"]
            self.assertEqual(entries, [original])
            console.remove_blacklist({"user_id": original["user_id"]})
            self.assertEqual(console.get_blacklist()["count"], 0)

    def test_invalid_identity_is_rejected_without_blacklisting_by_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            directory = self.deliver(root, user_id="同名玩家")
            self.assertEqual(console.get_blacklist()["count"], 0)
            self.assertEqual(len(list(directory.glob("*.rejected"))), 1)
            self.assertFalse(console.blacklist_path.exists())

    def test_failed_save_keeps_request_for_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            directory = self.deliver(root)
            with mock.patch.object(gm, "atomic_write_json", side_effect=OSError("disk failure")):
                console.process_anti_cheat_blacklist_requests()
            self.assertEqual(len(list(directory.glob("*.json"))), 1)
            console.process_anti_cheat_blacklist_requests()
            self.assertEqual(console.get_blacklist()["count"], 1)
            self.assertEqual(list(directory.glob("*.json")), [])

    def test_corrupt_existing_file_is_preserved_with_pending_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            console.blacklist_path.write_text("damaged existing blacklist", encoding="utf-8")
            directory = self.deliver(root)
            console.process_anti_cheat_blacklist_requests()
            self.assertEqual(console.blacklist_path.read_text(encoding="utf-8"), "damaged existing blacklist")
            self.assertEqual(len(list(directory.glob("*.json"))), 1)
            gm.atomic_write_json(console.blacklist_path, {"version": 1, "entries": []})
            console.process_anti_cheat_blacklist_requests()
            self.assertEqual(console.get_blacklist()["count"], 1)

    def test_only_structured_blacklist_requests_are_queued(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for payload in ("log only", {"type": "gm_result"}, {"type": "log", "user_id": "76561198000000000"}):
                loader.on_message("[服务端]反作弊物资_v2_Linux.js", {"type": "send", "payload": payload}, None, root)
            self.assertFalse((root / ".gm_runtime/anti_cheat_blacklist").exists())

    def test_renamed_plugin_still_routes_the_blacklist_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"type": "anti_cheat_blacklist", "player": "测试用户",
                       "user_id": "76561198000000000", "reason": "无限弹药"}
            loader.on_message("反作弊v2.js", {"type": "send", "payload": payload}, None, root)
            self.assertEqual(gm.GMConsole(root, "test").get_blacklist()["entries"][0]["reason"], "无限弹药")

    def test_three_argument_callback_discovers_install_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"type": "anti_cheat_blacklist", "player": "测试用户",
                       "user_id": "76561198000000000", "reason": "无限弹药"}
            with mock.patch.object(loader, "discover_root", return_value=root) as discover:
                loader.on_message("[服务端]反作弊物资_v2_Linux.js", {"type": "send", "payload": payload}, None)
            discover.assert_called_once_with(None)
            self.assertEqual(gm.GMConsole(root, "test").get_blacklist()["count"], 1)

    def test_install_root_discovery_does_not_treat_app_as_server_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "server"
            source = root / "app/frida_loader.py"
            (root / "DreadHunger").mkdir(parents=True)
            (root / "app/Linux 插件").mkdir(parents=True)
            for cwd in (base, source.parent):
                with self.subTest(cwd=cwd), mock.patch.object(loader, "__file__", str(source)), \
                     mock.patch.object(loader.Path, "cwd", return_value=cwd):
                    self.assertEqual(loader.discover_root(None), root)

    def test_manual_and_automatic_writes_preserve_both_accounts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            console = gm.GMConsole(root, "test")
            self.deliver(root)
            barrier = threading.Barrier(2)
            errors = []
            def automatic():
                barrier.wait()
                console.process_anti_cheat_blacklist_requests()
            def manual():
                try:
                    barrier.wait()
                    console.add_blacklist({"manual": True, "player": "人工拉黑",
                        "steam_id": "76561198000000001", "reason": "录像证据"})
                except Exception as exc:
                    errors.append(exc)
            threads = [threading.Thread(target=automatic), threading.Thread(target=manual)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual({entry["steam_id"] for entry in console.get_blacklist()["entries"]},
                             {"76561198000000000", "76561198000000001"})
