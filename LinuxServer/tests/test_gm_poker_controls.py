from pathlib import Path
import unittest


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "GM控制台_Linux.js"
CONSOLE_PATH = LINUX_SERVER_ROOT / "GM控制台" / "gm_console.py"


class GMPokerControlSourceTests(unittest.TestCase):
    def test_skip_poker_uses_native_match_start_pipeline(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        self.assertIn("base.add(0x43360E0)", source)
        self.assertIn("base.add(0x5A1B978)", source)
        self.assertIn("base.add(0x2730050)", source)
        self.assertIn("base.add(0x26CB250)", source)
        self.assertIn("base.add(0x4335A40)", source)
        start = source.index("function forceStartMatchFromPoker")
        end = source.index("function gmSkipPoker", start)
        pipeline = source[start:end]
        self.assertLess(pipeline.index("AGameMode_SetMatchState"), pipeline.index("ADH_RoleDealer_EndGame"))
        self.assertLess(pipeline.index("ADH_RoleDealer_EndGame"), pipeline.index("ADH_GameMode_RandomizeThralls"))
        self.assertLess(pipeline.index("ADH_GameMode_RandomizeThralls"), pipeline.index("AGameMode_StartMatch"))
        self.assertIn("设置 PokerGame 状态失败", pipeline)
        self.assertIn("gm.add(0x488).writeU8(1)", pipeline)
        self.assertIn("hasMatchStarted(gm)", pipeline)

    def test_end_game_starts_pregame_match_before_natural_settlement(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        start = source.index("function gmEndGame")
        end = source.index("function gmOpenArmory", start)
        handler = source[start:end]
        self.assertIn("forceStartMatchFromPoker", handler)
        self.assertIn("started_from_poker", handler)
        self.assertIn("gs.add(0x514).readU8()", handler)

    def test_skip_poker_api_and_confirmation_are_exposed(self):
        plugin_source = PLUGIN_PATH.read_text(encoding="utf-8")
        console_source = CONSOLE_PATH.read_text(encoding="utf-8")
        self.assertIn("'skip_poker':", plugin_source)
        self.assertIn('"skip_poker"', console_source)
        self.assertIn("confirmSkipPoker", console_source)
        self.assertIn("跳过打牌并开始游戏", console_source)

    def test_match_state_commands_run_from_game_mode_tick(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        self.assertIn("base.add(0x4336360)", source)
        self.assertIn("PendingGameThreadCommands", source)
        self.assertIn("Interceptor.attach(AGameMode_Tick", source)
        self.assertIn("requiresGameThread(cmd.action)", source)


if __name__ == "__main__":
    unittest.main()
