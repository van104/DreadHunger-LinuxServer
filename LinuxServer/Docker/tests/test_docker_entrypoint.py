from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("docker_entrypoint_under_test", ROOT / "app" / "docker_entrypoint.py")
entrypoint = importlib.util.module_from_spec(spec)
with mock.patch.object(sys, "path", [str(ROOT / "app"), *sys.path]):
    spec.loader.exec_module(entrypoint)
dhctl = entrypoint.dhctl


class DockerEntrypointTests(unittest.TestCase):
    def test_config_initializes_once_preserves_settings_and_rejects_invalid_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = root / "开服器"
            console = root / "GM控制台"
            manager.mkdir()
            console.mkdir()
            for source in (ROOT / "config" / "deploy_config.example.json", ROOT / "config" / "gm_announce.example.json"):
                destination = root / source.name if source.name == "deploy_config.example.json" else console / source.name
                destination.write_bytes(source.read_bytes())
            (manager / "manager_config.example.json").write_bytes(
                (ROOT / "config" / "manager_config.example.json").read_bytes()
            )
            settings = {"map": "Approach_Persistent", "server_port": 9200, "maxplayers": 16}
            manager_config = manager / "manager_config.json"
            environment = {
                "DH_PUBLIC_HOST": "example.com",
                "DH_MANAGER_PASSWORD": "manager123",
                "DH_GM_PASSWORD": "console123",
                "DH_GAME_PORT": "9100",
            }
            with mock.patch.object(dhctl, "ROOT", root), mock.patch.object(
                dhctl, "CONFIG_PATH", root / "deploy_config.json"
            ), mock.patch.dict(os.environ, environment, clear=True):
                config = entrypoint.prepare_config()
                self.assertEqual(config["game_port"], 9100)
                self.assertEqual(json.loads(manager_config.read_text(encoding="utf-8"))["server_port"], 9100)
                manager_config.write_text(json.dumps(settings), encoding="utf-8")
                announcement = console / "gm_announce.json"
                announcement.write_text('{"message": "custom announcement"}', encoding="utf-8")
                config = entrypoint.prepare_config()
                self.assertEqual(config["game_port"], 9200)
                self.assertEqual(json.loads(manager_config.read_text(encoding="utf-8")), settings)
                self.assertEqual(json.loads(announcement.read_text(encoding="utf-8"))["message"], "custom announcement")
                original = dhctl.CONFIG_PATH.read_bytes()
                for overrides in ({"DH_GM_PASSWORD": "short"}, {"DH_GM_PASSWORD": "manager123"}, {"DH_GM_PORT": "70000"}, {"DH_GM_PORT": "8800"}):
                    with mock.patch.dict(os.environ, overrides):
                        with self.assertRaises(dhctl.ControlError):
                            entrypoint.prepare_config()
                    self.assertEqual(dhctl.CONFIG_PATH.read_bytes(), original)

    def test_first_start_requires_explicit_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(dhctl, "CONFIG_PATH", Path(directory) / "deploy_config.json"), mock.patch.dict(
                os.environ, {}, clear=True
            ):
                with self.assertRaisesRegex(dhctl.ControlError, "DH_MANAGER_PASSWORD"):
                    entrypoint.prepare_config()
                self.assertFalse(dhctl.CONFIG_PATH.exists())

    def test_sigterm_runs_existing_stop_flow_after_start(self):
        handlers = {}
        events = []
        with mock.patch.object(entrypoint.signal, "signal", side_effect=lambda sig, handler: handlers.update({sig: handler})), mock.patch.object(
            dhctl, "start_all", side_effect=lambda config: (events.append("start"), handlers[signal.SIGTERM](signal.SIGTERM, None))
        ), mock.patch.object(dhctl, "stop_all", side_effect=lambda config: events.append("stop")):
            entrypoint.run_foreground({})
        self.assertEqual(events, ["start", "stop"])

    def test_partial_start_or_panel_exit_cleans_up_and_fails(self):
        stopping = mock.Mock(spec=threading.Event)
        stopping.wait.return_value = False
        for failure in (dhctl.ControlError("startup failed"), None):
            with self.subTest(failure=failure), mock.patch.object(entrypoint.signal, "signal"), mock.patch.object(
                entrypoint.threading, "Event", return_value=stopping
            ), mock.patch.object(dhctl, "start_all", side_effect=failure), mock.patch.object(
                dhctl, "read_service_pid", return_value=None
            ), mock.patch.object(dhctl, "stop_all") as stop:
                with self.assertRaises(dhctl.ControlError):
                    entrypoint.run_foreground({})
                stop.assert_called_once_with({})


if __name__ == "__main__":
    unittest.main()
