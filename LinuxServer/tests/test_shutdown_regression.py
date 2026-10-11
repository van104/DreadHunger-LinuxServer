from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
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


frida_loader = load_module("frida_loader_under_test", LINUX_SERVER_ROOT / "app" / "frida_loader.py")
dhctl_module = load_module("dhctl_under_test", LINUX_SERVER_ROOT / "app" / "dhctl.py")
manager_module = load_module(
    "manager_under_test",
    LINUX_SERVER_ROOT / "app" / "开服器" / "DreadHungerLinuxManager.py",
)


class MatchEndDetectionTests(unittest.TestCase):
    def test_anticheat_versions_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            v1 = directory / "[服务端]反作弊物资_Linux.js"
            v2 = directory / "[服务端]反作弊物资_v2_Linux.js"
            v1.write_text("v1", encoding="utf-8")
            other = directory / "[服务端]GM控制台_Linux.js"
            other.write_text("gm", encoding="utf-8")
            disabled = v2.with_suffix(".js.disabled")
            disabled.write_text("v2", encoding="utf-8")
            self.assertEqual(set(frida_loader.select_plugin_paths(directory)), {v1, other})
            disabled.rename(v2)
            self.assertEqual(set(frida_loader.select_plugin_paths(directory)), {v2, other})
            v2.rename(disabled)
            self.assertEqual(set(frida_loader.select_plugin_paths(directory)), {v1, other})

    def test_plugin_source_receives_actual_install_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "custom install"
            root.mkdir()
            script = root / "plugin.js"
            script.write_text("send('ok');\n", encoding="utf-8")

            source = frida_loader.prepare_plugin_source(script, root)

            self.assertIn('var DH_LINUX_ROOT = ', source)
            self.assertIn(json.dumps(str(root), ensure_ascii=False), source)
            self.assertTrue(source.endswith("send('ok');\n"))

    def test_only_new_match_end_log_triggers_detach(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "server.log"
            marker = b"Match State Changed from InProgress to WaitingPostMatch"
            log_path.write_bytes(marker + b"\nold match\n")

            offsets = frida_loader.capture_log_offsets(root, 999999)
            self.assertFalse(frida_loader.match_end_detected(root, 999999, offsets))

            with log_path.open("ab") as log_file:
                log_file.write(marker + b"\ncurrent match\n")
            self.assertTrue(frida_loader.match_end_detected(root, 999999, offsets))


class NativeAntiCheatRelayTests(unittest.TestCase):
    def test_partial_utf8_line_is_delivered_once_when_complete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "server.log"
            path.write_bytes(b"")
            offsets = frida_loader.capture_log_offsets(root, 999999)
            event = "LogDHAntiCheat: Warning: 测试用户 was found to be using the cheat [Infinite Ammo]\n".encode("utf-8")
            split = event.index("测试".encode("utf-8")) + 1
            path.write_bytes(event[:split])
            self.assertEqual(frida_loader.scan_server_log(root, 999999, offsets), (False, []))
            self.assertEqual(offsets[path], 0)
            with path.open("ab") as stream:
                stream.write(event[split:])
            _, events = frida_loader.scan_server_log(root, 999999, offsets)
            self.assertEqual([event["player_name"] for event in events], ["测试用户"])
            self.assertEqual(frida_loader.scan_server_log(root, 999999, offsets), (False, []))

    def test_read_failure_does_not_advance_cursor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "server.log"
            path.write_bytes(b"")
            offsets = frida_loader.capture_log_offsets(root, 999999)
            path.write_bytes(b"LogDHAntiCheat: Warning: player was found to be using the cheat [Fast Reloads]\n")
            with mock.patch("builtins.open", side_effect=OSError("temporary read failure")):
                self.assertEqual(frida_loader.scan_server_log(root, 999999, offsets), (False, []))
            self.assertEqual(offsets[path], 0)
            self.assertEqual(len(frida_loader.scan_server_log(root, 999999, offsets)[1]), 1)

    def test_truncation_and_capped_read_discard_leading_fragment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "server.log"
            line = b"LogDHAntiCheat: Warning: player was found to be using the cheat [Chainsaw Melee]\n"
            path.write_bytes(b"old match\n" * 30)
            offsets = frida_loader.capture_log_offsets(root, 999999)
            path.write_bytes(line)
            self.assertEqual(len(frida_loader.scan_server_log(root, 999999, offsets)[1]), 1)
            offsets[path] = 0
            # 恰好从半行中的 LogDHAntiCheat 开始读取；不能把这一碎片作为事件。
            path.write_bytes(b"x" * 1000 + line + b"x" * (512 * 1024 - 2 * len(line)) + b"\n" + line)
            events = frida_loader.scan_server_log(root, 999999, offsets)[1]
            self.assertEqual(len(events), 1)

    def test_manager_exposes_the_linux_game_log_that_the_loader_scans(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "DreadHunger" / "log" / "DreadHunger.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("LogDHAntiCheat: Warning: test\n", encoding="utf-8")

            manager = object.__new__(manager_module.ServerManager)
            manager.root = root
            manager.state_path = root / "server_state.json"

            self.assertIn(log_path, manager.log_paths())

    def test_only_new_native_anti_cheat_logs_are_forwarded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log_path = root / "server.log"
            log_path.write_text(
                "LogDHAntiCheat: Warning: 上一局玩家 was found to be using the cheat [Teleporting]\n",
                encoding="utf-8",
            )
            offsets = frida_loader.capture_log_offsets(root, 999999)
            start_offset = log_path.stat().st_size

            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(
                    "LogDHAntiCheat: Warning: 测试用户 was found to be using the cheat "
                    "[Long Range Interacts] with a multiplier of [3.5]\n"
                )

            match_ended, events = frida_loader.scan_server_log(root, 999999, offsets)
            self.assertFalse(match_ended)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "%s:%d:0" % (str(log_path), start_offset))
            self.assertEqual(events[0]["player_name"], "测试用户")
            self.assertEqual(events[0]["cheat_type"], "Long Range Interacts")
            self.assertEqual(events[0]["detail"], "with a multiplier of [3.5]")

            frida_loader.write_anti_cheat_events(root, events, reset=True)
            payload = json.loads((root / ".gm_runtime" / "anti_cheat_events.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["events"], events)

            _, repeated_events = frida_loader.scan_server_log(root, 999999, offsets)
            self.assertEqual(repeated_events, [])


class StopOrderTests(unittest.TestCase):
    def test_dhctl_uses_actual_manager_game_port(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            deploy_path = root / "deploy_config.json"
            deploy_path.write_text(
                json.dumps(
                    {
                        "public_host": "example.com",
                        "bind_host": "0.0.0.0",
                        "manager_port": 8800,
                        "gm_port": 9900,
                        "game_port": 9100,
                        "manager_password": "manager123",
                        "gm_password": "console123",
                    }
                ),
                encoding="utf-8",
            )
            manager_dir = root / "开服器"
            manager_dir.mkdir()
            (manager_dir / "manager_config.json").write_text('{"server_port": 9200}', encoding="utf-8")

            with mock.patch.object(dhctl_module, "ROOT", root), mock.patch.object(
                dhctl_module, "CONFIG_PATH", deploy_path
            ):
                config = dhctl_module.load_config()

            self.assertEqual(config["game_port"], 9200)

    def test_saving_server_port_updates_deploy_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            deploy_path = root / "deploy_config.json"
            deploy_path.write_text('{"game_port": 9100, "manager_password": "secret123"}', encoding="utf-8")

            manager = object.__new__(manager_module.ServerManager)
            manager.lock = threading.RLock()
            manager.root = root
            manager.config_path = root / "manager_config.json"
            manager.config = manager_module.normalize_config({}, root)

            manager.save_config({"server_port": 9200})

            deploy = json.loads(deploy_path.read_text(encoding="utf-8"))
            self.assertEqual(deploy["game_port"], 9200)
            self.assertEqual(deploy["manager_password"], "secret123")

    def test_zombie_process_is_not_reported_as_alive(self):
        manager = object.__new__(manager_module.ServerManager)
        with mock.patch.object(manager_module.Path, "is_file", return_value=True), mock.patch.object(
            manager_module.Path,
            "read_text",
            return_value="12345 (runuser) Z 1 2 3",
        ), mock.patch.object(manager_module.os, "kill") as kill:
            self.assertFalse(manager._pid_alive(12345))
        kill.assert_not_called()

    def test_injector_is_stopped_before_game_signal(self):
        events = []

        manager = object.__new__(manager_module.ServerManager)
        manager.lock = threading.RLock()
        manager.process = None
        manager.log_handle = None
        manager._refresh_process = lambda: None
        manager._current_pid = lambda: 12345
        manager._pid_matches = lambda pid: True
        manager._stop_injector = lambda: events.append("injector_detached")
        manager._pid_alive = lambda pid: False
        manager._clear_state = lambda: events.append("state_cleared")
        manager.status = lambda: {"running": False}

        signal_method = "killpg" if manager_module.os.name == "posix" else "kill"
        with mock.patch.object(
            manager_module.os,
            signal_method,
            side_effect=lambda pid, sig: events.append("game_signaled"),
        ):
            result = manager.stop()

        self.assertEqual(result, {"running": False})
        self.assertLess(events.index("injector_detached"), events.index("game_signaled"))


if __name__ == "__main__":
    unittest.main()
