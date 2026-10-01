# -*- coding: utf-8 -*-
"""Windows desktop client for the Dread Hunger Linux GM console."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from remote_common import (
    ACCENT, BG, DANGER, MUTED, PANEL, SUCCESS, TEXT, WARNING,
    ApiError, AsyncRunner, RemoteApi, apply_dark_theme, center_window, enable_windows_dpi_awareness,
    load_settings, save_settings,
)


class GMConsoleApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Dread Hunger · Linux GM 远程控制台")
        center_window(root, 1220, 800)
        apply_dark_theme(root)
        self.settings = load_settings("gm_console", {
            "host": "127.0.0.1", "port": 9900, "remember_password": False, "password": ""
        })
        self.api = None
        self.runner = AsyncRunner(root)
        self.players = []
        self.blacklist_entries = []
        self.refresh_job = None
        self.busy = False
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        header = ttk.Frame(self.root, padding=(22, 18, 22, 12)); header.pack(fill="x")
        title_box = ttk.Frame(header); title_box.pack(side="left")
        ttk.Label(title_box, text="GM 远程控制台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="玩家状态、消息广播与对局操作集中控制", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        self.status_label = tk.Label(header, text="● 未连接", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10, "bold")); self.status_label.pack(side="right")

        bar = ttk.Frame(self.root, style="Panel.TFrame", padding=15); bar.pack(fill="x", padx=22, pady=(0, 14))
        self.host_var = tk.StringVar(value=str(self.settings["host"])); self.port_var = tk.StringVar(value=str(self.settings["port"])); self.password_var = tk.StringVar(value=str(self.settings.get("password", ""))); self.remember_var = tk.BooleanVar(value=bool(self.settings.get("remember_password")))
        for col, (label, var, width, secret) in enumerate((("服务器 IP / 域名（支持 IP:端口）", self.host_var, 30, False), ("GM 端口", self.port_var, 10, False), ("GM 密码", self.password_var, 20, True))):
            box = ttk.Frame(bar, style="Panel.TFrame"); box.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 12, 0))
            ttk.Label(box, text=label, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Entry(box, textvariable=var, width=width, show="●" if secret else "").pack(fill="x", pady=(4, 0)); bar.columnconfigure(col, weight=2 if col == 0 else 1)
        ttk.Checkbutton(bar, text="记住密码", variable=self.remember_var).grid(row=0, column=3, padx=12, sticky="s")
        self.connect_btn = ttk.Button(bar, text="连接 GM 服务", style="Accent.TButton", command=self.connect); self.connect_btn.grid(row=0, column=4, sticky="s")

        body = ttk.Panedwindow(self.root, orient="horizontal"); body.pack(fill="both", expand=True, padx=22, pady=(0, 12))
        left = ttk.Frame(body, style="Panel.TFrame", padding=15); right = ttk.Frame(body, padding=(14, 0, 0, 0)); body.add(left, weight=1); body.add(right, weight=3)
        top = ttk.Frame(left, style="Panel.TFrame"); top.pack(fill="x")
        ttk.Label(top, text="实时在线玩家", style="CardTitle.TLabel").pack(side="left")
        self.player_count = tk.Label(top, text="0 人", bg=PANEL, fg=ACCENT, font=("Microsoft YaHei UI", 10, "bold")); self.player_count.pack(side="right")
        self.player_tree = ttk.Treeview(left, columns=("role", "steam", "blocked"), show="tree headings", height=18)
        self.player_tree.heading("#0", text="玩家名"); self.player_tree.heading("role", text="职业"); self.player_tree.heading("steam", text="Steam ID"); self.player_tree.heading("blocked", text="状态")
        self.player_tree.column("#0", width=150); self.player_tree.column("role", width=70); self.player_tree.column("steam", width=135); self.player_tree.column("blocked", width=60, anchor="center")
        self.player_tree.pack(fill="both", expand=True, pady=(12, 8)); self.player_tree.bind("<<TreeviewSelect>>", self.select_player)
        self.frida_label = ttk.Label(left, text="等待玩家列表同步", style="CardMuted.TLabel"); self.frida_label.pack(anchor="w")

        self.tabs = ttk.Notebook(right); self.tabs.pack(fill="both", expand=True)
        self.message_tab = ttk.Frame(self.tabs, padding=18); self.player_tab = ttk.Frame(self.tabs, padding=18); self.blacklist_tab = ttk.Frame(self.tabs, padding=18); self.round_tab = ttk.Frame(self.tabs, padding=18); self.output_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.message_tab, text="  消息广播  "); self.tabs.add(self.player_tab, text="  玩家管理  "); self.tabs.add(self.blacklist_tab, text="  黑名单  "); self.tabs.add(self.round_tab, text="  对局控制  "); self.tabs.add(self.output_tab, text="  操作记录  ")
        self._build_message(); self._build_player(); self._build_blacklist(); self._build_round(); self._build_output()
        self.footer = ttk.Label(self.root, text="输入 Linux 主机 IP 和 GM 端口后连接", style="Muted.TLabel"); self.footer.pack(fill="x", padx=24, pady=(0, 12))

    def _label_entry(self, parent, label, variable, values=None):
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(10, 4))
        if values is not None:
            widget = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        else: widget = ttk.Entry(parent, textvariable=variable)
        widget.pack(fill="x"); return widget

    def _build_message(self):
        ttk.Label(self.message_tab, text="向全服或指定玩家发送消息", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.message_tab, text="消息通过 Linux 端 Frida 插件写入游戏", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))
        self.message_target = tk.StringVar(value="全部玩家")
        self.message_combo = self._label_entry(self.message_tab, "接收目标", self.message_target, ("全部玩家",))
        ttk.Label(self.message_tab, text="消息内容", style="Muted.TLabel").pack(anchor="w", pady=(14, 4))
        self.message_text = tk.Text(self.message_tab, height=8, bg="#FBFCFE", fg=TEXT, insertbackground=TEXT, relief="solid", bd=1, highlightthickness=0, font=("Microsoft YaHei UI", 10), padx=12, pady=10, wrap="word"); self.message_text.pack(fill="both", expand=True)
        self.message_text.bind("<KeyRelease>", self._update_message_count)
        self.message_count = ttk.Label(self.message_tab, text="0 / 500", style="Muted.TLabel"); self.message_count.pack(anchor="e", pady=(3, 0))
        presets = ttk.Frame(self.message_tab); presets.pack(fill="x", pady=10)
        for text, value in (("维护公告", "[系统公告] 服务器将在 5 分钟后维护重启，请合理安排游戏时间。"), ("反作弊", "[警告] 严禁外挂、恶意卡 Bug 等破坏游戏公平的行为。"), ("暴风雪", "[提示] 暴风雪即将来临，请尽快做好防寒准备！")):
            ttk.Button(presets, text=text, command=lambda v=value: self._preset(v)).pack(side="left", padx=(0, 8))
        ttk.Button(self.message_tab, text="发送消息", style="Accent.TButton", command=self.send_message).pack(anchor="e")

    def _build_player(self):
        ttk.Label(self.player_tab, text="玩家即时管理", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.player_tab, text="可从左侧玩家列表快速选中目标", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))
        self.target_player = tk.StringVar(value=""); self.player_combo = self._label_entry(self.player_tab, "目标玩家", self.target_player, ())
        self.kick_reason = tk.StringVar(value=""); self._label_entry(self.player_tab, "踢出原因（可选）", self.kick_reason)
        actions = ttk.Frame(self.player_tab); actions.pack(fill="x", pady=22)
        ttk.Button(actions, text="复活玩家", style="Success.TButton", command=lambda: self.player_action("revive_player", "复活玩家")).pack(side="left")
        ttk.Button(actions, text="传送回船", style="Accent.TButton", command=lambda: self.player_action("teleport_to_ship", "传送玩家")).pack(side="left", padx=10)
        ttk.Button(actions, text="踢出玩家", style="Danger.TButton", command=lambda: self.player_action("kick_player", "踢出玩家", confirm=True)).pack(side="left")

    def _build_blacklist(self):
        ttk.Label(self.blacklist_tab, text="云端黑名单管理", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.blacklist_tab, text="选择在线玩家后一键读取 Steam / EOS ID；理由可使用预设或自定义", style="Muted.TLabel").pack(anchor="w", pady=(3, 12))
        token_frame = ttk.LabelFrame(self.blacklist_tab, text="进服器只读查询令牌", padding=10); token_frame.pack(fill="x", pady=(0, 8))
        self.blacklist_check_token = tk.StringVar(value="")
        ttk.Entry(token_frame, textvariable=self.blacklist_check_token, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(token_frame, text="复制", command=self.copy_blacklist_token).pack(side="left", padx=(8, 0))
        self.blacklist_player = tk.StringVar(value="")
        self.blacklist_player_combo = self._label_entry(self.blacklist_tab, "在线玩家", self.blacklist_player, ())
        self.blacklist_reason_code = tk.StringVar(value="死一次退")
        self._label_entry(self.blacklist_tab, "预设理由", self.blacklist_reason_code, ("死一次退", "恶意摆烂", "使用外挂", "恶意卡 Bug", "辱骂或骚扰", "其他"))
        self.blacklist_reason = tk.StringVar(value="")
        self._label_entry(self.blacklist_tab, "自定义理由（填写后覆盖预设）", self.blacklist_reason)
        action_row = ttk.Frame(self.blacklist_tab); action_row.pack(fill="x", pady=(12, 10))
        ttk.Button(action_row, text="一键拉黑选中玩家", style="Danger.TButton", command=self.add_blacklist).pack(side="left")
        ttk.Button(action_row, text="刷新黑名单", command=self.refresh_blacklist).pack(side="right")
        self.blacklist_tree = ttk.Treeview(self.blacklist_tab, columns=("steam", "reason"), show="tree headings", height=8)
        self.blacklist_tree.heading("#0", text="玩家"); self.blacklist_tree.heading("steam", text="Steam ID"); self.blacklist_tree.heading("reason", text="理由")
        self.blacklist_tree.column("#0", width=150); self.blacklist_tree.column("steam", width=150); self.blacklist_tree.column("reason", width=260)
        self.blacklist_tree.pack(fill="both", expand=True)
        ttk.Button(self.blacklist_tab, text="移除选中记录", style="Warning.TButton", command=self.remove_blacklist).pack(anchor="e", pady=(10, 0))

    def _build_round(self):
        ttk.Label(self.round_tab, text="当前对局控制", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.round_tab, text="危险操作会在执行前再次确认", style="Muted.TLabel").pack(anchor="w", pady=(3, 20))
        armory = ttk.LabelFrame(self.round_tab, text="军械库", padding=16); armory.pack(fill="x", pady=(0, 14))
        ttk.Label(armory, text="强制解锁船内军械库铁门", style="CardMuted.TLabel").pack(side="left")
        ttk.Button(armory, text="开启军械库", style="Warning.TButton", command=lambda: self.command("open_armory", {}, "开启军械库")).pack(side="right")
        end = ttk.LabelFrame(self.round_tab, text="强制结束对局", padding=16); end.pack(fill="x")
        self.win_team = tk.StringVar(value="探险者胜利")
        ttk.Combobox(end, textvariable=self.win_team, values=("探险者胜利", "叛徒胜利"), state="readonly", width=20).pack(side="left")
        ttk.Button(end, text="结束并结算", style="Danger.TButton", command=self.end_game).pack(side="right")
        recall = ttk.LabelFrame(self.round_tab, text="全员召回", padding=16); recall.pack(fill="x", pady=14)
        ttk.Label(recall, text="将全部在线玩家传送回船", style="CardMuted.TLabel").pack(side="left")
        ttk.Button(recall, text="传送全部玩家", command=lambda: self.command("teleport_to_ship", {"player": "all"}, "全员传送", True)).pack(side="right")

    def _build_output(self):
        top = ttk.Frame(self.output_tab); top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="GM 指令记录", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="清空", command=lambda: self._set_output("")).pack(side="right")
        self.output = tk.Text(self.output_tab, bg="#FBFCFE", fg="#34445A", insertbackground=TEXT, selectbackground="#D9E7FF", relief="solid", bd=1, highlightthickness=0, font=("Cascadia Mono", 10), padx=14, pady=12, state="disabled"); self.output.pack(fill="both", expand=True)

    def connect(self):
        try: api = RemoteApi(self.host_var.get(), self.port_var.get())
        except ApiError as exc: messagebox.showerror("连接参数", str(exc)); return
        self._busy(True, "正在连接 GM 服务…"); password = self.password_var.get()
        def work():
            login = api.request("/login", "POST", {"password": password}); api.token = str(login.get("token", "")); return api, api.request("/api/gm/players"), api.request("/api/gm/blacklist")
        self.runner.submit(work, self._connected, self._failed)

    def _connected(self, result):
        self.api, players, blacklist = result; self._busy(False, "GM 服务连接成功"); self.status_label.configure(text="● 已连接", fg=SUCCESS)
        self.port_var.set(str(self.api.port))
        save_settings("gm_console", {"host": self.host_var.get().strip(), "port": self.api.port, "remember_password": self.remember_var.get(), "password": self.password_var.get() if self.remember_var.get() else ""})
        self._apply_players(players); self._apply_blacklist(blacklist); self._schedule()

    def _failed(self, exc):
        self._busy(False, "操作失败：%s" % exc); self.status_label.configure(text="● 连接异常", fg=DANGER); messagebox.showerror("GM 控制台", str(exc))

    def _operation_failed(self, exc):
        self._busy(False, "操作失败：%s" % exc)
        if isinstance(exc, ApiError) and exc.status == 401:
            self.status_label.configure(text="● 登录已失效", fg=DANGER)
        messagebox.showerror("指令未下发", str(exc))

    def _busy(self, value, text):
        self.busy = value; self.connect_btn.configure(state="disabled" if value else "normal"); self.footer.configure(text=text)

    def _schedule(self):
        if self.refresh_job: self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(3000, self.refresh_players)

    def refresh_players(self):
        if not self.api or self.busy: return
        self.runner.submit(lambda: self.api.request("/api/gm/players"), self._players_ok, self._refresh_failed)

    def _players_ok(self, data): self._apply_players(data); self.footer.configure(text="玩家列表同步：" + datetime.now().strftime("%H:%M:%S")); self._schedule()
    def _refresh_failed(self, exc):
        self.footer.configure(text="玩家同步失败：%s" % exc)
        if isinstance(exc, ApiError) and exc.status == 401: self.status_label.configure(text="● 登录已失效", fg=DANGER)
        else: self._schedule()

    def _apply_players(self, data):
        self.players = data.get("players", []) if isinstance(data, dict) else []
        for item in self.player_tree.get_children(): self.player_tree.delete(item)
        names = []
        for i, player in enumerate(self.players):
            name = str(player.get("name") or "未知玩家"); names.append(name)
            self.player_tree.insert("", "end", iid=str(i), text=name, values=(player.get("role", ""), player.get("steam_id", ""), "已拉黑" if player.get("blacklisted") else ""))
        self.player_count.configure(text="%d 人" % len(self.players))
        stale = bool(data.get("stale", True)); self.frida_label.configure(text="Frida 数据已过期" if stale else "● Frida 数据实时同步", foreground=WARNING if stale else SUCCESS)
        self.message_combo.configure(values=("全部玩家",) + tuple(names)); self.player_combo.configure(values=tuple(names)); self.blacklist_player_combo.configure(values=tuple(names))
        if names and self.target_player.get() not in names: self.target_player.set(names[0])
        if names and self.blacklist_player.get() not in names: self.blacklist_player.set(names[0])

    def select_player(self, _event=None):
        selected = self.player_tree.selection()
        if selected:
            name = self.player_tree.item(selected[0], "text"); self.target_player.set(name); self.message_target.set(name); self.blacklist_player.set(name)

    @staticmethod
    def _reason_code(label):
        return {"死一次退": "quit_after_death", "恶意摆烂": "griefing", "使用外挂": "cheating", "恶意卡 Bug": "bug_abuse", "辱骂或骚扰": "harassment", "其他": "other"}.get(label, "other")

    def add_blacklist(self):
        player = self.blacklist_player.get().strip()
        if not player: messagebox.showwarning("未选择玩家", "请先选择在线玩家"); return
        selected = next((item for item in self.players if str(item.get("name")) == player), {})
        user_id = str(selected.get("user_id") or "")
        if not user_id: messagebox.showwarning("ID 尚未同步", "还没有从登录日志读取到该玩家 ID，请稍后刷新"); return
        if not messagebox.askyesno("加入黑名单", "确定拉黑【%s】吗？\n\n用户 ID：%s" % (player, user_id)): return
        payload = {"player": player, "reason_code": self._reason_code(self.blacklist_reason_code.get()), "reason": self.blacklist_reason.get().strip()}
        self._busy(True, "正在加入黑名单…")
        self.runner.submit(lambda: self.api.request("/api/gm/blacklist/add", "POST", payload), self._blacklist_changed, self._operation_failed)

    def refresh_blacklist(self):
        if not self.api: messagebox.showwarning("尚未连接", "请先连接 Linux GM 服务"); return
        self.runner.submit(lambda: self.api.request("/api/gm/blacklist"), self._apply_blacklist, self._operation_failed)

    def _apply_blacklist(self, data):
        entries = data.get("entries", []) if isinstance(data, dict) else []
        self.blacklist_check_token.set(str(data.get("check_token") or "") if isinstance(data, dict) else "")
        for item in self.blacklist_tree.get_children(): self.blacklist_tree.delete(item)
        for i, entry in enumerate(entries):
            self.blacklist_tree.insert("", "end", iid=str(i), text=entry.get("name", "未知玩家"), values=(entry.get("steam_id", ""), entry.get("reason", "")))
        self.blacklist_entries = entries

    def copy_blacklist_token(self):
        token = self.blacklist_check_token.get().strip()
        if not token: messagebox.showwarning("暂无令牌", "请先连接并刷新黑名单"); return
        self.root.clipboard_clear(); self.root.clipboard_append(token)
        self.footer.configure(text="只读查询令牌已复制，可粘贴到快速进服器")

    def remove_blacklist(self):
        selected = self.blacklist_tree.selection()
        if not selected: messagebox.showwarning("未选择记录", "请先选择要移除的黑名单记录"); return
        index = int(selected[0]); entry = self.blacklist_entries[index]
        if not messagebox.askyesno("移出黑名单", "确定移除【%s】吗？" % entry.get("name", "未知玩家")): return
        self._busy(True, "正在移出黑名单…")
        self.runner.submit(lambda: self.api.request("/api/gm/blacklist/remove", "POST", {"user_id": entry.get("user_id", "")}), self._blacklist_changed, self._operation_failed)

    def _blacklist_changed(self, data):
        self._busy(False, data.get("message", "黑名单已更新")); self.blacklist_reason.set("")
        self._append_output("[%s] ✓ %s\n" % (datetime.now().strftime("%H:%M:%S"), data.get("message", "黑名单已更新")))
        self.refresh_blacklist(); self.refresh_players()

    def _preset(self, value):
        self.message_text.delete("1.0", "end"); self.message_text.insert("1.0", value); self._update_message_count()

    def _update_message_count(self, _event=None):
        length = len(self.message_text.get("1.0", "end-1c"))
        self.message_count.configure(text="%d / 500" % length, foreground=DANGER if length > 500 else MUTED)

    def send_message(self):
        message = self.message_text.get("1.0", "end").strip()
        if not message: messagebox.showwarning("消息为空", "请输入要发送的消息"); return
        if len(message) > 500: messagebox.showwarning("消息过长", "消息最多允许 500 个字符"); return
        target = self.message_target.get(); self.command("send_message", {"player": "all" if target == "全部玩家" else target, "message": message}, "发送消息")

    def player_action(self, action, label, confirm=False):
        player = self.target_player.get().strip()
        if not player: messagebox.showwarning("未选择玩家", "请先选择目标玩家"); return
        params = {"player": player}
        if action == "kick_player": params["reason"] = self.kick_reason.get().strip()
        self.command(action, params, label, confirm)

    def end_game(self):
        team = 1 if self.win_team.get() == "探险者胜利" else 2
        self.command("end_game", {"team": team}, self.win_team.get(), True)

    def command(self, action, params, label, confirm=False):
        if not self.api: messagebox.showwarning("尚未连接", "请先连接 Linux GM 服务"); return
        if confirm and not messagebox.askyesno("危险操作确认", "确定要执行“%s”吗？" % label): return
        self._busy(True, "正在下发：%s…" % label)
        self.runner.submit(lambda: self.api.request("/api/gm/" + action, "POST", params), lambda d: self._command_ok(label, d), self._operation_failed)

    def _command_ok(self, label, data):
        self._busy(False, "%s成功" % label); self._append_output("[%s] ✓ %s\n指令 ID: %s\n" % (datetime.now().strftime("%H:%M:%S"), data.get("message", label), data.get("command_id", "--")))
        if label == "发送消息": self.message_text.delete("1.0", "end"); self._update_message_count()

    def _append_output(self, text):
        self.output.configure(state="normal"); self.output.insert("1.0", text + "\n"); self.output.configure(state="disabled")

    def _set_output(self, text):
        self.output.configure(state="normal"); self.output.delete("1.0", "end"); self.output.insert("1.0", text); self.output.configure(state="disabled")

    def close(self):
        self.runner.closed = True
        if self.refresh_job:
            try: self.root.after_cancel(self.refresh_job)
            except Exception: pass
        self.root.destroy()


def main():
    enable_windows_dpi_awareness()
    root = tk.Tk(); GMConsoleApp(root); root.mainloop()


if __name__ == "__main__": main()
