import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("layout_migration", ROOT / "migrate_layout.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class LayoutMigrationTests(unittest.TestCase):
    def test_preserves_config_logs_custom_plugins_and_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "deploy_config.json": b'{"password": "keep-me"}',
                "开服器/manager_config.json": b'{"server_port": 9200}',
                ".gm_runtime/fixed_roles.json": b'{"roles": [1]}',
                "manager_logs/server.log": b"existing log",
                "Linux 插件/custom.js": b"custom plugin",
                ".env": b"keep credentials",
                "app/frida_loader.py": b"updated loader",
                "Engine/game.bin": b"game content",
            }
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value)
            layout.migrate(root)
            for name, value in files.items():
                prefix = "legacy/" if name.startswith("Linux 插件/") else (
                    "" if name.startswith((".env", "app/", "Engine/")) else "data/"
                )
                self.assertEqual((root / (prefix + name)).read_bytes(), value)
            self.assertEqual(layout.migrate(root), 0)

    def test_conflict_fails_before_moving_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "deploy_config.json").write_bytes(b"old config")
            (root / "data" / "deploy_config.json").write_bytes(b"new config")
            (root / "frida_loader.log").write_bytes(b"log")
            with self.assertRaises(FileExistsError):
                layout.migrate(root)
            self.assertEqual((root / "deploy_config.json").read_bytes(), b"old config")
            self.assertEqual((root / "data" / "deploy_config.json").read_bytes(), b"new config")
            self.assertEqual((root / "frida_loader.log").read_bytes(), b"log")


if __name__ == "__main__":
    unittest.main()
