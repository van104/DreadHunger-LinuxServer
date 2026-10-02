from pathlib import Path
from types import SimpleNamespace
import json
import socket
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import quick_join_client as quick_join


class QuickJoinTests(unittest.TestCase):
    def test_bridge_waits_for_a_complete_utf16_response(self):
        response = ('{"success":true,"text":"' + "公告" * 2100 + '"}').encode("utf-16-le")
        client = MagicMock()
        client.recv.side_effect = [response[:17], response[17:4096], response[4096:]]
        with patch.object(quick_join.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = client
            result = quick_join.send_client_bridge_command({"op": "sendMessage", "msg": "公告"})
        self.assertEqual(result["text"], "公告" * 2100)

    def test_bridge_does_not_report_missing_or_invalid_ack_as_success(self):
        for reply in (socket.timeout(), b"", "not JSON".encode("utf-16-le")):
            with self.subTest(reply=reply):
                client = MagicMock()
                client.recv.side_effect = [reply, b""]
                with patch.object(quick_join.socket, "create_connection") as connect:
                    connect.return_value.__enter__.return_value = client
                    with self.assertRaises(OSError):
                        quick_join.send_client_bridge_command({"op": "sendMessage"})

    def test_bridge_preserves_rejection(self):
        client = MagicMock()
        client.recv.return_value = '{"success":false,"error":"not ready"}'.encode("utf-16-le")
        with patch.object(quick_join.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = client
            with self.assertRaisesRegex(OSError, "not ready"):
                quick_join.send_client_bridge_command({"op": "sendMessage"})

    def test_connect_without_reply_waits_for_game_logs_instead_of_resending(self):
        for reply in (b"", socket.timeout(), ConnectionResetError("reply closed")):
            with self.subTest(reply=reply):
                client = MagicMock()
                client.recv.side_effect = [reply]
                with patch.object(quick_join.socket, "create_connection") as connect:
                    connect.return_value.__enter__.return_value = client
                    self.assertEqual(quick_join.send_client_bridge_command({"op": "Connect"}), {})
                client.sendall.assert_called_once()

    def test_connect_still_rejects_unsent_commands_and_explicit_rejections(self):
        with patch.object(quick_join.socket, "create_connection", side_effect=ConnectionRefusedError()):
            with self.assertRaises(OSError):
                quick_join.send_client_bridge_command({"op": "Connect"})
        client = MagicMock()
        client.recv.return_value = '{"success":false,"error":"not ready"}'.encode("utf-16-le")
        with patch.object(quick_join.socket, "create_connection") as connect:
            connect.return_value.__enter__.return_value = client
            with self.assertRaisesRegex(OSError, "not ready"):
                quick_join.send_client_bridge_command({"op": "Connect"})

    def make_app(self):
        app = quick_join.QuickJoinApp.__new__(quick_join.QuickJoinApp)
        app.announcement_enabled_var = SimpleNamespace(get=lambda: True)
        app.announcement_status_var = MagicMock()
        app.blacklist_status_var = MagicMock()
        app.status_var = MagicMock()
        app.stop_button = MagicMock()
        app._announcement_value = lambda: "完整公告\n第二行"
        app._join_active = True
        app._join_generation = 1
        app._pre_join_announcement_handled = False
        app.root = MagicMock()
        app.runner = MagicMock()
        return app

    def test_manual_and_blacklist_notices_keep_overlay_when_native_channel_fails(self):
        app = self.make_app()
        with patch.object(quick_join, "send_client_announcement", side_effect=OSError("not ready")), \
                patch.object(quick_join, "launch_game_notice") as overlay:
            self.assertTrue(app._send_current_announcement(False))
            self.assertEqual(overlay.call_args.args[0], "完整公告\n第二行")
            self.assertTrue(app._show_lobby_notice("发现黑名单用户：测试", 6500, True))
            overlay.assert_called_with("发现黑名单用户：测试", 6500, True)

    def test_confirmed_native_notice_uses_the_game_text_without_overlay(self):
        app = self.make_app()
        with patch.object(quick_join, "send_client_announcement"), \
                patch.object(quick_join, "launch_game_notice") as overlay:
            self.assertTrue(app._send_current_announcement(False))
            overlay.assert_not_called()

    def test_native_notice_requires_a_matching_game_thread_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "DreadHunger-Win64-Shipping.exe"
            def reply(_delay):
                command = json.loads((game.parent / "quick_join_announce.json").read_text(encoding="utf-8"))
                self.assertEqual(command["text"], "游戏原生公告\n第二行")
                (game.parent / "quick_join_announce_result.json").write_text(
                    json.dumps({"id": command["id"], "success": True}), encoding="utf-8"
                )
            with patch.object(quick_join, "running_game_executable", return_value=game), \
                    patch.object(quick_join.time, "sleep", side_effect=reply), \
                    patch.object(quick_join, "send_client_bridge_command", side_effect=AssertionError("legacy queue used")):
                quick_join.send_client_announcement("游戏原生公告\n第二行")

    def test_native_notice_does_not_accept_a_previous_messages_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "DreadHunger-Win64-Shipping.exe"
            (game.parent / "quick_join_announce_result.json").write_text(
                '{"id":"old","success":true}', encoding="utf-8"
            )
            with patch.object(quick_join, "running_game_executable", return_value=game), \
                    patch.object(quick_join.time, "sleep"), \
                    patch.object(quick_join.time, "monotonic", side_effect=[0, 0, 3]), \
                    patch.object(quick_join, "send_client_bridge_command", side_effect=AssertionError("legacy queue used")):
                with self.assertRaises(OSError):
                    quick_join.send_client_announcement("公告")

    def test_failed_overlay_does_not_abort_cloud_query(self):
        app = self.make_app()
        with patch.object(quick_join, "send_client_announcement", side_effect=OSError("not ready")), \
                patch.object(quick_join, "launch_game_notice", side_effect=OSError("overlay failed")):
            app._announce_checking_and_query("127.0.0.1:9100", 1, False)
        app.runner.submit.assert_called_once()
        self.assertTrue(app._join_active)

    def test_automatic_announcement_uses_the_shared_visible_notice_path(self):
        app = self.make_app()
        app._blacklist_warning_text = ""
        with patch.object(app, "_send_current_announcement", return_value=True) as send:
            app._finish_pre_join_announcement("127.0.0.1:9100", 1, False)
        send.assert_called_once_with(require_enabled=False, text="完整公告\n第二行")
        self.assertEqual(app.root.after.call_args.args[0], quick_join.PRE_JOIN_ANNOUNCEMENT_DELAY_MS)

    def test_blacklist_check_shows_full_announcement_before_query_and_does_not_repeat_it(self):
        app = self.make_app()
        announcement = "第一行\r\n" + "告" * 495
        app._announcement_value = lambda: announcement
        data = {"local_identity_available": True, "lobby_matches": [], "lobby_stale": False}
        events = []
        app.runner.submit.side_effect = lambda *args: events.append("query")
        with patch.object(quick_join, "send_client_announcement", side_effect=events.append), \
                patch.object(quick_join, "launch_game_notice") as overlay:
            app._announce_checking_and_query("127.0.0.1:9100", 1, False)
            self.assertEqual(events, ["正在进入游戏，检查黑名单中……\n" + announcement, "query"])
            app._blacklist_check_ok(data, "127.0.0.1:9100", 1, False)
        self.assertEqual(events, [
            "正在进入游戏，检查黑名单中……\n" + announcement, "query", "检测完成，未发现黑名单用户。",
        ])
        overlay.assert_not_called()
        self.assertTrue(app._pre_join_announcement_handled)
        self.assertFalse(app._handle_pre_join_announcement())

    def test_disabled_announcement_only_shows_checking_notice_before_query(self):
        app = self.make_app()
        app.announcement_enabled_var = SimpleNamespace(get=lambda: False)
        with patch.object(quick_join, "send_client_announcement") as send:
            app._announce_checking_and_query("127.0.0.1:9100", 1, False)
        send.assert_called_once_with("正在进入游戏，检查黑名单中……")
        app.runner.submit.assert_called_once()

    def test_user_announcement_still_rejects_more_than_500_characters(self):
        app = self.make_app()
        app._announcement_value = lambda: "告" * 501
        with patch.object(quick_join, "send_client_announcement") as send:
            with self.assertRaisesRegex(ValueError, "500"):
                app._send_current_announcement(False)
        send.assert_not_called()

    def test_blacklisted_player_still_stops_connection_when_native_notice_fails(self):
        app = self.make_app()
        data = {"local_match": {"name": "测试", "reason": "作弊", "steam_id": "76561190000000001"}}
        with patch.object(quick_join, "send_client_announcement", side_effect=OSError("not ready")), \
                patch.object(quick_join, "launch_game_notice") as overlay:
            app._blacklist_check_ok(data, "127.0.0.1:9100", 1, False)
        self.assertFalse(app._join_active)
        app.root.after.assert_not_called()
        self.assertIn("发现黑名单用户", overlay.call_args.args[0])

    def test_running_game_takes_precedence_over_stale_saved_installation(self):
        app = self.make_app()
        app.exe_var = MagicMock()
        app.exe_var.get.return_value = "E:/Dread Hunger/DreadHunger.exe"
        running = Path("E:/SteamLibrary/steamapps/common/Dread Hunger/DreadHunger/Binaries/Win64/DreadHunger-Win64-Shipping.exe")
        with patch.object(quick_join, "running_game_executable", return_value=running, create=True):
            self.assertEqual(app._game_executable(), running)
        app.exe_var.set.assert_called_once_with(str(running))

    def test_successful_join_cancels_callbacks_even_when_the_match_ends(self):
        app = self.make_app()
        app._join_log_offset = 0
        app._join_attempt_started = 0
        app._join_load_seen_at = None
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "game.log"
            log.write_text("LogLoad: Took 1 seconds to LoadMap(/Game/Maps/Departure_Persistent)\n", encoding="utf-8")
            with patch.object(quick_join, "GAME_LOG", log), \
                    patch.object(quick_join, "process_is_running", return_value=True), \
                    patch.object(quick_join.time, "monotonic", return_value=31), \
                    patch.object(quick_join, "send_connector_command") as connect:
                app._poll_join_result("127.0.0.1:9100", 1)
                self.assertFalse(app._join_active)
                self.assertEqual(app._join_generation, 2)
                log.write_text("NetworkFailure: Host closed the connection.\nLogLoad: Game class is 'BP_LobbyGameMode_C'\n", encoding="utf-8")
                app._poll_join_result("127.0.0.1:9100", 1)
                app._send_join_attempt("127.0.0.1:9100", 1, True)
        connect.assert_not_called()
        app.root.after.assert_not_called()

    def test_slow_map_load_does_not_schedule_another_connection(self):
        app = self.make_app()
        app._join_log_offset = 0
        app._join_attempt_started = 0
        app._join_load_seen_at = None
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "game.log"
            log.write_text("LogLoad: LoadMap: server/Game/Maps/Departure_Persistent\n", encoding="utf-8")
            with patch.object(quick_join, "GAME_LOG", log), \
                    patch.object(quick_join, "process_is_running", return_value=True), \
                    patch.object(quick_join.time, "monotonic", side_effect=[31, 60]), \
                    patch.object(app, "_schedule_safe_retry") as retry:
                app._poll_join_result("127.0.0.1:9100", 1)
                app._poll_join_result("127.0.0.1:9100", 1)
        retry.assert_not_called()
        self.assertTrue(app._join_active)

    def test_join_finishing_while_waiting_to_retry_cancels_the_retry(self):
        app = self.make_app()
        app._join_attempt = 1
        app._retry_requires_fresh_lobby = True
        app._retry_log_offset = 0
        app._lobby_ready_since = None
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "game.log"
            log.write_text("LogNet: Join succeeded: Player\nLogLoad: Game class is 'BP_LobbyGameMode_C'\n", encoding="utf-8")
            with patch.object(quick_join, "GAME_LOG", log), \
                    patch.object(quick_join, "process_is_running", return_value=True), \
                    patch.object(quick_join, "send_connector_command") as connect:
                app._send_join_attempt("127.0.0.1:9100", 1, True)
        self.assertFalse(app._join_active)
        self.assertEqual(app._join_generation, 2)
        connect.assert_not_called()
        app.root.after.assert_not_called()

    def test_log_completion_uses_the_latest_success_or_failure(self):
        complete = "LogLoad: Took 1 seconds to LoadMap(/Game/Maps/Departure_Persistent)\n"
        failure = "NetworkFailure: Host closed the connection.\n"
        self.assertTrue(quick_join.log_reports_join_complete(failure + complete))
        self.assertFalse(quick_join.log_reports_join_complete(complete + failure))
        app = self.make_app()
        app._join_log_offset = 0
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "game.log"
            log.write_text(complete + failure, encoding="utf-8")
            with patch.object(quick_join, "GAME_LOG", log), \
                    patch.object(quick_join, "process_is_running", return_value=True), \
                    patch.object(app, "_schedule_safe_retry") as retry:
                app._poll_join_result("127.0.0.1:9100", 1)
        retry.assert_called_once()
        self.assertTrue(app._join_active)


if __name__ == "__main__":
    unittest.main()
