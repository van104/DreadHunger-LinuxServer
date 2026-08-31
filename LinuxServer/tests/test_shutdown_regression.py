from __future__ import annotations

import importlib.util
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
manager_module = load_module(
    "manager_under_test",
    LINUX_SERVER_ROOT / "开服器" / "DreadHungerLinuxManager.py",
)


class MatchEndDetectionTests(unittest.TestCase):
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

        with mock.patch.object(
            manager_module.os,
            "kill",
            side_effect=lambda pid, sig: events.append("game_signaled"),
        ):
            result = manager.stop()

        self.assertEqual(result, {"running": False})
        self.assertLess(events.index("injector_detached"), events.index("game_signaled"))


if __name__ == "__main__":
    unittest.main()
