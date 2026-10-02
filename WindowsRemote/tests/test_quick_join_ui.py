from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import DEFAULT, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import quick_join_client as quick_join


class QuickJoinUiTests(unittest.TestCase):
    def test_navigation_controls_and_legacy_settings(self):
        settings = {
            "address": "alpha.example.org:9100",
            "game_executable": "C:/Games/Dread Hunger/DreadHunger.exe",
            "history": ["alpha.example.org:9100", "beta.example.org:9101"],
            "announcement_enabled": True,
            "announcement_text": "告" * 250 + "\n" + "告" * 249,
            "blacklist_check_enabled": True,
            "fixed_roles_enabled": True,
            "gm_api_port": "9901",
            "blacklist_check_token": "abcdefghijklmnopqrstuvwxyz012345",
        }
        quick_join.enable_windows_dpi_awareness()
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        with patch.object(quick_join, "load_settings", return_value=settings), \
                patch.object(quick_join, "save_settings") as save, \
                patch.object(quick_join, "AsyncRunner"), \
                patch.multiple(
                    quick_join.QuickJoinApp,
                    _refresh_process_state=DEFAULT,
                    join_running_game=DEFAULT,
                    stop_auto_join=DEFAULT,
                    launch_with_address=DEFAULT,
                    publish_announcement=DEFAULT,
                    choose_executable=DEFAULT,
                ) as callbacks:
            app = quick_join.QuickJoinApp(root)
            root.deiconify()
            root.update()
            self.assertIn("恐惧饥饿进服器", root.title())
            self.assertIn("2.0.0", root.title())
            self.assertEqual(len(app.pages), 4)
            self.assertEqual(len(app.nav_buttons), 4)
            self.assertEqual(app._announcement_value(), settings["announcement_text"])
            self.assertEqual(app._settings_payload(), settings)
            self.assertLessEqual(app.connect_body.winfo_reqheight(), app.connect_canvas.winfo_height())
            self.assertLessEqual(app.connect_canvas.winfo_height() - app.connect_body.winfo_reqheight(), 24)
            root.geometry("%dx700" % root.winfo_width())
            root.update()
            self.assertLess(app.connect_canvas.winfo_height(), app.connect_body.winfo_reqheight())
            app.address_entry.event_generate("<MouseWheel>", delta=-120)
            root.update_idletasks()
            self.assertGreater(app.connect_canvas.yview()[0], 0)
            app.connect_canvas.yview_moveto(1)
            self.assertAlmostEqual(app.connect_canvas.yview()[1], 1.0)
            app._show_page(1)
            root.focus_force()
            app.announcement_text.focus_set()
            root.update()
            self.assertIs(root.focus_get(), app.announcement_text)
            app.nav_buttons[0].invoke()
            root.update()
            self.assertIs(root.focus_get(), app.nav_buttons[0])
            root.withdraw()

            for index, button in enumerate(app.nav_buttons):
                button.invoke()
                root.update_idletasks()
                self.assertTrue(app.pages[index].winfo_manager())
                self.assertTrue(all(
                    not page.winfo_manager() for position, page in enumerate(app.pages) if position != index
                ))
                self.assertTrue(all(
                    button.cget("bg") != other.cget("bg")
                    for position, other in enumerate(app.nav_buttons) if position != index
                ))

            app._show_page(2)
            rows = app.history_tree.get_children()
            self.assertEqual(len(rows), 2)
            app.history_tree.selection_set(rows[1])
            app.use_selected_history()
            self.assertEqual(app.address_var.get(), "beta.example.org:9101")
            app.delete_selected_history()
            self.assertEqual(app.history, ["alpha.example.org:9100"])
            self.assertEqual(len(app.history_tree.get_children()), 1)

            widgets = [root]
            for widget in widgets:
                widgets.extend(widget.winfo_children())
            for name in ("announcement_enabled", "blacklist_check_enabled", "fixed_roles_enabled"):
                variable = getattr(app, name + "_var")
                control = next(widget for widget in widgets if isinstance(widget, ttk.Checkbutton)
                               and str(widget.cget("variable")) == str(variable))
                control.invoke()
                self.assertFalse(variable.get())
                self.assertEqual(save.call_args.args[0], "quick_join")
                payload = save.call_args.args[1]
                self.assertEqual(set(payload), set(settings))
                self.assertEqual(payload[name], False)
                self.assertEqual(payload["announcement_text"], settings["announcement_text"])
                self.assertEqual(payload["blacklist_check_token"], settings["blacklist_check_token"])
                self.assertEqual(payload["gm_api_port"], "9901")

            app.join_button.invoke()
            callbacks["join_running_game"].assert_called_once_with()
            app.stop_button.configure(state="normal")
            app.stop_button.invoke()
            callbacks["stop_auto_join"].assert_called_once_with()
            for label, name in (("发布公告", "publish_announcement"),
                                ("启动客户端", "launch_with_address"),
                                ("选择客户端", "choose_executable")):
                button = next(widget for widget in widgets if isinstance(widget, (tk.Button, ttk.Button))
                              and label in str(widget.cget("text")))
                button.invoke()
                callbacks[name].assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
