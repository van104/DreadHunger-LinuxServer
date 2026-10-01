# -*- coding: utf-8 -*-
"""Shared HTTP, persistence and Tk helpers for the Windows remote clients."""

from __future__ import annotations

import json
import os
import queue
import threading
import ctypes
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional


APP_NAME = "DreadHungerRemote"
BG = "#F3F6FA"
PANEL = "#FFFFFF"
PANEL_2 = "#F7F9FC"
TEXT = "#172033"
MUTED = "#66758A"
ACCENT = "#2563EB"
SUCCESS = "#16A36A"
WARNING = "#D97706"
DANGER = "#DC3545"
BORDER = "#DCE3EC"


def enable_windows_dpi_awareness() -> None:
    """Keep Tk text and controls sharp on 125%-250% Windows displays."""
    if os.name != "nt":
        return
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    target = Path(base) / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_settings(name: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    path = config_dir() / (name + ".json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            result = dict(defaults)
            result.update(value)
            return result
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    return dict(defaults)


def save_settings(name: str, value: Dict[str, Any]) -> None:
    path = config_dir() / (name + ".json")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temp), str(path))


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class RemoteApi:
    def __init__(self, host: str, port: Any = None, token: str = "", timeout: float = 8.0):
        clean_host = host.strip().rstrip("/")
        if not clean_host:
            raise ApiError("请输入服务器 IP 或域名")
        if "://" not in clean_host:
            clean_host = "http://" + clean_host
        parsed = urllib.parse.urlsplit(clean_host)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ApiError("服务器地址格式无效")
        try:
            effective_port = parsed.port if parsed.port is not None else int(port)
        except (TypeError, ValueError):
            raise ApiError("请输入有效端口，或直接填写 IP:端口")
        if not 1 <= effective_port <= 65535:
            raise ApiError("端口必须在 1-65535 之间")
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = "[" + hostname + "]"
        self.port = effective_port
        self.base_url = "%s://%s:%d" % (parsed.scheme, hostname, effective_port)
        self.token = token
        self.timeout = timeout

    def request(self, path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None) -> Any:
        data = None
        headers = {"Accept": "application/json", "User-Agent": "DreadHunger-Windows-Remote/1.0"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8", "replace"))
                message = payload.get("error") or payload.get("message") or str(exc)
            except Exception:
                message = "HTTP %d: %s" % (exc.code, exc.reason)
            raise ApiError(str(message), exc.code)
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise ApiError("无法连接 %s（%s）" % (self.base_url, reason))
        except (TimeoutError, OSError) as exc:
            raise ApiError("连接超时或网络异常：%s" % exc)
        except json.JSONDecodeError:
            raise ApiError("服务器返回的不是有效 JSON，请检查端口是否正确")


class AsyncRunner:
    """Run network work outside Tk's UI thread and marshal callbacks safely."""

    def __init__(self, root):
        self.root = root
        self.results = queue.Queue()
        self.closed = False
        self.root.after(80, self._drain)

    def submit(
        self,
        work: Callable[[], Any],
        success: Optional[Callable[[Any], None]] = None,
        failure: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        def run() -> None:
            try:
                self.results.put((success, work(), None))
            except Exception as exc:
                self.results.put((failure, None, exc))

        threading.Thread(target=run, daemon=True).start()

    def _drain(self) -> None:
        if self.closed:
            return
        try:
            while True:
                callback, value, error = self.results.get_nowait()
                if callback:
                    callback(error if error is not None else value)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)


def apply_dark_theme(root) -> None:
    from tkinter import ttk
    import tkinter.font as tkfont

    root.configure(bg=BG)
    for font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(font_name).configure(family="Microsoft YaHei UI", size=10)
        except Exception:
            pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Microsoft YaHei UI", 10))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
    style.configure("Subtitle.TLabel", foreground=MUTED, font=("Microsoft YaHei UI", 10))
    style.configure("CardTitle.TLabel", background=PANEL, font=("Microsoft YaHei UI", 11, "bold"))
    style.configure("CardMuted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("TButton", padding=(14, 9), font=("Microsoft YaHei UI", 9), borderwidth=1, background=PANEL, foreground=TEXT, relief="flat")
    style.map("TButton", background=[("active", "#E8EEF8"), ("pressed", "#DDE7F5")])
    style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", bordercolor=ACCENT)
    style.map("Accent.TButton", background=[("active", "#1D4ED8"), ("disabled", "#9CB5EC")], foreground=[("disabled", "#EEF3FF")])
    style.configure("Success.TButton", background=SUCCESS, foreground="#FFFFFF", bordercolor=SUCCESS)
    style.map("Success.TButton", background=[("active", "#118257")])
    style.configure("Danger.TButton", background=DANGER, foreground="#FFFFFF", bordercolor=DANGER)
    style.map("Danger.TButton", background=[("active", "#B92B39")])
    style.configure("Warning.TButton", background=WARNING, foreground="#FFFFFF", bordercolor=WARNING)
    style.map("Warning.TButton", background=[("active", "#B76105")])
    style.configure("TEntry", padding=9, fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
    style.configure("TSpinbox", padding=8, fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, arrowcolor=MUTED, bordercolor=BORDER)
    style.configure("TCombobox", padding=8, fieldbackground=PANEL, foreground=TEXT, arrowcolor=MUTED, bordercolor=BORDER)
    style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 11), borderwidth=0, font=("Microsoft YaHei UI", 10))
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACCENT)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=1, bordercolor=BORDER, font=("Microsoft YaHei UI", 9))
    style.configure("Treeview.Heading", background=PANEL_2, foreground="#42526A", relief="flat", padding=9, font=("Microsoft YaHei UI", 9, "bold"))
    style.map("Treeview", background=[("selected", "#E0EAFE")], foreground=[("selected", "#173B82")])
    style.configure("TLabelframe", background=PANEL, foreground=TEXT, bordercolor=BORDER, relief="solid")
    style.configure("TLabelframe.Label", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("TCheckbutton", background=PANEL, foreground=TEXT)


def center_window(root, width: int, height: int) -> None:
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = max(0, (sw - width) // 2), max(0, (sh - height) // 2)
    root.geometry("%dx%d+%d+%d" % (width, height, x, y))
    root.minsize(min(width, 980), min(height, 680))
