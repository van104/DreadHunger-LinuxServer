import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = ROOT / "开服器" / "DreadHungerLinuxManager.py"


def load_manager_module():
    spec = importlib.util.spec_from_file_location("dread_hunger_linux_manager_capacity", MANAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ServerManagerCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_manager_module()

    def test_max_players_accepts_64(self):
        config = self.module.normalize_config({"maxplayers": 64}, ROOT)
        self.assertEqual(config["maxplayers"], 64)

    def test_max_players_rejects_values_above_64(self):
        with self.assertRaises(self.module.ManagerError):
            self.module.normalize_config({"maxplayers": 65}, ROOT)


if __name__ == "__main__":
    unittest.main()
