# -*- coding: utf-8 -*-
"""Windows desktop client for Dread Hunger Linux server manager."""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from urllib.parse import quote

from remote_common import (
    ACCENT, BG, BORDER, DANGER, MUTED, PANEL, SUCCESS, TEXT, WARNING,
    ApiError, AsyncRunner, RemoteApi, apply_dark_theme, center_window, enable_windows_dpi_awareness,
    load_settings, save_settings,
)


class ServerManagerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Dread Hunger · Linux 远程开服器")
        center_window(root, 1280, 820)
        apply_dark_theme(root)
        self.settings = load_settings("server_manager", {
            "host": "127.0.0.1", "port": 8800, "remember_password": False, "password": ""
        })
        self.api = None
        self.token = ""
        self.state = {}
        self.refresh_job = None
        self.auto_log_job = None
        self.runner = AsyncRunner(root)
        self.connected = False
        self.busy = False
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        header = ttk.Frame(self.root, padding=(22, 18, 22, 12))
        header.pack(fill="x")
        title_box = ttk.Frame(header); title_box.pack(side="left")
        ttk.Label(title_box, text="Linux 远程开服器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="集中管理游戏进程、参数、插件与运行日志", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))
        self.status_dot = tk.Label(header, text="● 未连接", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 10, "bold"))
        self.status_dot.pack(side="right")

        connect = ttk.Frame(self.root, style="Panel.TFrame", padding=16)
        connect.pack(fill="x", padx=22, pady=(0, 14))
        self.host_var = tk.StringVar(value=str(self.settings["host"]))
        self.port_var = tk.StringVar(value=str(self.settings["port"]))
        self.password_var = tk.StringVar(value=str(self.settings.get("password", "")))
        self.remember_var = tk.BooleanVar(value=bool(self.settings.get("remember_password")))
        ttk.Label(connect, text="服务器 IP / 域名（支持 IP:端口）", style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(connect, text="管理端口", style="CardMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(connect, text="面板密码（可空）", style="CardMuted.TLabel").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(connect, textvariable=self.host_var, width=32).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Entry(connect, textvariable=self.port_var, width=10).grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(5, 0))
        ttk.Entry(connect, textvariable=self.password_var, show="●", width=22).grid(row=1, column=2, sticky="ew", padx=(12, 0), pady=(5, 0))
        ttk.Checkbutton(connect, text="记住密码", variable=self.remember_var).grid(row=1, column=3, padx=12, pady=(5, 0))
        self.connect_btn = ttk.Button(connect, text="连接服务器", style="Accent.TButton", command=self.connect)
        self.connect_btn.grid(row=1, column=4, padx=(4, 0), pady=(5, 0))
        connect.columnconfigure(0, weight=2); connect.columnconfigure(2, weight=1)

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=22, pady=(0, 12))
        self.overview = ttk.Frame(self.tabs, padding=16)
        self.config_tab = ttk.Frame(self.tabs, padding=16)
        self.plugins_tab = ttk.Frame(self.tabs, padding=16)
        self.logs_tab = ttk.Frame(self.tabs, padding=16)
        self.tabs.add(self.overview, text="  概览  ")
        self.tabs.add(self.config_tab, text="  游戏配置  ")
        self.tabs.add(self.plugins_tab, text="  插件管理  ")
        self.tabs.add(self.logs_tab, text="  运行日志  ")
        self._build_overview(); self._build_config(); self._build_plugins(); self._build_logs()
        self.footer = ttk.Label(self.root, text="输入 Linux 主机 IP 与面板端口后连接", style="Muted.TLabel")
        self.footer.pack(fill="x", padx=24, pady=(0, 12))

    def _panel(self, parent, title):
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=18)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        return frame

    def _build_overview(self):
        cards = ttk.Frame(self.overview); cards.pack(fill="x")
        self.card_values = {}
        for i, (key, title) in enumerate((("running", "服务器状态"), ("pid", "进程 PID"), ("port", "游戏端口"), ("injector", "Frida 注入器"))):
            card = self._panel(cards, title); card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0))
            value = tk.Label(card, text="--", bg=PANEL, fg=TEXT, font=("Microsoft YaHei UI", 18, "bold"))
            value.pack(anchor="w"); self.card_values[key] = value; cards.columnconfigure(i, weight=1)
        actions = self._panel(self.overview, "服务器控制"); actions.pack(fill="x", pady=14)
        ttk.Button(actions, text="▶  启动服务器", style="Success.TButton", command=lambda: self.action("/api/start", "启动服务器")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="■  停止服务器", style="Danger.TButton", command=lambda: self.confirm_action("/api/stop", "停止服务器")).pack(side="left", padx=8)
        ttk.Button(actions, text="↻  重启服务器", style="Warning.TButton", command=lambda: self.confirm_action("/api/restart", "重启服务器")).pack(side="left", padx=8)
        ttk.Button(actions, text="重载注入器", command=lambda: self.action("/api/injector/restart", "重载注入器")).pack(side="left", padx=8)
        detail = self._panel(self.overview, "远程主机信息"); detail.pack(fill="both", expand=True)
        self.detail_text = tk.Text(detail, height=9, bg=PANEL, fg=MUTED, insertbackground=TEXT, relief="flat", font=("Consolas", 10), padx=2, pady=2)
        self.detail_text.pack(fill="both", expand=True); self.detail_text.configure(state="disabled")

    def _build_config(self):
        panel = self._panel(self.config_tab, "游戏参数"); panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="使用右侧箭头精确增减数值；保存后下次启动服务器时生效。", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 10))
        fields = [
            ("map", "地图", "Departure_Persistent", "map", None),
            ("server_port", "游戏端口", "9100", "int", (1, 65535, 1)),
            ("maxplayers", "最大玩家", "8", "int", (1, 32, 1)),
            ("thralls", "狼人数量", "2", "int", (0, 8, 1)),
            ("dayminutes", "每日分钟数", "9", "int", (1, 240, 1)),
            ("daysbeforeblizzard", "暴风雪前天数", "3", "int", (0, 30, 1)),
            ("predatordamage", "野兽伤害倍率", "1.0", "float", (0, 100, 0.1)),
            ("coalburnrate", "煤炭消耗倍率", "1.0", "float", (0, 100, 0.1)),
            ("hungerrate", "饥饿倍率", "1.0", "float", (0, 100, 0.1)),
            ("coldintensity", "寒冷强度", "1.0", "float", (0, 100, 0.1)),
            ("patch_source", "插件目录", "Linux 插件", "text", None),
            ("extra_args", "额外启动参数", "", "text", None),
        ]
        self.config_vars = {}
        grid = ttk.Frame(panel, style="Panel.TFrame"); grid.pack(fill="x")
        maps = ("Departure_Persistent", "Approach_Persistent", "Summit_Persistent", "Expedition_Persistent", "Archipelago_Persistent")
        for i, (key, label, default, kind, limits) in enumerate(fields):
            row, col = divmod(i, 3); box = ttk.Frame(grid, style="Panel.TFrame"); box.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 14, 0), pady=8)
            ttk.Label(box, text=label, style="CardMuted.TLabel").pack(anchor="w")
            var = tk.StringVar(value=default); self.config_vars[key] = var
            if kind == "map":
                widget = ttk.Combobox(box, textvariable=var, values=maps, state="readonly")
            elif kind in {"int", "float"}:
                widget = ttk.Spinbox(box, textvariable=var, from_=limits[0], to=limits[1], increment=limits[2])
            else:
                widget = ttk.Entry(box, textvariable=var)
            widget.pack(fill="x", pady=(4, 0))
            if limits:
                ttk.Label(box, text="范围 %s–%s · 步进 %s" % limits, style="CardMuted.TLabel", font=("Microsoft YaHei UI", 8)).pack(anchor="w", pady=(3, 0))
            grid.columnconfigure(col, weight=1)
        buttons = ttk.Frame(panel, style="Panel.TFrame"); buttons.pack(fill="x", pady=(18, 0))
        ttk.Button(buttons, text="恢复服务器当前值", command=self.restore_config).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="保存配置", style="Accent.TButton", command=self.save_config).pack(side="right")

    def _build_plugins(self):
        toolbar = ttk.Frame(self.plugins_tab); toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="启用或停用后，建议重载注入器", style="Muted.TLabel").pack(side="left")
        ttk.Button(toolbar, text="刷新列表", command=self.refresh).pack(side="right")
        self.plugin_tree = ttk.Treeview(self.plugins_tab, columns=("state", "size", "path"), show="tree headings")
        self.plugin_tree.heading("#0", text="插件名称"); self.plugin_tree.heading("state", text="状态")
        self.plugin_tree.heading("size", text="大小"); self.plugin_tree.heading("path", text="目标路径")
        self.plugin_tree.column("#0", width=330); self.plugin_tree.column("state", width=90, anchor="center")
        self.plugin_tree.column("size", width=90, anchor="e"); self.plugin_tree.column("path", width=430)
        self.plugin_tree.pack(fill="both", expand=True)
        bar = ttk.Frame(self.plugins_tab); bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="启用选中", style="Success.TButton", command=lambda: self.toggle_plugin(True)).pack(side="left")
        ttk.Button(bar, text="停用选中", style="Danger.TButton", command=lambda: self.toggle_plugin(False)).pack(side="left", padx=10)

    def _build_logs(self):
        toolbar = ttk.Frame(self.logs_tab); toolbar.pack(fill="x", pady=(0, 10))
        self.log_kind = tk.StringVar(value="服务器日志")
        ttk.Combobox(toolbar, textvariable=self.log_kind, values=("服务器日志", "注入器日志"), state="readonly", width=16).pack(side="left")
        ttk.Button(toolbar, text="刷新日志", command=self.refresh_logs).pack(side="left", padx=10)
        ttk.Button(toolbar, text="清空显示", command=lambda: self._set_log("")).pack(side="left")
        self.auto_log_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="每 3 秒自动刷新", variable=self.auto_log_var, command=self._auto_log_changed).pack(side="left", padx=12)
        self.log_text = tk.Text(self.logs_tab, bg="#FBFCFE", fg="#34445A", insertbackground=TEXT, selectbackground="#D9E7FF", relief="solid", bd=1, highlightthickness=0, font=("Cascadia Mono", 10), padx=14, pady=12, wrap="none")
        sy = ttk.Scrollbar(self.logs_tab, orient="vertical", command=self.log_text.yview); self.log_text.configure(yscrollcommand=sy.set)
        sy.pack(side="right", fill="y"); self.log_text.pack(fill="both", expand=True)

    def connect(self):
        try:
            api = RemoteApi(self.host_var.get(), self.port_var.get())
        except ApiError as exc:
            messagebox.showerror("连接参数", str(exc)); return
        self._busy(True, "正在连接并验证身份…")
        password = self.password_var.get()
        def work():
            login = api.request("/api/login", "POST", {"password": password})
            api.token = str(login.get("token", ""))
            return api, api.request("/api/state")
        self.runner.submit(work, self._connected, self._failed)

    def _connected(self, result):
        self.api, state = result; self.token = self.api.token; self.connected = True
        self._busy(False, "连接成功")
        self.status_dot.configure(text="● 已连接", fg=SUCCESS)
        self.port_var.set(str(self.api.port))
        save_settings("server_manager", {"host": self.host_var.get().strip(), "port": self.api.port, "remember_password": self.remember_var.get(), "password": self.password_var.get() if self.remember_var.get() else ""})
        self._apply_state(state); self._schedule_refresh()

    def _failed(self, exc):
        self._busy(False, "连接失败：%s" % exc); self.status_dot.configure(text="● 连接失败", fg=DANGER)
        messagebox.showerror("远程连接失败", str(exc))

    def _operation_failed(self, exc):
        self._busy(False, "操作失败：%s" % exc)
        if isinstance(exc, ApiError) and exc.status == 401:
            self.connected = False
            self.status_dot.configure(text="● 登录已失效", fg=DANGER)
        messagebox.showerror("操作未完成", str(exc))

    def _busy(self, active, text):
        self.busy = active; self.connect_btn.configure(state="disabled" if active else "normal"); self.footer.configure(text=text)

    def _schedule_refresh(self):
        if self.refresh_job: self.root.after_cancel(self.refresh_job)
        self.refresh_job = self.root.after(4000, self.refresh)

    def refresh(self):
        if not self.api or self.busy: return
        self.runner.submit(lambda: self.api.request("/api/state"), self._refresh_ok, self._refresh_error)

    def _refresh_ok(self, state):
        self._apply_state(state); self.footer.configure(text="最后同步：" + datetime.now().strftime("%H:%M:%S")); self._schedule_refresh()

    def _refresh_error(self, exc):
        self.footer.configure(text="同步失败：%s" % exc)
        if isinstance(exc, ApiError) and exc.status == 401:
            self.connected = False; self.status_dot.configure(text="● 登录已失效", fg=DANGER)
        else: self._schedule_refresh()

    def _apply_state(self, state):
        self.state = state or {}; status = self.state.get("status", {}); injector = self.state.get("injector", {})
        running = bool(status.get("running"))
        self.card_values["running"].configure(text="运行中" if running else "已停止", fg=SUCCESS if running else DANGER)
        self.card_values["pid"].configure(text=str(status.get("pid") or "--"))
        self.card_values["port"].configure(text=str(status.get("port") or "--"))
        inj = bool(injector.get("running")); self.card_values["injector"].configure(text="在线" if inj else "离线", fg=SUCCESS if inj else WARNING)
        details = "Linux 根目录  %s\n服务端二进制  %s\n启动时间      %s\n退出码        %s\n启动命令      %s" % (
            status.get("root", "--"), status.get("binary", "--"), status.get("started_at") or "--",
            status.get("last_exit_code") if status.get("last_exit_code") is not None else "--", " ".join(status.get("command") or []))
        self.detail_text.configure(state="normal"); self.detail_text.delete("1.0", "end"); self.detail_text.insert("1.0", details); self.detail_text.configure(state="disabled")
        config = self.state.get("config", {})
        for key, var in self.config_vars.items():
            value = config.get(key, "")
            var.set(" ".join(value) if isinstance(value, list) else str(value))
        for item in self.plugin_tree.get_children(): self.plugin_tree.delete(item)
        for patch in self.state.get("patches", []):
            active = bool(patch.get("active")); self.plugin_tree.insert("", "end", iid=patch.get("name"), text=patch.get("name"), values=("已启用" if active else "已停用", self._size(patch.get("size", 0)), patch.get("target", "")), tags=("on" if active else "off",))
        self.plugin_tree.tag_configure("on", foreground=SUCCESS); self.plugin_tree.tag_configure("off", foreground=MUTED)

    def restore_config(self):
        config = self.state.get("config", {})
        if not config:
            messagebox.showinfo("游戏配置", "请先连接服务器读取配置")
            return
        for key, var in self.config_vars.items():
            value = config.get(key, "")
            var.set(" ".join(value) if isinstance(value, list) else str(value))
        self.footer.configure(text="已恢复为服务器当前保存值")

    @staticmethod
    def _size(value):
        value = int(value or 0); return ("%.1f MB" % (value / 1048576)) if value >= 1048576 else ("%.1f KB" % (value / 1024))

    def action(self, path, name):
        if not self._require_connection(): return
        self._busy(True, "正在%s…" % name)
        self.runner.submit(lambda: self.api.request(path, "POST", {}), lambda _: self._action_ok(name), self._operation_failed)

    def confirm_action(self, path, name):
        if messagebox.askyesno("确认操作", "确定要%s吗？" % name): self.action(path, name)

    def _action_ok(self, name):
        self._busy(False, "%s成功" % name); self.refresh()

    def save_config(self):
        if not self._require_connection(): return
        values = {k: v.get().strip() for k, v in self.config_vars.items()}
        try:
            for key in ("server_port", "maxplayers", "thralls", "dayminutes", "daysbeforeblizzard"): values[key] = int(values[key])
            for key in ("predatordamage", "coalburnrate", "hungerrate", "coldintensity"): values[key] = float(values[key])
            values["extra_args"] = values["extra_args"].split() if values["extra_args"] else []
        except ValueError:
            messagebox.showerror("配置无效", "端口、人数和天数应为整数，倍率应为数字"); return
        self._busy(True, "正在保存配置…")
        self.runner.submit(lambda: self.api.request("/api/config", "POST", values), lambda _: self._action_ok("保存配置"), self._operation_failed)

    def toggle_plugin(self, active):
        selected = self.plugin_tree.selection()
        if not selected: messagebox.showinfo("插件管理", "请先选择一个插件"); return
        name = selected[0]; path = "/api/patch/activate" if active else "/api/patch/deactivate"
        self.runner.submit(lambda: self.api.request(path, "POST", {"name": name}), lambda _: self._action_ok("启用插件" if active else "停用插件"), self._operation_failed)

    def refresh_logs(self):
        if not self._require_connection(): return
        path = "/api/injector/logs?tail=1000" if self.log_kind.get() == "注入器日志" else "/api/logs?tail=1000"
        self.runner.submit(lambda: self.api.request(path), lambda d: self._set_log(d.get("content", "")), self._operation_failed)

    def _auto_log_changed(self):
        if self.auto_log_job:
            self.root.after_cancel(self.auto_log_job)
            self.auto_log_job = None
        if self.auto_log_var.get():
            self.refresh_logs()
            self._schedule_auto_log()

    def _schedule_auto_log(self):
        if self.auto_log_var.get():
            self.auto_log_job = self.root.after(3000, self._auto_log_tick)

    def _auto_log_tick(self):
        self.auto_log_job = None
        if self.auto_log_var.get() and self.api:
            self.refresh_logs()
            self._schedule_auto_log()

    def _set_log(self, content):
        self.log_text.delete("1.0", "end"); self.log_text.insert("1.0", content); self.log_text.see("end")

    def _require_connection(self):
        if self.api and self.connected: return True
        messagebox.showwarning("尚未连接", "请先连接 Linux 管理面板"); return False

    def close(self):
        self.runner.closed = True
        if self.refresh_job:
            try: self.root.after_cancel(self.refresh_job)
            except Exception: pass
        if self.auto_log_job:
            try: self.root.after_cancel(self.auto_log_job)
            except Exception: pass
        self.root.destroy()


def main():
    enable_windows_dpi_awareness()
    root = tk.Tk(); ServerManagerApp(root); root.mainloop()


if __name__ == "__main__": main()
