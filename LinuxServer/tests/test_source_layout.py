import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class SourceLayoutTests(unittest.TestCase):
    def test_controller_runs_app_code_with_the_game_root(self):
        for bundle in (ROOT, ROOT / "Docker"):
            spec = importlib.util.spec_from_file_location("layout_controller", bundle / "app" / "dhctl.py")
            controller = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(controller)
            config = {"bind_host": "127.0.0.1", "manager_port": 8800, "gm_port": 9900, "manager_password": "manager123", "gm_password": "console123"}
            with self.subTest(bundle=bundle.name), mock.patch.object(controller, "SERVER_BINARY") as binary, mock.patch.object(
                controller, "python_executable", return_value="python3"
            ), mock.patch.object(controller, "start_service") as start, mock.patch.object(controller, "wait_port"), mock.patch.object(
                controller, "manager_token", return_value="token"
            ), mock.patch.object(controller, "api_request", side_effect=[{"running": True}, {}]), mock.patch.object(controller, "print_access"):
                binary.is_file.return_value = True
                binary.stat.return_value.st_mode = 0o755
                controller.start_all(config)
                for call, filename in zip(start.call_args_list, ("开服器/DreadHungerLinuxManager.py", "GM控制台/gm_console.py")):
                    command = call.args[2]
                    self.assertEqual(Path(command[1]), bundle / "app" / filename)
                    self.assertEqual(Path(command[command.index("--root") + 1]), bundle)

    def test_windows_resources_work_from_source_and_packaged_exe(self):
        script = ROOT.parent / "WindowsRemote" / "app" / "quick_join_client.py"
        if not script.is_file():
            self.skipTest("Windows 源码未包含在独立 Linux 工具包中")
        function = next(node for node in ast.parse(script.read_text(encoding="utf-8")).body if isinstance(node, ast.FunctionDef) and node.name == "resource_path")
        for packaged in (False, True):
            runtime = SimpleNamespace(_MEIPASS="C:/package") if packaged else SimpleNamespace()
            namespace = {"Path": Path, "sys": runtime, "__file__": str(script)}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), "exec"), namespace)
            resource = namespace["resource_path"]
            base = Path("C:/package") if packaged else script.parent
            self.assertEqual(resource("connect_client_win64.js"), base / "connect_client_win64.js")
            assets = base if packaged else script.parent.parent
            self.assertEqual(resource("assets/quick_join_icon.png"), assets / "assets/quick_join_icon.png")


if __name__ == "__main__":
    unittest.main()
