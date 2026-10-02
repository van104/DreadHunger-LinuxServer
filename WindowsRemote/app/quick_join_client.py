# -*- coding: utf-8 -*-
"""Windows quick-join launcher for a Dread Hunger dedicated server."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from remote_common import (
    ApiError,
    AsyncRunner,
    RemoteApi,
    apply_dark_theme,
    center_window,
    enable_windows_dpi_awareness,
    load_settings,
    save_settings,
)


APP_ID = "1418630"
QUICK_JOIN_NAME = "恐惧饥饿进服器"
QUICK_JOIN_VERSION = "2.0.0"
BG = "#EEF3F6"
PANEL = "#FFFFFF"
TEXT = "#172C3D"
MUTED = "#667B88"
ACCENT = "#087E95"
BORDER = "#D8E3E9"
APP_USER_MODEL_ID = "van104.DreadHungerQuickJoin.2.0.0"
DEFAULT_ADDRESS = "127.0.0.1:9100"
DEFAULT_CLIENT = Path(r"E:\Dread Hunger\DreadHunger.exe")
GAME_PROCESS_NAMES = ("DreadHunger-Win64-Shipping.exe", "DreadHunger.exe")
CLIENT_BRIDGE_PORT = 54730
CLIENT_BRIDGE_TIMEOUT_SECONDS = 2
CLIENT_BRIDGE_ACK_SECONDS = 2.0
GAME_LOG = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DreadHunger" / "Saved" / "Logs" / "DreadHunger.log"
TRACE_LOG = GAME_LOG.with_name("QuickJoinTrace.log")
ANNOUNCEMENT_FOCUS_DELAY_MS = 300
PRE_JOIN_ANNOUNCEMENT_DELAY_MS = 3000
BLACKLIST_WARNING_DELAY_MS = 5000
BLACKLIST_SUCCESS_DELAY_MS = 1000
# The client bridge accepts a message immediately, but the game renders it on
# a later game-thread tick.  Keep the checking notice and announcement visible
# long enough that the result cannot replace them before the HUD has drawn them.
BLACKLIST_CHECK_MIN_RESULT_MS = 6000
LOBBY_NOTICE_RESULT_MS = 6500
CHECKING_NOTICE_OVERLAY_MS = 5200
JOIN_RETRY_DELAY_MS = 3000
LOBBY_STABLE_SECONDS = 5
HISTORY_LIMIT = 20
CLIENT_BRIDGE_HOOK_FILENAME = "connect_client_win64.js"
CLIENT_NOTICE_HOOK_FILENAME = "quick_join_announce_hook.js"
DEFAULT_ANNOUNCEMENT = "欢迎来到服务器，祝你游戏愉快！"
DEFAULT_GM_PORT = 9900
CLIENT_ROLE_TYPES = {
    "captain": 1,
    "engineer": 2,
    "hunter": 3,
    "cook": 4,
    "navigator": 5,
    "chaplain": 6,
    "marine": 7,
    "royal marine": 7,
    "doctor": 8,
}
LOCAL_USER_ID_PATTERN = re.compile(
    r"(?:UniqueId:\s*|userId:\s*)(?:EOSPlus:)?(?P<user_id>\d{10,20}_\+_\|[0-9A-Za-z-]{8,})",
    re.IGNORECASE,
)


def trace_quick_join(event: str) -> None:
    try:
        TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_LOG.open("a", encoding="utf-8") as trace_file:
            trace_file.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), event.replace("\n", " ")[:400]))
    except OSError:
        pass


def log_reports_join_failure(text: str) -> bool:
    markers = (
        "Host closed the connection",
        "ConnectionTimeout",
        "ConnectionLost",
        "PendingConnectionFailure",
        "Connection refused",
    )
    return any(marker.lower() in text.lower() for marker in markers)


def log_reports_game_map(text: str) -> bool:
    return "LogLoad: LoadMap:" in text and "Departure_Persistent" in text


def log_reports_join_complete(text: str) -> bool:
    for line in reversed(text.splitlines()):
        if log_reports_join_failure(line):
            return False
        if "LogNet: Join succeeded:" in line or (
            "LogLoad: Took " in line and "LoadMap(" in line and "Departure_Persistent" in line
        ):
            return True
    return False


def log_reports_lobby_ready(text: str) -> bool:
    game_classes = re.findall(r"LogLoad: Game class is '([^']+)'", text)
    return bool(game_classes and game_classes[-1] == "BP_LobbyGameMode_C")


def game_log_is_lobby_ready() -> bool:
    try:
        with GAME_LOG.open("rb") as log_file:
            size = GAME_LOG.stat().st_size
            probe_size = 8 * 1024 * 1024
            ranges = [(0, min(size, probe_size))]
            tail_start = max(0, size - probe_size)
            if tail_start > ranges[0][1]:
                ranges.append((tail_start, size))

            latest_offset = -1
            latest_class = b""
            for start, end in ranges:
                log_file.seek(start)
                raw = log_file.read(end - start)
                for match in re.finditer(rb"LogLoad: Game class is '([^']+)'", raw):
                    absolute_offset = start + match.start()
                    if absolute_offset > latest_offset:
                        latest_offset = absolute_offset
                        latest_class = match.group(1)
            return latest_class == b"BP_LobbyGameMode_C"
    except OSError:
        return False


def normalize_history(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        raw = item.get("address", "") if isinstance(item, dict) else item
        try:
            address = normalize_server_address(str(raw))
        except (TypeError, ValueError):
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(address)
        if len(result) >= HISTORY_LIMIT:
            break
    return result


def remember_history(history: list[str], address: str) -> list[str]:
    normalized = normalize_server_address(address)
    return [normalized] + [item for item in normalize_history(history) if item.lower() != normalized.lower()][: HISTORY_LIMIT - 1]


def address_host(address: str) -> str:
    normalized = normalize_server_address(address)
    if normalized.startswith("["):
        return normalized[1:].split("]", 1)[0]
    return normalized.rsplit(":", 1)[0]


def extract_local_user_id(text: str) -> str:
    matches = list(LOCAL_USER_ID_PATTERN.finditer(text or ""))
    return matches[-1].group("user_id") if matches else ""


def read_local_user_id() -> str:
    def read_from_log(path: Path) -> str:
        with path.open("rb") as log_file:
            size = path.stat().st_size
            probe_size = 8 * 1024 * 1024
            ranges = [(0, min(size, probe_size))]
            tail_start = max(0, size - probe_size)
            if tail_start > ranges[0][1]:
                ranges.append((tail_start, size))
            latest = ""
            for start, end in ranges:
                log_file.seek(start)
                candidate = extract_local_user_id(log_file.read(end - start).decode("utf-8", errors="replace"))
                if candidate:
                    latest = candidate
            return latest

    try:
        current = read_from_log(GAME_LOG)
        if current:
            return current
        # A new client session can rotate the active log before it writes its
        # identity. Reuse only the newest few DreadHunger backups as a fallback.
        log_dir = GAME_LOG.parent
        backups = sorted(
            (path for path in log_dir.glob("DreadHunger*-backup-*.log") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:6]
        for backup in backups:
            candidate = read_from_log(backup)
            if candidate:
                return candidate
        return ""
    except OSError:
        return ""


def focus_running_game() -> bool:
    """Bring the active shipping-client window forward without touching its input."""
    try:
        import ctypes
        from ctypes import wintypes

        target_pids = {pid for pid, _name in running_game_processes(("DreadHunger-Win64-Shipping.exe",))}
        if not target_pids:
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        found = []

        def visit(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in target_pids and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
            return True

        callback = enum_proc(visit)
        user32.EnumWindows(callback, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except (AttributeError, OSError):
        return False


def format_blacklist_warning(matches: object, limit: int = 500) -> str:
    if not isinstance(matches, list):
        return ""
    blocks = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        name = str(match.get("name") or "未知玩家").strip()
        reason = str(match.get("reason") or "未填写").strip()
        steam_id = str(match.get("steam_id") or "").strip()
        lines = ["检测到黑名单玩家：%s" % name, "理由：%s" % reason]
        if steam_id:
            lines.append("Steam ID：%s" % steam_id)
        candidate = "\n\n".join(blocks + ["\n".join(lines)])
        if len(candidate) > limit:
            break
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    hidden = len([item for item in matches if isinstance(item, dict)]) - len(blocks)
    text = "\n\n".join(blocks)
    if hidden > 0:
        suffix = "\n\n另有 %d 名黑名单玩家，请查看进服器。" % hidden
        if len(text) + len(suffix) <= limit:
            text += suffix
    return text


def format_local_blacklist_block(match: object) -> str:
    if not isinstance(match, dict):
        return ""
    name = str(match.get("name") or "当前账号").strip()
    reason = str(match.get("reason") or "未填写").strip()
    steam_id = str(match.get("steam_id") or "").strip()
    lines = ["当前账号已被列入黑名单：%s" % name, "理由：%s" % reason]
    if steam_id:
        lines.append("Steam ID：%s" % steam_id)
    lines.append("进服器已阻止本次连接。")
    return "\n".join(lines)


def preflight_matches(data: object) -> list[dict]:
    if not isinstance(data, dict):
        return []
    candidates = []
    if isinstance(data.get("local_match"), dict):
        candidates.append(data["local_match"])
    candidates.extend(item for item in data.get("lobby_matches", []) if isinstance(item, dict))
    result = []
    seen = set()
    for item in candidates:
        key = str(item.get("user_id") or item.get("steam_id") or item.get("name") or "").strip().casefold()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result


def preflight_decision(data: object) -> str:
    if preflight_matches(data):
        return "blocked"
    if not isinstance(data, dict) or not bool(data.get("local_identity_available", False)):
        return "identity_unavailable"
    if bool(data.get("lobby_stale", False)):
        return "lobby_stale"
    return "clear"


def compact_game_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def format_preflight_block_notice(matches: object) -> str:
    if not isinstance(matches, list):
        return ""
    valid = [match for match in matches if isinstance(match, dict)]
    if not valid:
        return ""
    first = valid[0]
    name = compact_game_text(first.get("name") or "未知玩家", 14)
    reason = compact_game_text(first.get("reason") or "未填写", 18)
    text = "发现黑名单用户：%s；理由：%s" % (name, reason)
    if len(valid) > 1:
        text += "；另有%d人" % (len(valid) - 1)
    return text


def format_preflight_clear_notice() -> str:
    return "检测完成，未发现黑名单用户。"


def resource_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if name.startswith("assets/") and not hasattr(sys, "_MEIPASS"):
        root = root.parent
    return root / name


def set_windows_app_user_model_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def client_win64_directory(executable: Path) -> Path:
    if executable.name.lower() == "dreadhunger-win64-shipping.exe":
        return executable.parent
    candidate = executable.parent / "DreadHunger" / "Binaries" / "Win64"
    return candidate


def client_working_directory(executable: Path) -> Path:
    if executable.name.lower() == "dreadhunger-win64-shipping.exe":
        win64 = executable.parent
        return win64.parents[2] if len(win64.parents) >= 3 else win64
    return executable.parent


def normalize_server_address(value: str) -> str:
    address = value.strip()
    if not address:
        raise ValueError("请输入服务器 IP 和端口")
    if "://" in address or "/" in address or "?" in address or "#" in address:
        raise ValueError("地址必须使用 IP:端口 或 域名:端口 格式")

    if address.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\]:(\d+)", address)
        if not match:
            raise ValueError("IPv6 地址必须使用 [IPv6]:端口 格式")
        host, port_text = match.groups()
        normalized_host = "[%s]" % host
    else:
        if address.count(":") != 1:
            raise ValueError("地址必须包含一个明确端口，例如 127.0.0.1:9100")
        host, port_text = address.rsplit(":", 1)
        host = host.strip()
        if not host or not re.fullmatch(r"[A-Za-z0-9._-]+", host):
            raise ValueError("服务器 IP 或域名格式无效")
        normalized_host = host

    try:
        port = int(port_text)
    except ValueError:
        raise ValueError("端口必须是数字")
    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1-65535 之间")
    return "%s:%d" % (normalized_host, port)


def normalize_query_token(value: object) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("尚未填写 GM 控制台生成的只读查询令牌")
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,}", token):
        raise ValueError("查询令牌格式不正确；请从 GM 控制台黑名单页重新复制只读查询令牌")
    return token


def _registry_steam_roots() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    roots = []
    for hive, key_name, value_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                roots.append(Path(winreg.QueryValueEx(key, value_name)[0]))
        except OSError:
            continue
    return roots


def steam_library_roots() -> list[Path]:
    candidates = _registry_steam_roots() + [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    roots = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen or not candidate.is_dir():
            continue
        seen.add(key)
        roots.append(candidate)
        library_file = candidate / "steamapps" / "libraryfolders.vdf"
        try:
            content = library_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content, flags=re.IGNORECASE):
            library = Path(raw_path.replace("\\\\", "\\"))
            library_key = str(library).lower()
            if library_key not in seen and library.is_dir():
                seen.add(library_key)
                roots.append(library)
    return roots


def discover_game_executable() -> Path | None:
    if DEFAULT_CLIENT.is_file():
        return DEFAULT_CLIENT
    for library_root in steam_library_roots():
        steamapps = library_root / "steamapps"
        manifest = steamapps / ("appmanifest_%s.acf" % APP_ID)
        try:
            content = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r'"installdir"\s+"([^"]+)"', content, flags=re.IGNORECASE)
        install_name = match.group(1) if match else "Dread Hunger"
        install_dir = steamapps / "common" / install_name
        candidates = (
            install_dir / "DreadHunger.exe",
            install_dir / "DreadHunger" / "Binaries" / "Win64" / "DreadHunger-Win64-Shipping.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return None


def process_is_running(image_names: tuple[str, ...] = GAME_PROCESS_NAMES) -> bool:
    if os.name != "nt":
        return False
    return bool(running_game_processes(image_names))


def running_game_processes(image_names: tuple[str, ...] = GAME_PROCESS_NAMES) -> list[tuple[int, str]]:
    """Enumerate game processes without launching the relatively slow tasklist.exe."""
    if os.name != "nt":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessEntry32W(ctypes.Structure):
            _fields_ = (
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            )

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_snapshot = kernel32.CreateToolhelp32Snapshot
        create_snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        create_snapshot.restype = wintypes.HANDLE
        process_first = kernel32.Process32FirstW
        process_first.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
        process_first.restype = wintypes.BOOL
        process_next = kernel32.Process32NextW
        process_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W))
        process_next.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        snapshot = create_snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
        if snapshot == wintypes.HANDLE(-1).value:
            return []
        wanted = {name.lower() for name in image_names}
        matches = []
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            has_entry = bool(process_first(snapshot, ctypes.byref(entry)))
            while has_entry:
                name = entry.szExeFile
                if name.lower() in wanted:
                    matches.append((int(entry.th32ProcessID), name))
                has_entry = bool(process_next(snapshot, ctypes.byref(entry)))
        finally:
            close_handle(snapshot)
        return matches
    except (AttributeError, OSError, ValueError):
        return []


def resolve_host(address: str) -> str:
    normalized = normalize_server_address(address)
    host = normalized[1:].split("]", 1)[0] if normalized.startswith("[") else normalized.rsplit(":", 1)[0]
    # The bundled connector's ConnectForIP command accepts an IPv4 address.
    infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_DGRAM)
    if not infos:
        raise OSError("无法解析服务器地址")
    return infos[0][4][0]


def running_game_executable() -> Path | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    for pid, _name in running_game_processes(("DreadHunger-Win64-Shipping.exe",)):
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return Path(buffer.value)
        finally:
            kernel32.CloseHandle(handle)
    return None


def connector_request(address: str) -> dict:
    normalized = normalize_server_address(address)
    resolved = resolve_host(normalized)
    port = int(normalized.rsplit(":", 1)[1])
    return {"op": "Connect", "IP": resolved, "Port": port}


def send_client_bridge_command(command: dict, ack_seconds: float = CLIENT_BRIDGE_ACK_SECONDS) -> dict:
    payload = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-16-le")
    trace_quick_join("bridge-send op=%s" % command.get("op", "?"))
    result = None
    sent = False
    try:
        with socket.create_connection(("127.0.0.1", CLIENT_BRIDGE_PORT), timeout=CLIENT_BRIDGE_TIMEOUT_SECONDS) as client:
            client.sendall(payload)
            sent = True
            client.shutdown(socket.SHUT_WR)
            deadline = time.monotonic() + ack_seconds
            response = bytearray()
            while time.monotonic() < deadline:
                client.settimeout(max(0.01, deadline - time.monotonic()))
                try:
                    chunk = client.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                response.extend(chunk)
                if len(response) > 65536:
                    break
                try:
                    result = json.loads(response.decode("utf-16-le").rstrip("\x00"))
                    break
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
    except OSError as exc:
        if sent and command.get("op") == "Connect":
            trace_quick_join("bridge-queued op=Connect; waiting-game-log")
            return {}
        raise OSError("客户端内置连接服务尚未就绪（127.0.0.1:%d）" % CLIENT_BRIDGE_PORT) from exc

    if not isinstance(result, dict) or not result:
        trace_quick_join("bridge-no-ack op=%s" % command.get("op", "?"))
        if command.get("op") == "Connect":
            trace_quick_join("bridge-queued op=Connect; waiting-game-log")
            return {}
        raise OSError("客户端连接器未返回有效回执，请确认游戏大厅已就绪")
    if result.get("success") is False:
        trace_quick_join("bridge-rejected op=%s error=%s" % (command.get("op", "?"), result.get("error") or "unknown"))
        raise OSError(str(result.get("error") or "客户端连接器拒绝了命令"))
    trace_quick_join("bridge-accepted op=%s" % command.get("op", "?"))
    return result


def send_connector_command(address: str) -> str:
    command = connector_request(address)
    send_client_bridge_command(command)
    return str(command["IP"])


def send_client_announcement(text: str) -> None:
    executable = running_game_executable()
    if executable is None:
        raise OSError("客户端未运行，无法发送游戏原生文字")
    win64 = client_win64_directory(executable)
    trigger = win64 / "quick_join_announce.json"
    receipt = win64 / "quick_join_announce_result.json"
    command_id = "%d-%d" % (os.getpid(), time.time_ns())
    command = {"id": command_id, "text": text, "expires_at": int(time.time() * 1000) + 3000}
    temporary = trigger.with_suffix(".%s.tmp" % command_id)
    temporary.write_text(json.dumps(command, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, trigger)
    trace_quick_join("native-notice-queued id=%s" % command_id)
    deadline = time.monotonic() + CLIENT_BRIDGE_ACK_SECONDS
    while time.monotonic() < deadline:
        try:
            result = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            result = {}
        if isinstance(result, dict) and result.get("id") == command_id:
            if result.get("success") is not True:
                raise OSError(str(result.get("error") or "游戏原生文字发送失败"))
            trace_quick_join("native-notice-displayed id=%s" % command_id)
            return
        time.sleep(0.05)
    raise OSError("游戏原生公告 Hook 未返回回执；首次安装后请重启游戏客户端一次")


def read_client_fixed_roles() -> list[dict]:
    for attempt in range(1, 6):
        result = send_client_bridge_command({"op": "GetFixedRoles"}, ack_seconds=1.0)
        records = result.get("PlayerRoles")
        if isinstance(records, dict):
            records = records.get("Records")

        roles = []
        seen_users = set()
        seen_roles = set()
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, dict):
                    continue
                user_id = str(record.get("UID") or record.get("UniqueID") or record.get("user_id") or "").strip()
                if user_id.startswith("EOSPlus:"):
                    user_id = user_id[len("EOSPlus:") :]
                raw_role = record.get("Job", record.get("role", 0))
                try:
                    role = int(raw_role)
                except (TypeError, ValueError):
                    role = CLIENT_ROLE_TYPES.get(str(raw_role).strip().casefold(), 0)
                if not user_id or not 1 <= role <= 8:
                    continue
                user_key = user_id.casefold()
                if user_key in seen_users or role in seen_roles:
                    raise OSError("客户端大厅职业名单存在重复玩家或重复职业")
                seen_users.add(user_key)
                seen_roles.add(role)
                roles.append({"user_id": user_id, "role": role})

        if roles:
            return roles
        trace_quick_join("fixed-roles-read empty attempt=%d" % attempt)
        if attempt < 5:
            time.sleep(0.2)
    raise OSError("客户端连接器连续 5 次没有返回大厅职业名单，请留在大厅职业选择界面后重试")


def show_game_notice(text: str, duration_ms: int, danger: bool = False) -> None:
    """Show a no-focus overlay above the game without using its message queue."""
    foreground = None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        foreground = user32.GetForegroundWindow()
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg="#C94444" if danger else "#0A2440")
    root.attributes("-topmost", True)
    try:
        root.attributes("-toolwindow", True)
        root.attributes("-disabled", True)
    except tk.TclError:
        pass

    screen_width = root.winfo_screenwidth()
    width = min(860, max(560, screen_width - 120))
    frame = tk.Frame(root, bg="#C94444" if danger else "#0A2440", highlightbackground="#FF9A9A" if danger else "#41AEFF", highlightthickness=2)
    frame.pack(fill="both", expand=True)
    tk.Label(
        frame,
        text="DREAD HUNGER  ·  快速进服器",
        bg="#C94444" if danger else "#0A2440",
        fg="#FFE4E4" if danger else "#7DD5FF",
        font=("Segoe UI", 10, "bold"),
        anchor="w",
    ).pack(fill="x", padx=22, pady=(15, 3))
    tk.Label(
        frame,
        text=text,
        bg="#C94444" if danger else "#0A2440",
        fg="white",
        font=("Microsoft YaHei UI", 17, "bold"),
        anchor="w",
        justify="left",
        wraplength=width - 44,
    ).pack(fill="both", expand=True, padx=22, pady=(0, 17))
    root.update_idletasks()
    root.geometry("%dx%d+%d+42" % (width, root.winfo_reqheight(), (screen_width - width) // 2))
    if os.name == "nt":
        user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | 0x08000000)  # WS_EX_NOACTIVATE
    root.deiconify()
    root.update()
    if foreground:
        user32.SetForegroundWindow(foreground)
    root.after(max(1000, duration_ms), root.destroy)
    root.mainloop()


def launch_game_notice(text: str, duration_ms: int, danger: bool = False) -> None:
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve()))
    command.extend(["--game-notice", text, "--notice-duration-ms", str(duration_ms)])
    if danger:
        command.append("--notice-danger")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(command, creationflags=flags)


class QuickJoinApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("%s · %s" % (QUICK_JOIN_NAME, QUICK_JOIN_VERSION))
        self.ui_scale = max(1.0, root.winfo_fpixels("1i") / 96)
        window_width = min(round(1100 * self.ui_scale), root.winfo_screenwidth() - 80)
        window_height = min(round(760 * self.ui_scale), root.winfo_screenheight() - 100)
        center_window(root, window_width, window_height)
        root.minsize(min(round(980 * self.ui_scale), window_width), min(700, window_height))
        apply_dark_theme(root)
        self.settings = load_settings(
            "quick_join",
            {
                "address": DEFAULT_ADDRESS,
                "game_executable": str(DEFAULT_CLIENT),
                "history": [],
                "announcement_enabled": False,
                "announcement_text": DEFAULT_ANNOUNCEMENT,
                "blacklist_check_enabled": True,
                "fixed_roles_enabled": True,
                "gm_api_port": DEFAULT_GM_PORT,
                "blacklist_check_token": "",
            },
        )
        self.history = normalize_history(self.settings.get("history"))
        self.address_var = tk.StringVar(value=str(self.settings.get("address") or DEFAULT_ADDRESS))
        self.exe_var = tk.StringVar(value=str(self.settings.get("game_executable") or DEFAULT_CLIENT))
        self.announcement_enabled_var = tk.BooleanVar(value=bool(self.settings.get("announcement_enabled", False)))
        self.announcement_status_var = tk.StringVar(value="公告将在当前游戏大厅中显示")
        self.blacklist_check_enabled_var = tk.BooleanVar(value=bool(self.settings.get("blacklist_check_enabled", True)))
        self.fixed_roles_enabled_var = tk.BooleanVar(value=bool(self.settings.get("fixed_roles_enabled", True)))
        self.gm_api_port_var = tk.StringVar(value=str(self.settings.get("gm_api_port") or DEFAULT_GM_PORT))
        self.blacklist_check_token_var = tk.StringVar(value=str(self.settings.get("blacklist_check_token") or ""))
        self.blacklist_status_var = tk.StringVar(value="进入前将同时检查本机账号与 Linux 实时大厅")
        self.process_var = tk.StringVar(value="正在检测客户端…")
        self.status_var = tk.StringVar(value="请先启动 Dread Hunger 并留在大厅")
        self._last_running = None
        self._status_locked = False
        self._join_active = False
        self._join_generation = 0
        self._join_attempt = 0
        self._connector_waits = 0
        self._join_log_offset = 0
        self._join_attempt_started = 0.0
        self._join_load_seen_at = None
        self._pre_join_announcement_handled = False
        self._blacklist_warning_text = ""
        self._blacklist_check_started_at = 0.0
        self._fixed_roles_synced = False
        self._fixed_roles_syncing = False
        self._retry_requires_fresh_lobby = False
        self._retry_log_offset = 0
        self._lobby_ready_since = None
        self._header_icon = None
        self._window_icon = None
        self.runner = AsyncRunner(root)
        self._build()
        root.update_idletasks()
        content_height = root.winfo_height() - self.connect_canvas.winfo_height() + self.connect_body.winfo_reqheight()
        window_height = min(content_height + 12, root.winfo_screenheight() - 100)
        center_window(root, window_width, window_height)
        root.minsize(min(round(980 * self.ui_scale), window_width), min(700, window_height))
        self._refresh_process_state()

    def _build(self) -> None:
        try:
            self.root.iconbitmap(str(resource_path("assets/quick_join_taskbar.ico")))
            self._window_icon = tk.PhotoImage(file=str(resource_path("assets/quick_join_taskbar.png")))
            self.root.iconphoto(True, self._window_icon)
        except (OSError, tk.TclError):
            pass

        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        style.configure("TButton", background=PANEL, foreground=TEXT, bordercolor=BORDER, padding=(16, 10))
        style.map("TButton", background=[("active", "#EAF2F5"), ("pressed", "#DCEBF0")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT, font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("disabled", "#A7C4CD"), ("pressed", "#055C70"), ("active", "#096D82")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, bordercolor=BORDER, padding=10)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.configure("Toggle.TCheckbutton", background=PANEL, foreground=TEXT, padding=(0, 4), font=("Microsoft YaHei UI", 10))
        style.map("Toggle.TCheckbutton", background=[("active", PANEL)], indicatorbackground=[("selected", ACCENT)])
        style.configure("Treeview", rowheight=42, borderwidth=0, background=PANEL, fieldbackground=PANEL, foreground=TEXT)
        style.configure("Treeview.Heading", background="#EEF4F7", foreground=MUTED, padding=12)
        style.map("Treeview", background=[("selected", "#DDF1F5")], foreground=[("selected", "#075C70")])

        sidebar = tk.Frame(self.root, bg="#102B3C", width=round(184 * self.ui_scale))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg="#102B3C")
        brand.pack(fill="x", padx=22, pady=(28, 26))
        try:
            self._header_icon = tk.PhotoImage(file=str(resource_path("assets/quick_join_icon_v2.png"))).subsample(8, 8)
            tk.Label(brand, image=self._header_icon, bg="#102B3C").pack(anchor="w", pady=(0, 14))
        except (OSError, tk.TclError):
            pass
        tk.Label(brand, text="恐惧饥饿", bg="#102B3C", fg="#F1F8FC", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        tk.Label(brand, text="进服器", bg="#102B3C", fg="#80D4E2", font=("Microsoft YaHei UI", 12)).pack(anchor="w", pady=(4, 0))
        tk.Frame(sidebar, bg="#294553", height=1).pack(fill="x", padx=22, pady=(0, 20))
        self.nav_buttons = []
        for index, title in enumerate(("连接服务器", "本地公告", "最近服务器", "客户端设置")):
            button = tk.Button(sidebar, text="  " + title, command=lambda page=index: self._show_page(page),
                               anchor="w", bg="#102B3C", fg="#AFC6D1", activebackground="#1D4356",
                               activeforeground="white", relief="flat", borderwidth=0, cursor="hand2",
                               font=("Microsoft YaHei UI", 10), padx=12, pady=12)
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons.append(button)
        sidebar_footer = tk.Frame(sidebar, bg="#102B3C")
        sidebar_footer.pack(side="bottom", fill="x", padx=22, pady=24)
        tk.Label(sidebar_footer, text="DREAD HUNGER", bg="#102B3C", fg="#94ADBB", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(sidebar_footer, text="版本 " + QUICK_JOIN_VERSION, bg="#102B3C", fg="#8FD7E3", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(6, 0))

        content = tk.Frame(self.root, bg=BG)
        content.pack(side="left", fill="both", expand=True, padx=28, pady=24)
        self.page_title_var = tk.StringVar()
        self.page_subtitle_var = tk.StringVar()
        tk.Label(content, textvariable=self.page_title_var, bg=BG, fg=TEXT, font=("Microsoft YaHei UI", 22, "bold"), anchor="w").pack(fill="x")
        tk.Label(content, textvariable=self.page_subtitle_var, bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x", pady=(6, 20))

        footer = tk.Frame(content, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(16, 0))
        tk.Frame(footer, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))
        tk.Label(footer, textvariable=self.process_var, bg=BG, fg=ACCENT, font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(fill="x")
        self.status_label = tk.Label(footer, textvariable=self.status_var, bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=700)
        self.status_label.pack(fill="x", pady=(5, 0))
        self.status_label.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(1, event.width)))

        page_area = tk.Frame(content, bg=BG)
        page_area.pack(fill="both", expand=True)
        page_area.grid_columnconfigure(0, weight=1)
        page_area.grid_rowconfigure(0, weight=1)
        self.pages = [tk.Frame(page_area, bg=BG) for _ in range(4)]
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")
        connect_page, announcement_page, history_page, client_page = self.pages

        connect_canvas = tk.Canvas(connect_page, bg=BG, highlightthickness=0)
        connect_scroll = ttk.Scrollbar(connect_page, orient="vertical", command=connect_canvas.yview)
        connect_scroll.pack(side="right", fill="y")
        connect_canvas.pack(side="left", fill="both", expand=True)
        connect_canvas.configure(yscrollcommand=connect_scroll.set)
        self.connect_canvas = connect_canvas
        connect_body = tk.Frame(connect_canvas, bg=BG)
        self.connect_body = connect_body
        connect_window = connect_canvas.create_window((0, 0), window=connect_body, anchor="nw")
        connect_body.bind("<Configure>", lambda _event: connect_canvas.configure(scrollregion=connect_canvas.bbox("all")))
        connect_canvas.bind("<Configure>", lambda event: connect_canvas.itemconfigure(connect_window, width=event.width))
        self.root.bind("<MouseWheel>", lambda event: connect_canvas.yview_scroll(-int(event.delta / 120), "units") if connect_page.winfo_ismapped() else None, add="+")

        server_card = self._card(connect_body)
        server_card.pack(fill="x", pady=(0, 16))
        self._card_title(server_card, "目标服务器", "填写服务器 IP 或域名，并带上游戏端口")
        address_row = tk.Frame(server_card, bg=PANEL)
        address_row.pack(fill="x", padx=22, pady=(0, 8))
        self.address_entry = ttk.Entry(address_row, textvariable=self.address_var, font=("Cascadia Mono", 17))
        self.address_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.address_entry.bind("<Return>", lambda _event: self.join_running_game())
        self.address_history_button = ttk.Button(address_row, text="最近 ▾", command=self.show_address_history_menu)
        self.address_history_button.pack(side="left", padx=(10, 0), ipady=5)
        tk.Label(server_card, text="例如 127.0.0.1:9100  ·  地址中的端口是游戏端口", bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 8), anchor="w").pack(fill="x", padx=22, pady=(0, 18))
        join_row = tk.Frame(server_card, bg=PANEL)
        join_row.pack(fill="x", padx=22, pady=(0, 22))
        self.join_button = ttk.Button(join_row, text="进入服务器  →", style="Accent.TButton", command=self.join_running_game)
        self.join_button.pack(side="left", fill="x", expand=True, ipady=5)
        self.launch_button = ttk.Button(join_row, text="启动客户端并进入", command=self.launch_with_address)
        self.launch_button.pack(side="left", padx=(10, 0), ipady=5)
        self.stop_button = ttk.Button(join_row, text="停止重试", command=self.stop_auto_join, state="disabled")
        self.stop_button.pack(side="left", padx=(10, 0), ipady=5)

        security_card = self._card(connect_body)
        security_card.pack(fill="x")
        self._card_title(security_card, "连接前检查", "查询令牌来自 GM 控制台的黑名单页面")
        toggles = tk.Frame(security_card, bg=PANEL)
        toggles.pack(fill="x", padx=22, pady=(0, 12))
        self._large_toggle(toggles, "检查云端黑名单", self.blacklist_check_enabled_var, self._save_settings).pack(side="left")
        self._large_toggle(toggles, "同步大厅职业", self.fixed_roles_enabled_var, self._save_settings).pack(side="left", padx=(24, 0))
        fields = tk.Frame(security_card, bg=PANEL)
        fields.pack(fill="x", padx=22)
        fields.columnconfigure(1, weight=1)
        tk.Label(fields, text="GM 端口", bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        tk.Label(fields, text="只读查询令牌", bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w").grid(row=0, column=1, sticky="w", padx=(14, 0), pady=(0, 6))
        ttk.Entry(fields, textvariable=self.gm_api_port_var, width=10).grid(row=1, column=0, sticky="ew")
        ttk.Entry(fields, textvariable=self.blacklist_check_token_var, show="●").grid(row=1, column=1, sticky="ew", padx=(14, 0))
        security_status = tk.Label(security_card, textvariable=self.blacklist_status_var, bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=660)
        security_status.pack(fill="x", padx=22, pady=(14, 18))
        security_status.bind("<Configure>", lambda event: security_status.configure(wraplength=max(1, event.width)))

        announcement_card = self._card(announcement_page)
        announcement_card.pack(fill="both", expand=True)
        self._card_title(announcement_card, "公告内容", "最多 500 字；自动公告显示后，等待 3 秒再连接")
        self._large_toggle(announcement_card, "进服前自动发布公告", self.announcement_enabled_var, self.save_announcement_settings).pack(anchor="w", padx=22, pady=(0, 12))
        editor = tk.Frame(announcement_card, bg=PANEL)
        editor.pack(fill="both", expand=True, padx=22)
        self.announcement_text = tk.Text(editor, height=8, wrap="word", font=("Microsoft YaHei UI", 11), relief="flat", highlightthickness=1,
                                         highlightbackground=BORDER, highlightcolor=ACCENT, fg=TEXT, bg="#F7FAFC", insertbackground=TEXT, padx=14, pady=12)
        self.announcement_text.pack(side="left", fill="both", expand=True)
        editor_scroll = ttk.Scrollbar(editor, orient="vertical", command=self.announcement_text.yview)
        editor_scroll.pack(side="right", fill="y")
        self.announcement_text.configure(yscrollcommand=editor_scroll.set)
        self.announcement_text.insert("1.0", str(self.settings.get("announcement_text") or DEFAULT_ANNOUNCEMENT))
        announcement_status = tk.Label(announcement_card, textvariable=self.announcement_status_var, bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=660)
        announcement_status.pack(fill="x", padx=22, pady=(12, 0))
        announcement_status.bind("<Configure>", lambda event: announcement_status.configure(wraplength=max(1, event.width)))
        announcement_buttons = tk.Frame(announcement_card, bg=PANEL)
        announcement_buttons.pack(fill="x", padx=22, pady=20)
        ttk.Button(announcement_buttons, text="保存公告", command=self.save_announcement_settings).pack(side="left")
        ttk.Button(announcement_buttons, text="立即发布公告", style="Accent.TButton", command=self.publish_announcement).pack(side="right")

        history_card = self._card(history_page)
        history_card.pack(fill="both", expand=True)
        self._card_title(history_card, "最近连接", "保留最近 20 个地址；双击地址即可填入连接页")
        tree_frame = tk.Frame(history_card, bg=PANEL)
        tree_frame.pack(fill="both", expand=True, padx=22)
        self.history_tree = ttk.Treeview(tree_frame, columns=("address",), show="headings", height=8, selectmode="browse")
        self.history_tree.heading("address", text="服务器地址")
        self.history_tree.column("address", anchor="w", width=480)
        history_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        history_scroll.pack(side="right", fill="y")
        self.history_tree.bind("<Double-1>", lambda _event: self.use_selected_history())
        history_buttons = tk.Frame(history_card, bg=PANEL)
        history_buttons.pack(fill="x", padx=22, pady=20)
        ttk.Button(history_buttons, text="使用所选地址", style="Accent.TButton", command=self.use_selected_history).pack(side="left")
        ttk.Button(history_buttons, text="删除所选", command=self.delete_selected_history).pack(side="left", padx=10)
        ttk.Button(history_buttons, text="清空历史", command=self.clear_history).pack(side="right")
        self._refresh_history_view()

        client_card = self._card(client_page)
        client_card.pack(fill="x")
        self._card_title(client_card, "游戏安装位置", "支持 DreadHunger.exe 或 DreadHunger-Win64-Shipping.exe")
        ttk.Entry(client_card, textvariable=self.exe_var).pack(fill="x", padx=22, pady=(0, 14))
        client_buttons = tk.Frame(client_card, bg=PANEL)
        client_buttons.pack(fill="x", padx=22, pady=(0, 22))
        ttk.Button(client_buttons, text="选择客户端", command=self.choose_executable).pack(side="left")
        ttk.Button(client_buttons, text="启动客户端并进入", style="Accent.TButton", command=self.launch_with_address).pack(side="right")
        tips_card = self._card(client_page)
        tips_card.pack(fill="x", pady=(16, 0))
        self._card_title(tips_card, "使用提示", "启动客户端后，在船上大厅中连接服务器")
        tk.Label(tips_card, text="首次安装或更新连接服务后，需要重启游戏一次。\n如果游戏已经在大厅运行，直接点击“进入服务器”。",
                 bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 10), anchor="w", justify="left").pack(fill="x", padx=22, pady=(0, 22))
        self._show_page(0)

    def _show_page(self, index: int) -> None:
        titles = ("连接服务器", "本地公告", "最近服务器", "客户端设置")
        subtitles = ("在游戏大厅中，连接你要加入的服务器。", "将你的公告显示在游戏大厅中。", "常用的服务器，下次更快找到。", "选择游戏程序，准备进入大厅。")
        for page in self.pages:
            page.grid_remove()
        self.pages[index].grid()
        self.page_title_var.set(titles[index])
        self.page_subtitle_var.set(subtitles[index])
        for position, button in enumerate(self.nav_buttons):
            button.configure(bg="#1E4A5D" if position == index else "#102B3C", fg="#A3EBF4" if position == index else "#AFC6D1")
        self.nav_buttons[index].focus_set()

    @staticmethod
    def _large_toggle(parent: tk.Widget, text: str, variable: tk.BooleanVar, command, background: str = PANEL) -> tk.Frame:
        holder = tk.Frame(parent, bg=background)
        ttk.Checkbutton(holder, text=text, variable=variable, command=command, style="Toggle.TCheckbutton", cursor="hand2").pack(anchor="w")
        return holder

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)

    @staticmethod
    def _card_title(parent: tk.Widget, title: str, subtitle: str) -> None:
        tk.Label(parent, text=title, bg=PANEL, fg=TEXT, font=("Microsoft YaHei UI", 12, "bold"), anchor="w").pack(fill="x", padx=22, pady=(20, 4))
        tk.Label(parent, text=subtitle, bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=650).pack(fill="x", padx=22, pady=(0, 16))


    def _announcement_value(self) -> str:
        return self.announcement_text.get("1.0", "end-1c").strip()

    def _settings_payload(self, address: str | None = None) -> dict:
        return {
            "address": address or self.address_var.get().strip() or DEFAULT_ADDRESS,
            "game_executable": self.exe_var.get().strip(),
            "history": list(self.history),
            "announcement_enabled": bool(self.announcement_enabled_var.get()),
            "announcement_text": self._announcement_value(),
            "blacklist_check_enabled": bool(self.blacklist_check_enabled_var.get()),
            "fixed_roles_enabled": bool(self.fixed_roles_enabled_var.get()),
            "gm_api_port": self.gm_api_port_var.get().strip() or str(DEFAULT_GM_PORT),
            "blacklist_check_token": self.blacklist_check_token_var.get().strip(),
        }

    def _save_settings(self, address: str | None = None) -> None:
        save_settings("quick_join", self._settings_payload(address))

    def _refresh_history_view(self) -> None:
        if not hasattr(self, "history_tree"):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for address in self.history:
            self.history_tree.insert("", "end", values=(address,))
        if hasattr(self, "address_history_button"):
            self.address_history_button.configure(state="normal" if self.history else "disabled")

    def show_address_history_menu(self) -> None:
        if not self.history:
            return
        menu = tk.Menu(self.root, tearoff=False, font=("Cascadia Mono", 10))
        for address in self.history:
            menu.add_command(label=address, command=lambda value=address: self.address_var.set(value))
        try:
            menu.tk_popup(
                self.address_history_button.winfo_rootx(),
                self.address_history_button.winfo_rooty() + self.address_history_button.winfo_height(),
            )
        finally:
            menu.grab_release()

    def _remember_address(self, address: str) -> None:
        self.history = remember_history(self.history, address)
        self._refresh_history_view()
        self._save_settings(address)

    def use_selected_history(self) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        values = self.history_tree.item(selection[0], "values")
        if values:
            self.address_var.set(values[0])
            self._show_page(0)
            self.address_entry.focus_set()

    def delete_selected_history(self) -> None:
        selection = self.history_tree.selection()
        if not selection:
            return
        values = self.history_tree.item(selection[0], "values")
        if not values:
            return
        target = str(values[0]).lower()
        self.history = [item for item in self.history if item.lower() != target]
        self._refresh_history_view()
        self._save_settings()

    def clear_history(self) -> None:
        if not self.history:
            return
        if not messagebox.askyesno("清空服务器历史", "确定删除全部服务器历史吗？"):
            return
        self.history = []
        self._refresh_history_view()
        self._save_settings()

    def _sync_client_bridge(self) -> tuple[bool, bool, str]:
        executable = self._game_executable()
        if executable is None:
            return False, False, "尚未找到客户端，无法同步内置连接服务"
        win64 = client_win64_directory(executable)
        if not win64.is_dir():
            return False, False, "客户端 Win64 目录不存在：%s" % win64
        source = resource_path(CLIENT_BRIDGE_HOOK_FILENAME)
        if not source.is_file():
            return False, False, "程序包中缺少客户端连接服务"
        target = win64 / "Patches" / CLIENT_BRIDGE_HOOK_FILENAME
        target.parent.mkdir(parents=True, exist_ok=True)
        changed = not target.is_file() or target.read_bytes() != source.read_bytes()
        if changed:
            shutil.copyfile(str(source), str(target))
        notice_source = resource_path(CLIENT_NOTICE_HOOK_FILENAME)
        if not notice_source.is_file():
            return False, changed, "程序包中缺少游戏原生公告 Hook"
        notice_target = target.with_name(CLIENT_NOTICE_HOOK_FILENAME)
        notice_changed = not notice_target.is_file() or notice_target.read_bytes() != notice_source.read_bytes()
        if notice_changed:
            shutil.copyfile(str(notice_source), str(notice_target))
        changed = changed or notice_changed
        return True, changed, "客户端内置连接服务已就绪"

    def save_announcement_settings(self) -> None:
        text = self._announcement_value()
        if self.announcement_enabled_var.get() and not text:
            self.announcement_enabled_var.set(False)
            messagebox.showwarning("公告内容", "公告内容为空，已自动关闭公告功能。")
        if len(text) > 500:
            messagebox.showerror("公告内容", "公告内容最多 500 个字符。")
            return
        self._save_settings()
        if not self.announcement_enabled_var.get():
            self.announcement_status_var.set("公告功能已关闭")
            return
        self.announcement_status_var.set("点击进服时会先显示公告，3 秒后开始连接")

    def _send_current_announcement(self, require_enabled: bool, text=None, duration_ms: int = LOBBY_NOTICE_RESULT_MS, danger: bool = False) -> bool:
        if require_enabled and not self.announcement_enabled_var.get():
            return False
        message = str(text).strip() if text is not None else self._announcement_value()
        if not message:
            return False
        limit = 500 if text is None else 1000
        if len(message) > limit:
            raise ValueError("公告内容最多 %d 个字符。" % limit)
        try:
            send_client_announcement(message)
            self.announcement_status_var.set("公告已显示在游戏左侧原生文字通道")
        except OSError as exc:
            trace_quick_join("native-notice-failed reason=%s" % exc)
            launch_game_notice(message, duration_ms, danger)
            self.announcement_status_var.set("原生文字未就绪，已显示本机悬浮提示：%s" % exc)
        return True

    def _clear_game_notice(self) -> None:
        # Game notices deliberately use the same one-shot behavior as the
        # “立即发布公告” button. Reposting restarts this client's text effect.
        return

    def _show_lobby_notice(self, text: str, duration_ms: int = 0, danger: bool = False) -> bool:
        clean = str(text).strip()
        if not clean:
            return False
        trace_quick_join("notice-send text=%s" % clean)
        try:
            self._send_current_announcement(require_enabled=False, text=clean, duration_ms=duration_ms, danger=danger)
        except (OSError, ValueError):
            trace_quick_join("notice-failed")
            return False
        trace_quick_join("notice-accepted")
        return True

    def _pre_join_notice(self) -> str:
        parts = []
        if self._blacklist_warning_text:
            parts.append(self._blacklist_warning_text)
        if self.announcement_enabled_var.get():
            announcement = self._announcement_value()
            if announcement:
                parts.append(announcement)
        return "\n\n".join(parts)[:1000]

    def _handle_pre_join_announcement(self) -> bool:
        if self._pre_join_announcement_handled:
            return False
        self._pre_join_announcement_handled = True
        if not self._pre_join_notice():
            return False
        self.root.iconify()
        focus_running_game()
        self.status_var.set("正在切换到游戏并显示进服提示……")
        return True

    def _finish_pre_join_announcement(self, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        try:
            notice = self._pre_join_notice()
            if not notice:
                published = False
            else:
                published = self._send_current_announcement(require_enabled=False, text=notice)
        except (OSError, ValueError) as exc:
            self.announcement_status_var.set("自动公告发布失败：%s" % exc)
            published = False
        if published:
            if self._blacklist_warning_text:
                self.status_var.set("黑名单警告已显示；5 秒后开始连接服务器……")
                delay = BLACKLIST_WARNING_DELAY_MS
            else:
                self.status_var.set("公告已显示；3 秒后开始连接服务器……")
                delay = PRE_JOIN_ANNOUNCEMENT_DELAY_MS
        else:
            delay = 0
        self.root.after(delay, lambda: self._send_join_attempt(address, generation, wait_for_client))

    def _query_cloud_blacklist(self, address: str) -> dict:
        token = normalize_query_token(self.blacklist_check_token_var.get())
        try:
            port = int(self.gm_api_port_var.get().strip())
        except ValueError:
            raise ValueError("GM 端口必须是数字")
        api = RemoteApi(address_host(address), port, token=token, timeout=6.0)
        try:
            return api.request(
                "/api/blacklist/preflight",
                "POST",
                {"user_id": read_local_user_id()},
            )
        except ApiError as exc:
            if exc.status == 401:
                raise ValueError("查询令牌被服务器拒绝；请从当前服务器的 GM 黑名单页重新复制只读查询令牌") from exc
            raise

    def _upload_fixed_roles(self, address: str) -> dict:
        token = normalize_query_token(self.blacklist_check_token_var.get())
        try:
            port = int(self.gm_api_port_var.get().strip())
        except ValueError:
            raise ValueError("GM 端口必须是数字")
        roles = read_client_fixed_roles()
        api = RemoteApi(address_host(address), port, token=token, timeout=6.0)
        try:
            return api.request("/api/fixed-roles", "POST", {"roles": roles})
        except ApiError as exc:
            if exc.status == 401:
                raise ValueError("远端 GM 控制台尚未更新，或大厅同步令牌与该服务器不匹配") from exc
            raise

    def _fixed_roles_sync_ok(self, data: dict, address: str, generation: int, wait_for_client: bool) -> None:
        self._fixed_roles_syncing = False
        if not self._join_active or generation != self._join_generation:
            return
        count = int(data.get("count", 0)) if isinstance(data, dict) else 0
        if count < 1:
            self._fixed_roles_sync_failed(
                OSError("服务器没有接受大厅职业名单"), address, generation, wait_for_client
            )
            return
        self._fixed_roles_synced = True
        self.status_var.set("已同步 %d 名玩家的大厅职业，准备连接服务器……" % count)
        self.root.after(0, lambda: self._send_join_attempt(address, generation, wait_for_client))

    def _fixed_roles_sync_failed(self, exc: Exception, address: str, generation: int, wait_for_client: bool) -> None:
        self._fixed_roles_syncing = False
        if not self._join_active or generation != self._join_generation:
            return
        self.stop_auto_join("大厅职业同步失败，已停止连接：%s" % exc)
        self.root.deiconify()
        messagebox.showerror("固定职业同步失败", str(exc))

    def _continue_after_blacklist_check(self, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        initial_delay = 500 if wait_for_client else 0
        if not wait_for_client and self._handle_pre_join_announcement():
            self.root.after(
                ANNOUNCEMENT_FOCUS_DELAY_MS,
                lambda: self._finish_pre_join_announcement(address, generation, wait_for_client),
            )
            return
        self.root.after(initial_delay, lambda: self._send_join_attempt(address, generation, wait_for_client))

    def _wait_to_begin_blacklist_check(self, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        if not process_is_running(("DreadHunger-Win64-Shipping.exe",)):
            if wait_for_client and self._connector_waits < 120:
                self._connector_waits += 1
                self.root.after(500, lambda: self._wait_to_begin_blacklist_check(address, generation, True))
                return
            self.stop_auto_join("客户端未运行，黑名单检查已停止。")
            return

        if not wait_for_client:
            # The user explicitly clicked while an existing client is running.
            # Do not let a multi-gigabyte EOS error flood hide the old lobby marker
            # and block the visible blacklist check forever. Fresh launches and
            # retries still require a newly observed lobby marker below.
            self._retry_requires_fresh_lobby = False
            self._lobby_ready_since = time.monotonic() - LOBBY_STABLE_SECONDS
        elif not self._wait_for_safe_lobby():
            self._connector_waits += 1
            if self._connector_waits >= 240:
                self.stop_auto_join("等待游戏大厅超时，黑名单检查已停止。")
                return
            self.status_var.set("等待客户端进入船上大厅并稳定 %d 秒……" % LOBBY_STABLE_SECONDS)
            self.root.after(500, lambda: self._wait_to_begin_blacklist_check(address, generation, wait_for_client))
            return

        self.status_var.set("正在切换到游戏并检查黑名单……")
        trace_quick_join("preflight-focus-handoff address=%s" % address)
        self.root.iconify()
        focus_running_game()
        self.root.after(
            ANNOUNCEMENT_FOCUS_DELAY_MS,
            lambda: self._announce_checking_and_query(address, generation, wait_for_client),
        )

    def _announce_checking_and_query(self, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        trace_quick_join("preflight-checking-start")
        checking_notice = "正在进入游戏，检查黑名单中……"
        if self.announcement_enabled_var.get() and not self._pre_join_announcement_handled:
            announcement = self._announcement_value()
            if announcement:
                checking_notice += "\n" + announcement
        if not self._show_lobby_notice(checking_notice, CHECKING_NOTICE_OVERLAY_MS):
            self.root.deiconify()
            trace_quick_join("checking-overlay-unavailable; continuing-cloud-query")
        self._pre_join_announcement_handled = True
        self._blacklist_check_started_at = time.monotonic()
        self.blacklist_status_var.set("正在核对本机账号与 Linux 实时大厅……")
        self.runner.submit(
            lambda: self._query_cloud_blacklist(address),
            lambda data: self._defer_blacklist_result(
                lambda: self._blacklist_check_ok(data, address, generation, wait_for_client)
            ),
            lambda exc: self._defer_blacklist_result(
                lambda: self._blacklist_check_failed(exc, address, generation, wait_for_client)
            ),
        )

    def _defer_blacklist_result(self, callback) -> None:
        elapsed_ms = int((time.monotonic() - self._blacklist_check_started_at) * 1000)
        remaining_ms = max(0, BLACKLIST_CHECK_MIN_RESULT_MS - elapsed_ms)
        if remaining_ms:
            self.root.after(remaining_ms, callback)
        else:
            callback()

    def _send_preflight_result_notice(self, text: str) -> bool:
        if not self._show_lobby_notice(
            text,
            duration_ms=LOBBY_NOTICE_RESULT_MS,
            danger=text.startswith("发现黑名单") or "失败" in text or "未完成" in text,
        ):
            self._preflight_notice_failed(OSError("客户端提示通道未就绪"))
            return False
        self.announcement_status_var.set("黑名单检测结果已显示在游戏大厅")
        return True

    def _preflight_notice_failed(self, exc: Exception) -> None:
        self._show_lobby_notice("游戏提示通道未就绪，已停止连接。", LOBBY_NOTICE_RESULT_MS, danger=True)
        self.blacklist_status_var.set("游戏内公告发送失败：%s" % exc)
        self.stop_auto_join("无法在游戏大厅显示黑名单结果，已停止连接。")
        self.root.deiconify()
        messagebox.showerror("游戏内提示失败", "无法向游戏大厅发送黑名单提示，已停止连接。\n\n%s" % exc)

    def _blacklist_check_ok(self, data: dict, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        decision = preflight_decision(data)
        trace_quick_join("preflight-result decision=%s matches=%d" % (decision, len(preflight_matches(data))))
        matches = preflight_matches(data)
        if decision == "blocked":
            warning = format_preflight_block_notice(matches)
            self._blacklist_warning_text = warning
            if not self._send_preflight_result_notice(warning):
                return
            self.blacklist_status_var.set("⛔ 发现 %d 名黑名单用户，已停止连接" % len(matches))
            self.stop_auto_join("发现黑名单用户，本次连接已停止。")
            return

        if decision == "identity_unavailable":
            notice = "黑名单检查未完成，已停止进入服务器；原因：无法读取当前账号 ID。"
            if self._send_preflight_result_notice(notice):
                self.blacklist_status_var.set("无法读取当前账号 ID，已停止连接")
                self.stop_auto_join("无法验证当前账号身份，已停止连接。")
            return

        if decision == "lobby_stale":
            notice = "黑名单检查未完成，已停止进入服务器；原因：服务器大厅名单已过期。"
            if self._send_preflight_result_notice(notice):
                self.blacklist_status_var.set("服务器大厅名单已过期，已停止连接")
                self.stop_auto_join("服务器大厅名单已过期，已停止连接。")
            return

        notice = format_preflight_clear_notice()
        if not self._send_preflight_result_notice(notice):
            return
        self._pre_join_announcement_handled = True
        self._blacklist_warning_text = ""
        self._blacklist_check_started_at = 0.0
        self.blacklist_status_var.set("✓ 检测完成，未发现黑名单用户")
        self.status_var.set("检测完成；1 秒后进入服务器……")
        self.root.after(
            BLACKLIST_SUCCESS_DELAY_MS,
            lambda: self._send_join_attempt(address, generation, wait_for_client),
        )

    def _blacklist_check_failed(self, exc: Exception, address: str, generation: int, wait_for_client: bool) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        reason = str(exc).strip().replace("\n", " ")[:180] or "未知错误"
        trace_quick_join("preflight-request-failed reason=%s" % reason)
        notice = "黑名单检查失败，已停止进入服务器；原因：%s" % compact_game_text(reason, 36)
        if self._send_preflight_result_notice(notice):
            self.blacklist_status_var.set("云端黑名单检查失败，已停止连接：%s" % reason)
            self.stop_auto_join("黑名单检查失败，已停止连接。")

    def publish_announcement(self) -> None:
        text = self._announcement_value()
        if not text:
            messagebox.showwarning("公告内容", "请输入需要发布的公告内容。")
            return
        if len(text) > 500:
            messagebox.showerror("公告内容", "公告内容最多 500 个字符。")
            return
        if not process_is_running(("DreadHunger-Win64-Shipping.exe",)):
            messagebox.showwarning("未检测到客户端", "请先启动 Dread Hunger 并进入船上大厅。")
            return
        try:
            ok, changed, message = self._sync_client_bridge()
        except OSError as exc:
            messagebox.showerror("公告发布失败", str(exc))
            return
        if not ok:
            messagebox.showerror("公告发布失败", message)
            return
        if changed:
            messagebox.showwarning("需要重启客户端", "已安装客户端消息服务，请重启 Dread Hunger 一次后再发布。")
            return
        self._save_settings()
        trace_quick_join("manual-notice-focus-handoff")
        self.root.iconify()
        focus_running_game()
        self.announcement_status_var.set("正在切换到游戏并发布公告……")
        self.root.after(ANNOUNCEMENT_FOCUS_DELAY_MS, self._finish_manual_announcement)

    def _finish_manual_announcement(self) -> None:
        try:
            trace_quick_join("manual-notice-send")
            self._send_current_announcement(require_enabled=False)
        except (OSError, ValueError) as exc:
            self.announcement_status_var.set("公告发布失败：%s" % exc)
            self.root.deiconify()
            messagebox.showerror("公告发布失败", str(exc))

    def _validated_address(self) -> str | None:
        try:
            address = normalize_server_address(self.address_var.get())
        except ValueError as exc:
            messagebox.showerror("服务器地址", str(exc))
            return None
        self.address_var.set(address)
        self._remember_address(address)
        return address

    def _refresh_process_state(self) -> None:
        processes = running_game_processes()
        running = bool(processes)
        shipping_count = sum(name.lower() == "dreadhunger-win64-shipping.exe" for _pid, name in processes)
        if shipping_count > 1:
            self.process_var.set("● 已检测到 %d 个 Dread Hunger 客户端" % shipping_count)
        else:
            self.process_var.set("● 已检测到 Dread Hunger 客户端" if running else "○ 未检测到 Dread Hunger 客户端")
        if running != self._last_running and not self._status_locked:
            self.status_var.set(
                "客户端已运行；点击“进入服务器”发送本地直连命令。"
                if running
                else "客户端未运行；可点击“启动客户端并进入”。"
            )
        if shipping_count > 1 and not self._join_active:
            self.status_var.set("检测到多个客户端；请只保留一个，否则直连命令可能发送到另一个窗口。")
        self._last_running = running
        self.root.after(3000, self._refresh_process_state)

    def join_running_game(self) -> None:
        address = self._validated_address()
        if address is None:
            return
        if not process_is_running():
            messagebox.showwarning("未检测到客户端", "请点击下方“启动客户端并进入”。")
            return
        self._start_auto_join(address, wait_for_client=False)

    def choose_executable(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 Dread Hunger 客户端",
            filetypes=(("Dread Hunger", "DreadHunger*.exe"), ("Windows 程序", "*.exe")),
        )
        if selected:
            self.exe_var.set(selected)
            self._save_settings()

    def _game_executable(self) -> Path | None:
        running = running_game_executable()
        if running:
            self.exe_var.set(str(running))
            return running
        configured = Path(self.exe_var.get().strip()) if self.exe_var.get().strip() else None
        if configured and configured.is_file():
            return configured
        discovered = discover_game_executable()
        if discovered:
            self.exe_var.set(str(discovered))
            return discovered
        return None

    def launch_with_address(self) -> None:
        address = self._validated_address()
        if address is None:
            return
        if process_is_running():
            self.join_running_game()
            return
        executable = self._game_executable()
        if executable is None:
            messagebox.showerror("找不到客户端", "未自动找到 Dread Hunger，请点击“选择客户端”。")
            return
        try:
            ok, _changed, message = self._sync_client_bridge()
        except OSError as exc:
            messagebox.showerror("连接服务同步失败", str(exc))
            return
        if not ok:
            messagebox.showerror("连接服务同步失败", message)
            return
        try:
            subprocess.Popen([str(executable)], cwd=str(executable.parent))
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc))
            return
        self.exe_var.set(str(executable))
        self._save_settings(address)
        self._status_locked = True
        self.status_var.set("客户端正在启动；内置连接服务就绪后将自动进入：%s" % address)
        self._start_auto_join(address, wait_for_client=True)

    def _start_auto_join(self, address: str, wait_for_client: bool) -> None:
        try:
            ok, changed, message = self._sync_client_bridge()
        except OSError as exc:
            messagebox.showerror("连接服务同步失败", str(exc))
            return
        if not ok:
            messagebox.showerror("连接服务同步失败", message)
            return
        if changed and process_is_running(("DreadHunger-Win64-Shipping.exe",)):
            self.status_var.set("客户端连接服务已安装；请重启游戏客户端一次后再进入。")
            messagebox.showwarning("需要重启客户端", "已安装客户端内置连接服务，请重启 Dread Hunger 一次。")
            return
        self._join_generation += 1
        trace_quick_join("join-start address=%s wait_for_client=%s blacklist=%s" % (address, wait_for_client, self.blacklist_check_enabled_var.get()))
        generation = self._join_generation
        self._clear_game_notice()
        self._join_active = True
        self._join_attempt = 0
        self._connector_waits = 0
        self._join_load_seen_at = None
        self._fixed_roles_synced = False
        self._fixed_roles_syncing = False
        self._pre_join_announcement_handled = False
        self._blacklist_warning_text = ""
        self._retry_requires_fresh_lobby = wait_for_client
        try:
            self._retry_log_offset = GAME_LOG.stat().st_size if wait_for_client else 0
        except OSError:
            self._retry_log_offset = 0
        self._lobby_ready_since = None if wait_for_client else time.monotonic() - LOBBY_STABLE_SECONDS
        self._status_locked = True
        self.stop_button.configure(state="normal")
        self._save_settings(address)
        if self.blacklist_check_enabled_var.get():
            self.blacklist_status_var.set("准备在游戏大厅检查黑名单……")
            self._wait_to_begin_blacklist_check(address, generation, wait_for_client)
            return
        self.blacklist_status_var.set("云端黑名单检查已关闭")
        self._continue_after_blacklist_check(address, generation, wait_for_client)

    def stop_auto_join(self, message: str = "已停止自动重试。") -> None:
        trace_quick_join("join-stop message=%s" % message)
        self._join_active = False
        self._join_generation += 1
        self.stop_button.configure(state="disabled")
        self.status_var.set(message)

    def _wait_for_safe_lobby(self) -> bool:
        if self._retry_requires_fresh_lobby:
            try:
                with GAME_LOG.open("rb") as log_file:
                    size = GAME_LOG.stat().st_size
                    if size < self._retry_log_offset:
                        self._retry_log_offset = 0
                    log_file.seek(self._retry_log_offset)
                    raw = log_file.read()
                    self._retry_log_offset += len(raw)
                chunk = raw.decode("utf-8", errors="replace")
                if self._join_attempt > 0 and log_reports_join_complete(chunk):
                    self.stop_auto_join("已进入服务器，自动重试已停止。")
                    return False
                if log_reports_lobby_ready(chunk):
                    self._retry_requires_fresh_lobby = False
                    self._lobby_ready_since = time.monotonic()
            except OSError:
                return False
        elif self._lobby_ready_since is None:
            if game_log_is_lobby_ready():
                self._lobby_ready_since = time.monotonic()
        return self._lobby_ready_since is not None and time.monotonic() - self._lobby_ready_since >= LOBBY_STABLE_SECONDS

    def _schedule_safe_retry(self, address: str, generation: int, message: str) -> None:
        self._retry_requires_fresh_lobby = True
        self._retry_log_offset = self._join_log_offset
        self._lobby_ready_since = None
        self.status_var.set(message)
        self.root.after(JOIN_RETRY_DELAY_MS, lambda: self._send_join_attempt(address, generation, True))

    def _send_join_attempt(self, address: str, generation: int, wait_for_client: bool = False) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        if not process_is_running(("DreadHunger-Win64-Shipping.exe",)):
            if wait_for_client and self._connector_waits < 120:
                self._connector_waits += 1
                self.root.after(500, lambda: self._send_join_attempt(address, generation, True))
                return
            self.stop_auto_join("客户端已退出，自动重试已停止。")
            return
        if not self._wait_for_safe_lobby():
            if not self._join_active:
                return
            self._connector_waits += 1
            if self._connector_waits >= 240:
                self.stop_auto_join("等待安全重试超时。请让客户端稳定进入船上大厅后再点击进入。")
                return
            self.status_var.set("等待客户端进入船上大厅并稳定 %d 秒……" % LOBBY_STABLE_SECONDS)
            self.root.after(500, lambda: self._send_join_attempt(address, generation, True))
            return
        if self.fixed_roles_enabled_var.get() and not self._fixed_roles_synced:
            if self._fixed_roles_syncing:
                return
            self._fixed_roles_syncing = True
            self.status_var.set("正在读取并同步客户端大厅职业……")
            self.runner.submit(
                lambda: self._upload_fixed_roles(address),
                lambda data: self._fixed_roles_sync_ok(data, address, generation, wait_for_client),
                lambda exc: self._fixed_roles_sync_failed(exc, address, generation, wait_for_client),
            )
            return
        if self._handle_pre_join_announcement():
            self.root.after(
                ANNOUNCEMENT_FOCUS_DELAY_MS,
                lambda: self._finish_pre_join_announcement(address, generation, wait_for_client),
            )
            return
        try:
            self._join_log_offset = GAME_LOG.stat().st_size
        except OSError:
            self._join_log_offset = 0
        try:
            resolved = send_connector_command(address)
        except OSError as exc:
            self._connector_waits += 1
            if self._connector_waits >= 120:
                self.stop_auto_join("等待客户端内置连接服务超时。请确认游戏能正常进入大厅后再重试。")
                messagebox.showerror(
                    "直连失败",
                    "请确认客户端已加载 Patches\\connect_client_win64.js。\n"
                    "可重启一次游戏客户端后重试。\n\n%s" % exc,
                )
                return
            self.status_var.set("正在等待客户端连接器就绪……")
            self.root.after(500, lambda: self._send_join_attempt(address, generation, True))
            return
        self._connector_waits = 0
        self._join_attempt += 1
        self._join_attempt_started = time.monotonic()
        self._join_load_seen_at = None
        self.status_var.set("第 %d 次直连已发送：%s（%s），正在等待服务器……" % (self._join_attempt, address, resolved))
        self.root.after(500, lambda: self._poll_join_result(address, generation))

    def _poll_join_result(self, address: str, generation: int) -> None:
        if not self._join_active or generation != self._join_generation:
            return
        if not process_is_running():
            self.stop_auto_join("客户端已退出，自动重试已停止。")
            return
        chunk = ""
        try:
            with GAME_LOG.open("rb") as log_file:
                if GAME_LOG.stat().st_size < self._join_log_offset:
                    self._join_log_offset = 0
                log_file.seek(self._join_log_offset)
                raw = log_file.read()
                self._join_log_offset += len(raw)
                chunk = raw.decode("utf-8", errors="replace")
        except OSError:
            pass
        if log_reports_join_complete(chunk):
            self.stop_auto_join("已进入服务器，自动重试已停止。")
            return
        if log_reports_join_failure(chunk):
            self._schedule_safe_retry(address, generation, "服务器暂时拒绝或断开；返回并稳定进入船上大厅后自动重试……")
            return
        now = time.monotonic()
        if log_reports_game_map(chunk):
            self._join_load_seen_at = now
            self.status_var.set("服务器已响应，正在载入地图；已暂停所有连接重试……")
        if self._join_load_seen_at is None and now - self._join_attempt_started >= 30:
            self._schedule_safe_retry(address, generation, "本次连接未完成；返回并稳定进入船上大厅后自动重试……")
            return
        self.root.after(500, lambda: self._poll_join_result(address, generation))


def run_self_test() -> int:
    assert normalize_server_address(" 127.0.0.1:9100 ") == "127.0.0.1:9100"
    assert normalize_server_address("example.com:7777") == "example.com:7777"
    assert normalize_server_address("[::1]:7777") == "[::1]:7777"
    assert normalize_query_token("Abcdefghijklmnopqrstuvwxyz012345_-") == "Abcdefghijklmnopqrstuvwxyz012345_-"
    assert connector_request("127.0.0.1:9100") == {
        "op": "Connect",
        "IP": "127.0.0.1",
        "Port": 9100,
    }
    assert address_host("127.0.0.1:9100") == "127.0.0.1"
    assert address_host("[::1]:9101") == "::1"
    assert format_blacklist_warning([
        {"name": "景岗山王二", "reason": "死一次退", "steam_id": "76561198661845743"}
    ]) == "检测到黑名单玩家：景岗山王二\n理由：死一次退\nSteam ID：76561198661845743"
    sample_user_id = "76561198863268516_+_|000279d3b6404969a8ce88129339ca95"
    assert extract_local_user_id(
        "RemoteAddr: 127.0.0.1:9100, UniqueId: EOSPlus:%s, Channels: 21" % sample_user_id
    ) == sample_user_id
    assert extract_local_user_id("LogNet: Login request: ?Name=测试 userId: EOSPlus:%s platform: EOSPlus" % sample_user_id) == sample_user_id
    assert format_local_blacklist_block(
        {"name": "测试玩家", "reason": "死一次退", "steam_id": "76561198863268516"}
    ) == "当前账号已被列入黑名单：测试玩家\n理由：死一次退\nSteam ID：76561198863268516\n进服器已阻止本次连接。"
    blocked = {
        "local_identity_available": True,
        "local_match": {"name": "测试玩家", "reason": "死一次退", "user_id": sample_user_id},
        "lobby_matches": [
            {"name": "测试玩家", "reason": "死一次退", "user_id": sample_user_id},
            {"name": "违规玩家", "reason": "使用外挂", "steam_id": "76561190000000001"},
        ],
        "lobby_stale": False,
    }
    assert preflight_decision(blocked) == "blocked"
    assert len(preflight_matches(blocked)) == 2
    assert compact_game_text("玩家一\n玩家二", 20) == "玩家一 玩家二"
    assert compact_game_text("123456789", 6) == "12345…"
    assert format_preflight_block_notice(preflight_matches(blocked)) == "发现黑名单用户：测试玩家；理由：死一次退；另有1人"
    assert preflight_decision({"local_identity_available": False, "lobby_matches": [], "lobby_stale": False}) == "identity_unavailable"
    assert preflight_decision({"local_identity_available": True, "lobby_matches": [], "lobby_stale": True}) == "lobby_stale"
    assert preflight_decision({"local_identity_available": True, "lobby_matches": [], "lobby_stale": False}) == "clear"
    assert format_preflight_clear_notice() == "检测完成，未发现黑名单用户。"
    assert "\n" not in format_preflight_block_notice(preflight_matches(blocked))
    assert normalize_history(["198.51.100.10:9101", "bad", "198.51.100.10:9101", "192.0.2.10:9100"]) == [
        "198.51.100.10:9101",
        "192.0.2.10:9100",
    ]
    assert remember_history(["192.0.2.10:9100", "198.51.100.10:9101"], "198.51.100.10:9101") == [
        "198.51.100.10:9101",
        "192.0.2.10:9100",
    ]
    assert client_win64_directory(Path(r"E:\Dread Hunger\DreadHunger.exe")) == Path(
        r"E:\Dread Hunger\DreadHunger\Binaries\Win64"
    )
    assert client_working_directory(Path(r"E:\Dread Hunger\DreadHunger.exe")) == Path(r"E:\Dread Hunger")
    assert client_working_directory(
        Path(r"E:\Dread Hunger\DreadHunger\Binaries\Win64\DreadHunger-Win64-Shipping.exe")
    ) == Path(r"E:\Dread Hunger")
    assert log_reports_join_failure("NetworkFailure: Host closed the connection.")
    assert not log_reports_join_failure("LogNet: Game client on port 9101")
    assert log_reports_game_map("LogLoad: LoadMap: server/Game/Maps/Departure_Persistent")
    assert log_reports_join_complete("LogNet: Join succeeded: Player")
    assert log_reports_join_complete(
        "LogLoad: Took 2.473994 seconds to LoadMap(/Game/Maps/NorthWestPassage/Departure/Departure_Persistent)"
    )
    assert not log_reports_join_complete("LogLoad: Took 1.2 seconds to LoadMap(/Game/Maps/Test/MenuLobby)")
    assert log_reports_lobby_ready("LogLoad: Game class is 'BP_LobbyGameMode_C'")
    assert not log_reports_lobby_ready(
        "LogLoad: Game class is 'BP_LobbyGameMode_C'\nLogLoad: Game class is 'BP_DreadGameMode_C'"
    )
    for invalid in ("", "127.0.0.1", "http://127.0.0.1:9100", "host:70000"):
        try:
            normalize_server_address(invalid)
        except ValueError:
            continue
        raise AssertionError("无效地址未被拒绝: %s" % invalid)
    for invalid_token in ("", "测试查询令牌", "short-token", "token with spaces 12345678901234567890"):
        try:
            normalize_query_token(invalid_token)
        except ValueError:
            continue
        raise AssertionError("无效查询令牌未被拒绝")
    print("quick_join self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=QUICK_JOIN_NAME)
    parser.add_argument("--self-test", action="store_true", help="运行无界面自检")
    parser.add_argument("--game-notice", help=argparse.SUPPRESS)
    parser.add_argument("--notice-duration-ms", type=int, default=5000, help=argparse.SUPPRESS)
    parser.add_argument("--notice-danger", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    enable_windows_dpi_awareness()
    set_windows_app_user_model_id()
    if args.game_notice:
        show_game_notice(args.game_notice, args.notice_duration_ms, args.notice_danger)
        return 0
    root = tk.Tk()
    QuickJoinApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
