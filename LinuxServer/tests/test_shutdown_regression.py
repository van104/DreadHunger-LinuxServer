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


frida_loader = load_module("frida_loader_under_test", LINUX_SERVER_ROOT / "frida_loader.py")
dhctl_module = load_module("dhctl_under_test", LINUX_SERVER_ROOT / "dhctl.py")
manager_module = load_module(
    "manager_under_test",
    LINUX_SERVER_ROOT / "开服器" / "DreadHungerLinuxManager.py",
)


class MatchEndDetectionTests(unittest.TestCase):
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
