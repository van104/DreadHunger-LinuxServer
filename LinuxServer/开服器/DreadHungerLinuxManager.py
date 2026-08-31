#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import json
import math
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit


APP_VERSION = "1.0.0"
SERVER_BINARY = "DreadHungerServer-Linux-Shipping"
CONFIG_FILE = "manager_config.json"
STATE_FILE = ".dread_hunger_manager_state.json"
PATCH_EXTENSIONS = {".js", ".pak", ".sig"}
DEFAULT_LINUX_ROOT = Path("/www/wwwroot/Dread Hunger/LinuxServer")
GAME_KEYS = (
    "maxplayers",
    "thralls",
    "dayminutes",
    "daysbeforeblizzard",
    "predatordamage",
    "coalburnrate",
    "hungerrate",
    "coldintensity",
)

DEFAULT_GAME = {
    "map": "Departure_Persistent",
    "maxplayers": 8,
    "thralls": 2,
    "dayminutes": 9,
    "daysbeforeblizzard": 3,
    "predatordamage": 1.0,
    "coalburnrate": 1.0,
    "hungerrate": 1.0,
    "coldintensity": 1.0,
    "patch_source": "Linux 插件",
}


class ManagerError(RuntimeError):
    pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temp), str(path))


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback


def server_root_valid(path: Path) -> bool:
    binary = path / "DreadHunger" / "Binaries" / "Linux" / SERVER_BINARY
    return path.is_dir() and (path / "DreadHunger").is_dir() and (
        (path / "DreadHungerServer.sh").is_file() or binary.is_file()
    )


def discover_root(explicit: Optional[Path]) -> Path:
    candidates: List[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    if DEFAULT_LINUX_ROOT.is_dir():
        candidates.append(DEFAULT_LINUX_ROOT)
    candidates.append(Path.cwd())
    try:
        candidates.append(Path(__file__).resolve().parent)
        candidates.append(Path(__file__).resolve().parent.parent)
    except OSError:
        pass

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if str(resolved) in seen:
            continue
        seen.add(str(resolved))
        if server_root_valid(resolved):
            return resolved

    requested = str(explicit) if explicit else str(DEFAULT_LINUX_ROOT)
    raise ManagerError("未找到 LinuxServer 目录，请使用 --root 指定: " + requested)


def scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def valid_map_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 120 or not re.fullmatch(r"[A-Za-z0-9_./-]+", text):
        raise ManagerError("地图名只允许字母、数字、下划线、点、斜线和连字符")
    return text


def valid_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ManagerError(name + " 必须是整数")
    if not minimum <= result <= maximum:
        raise ManagerError("%s 范围必须是 %d-%d" % (name, minimum, maximum))
    return result


def valid_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ManagerError(name + " 必须是数字")
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ManagerError("%s 范围必须是 %s-%s" % (name, minimum, maximum))
    return result


def normalize_config(raw: Dict[str, Any], root: Path) -> Dict[str, Any]:
    config = dict(DEFAULT_GAME)
    config.update({key: raw[key] for key in GAME_KEYS if key in raw})
    if "map" in raw:
        config["map"] = raw["map"]

    existing_game = root / "game_config.json"
    if not existing_game.is_file():
        existing_game = root / "配置文件" / "game_config.json"
    game_file = read_json(existing_game, {}) if existing_game.is_file() else {}
    if not raw and isinstance(game_file, dict):
        config.update({key: game_file[key] for key in GAME_KEYS + ("map",) if key in game_file})

    port_default = 9100
    port_file = root / "port_config.json"
    if not port_file.is_file():
        port_file = root / "配置文件" / "port_config.json"
    port_data = read_json(port_file, {}) if port_file.is_file() else {}
    if isinstance(port_data, dict) and "current_port" in port_data:
        port_default = port_data["current_port"]

    server_config = root / "server_config.json"
    if not server_config.is_file():
        server_config = root / "配置文件" / "server_config.json"
    server_data = read_json(server_config, {}) if server_config.is_file() else {}
    if isinstance(server_data, dict) and "port1" in server_data:
        port_default = server_data["port1"]

    result = {
        "map": valid_map_name(config["map"]),
        "maxplayers": valid_int(config["maxplayers"], "maxplayers", 1, 32),
        "thralls": valid_int(config["thralls"], "thralls", 0, 8),
        "dayminutes": valid_int(config["dayminutes"], "dayminutes", 1, 240),
        "daysbeforeblizzard": valid_int(config["daysbeforeblizzard"], "daysbeforeblizzard", 0, 30),
        "predatordamage": valid_float(config["predatordamage"], "predatordamage", 0, 100),
        "coalburnrate": valid_float(config["coalburnrate"], "coalburnrate", 0, 100),
        "hungerrate": valid_float(config["hungerrate"], "hungerrate", 0, 100),
        "coldintensity": valid_float(config["coldintensity"], "coldintensity", 0, 100),
        "server_port": valid_int(raw.get("server_port", port_default), "server_port", 1, 65535),
        "extra_args": [],
        "patch_source": str(raw.get("patch_source", "Linux 插件")),
    }

    extra_args = raw.get("extra_args", [])
    if isinstance(extra_args, str):
        try:
            extra_args = shlex.split(extra_args)
        except ValueError as exc:
            raise ManagerError("extra_args 格式错误: " + str(exc))
    if not isinstance(extra_args, list) or not all(isinstance(item, str) for item in extra_args):
        raise ManagerError("extra_args 必须是字符串数组")
    if any("\x00" in item for item in extra_args):
        raise ManagerError("extra_args 含非法字符")
    if not result["patch_source"] or "\\" in result["patch_source"] or ".." in result["patch_source"] or not re.fullmatch(r"[\w\s\u4e00-\u9fa5_.-]+", result["patch_source"]):
        raise ManagerError("patch_source 名称非法")
    return result


class ServerManager:
    def __init__(self, root: Path):
        self.root = root
        config_candidates = [
            root / "开服器" / CONFIG_FILE,
            root / CONFIG_FILE,
            Path(__file__).resolve().parent / CONFIG_FILE,
        ]
        self.config_path = next((p for p in config_candidates if p.is_file()), root / "开服器" / CONFIG_FILE)
        self.state_path = self.config_path.parent / STATE_FILE
        self.log_dir = root / "manager_logs"
        self.lock = threading.RLock()
        self.process: Optional[subprocess.Popen] = None
        self.log_handle = None
        self.started_at: Optional[str] = None
        self.last_exit_code: Optional[int] = None
        raw = read_json(self.config_path, {})
        if not isinstance(raw, dict):
            raw = {}
        self.config = normalize_config(raw, root)
        self.config_error = None
        try:
            self._adopt_state()
        except ManagerError as exc:
            self.config_error = str(exc)

    @property
    def script_path(self) -> Path:
        return self.root / "DreadHungerServer.sh"

    @property
    def binary_path(self) -> Path:
        return self.root / "DreadHunger" / "Binaries" / "Linux" / SERVER_BINARY

    def _adopt_state(self) -> None:
        state = read_json(self.state_path, {})
        if not isinstance(state, dict):
            return
        pid = state.get("pid")
        if isinstance(pid, int) and self._pid_matches(pid):
            self.started_at = state.get("started_at")

    def _pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        # kill(pid, 0) 对尚未 wait() 回收的僵尸进程仍会成功。
        # 把 Z 误判为存活会让每次停服都无意义地等满 10 秒。
        proc_stat = Path("/proc") / str(pid) / "stat"
        if proc_stat.is_file():
            try:
                stat_tail = proc_stat.read_text(encoding="utf-8", errors="replace").rsplit(")", 1)[1].strip()
                if stat_tail.startswith("Z"):
                    return False
            except (IndexError, OSError):
                pass
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ValueError):
            return False

    def _pid_matches(self, pid: int) -> bool:
        if not self._pid_alive(pid):
            return False
        proc_cmdline = Path("/proc") / str(pid) / "cmdline"
        if proc_cmdline.is_file():
            try:
                command = proc_cmdline.read_bytes().decode("utf-8", "replace")
                return "DreadHungerServer" in command
            except OSError:
                return False
        return True

    def _state_data(self, pid: int, log_file: Path, args: List[str]) -> Dict[str, Any]:
        try:
            log_name = str(log_file.relative_to(self.root))
        except ValueError:
            log_name = str(log_file)
        return {
            "pid": pid,
            "started_at": self.started_at,
            "log_file": log_name,
            "args": args,
        }

    def _clear_state(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass

    def _refresh_process(self) -> None:
        if self.process is None:
            return
        code = self.process.poll()
        if code is None:
            return
        self.last_exit_code = code
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None
        self.process = None
        self._clear_state()
        self._stop_injector()

    def _state_pid(self) -> Optional[int]:
        state = read_json(self.state_path, {})
        pid = state.get("pid") if isinstance(state, dict) else None
        return pid if isinstance(pid, int) else None

    def _current_pid(self) -> Optional[int]:
        if self.process is not None and self.process.poll() is None:
            return self.process.pid
        pid = self._state_pid()
        return pid if pid is not None and self._pid_matches(pid) else None

    def _set_executable(self, path: Path) -> None:
        if os.name == "posix" and path.is_file():
            path.chmod(path.stat().st_mode | 0o755)

    def _library_environment(self) -> Dict[str, str]:
        env = os.environ.copy()
        if os.name != "posix":
            return env
        lib_dirs = [
            self.binary_path.parent,
            self.root / "Engine" / "Binaries" / "ThirdParty" / "PhysX3" / "Linux" / "x86_64-unknown-linux-gnu",
            self.root / "Engine" / "Binaries" / "ThirdParty" / "Steamworks" / "Steamv151" / "x86_64-unknown-linux-gnu",
        ]
        paths = [str(path) for path in lib_dirs if path.is_dir()]
        if env.get("LD_LIBRARY_PATH"):
            paths.append(env["LD_LIBRARY_PATH"])
        if paths:
            env["LD_LIBRARY_PATH"] = ":".join(paths)
        return env

    def build_args(self) -> List[str]:
        query = [self.config["map"]]
        for key in GAME_KEYS:
            query.append("%s=%s" % (key, scalar_text(self.config[key])))
        return ["?".join(query), "-port=%d" % self.config["server_port"], "-log"] + list(
            self.config["extra_args"]
        )

    def command(self) -> List[str]:
        args = self.build_args()
        if self.script_path.is_file() and os.name == "posix":
            return ["/bin/sh", str(self.script_path)] + args
        if not self.binary_path.is_file():
            raise ManagerError("找不到 Linux 服务器二进制文件: " + str(self.binary_path))
        return [str(self.binary_path), "DreadHunger"] + args

    def save_config(self, incoming: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            merged = dict(self.config)
            for key in list(DEFAULT_GAME) + ["server_port", "extra_args", "patch_source"]:
                if key in incoming:
                    merged[key] = incoming[key]
            self.config = normalize_config(merged, self.root)
            atomic_write_json(self.config_path, self.config)
            return dict(self.config)

    def start(self) -> Dict[str, Any]:
        with self.lock:
            self._refresh_process()
            if self._current_pid() is not None:
                raise ManagerError("服务器已经运行")
            if not self.binary_path.is_file():
                raise ManagerError("找不到 Linux 服务器二进制文件")

            # 先启动注入器（注入器会等待游戏进程出现后自动注入）
            self._start_injector()

            self._set_executable(self.script_path)
            self._set_executable(self.binary_path)
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / ("server-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".log")
            args = self.build_args()
            command = self.command()
            if os.name == "posix" and os.geteuid() == 0:
                import pwd

                try:
                    pwd.getpwnam("www")
                    command = ["runuser", "-u", "www", "--"] + command
                except KeyError:
                    pass
            self.log_handle = log_path.open("ab")
            self.log_handle.write(("\n[%s] start: %s\n" % (now_text(), " ".join(command))).encode("utf-8"))
            self.log_handle.flush()
            try:
                self.process = subprocess.Popen(
                    command,
                    cwd=str(self.root),
                    stdin=subprocess.DEVNULL,
                    stdout=self.log_handle,
                    stderr=subprocess.STDOUT,
                    env=self._library_environment(),
                    start_new_session=(os.name == "posix"),
                )
            except OSError as exc:
                self.log_handle.close()
                self.log_handle = None
                raise ManagerError("启动失败: " + str(exc))

            self.started_at = now_text()
            atomic_write_json(self.state_path, self._state_data(self.process.pid, log_path, args))
            return self.status()

    def stop(self) -> Dict[str, Any]:
        with self.lock:
            self._refresh_process()
            pid = self._current_pid()
            if pid is None:
                self._stop_injector()
                self._clear_state()
                return self.status()
            if not self._pid_matches(pid):
                raise ManagerError("拒绝停止非本管理器启动的进程")

            # Frida Hook 必须在 Unreal 开始 CleanupWorld 前解除。
            # 先给游戏发 SIGTERM 会使其在卸载模块时卡死，并拖慢整机。
            self._stop_injector()

            try:
                if os.name == "posix":
                    os.killpg(pid, signal.SIGTERM)
                elif self.process is not None:
                    self.process.terminate()
                else:
                    os.kill(pid, signal.SIGTERM)
            except OSError as exc:
                raise ManagerError("停止失败: " + str(exc))

            deadline = time.time() + 10
            while time.time() < deadline and self._pid_alive(pid):
                time.sleep(0.2)
            if self._pid_alive(pid):
                try:
                    if os.name == "posix":
                        os.killpg(pid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass

            if self.process is not None:
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                self.process = None
            if self.log_handle is not None:
                self.log_handle.close()
                self.log_handle = None
            self._clear_state()
            return self.status()

    def restart(self) -> Dict[str, Any]:
        self.stop()
        time.sleep(0.5)
        return self.start()

    # ---------- 注入器管理 ----------

    def _injector_pids(self) -> List[int]:
        """当前运行中的 frida 注入器进程 PID 列表"""
        pids: List[int] = []
        proc_root = Path("/proc")
        if not proc_root.is_dir():
            return pids
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                cmdline = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            if b"frida_loader.py" in cmdline:
                try:
                    pids.append(int(entry.name))
                except ValueError:
                    pass
        return pids

    def _frida_python(self) -> str:
        """返回带 frida 的 python 解释器路径, 用于拉起注入器"""
        candidates: List[str] = [sys.executable]
        candidates.append("/www/server/pyporject_evn/versions/3.11.15/bin/python3.11")
        for cand in candidates:
            try:
                result = subprocess.run(
                    [cand, "-c", "import frida"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                )
                if result.returncode == 0:
                    return cand
            except (OSError, subprocess.SubprocessError):
                continue
        raise ManagerError("找不到带 frida 的 python, 无法启动注入器")

    def injector_status(self) -> Dict[str, Any]:
        pids = self._injector_pids()
        return {"running": bool(pids), "pids": pids}

    def _start_injector(self) -> None:
        """启动注入器（不先停止旧的; 若已有则先停止）"""
        if self._injector_pids():
            self._stop_injector()

        python = self._frida_python()
        log_path = self.root / "frida_loader.log"
        command = [python, "frida_loader.py", "--root", str(self.root)]
        if os.name == "posix" and os.geteuid() == 0:
            import pwd
            try:
                pwd.getpwnam("www")
                command = ["runuser", "-u", "www", "--"] + command
            except KeyError:
                pass
        log_handle = log_path.open("ab")
        try:
            subprocess.Popen(
                command,
                cwd=str(self.root),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name == "posix"),
            )
        finally:
            log_handle.close()

    def _stop_injector(self) -> None:
        """先让注入器走 KeyboardInterrupt/finally 优雅卸载，超时后才强制结束。"""
        pids = self._injector_pids()
        if not pids:
            return

        if os.name == "posix":
            process_groups = set()
            for pid in pids:
                try:
                    process_groups.add(os.getpgid(pid))
                except OSError:
                    pass
            for pgid in process_groups:
                try:
                    os.killpg(pgid, signal.SIGINT)
                except OSError:
                    pass
        else:
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGINT)
                except OSError:
                    pass

        deadline = time.time() + 5
        while time.time() < deadline and self._injector_pids():
            time.sleep(0.1)

        remaining = self._injector_pids()
        if os.name == "posix":
            remaining_groups = set()
            for pid in remaining:
                try:
                    remaining_groups.add(os.getpgid(pid))
                except OSError:
                    pass
            for pgid in remaining_groups:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    pass
        else:
            for pid in remaining:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

    def restart_injector(self) -> Dict[str, Any]:
        """停止旧注入器并重新拉起, 用于加载新增/修改的插件"""
        with self.lock:
            self._stop_injector()

            python = self._frida_python()
            log_path = self.root / "frida_loader.log"
            command = [python, "frida_loader.py", "--root", str(self.root)]
            if os.name == "posix" and os.geteuid() == 0:
                import pwd

                try:
                    pwd.getpwnam("www")
                    command = ["runuser", "-u", "www", "--"] + command
                except KeyError:
                    pass
            log_handle = log_path.open("ab")
            try:
                subprocess.Popen(
                    command,
                    cwd=str(self.root),
                    stdin=subprocess.DEVNULL,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=(os.name == "posix"),
                )
            except OSError as exc:
                raise ManagerError("注入器启动失败: " + str(exc))
            finally:
                log_handle.close()
            time.sleep(1)
            return self.injector_status()

    def status(self) -> Dict[str, Any]:
        with self.lock:
            self._refresh_process()
            pid = self._current_pid()
            return {
                "running": pid is not None,
                "pid": pid,
                "started_at": self.started_at,
                "last_exit_code": self.last_exit_code,
                "port": self.config["server_port"],
                "root": str(self.root),
                "binary": str(self.binary_path),
                "command": self.command() if self.binary_path.is_file() else [],
            }

    def _source_dir(self) -> Path:
        source_name = self.config.get("patch_source", "Linux 插件")
        source = (self.root / source_name).resolve()
        if not source.is_dir():
            if (self.root / "Linux 插件").is_dir():
                source = (self.root / "Linux 插件").resolve()
            elif (self.root / "Patches").is_dir():
                source = (self.root / "Patches").resolve()
        return source

    def _patch_target(self, name: str) -> Path:
        suffix = Path(name).suffix.lower()
        if suffix in {".pak", ".sig"}:
            return self.root / "DreadHunger" / "Content" / "Paks" / name
        if self.config.get("patch_source") == "Linux 插件" or not (self.root / "DreadHunger" / "Binaries" / "Linux" / "Patches").is_dir():
            return self.root / "Linux 插件" / name
        return self.root / "DreadHunger" / "Binaries" / "Linux" / "Patches" / name

    def patches(self) -> List[Dict[str, Any]]:
        source = self._source_dir()
        if not source.is_dir():
            return []
        result = []
        is_plugin_dir = source.name == "Linux 插件"
        seen = set()
        for path in sorted(source.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            name = path.name
            suffix = path.suffix.lower()

            if is_plugin_dir:
                if name.endswith(".disabled"):
                    clean_name = name[:-9]
                    active = False
                elif suffix == ".js":
                    clean_name = name
                    active = True
                else:
                    continue
                if clean_name in seen:
                    continue
                seen.add(clean_name)
                result.append(
                    {
                        "name": clean_name,
                        "size": path.stat().st_size,
                        "source": str(path.relative_to(self.root)),
                        "active": active,
                        "target": str(path.relative_to(self.root)),
                        "is_script": True,
                    }
                )
            else:
                if suffix not in PATCH_EXTENSIONS:
                    continue
                target = self._patch_target(name)
                result.append(
                    {
                        "name": name,
                        "size": path.stat().st_size,
                        "source": str(path.relative_to(self.root)),
                        "active": target.is_file(),
                        "target": str(target.relative_to(self.root)),
                        "is_script": suffix == ".js",
                    }
                )
        return result

    def activate_patch(self, name: str) -> Dict[str, Any]:
        if not name or Path(name).name != name or "\\" in name or ".." in Path(name).parts:
            raise ManagerError("插件名称非法")
        source_dir = self._source_dir()
        is_plugin_dir = source_dir.name == "Linux 插件"

        if is_plugin_dir:
            disabled_file = source_dir / (name + ".disabled")
            active_file = source_dir / name
            if disabled_file.is_file():
                os.replace(str(disabled_file), str(active_file))
            elif not active_file.is_file():
                raise ManagerError("找不到插件: " + name)
            return {"name": name, "active": True, "target": str(active_file.relative_to(self.root))}
        else:
            source = source_dir / name
            if not source.is_file():
                raise ManagerError("找不到补丁: " + name)
            target = self._patch_target(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file():
                backup_dir = self.root / ".manager_backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(target), str(backup_dir / target.name))
            shutil.copy2(str(source), str(target))
            return {"name": name, "active": True, "target": str(target.relative_to(self.root))}

    def deactivate_patch(self, name: str) -> Dict[str, Any]:
        if not name or Path(name).name != name or "\\" in name or ".." in Path(name).parts:
            raise ManagerError("插件名称非法")
        source_dir = self._source_dir()
        is_plugin_dir = source_dir.name == "Linux 插件"

        if is_plugin_dir:
            active_file = source_dir / name
            disabled_file = source_dir / (name + ".disabled")
            if active_file.is_file():
                os.replace(str(active_file), str(disabled_file))
            return {"name": name, "active": False, "target": str(disabled_file.relative_to(self.root))}
        else:
            target = self._patch_target(name)
            if target.is_file():
                target.unlink()
            return {"name": name, "active": False, "target": str(target.relative_to(self.root))}

    def get_patch_content(self, name: str) -> Dict[str, Any]:
        if not name or Path(name).name != name or "\\" in name or ".." in Path(name).parts:
            raise ManagerError("插件名称非法")
        source_dir = self._source_dir()
        file_path = source_dir / name
        if not file_path.is_file():
            file_path = source_dir / (name + ".disabled")
        if not file_path.is_file():
            raise ManagerError("插件文件不存在: " + name)
        try:
            content = file_path.read_text(encoding="utf-8")
            return {"name": name, "content": content, "size": file_path.stat().st_size}
        except (OSError, UnicodeError) as exc:
            raise ManagerError("读取插件文件失败: " + str(exc))

    def save_patch_content(self, name: str, content: str) -> Dict[str, Any]:
        if not name or Path(name).name != name or "\\" in name or ".." in Path(name).parts:
            raise ManagerError("插件名称非法")
        source_dir = self._source_dir()
        file_path = source_dir / name
        if not file_path.is_file():
            file_path = source_dir / (name + ".disabled")
        if not file_path.is_file():
            file_path = source_dir / name
        try:
            backup_dir = self.root / ".manager_backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir.mkdir(parents=True, exist_ok=True)
            if file_path.is_file():
                shutil.copy2(str(file_path), str(backup_dir / file_path.name))
            file_path.write_text(content, encoding="utf-8")
            return {"name": name, "size": file_path.stat().st_size, "saved_at": now_text()}
        except OSError as exc:
            raise ManagerError("保存插件失败: " + str(exc))

    def upload_patch(self, filename: str, content: str) -> Dict[str, Any]:
        if not filename or "\\" in filename or "/" in filename or ".." in filename:
            raise ManagerError("文件名非法")
        clean_name = Path(filename).name
        if not clean_name.lower().endswith(".js"):
            raise ManagerError("仅支持上传 .js 格式的插件文件")
        source_dir = self._source_dir()
        source_dir.mkdir(parents=True, exist_ok=True)
        target_path = source_dir / clean_name
        disabled_path = source_dir / (clean_name + ".disabled")
        try:
            backup_dir = self.root / ".manager_backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir.mkdir(parents=True, exist_ok=True)
            if target_path.is_file():
                shutil.copy2(str(target_path), str(backup_dir / target_path.name))
            if disabled_path.is_file():
                disabled_path.unlink()
            target_path.write_text(content, encoding="utf-8")
            return {
                "name": clean_name,
                "size": target_path.stat().st_size,
                "active": True,
                "target": str(target_path.relative_to(self.root)),
            }
        except OSError as exc:
            raise ManagerError("写入插件失败: " + str(exc))

    def log_paths(self) -> List[Path]:
        paths: List[Path] = []
        state = read_json(self.state_path, {})
        if isinstance(state, dict) and isinstance(state.get("log_file"), str):
            paths.append(self.root / state["log_file"])
        paths.extend(
            [
                self.root / "DreadHunger" / "Binaries" / "Linux" / "output.log",
                self.root / "DreadHunger" / "Saved" / "Logs" / "DreadHunger.log",
                self.root / "DreadHunger" / "Binaries" / "Linux" / "player.log",
                self.root / "output.log",
            ]
        )
        result = []
        seen = set()
        for path in paths:
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key not in seen and path.is_file():
                seen.add(key)
                result.append(path)
        return sorted(result, key=lambda path: path.stat().st_mtime, reverse=True)

    def read_log(self, tail: int = 300, requested: Optional[str] = None) -> Dict[str, str]:
        tail = max(1, min(tail, 2000))
        paths = self.log_paths()
        path = None
        if requested:
            for candidate in paths:
                if str(candidate.relative_to(self.root)) == requested:
                    path = candidate
                    break
        if path is None and paths:
            path = paths[0]
        if path is None:
            return {"file": "", "content": "暂无日志"}
        try:
            data = path.read_bytes()
            data = data[-2_000_000:]
            content = data.decode("utf-8", "replace").splitlines()[-tail:]
            return {"file": str(path.relative_to(self.root)), "content": "\n".join(content)}
        except OSError as exc:
            raise ManagerError("读取日志失败: " + str(exc))

    def injector_log_path(self) -> Path:
        return self.root / "frida_loader.log"

    def read_injector_log(self, tail: int = 200) -> Dict[str, str]:
        tail = max(1, min(tail, 2000))
        path = self.injector_log_path()
        if not path.is_file():
            return {"file": "frida_loader.log", "content": "暂无注入器日志"}
        try:
            data = path.read_bytes()
            data = data[-2_000_000:]
            content = data.decode("utf-8", "replace").splitlines()[-tail:]
            return {"file": str(path.relative_to(self.root)), "content": "\n".join(content)}
        except OSError as exc:
            raise ManagerError("读取注入器日志失败: " + str(exc))

    def saved_logs_dir(self) -> Path:
        candidates = [
            self.root / "DreadHunger" / "Saved" / "Logs",
            Path("/www/wwwroot/Dread Hunger/LinuxServer/DreadHunger/Saved/Logs"),
            self.root / "Saved" / "Logs",
            self.root.parent / "WindowsServer" / "DreadHunger" / "Saved" / "Logs",
        ]
        for c in candidates:
            if c.is_dir():
                return c
        target = self.root / "DreadHunger" / "Saved" / "Logs"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def list_saved_logs(self) -> List[Dict[str, Any]]:
        log_dir = self.saved_logs_dir()
        if not log_dir.is_dir():
            return []
        items = []
        for p in log_dir.glob("*.log"):
            if not p.is_file():
                continue
            stat = p.stat()
            size = stat.st_size
            size_fmt = f"{size / 1024:.1f} KB" if size < 1048576 else f"{size / 1048576:.2f} MB"
            items.append({
                "name": p.name,
                "size": size,
                "size_fmt": size_fmt,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return sorted(items, key=lambda x: x["mtime"], reverse=True)

    def analyze_saved_log(self, filename: str) -> Dict[str, Any]:
        if not filename or "\\" in filename or "/" in filename or ".." in filename:
            raise ManagerError("日志文件名非法")
        log_dir = self.saved_logs_dir()
        log_path = log_dir / filename
        if not log_path.is_file():
            found = False
            for c in [self.root / "DreadHunger" / "Saved" / "Logs", self.root.parent / "WindowsServer" / "DreadHunger" / "Saved" / "Logs"]:
                if (c / filename).is_file():
                    log_path = c / filename
                    found = True
                    break
            if not found:
                raise ManagerError("找不到日志文件: " + filename)

        try:
            raw_bytes = log_path.read_bytes()
            text = raw_bytes.decode("utf-8", "replace")
        except OSError as exc:
            raise ManagerError("读取日志文件失败: " + str(exc))

        lines = text.splitlines()
        total_lines = len(lines)

        recent_ips = []
        for line in lines:
            m_remote = re.search(r'RemoteAddr:\s*([0-9a-zA-Z.:]+)', line)
            if m_remote:
                recent_ips.append(m_remote.group(1))

        # 提取登录请求 (Login requests)
        logins = []
        seen_users = set()
        ip_idx = 0
        for line in lines:
            m_login = re.search(
                r'LogNet:\s*Login request:\s*\?Name=(?P<name>.+?)\s+userId:\s*(?P<uid>[^\s]+)(?:\s+platform:\s*(?P<platform>[^\s]+))?',
                line
            )
            if m_login:
                name = m_login.group("name").strip()
                uid = m_login.group("uid").strip()
                platform = m_login.group("platform") or "EOSPlus"
                clean_uid = uid.replace("EOSPlus:", "")
                player_ip = recent_ips[ip_idx] if ip_idx < len(recent_ips) else "未知"
                ip_idx += 1

                user_key = f"{name}_{clean_uid}"
                if user_key not in seen_users:
                    seen_users.add(user_key)
                    joined = any(f"Join succeeded: {name}" in l for l in lines)
                    logins.append({
                        "name": name,
                        "userId": clean_uid,
                        "ip": player_ip,
                        "platform": platform,
                        "joined": joined,
                    })

        # 提取作弊与异常检测 (Cheat & Anomaly Detection)
        cheat_keywords = [
            "SpeedHack", "Cheat", "Fly", "TeleportSpot", "invalid attempt to read",
            "SIGSEGV", "Fatal error!", "Assertion failed", "DDoS", "Banned", "Kicked for",
            "UWorld::FindTeleportSpot called with an actor that is intersecting"
        ]
        cheats = []
        for line in lines:
            for kw in cheat_keywords:
                if kw in line:
                    cheats.append(line.strip())
                    break

        time_stamps = re.findall(r'\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2})', text)
        time_range = "未知"
        if time_stamps:
            time_range = f"{time_stamps[0]} ~ {time_stamps[-1]}"

        # 格式化生成摘要文本 (严格符合摘要规范)
        summary_lines = []
        summary_lines.append("摘要")
        summary_lines.append("作弊总结:")
        if not cheats:
            summary_lines.append("未发现作弊者")
        else:
            summary_lines.append(f"发现 {len(cheats)} 条异常/可疑行为:")
            for c in cheats[:10]:
                summary_lines.append(f"  • {c}")
            if len(cheats) > 10:
                summary_lines.append(f"  ... 另有 {len(cheats) - 10} 条异常日志")

        summary_lines.append("")
        summary_lines.append("登录请求:")
        if not logins:
            summary_lines.append("暂无玩家登录记录")
        else:
            for item in logins:
                summary_lines.append(
                    f"Steam用户名: {item['name']}  用户ID: {item['userId']} ip:{item['ip']}"
                )

        summary_text = "\n".join(summary_lines)

        return {
            "file": filename,
            "time_range": time_range,
            "total_lines": total_lines,
            "size": len(raw_bytes),
            "size_fmt": f"{len(raw_bytes) / 1024:.1f} KB" if len(raw_bytes) < 1048576 else f"{len(raw_bytes) / 1048576:.2f} MB",
            "cheats_count": len(cheats),
            "cheats": cheats[:50],
            "logins": logins,
            "summary_text": summary_text,
        }

    def delete_saved_log(self, filename: str) -> Dict[str, Any]:
        if not filename or "\\" in filename or "/" in filename or ".." in filename:
            raise ManagerError("日志文件名非法")
        log_dir = self.saved_logs_dir()
        log_path = log_dir / filename
        if not log_path.is_file():
            for c in [self.root / "DreadHunger" / "Saved" / "Logs", self.root.parent / "WindowsServer" / "DreadHunger" / "Saved" / "Logs"]:
                if (c / filename).is_file():
                    log_path = c / filename
                    break
        if log_path.is_file():
            log_path.unlink()
            return {"name": filename, "deleted": True}
        raise ManagerError("日志文件不存在: " + filename)

    def state(self) -> Dict[str, Any]:
        return {
            "version": APP_VERSION,
            "status": self.status(),
            "config": self.config,
            "patches": self.patches(),
            "injector": self.injector_status(),
            "logs": [str(path.relative_to(self.root)) for path in self.log_paths()],
        }

    def check(self) -> Dict[str, Any]:
        magic = ""
        try:
            magic = self.binary_path.read_bytes()[:4].hex()
        except OSError:
            pass
        return {
            "version": APP_VERSION,
            "root": str(self.root),
            "script_exists": self.script_path.is_file(),
            "binary_exists": self.binary_path.is_file(),
            "binary_magic": magic,
            "elf": magic == "7f454c46",
            "config_path": str(self.config_path),
            "config": self.config,
            "logs": [str(path.relative_to(self.root)) for path in self.log_paths()],
        }


def html_page() -> str:
    return r'''<!doctype html>
<html lang="zh-CN" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dread Hunger Linux 开服管理器</title>
<!-- Element Plus & Dark Theme CSS -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus/dist/index.css" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/element-plus/theme-chalk/dark/css-vars.css" />
<script src="https://cdn.jsdelivr.net/npm/vue@3/dist/vue.global.prod.js"></script>
<script src="https://cdn.jsdelivr.net/npm/element-plus/dist/index.full.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/element-plus/dist/locale/zh-cn.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@element-plus/icons-vue"></script>
<style>
:root{
  --bg-color:#080d12;
  --el-bg-color:#0f1721;
  --el-bg-color-overlay:#131c26;
  --el-border-color:#1e2e3d;
  --el-border-color-light:#25374a;
}
body{
  margin:0;padding:16px;background:radial-gradient(ellipse at 80% 0%,#112938 0%,var(--bg-color) 60%),var(--bg-color);
  color:#e2edf8;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
  min-height:100vh;box-sizing:border-box;
}
#app{max-width:1440px;margin:0 auto;display:flex;flex-direction:column;gap:14px}

/* Header */
.header-card{
  background:#0f1721;border:1px solid #1e2e3d;border-radius:10px;padding:12px 18px;
  display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;
}
.header-brand{display:flex;align-items:center;gap:12px}
.header-brand h1{font-size:17px;font-weight:700;margin:0;color:#fff;display:flex;align-items:center;gap:8px}
.header-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}

.card-header-title{
  font-size:13px;font-weight:600;display:flex;align-items:center;justify-content:space-between;
  color:#fff;flex-wrap:wrap;gap:8px;min-height:32px;
}

.fullscreen-mask{
  position:fixed;inset:0;background:rgba(0,0,0,0.75);backdrop-filter:blur(4px);z-index:9998;
}

.cmd-box{
  background:#070b10;border:1px solid #162330;border-radius:6px;padding:8px 10px;
  font:11px/1.4 "Cascadia Mono",Consolas,monospace;color:#8fa7b8;word-break:break-all;max-height:75px;overflow-y:auto;
}

/* Terminal Log Box */
.terminal-box {
  background: #060a0f;
  border: 1px solid #162330;
  border-radius: 8px;
  padding: 12px 14px;
  font: 12px/1.55 "Cascadia Code", Consolas, "Courier New", monospace;
  color: #c9d8e6;
  white-space: pre-wrap;
  word-break: break-all;
  height: 330px;
  max-height: 330px;
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.6);
  position: relative;
}
.terminal-box.collapsed {
  height: 60px;
  max-height: 60px;
}
.terminal-box.fullscreen {
  position: fixed;
  inset: 24px 30px;
  height: calc(100vh - 48px) !important;
  max-height: calc(100vh - 48px) !important;
  z-index: 9999;
  border: 1px solid #0284c7;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.9), 0 0 30px rgba(14, 165, 233, 0.3);
}

/* Custom Scrollbar for terminal-box */
.terminal-box::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.terminal-box::-webkit-scrollbar-track {
  background: #090e15;
  border-radius: 4px;
}
.terminal-box::-webkit-scrollbar-thumb {
  background: #1e3347;
  border-radius: 4px;
}
.terminal-box::-webkit-scrollbar-thumb:hover {
  background: #0284c7;
}

.el-card {
  border-radius: 10px !important;
  overflow: hidden;
}
.el-card__header {
  padding: 10px 16px !important;
}
.el-card__body {
  padding: 14px 16px !important;
}

/* Fullscreen Login Page */
.login-wrapper {
  min-height: calc(100vh - 32px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 440px;
  background: rgba(15, 25, 38, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(56, 189, 248, 0.25);
  border-radius: 16px;
  padding: 42px 36px;
  box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 35px rgba(14, 165, 233, 0.15);
  animation: fadeIn 0.35s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
}
.login-header {
  text-align: center;
  margin-bottom: 28px;
}
.login-icon-box {
  width: 68px;
  height: 68px;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.25), rgba(99, 102, 241, 0.2));
  border: 1px solid rgba(56, 189, 248, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  box-shadow: 0 0 24px rgba(14, 165, 233, 0.3);
}
.login-header h2 {
  font-size: 22px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.login-sub {
  color: #8fa7b8;
  font-size: 13px;
}
.form-label {
  display: block;
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 8px;
  font-weight: 500;
}
.login-submit-btn {
  width: 100%;
  margin-top: 24px;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
  background: linear-gradient(135deg, #0284c7, #4f46e5) !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 16px rgba(14, 165, 233, 0.35);
  transition: all 0.2s;
}
.login-submit-btn:hover {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(14, 165, 233, 0.45);
}
.login-footer-tips {
  margin-top: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}
.login-footer-tips code {
  color: #38bdf8;
  background: rgba(14, 165, 233, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
</head>
<body>
<div id="app" v-cloak>
  <!-- Fullscreen Login View (When Not Logged In) -->
  <div v-if="!isLoggedIn" class="login-wrapper">
    <div class="login-card">
      <div class="login-header">
        <div class="login-icon-box">
          <el-icon :size="36" color="#38bdf8"><Compass /></el-icon>
        </div>
        <h2>Dread Hunger 开服管理器</h2>
        <p class="login-sub">Linux 独立服务端控制中心</p>
      </div>

      <div class="login-form">
        <div style="margin-bottom: 18px">
          <label class="form-label">管理密码 (Access Password)</label>
          <el-input
            v-model="loginPwd"
            type="password"
            size="large"
            placeholder="请输入开服器管理密码"
            show-password
            :prefix-icon="Key"
            @keyup.enter="doLogin"
            autofocus
          />
        </div>

        <el-button
          type="primary"
          size="large"
          :icon="Check"
          :loading="isLoggingIn"
          class="login-submit-btn"
          @click="doLogin"
        >
          登 录 开 服 器
        </el-button>
      </div>
    </div>
  </div>

  <!-- Main Dashboard View (When Logged In) -->
  <div v-else style="display:flex;flex-direction:column;gap:14px">
    <!-- Fullscreen Backdrop if active -->
    <div v-if="isLogFullscreen" class="fullscreen-mask" @click="isLogFullscreen = false"></div>

    <!-- Header Bar -->
    <div class="header-card">
      <div class="header-brand">
        <h1>
          <el-icon :size="18" color="#409EFF"><Compass /></el-icon>
          <span>Dread Hunger</span>
          <el-tag size="small" effect="dark" type="primary">Linux 独立版</el-tag>
        </h1>
        <el-tag :type="status.running ? 'success' : 'danger'" effect="dark" size="small">
          <el-icon style="margin-right:3px"><component :is="status.running ? 'Check' : 'Close'" /></el-icon>
          {{ status.running ? ('运行中 PID ' + status.pid) : '已停止' }}
        </el-tag>
        <el-tag :type="injector.running ? 'success' : 'info'" effect="plain" size="small">
          <el-icon style="margin-right:3px"><Lightning /></el-icon>
          {{ injector.running ? ('注入器 PID ' + (injector.pids||[]).join(',')) : '注入器未运行' }}
        </el-tag>
      </div>
      <div class="header-actions">
        <el-button type="success" size="small" :icon="VideoPlay" @click="action('/api/start', '启动')">启动</el-button>
        <el-button type="danger" size="small" :icon="SwitchButton" @click="action('/api/stop', '停止')">停止</el-button>
        <el-button type="warning" size="small" :icon="Refresh" @click="action('/api/restart', '重启')">重启</el-button>
        <el-button type="primary" size="small" :icon="Cpu" @click="action('/api/injector/restart', '重启注入器')">重启注入器</el-button>
        <el-button size="small" :icon="RefreshRight" @click="refresh">刷新</el-button>
        <el-button size="small" type="danger" plain :icon="SwitchButton" @click="doLogout">登出</el-button>
      </div>
    </div>

    <!-- Upper Grid: Status & Game Config -->
    <el-row :gutter="14">
      <!-- Server Status Column -->
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header-title">
              <div style="display:flex;align-items:center;gap:6px">
                <el-icon color="#409EFF"><Monitor /></el-icon>
                <span>运行状态</span>
              </div>
            </div>
          </template>
          <el-descriptions border :column="1" size="small">
            <el-descriptions-item label="进程 PID">
              <strong>{{ status.pid || '-' }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="游戏端口">
              <el-tag size="small" type="primary">{{ status.port || config.server_port || 9100 }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Frida 注入器">
              <el-tag size="small" :type="injector.running ? 'success' : 'danger'">
                <el-icon style="margin-right:2px"><Lightning /></el-icon>
                {{ injector.running ? ('正常 (PID: ' + (injector.pids||[]).join(',') + ')') : '未运行' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="服务器根目录">
              <span style="font-size:12px;color:#8fa7b8;word-break:break-all">{{ status.root || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <div style="margin-top:10px">
            <div style="font-size:11px;color:#8fa7b8;margin-bottom:4px;font-weight:600;display:flex;align-items:center;gap:4px">
              <el-icon><Operation /></el-icon> 启动指令
            </div>
            <div class="cmd-box">{{ (status.command || []).join(' ') || '-' }}</div>
          </div>
        </el-card>
      </el-col>

      <!-- Game Configuration Column -->
      <el-col :xs="24" :sm="24" :md="16" :lg="16">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header-title">
              <div style="display:flex;align-items:center;gap:6px">
                <el-icon color="#67C23A"><Setting /></el-icon>
                <span>游戏房间与规则配置</span>
              </div>
              <div style="display:flex;align-items:center;gap:6px">
                <el-button size="small" :icon="RefreshRight" @click="resetConfig">重置/重新读取</el-button>
                <el-button type="primary" size="small" :icon="Check" @click="saveConfig">保存并应用</el-button>
              </div>
            </div>
          </template>
          <el-form :model="config" label-position="top" size="small">
            <el-row :gutter="12">
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="地图 (Map)">
                  <el-select v-model="config.map" filterable allow-create placeholder="选择或输入地图" style="width:100%">
                    <el-option v-for="item in mapOptions" :key="item.value" :label="item.label" :value="item.value" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="4">
                <el-form-item label="端口 (Port)">
                  <el-input-number v-model="config.server_port" :min="1" :max="65535" :step="1" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="4">
                <el-form-item label="最大玩家">
                  <el-input-number v-model="config.maxplayers" :min="1" :max="32" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="4">
                <el-form-item label="内奸 (Thralls)">
                  <el-input-number v-model="config.thralls" :min="0" :max="8" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="4">
                <el-form-item label="白天分钟">
                  <el-input-number v-model="config.dayminutes" :min="1" :max="240" style="width:100%" />
                </el-form-item>
              </el-col>

              <el-col :xs="12" :sm="6" :md="4">
                <el-form-item label="暴风雪前天数">
                  <el-input-number v-model="config.daysbeforeblizzard" :min="0" :max="30" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="5">
                <el-form-item label="捕食者伤害倍率">
                  <el-input-number v-model="config.predatordamage" :min="0" :step="0.1" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="5">
                <el-form-item label="煤炭燃烧倍率">
                  <el-input-number v-model="config.coalburnrate" :min="0" :step="0.1" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="5">
                <el-form-item label="饥饿速度倍率">
                  <el-input-number v-model="config.hungerrate" :min="0" :step="0.1" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :xs="12" :sm="6" :md="5">
                <el-form-item label="寒冷强度倍率">
                  <el-input-number v-model="config.coldintensity" :min="0" :step="0.1" style="width:100%" />
                </el-form-item>
              </el-col>

              <el-col :span="24">
                <el-form-item label="附加启动参数 (Extra Args)">
                  <el-input v-model="config.extra_args" placeholder="例如：-Log -serverName=MyServer" clearable />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- Lower Grid: Unified Tabbed Logs & Plugins Management -->
    <el-row :gutter="14">
      <!-- Log Console Column -->
      <el-col :xs="24" :sm="24" :md="14" :lg="14">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header-title">
              <el-radio-group v-model="activeLogTab" size="small" @change="handleLogTabChange">
                <el-radio-button label="server">
                  <el-icon style="vertical-align:middle;margin-right:2px"><Document /></el-icon>
                  <span>服务端主日志</span>
                </el-radio-button>
                <el-radio-button label="injector">
                  <el-icon style="vertical-align:middle;margin-right:2px"><Lightning /></el-icon>
                  <span>Frida 注入日志</span>
                </el-radio-button>
                <el-radio-button label="saved_logs">
                  <el-icon style="vertical-align:middle;margin-right:2px"><DataAnalysis /></el-icon>
                  <span>历史日志智能分析</span>
                </el-radio-button>
              </el-radio-group>

              <!-- Log Actions Toolbar (Visible on server/injector tabs) -->
              <div v-if="activeLogTab !== 'saved_logs'" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <el-input v-model="logFilter" :prefix-icon="Search" placeholder="过滤..." clearable size="small" style="width:100px" />
                <el-select v-model="tailLines" size="small" style="width:80px" @change="refreshLogs">
                  <el-option label="100行" :value="100" />
                  <el-option label="300行" :value="300" />
                  <el-option label="500行" :value="500" />
                  <el-option label="1000行" :value="1000" />
                </el-select>
                <el-tooltip content="强制滑到底部" placement="top">
                  <el-button size="small" :icon="Bottom" type="primary" plain @click="manualScrollToBottom">滑底</el-button>
                </el-tooltip>
                <el-button size="small" :type="autoScroll ? 'success' : 'default'" @click="toggleAutoScroll">
                  {{ autoScroll ? '自动滑底:开' : '自动滑底:关' }}
                </el-button>
                <el-tooltip content="复制日志到剪贴板" placement="top">
                  <el-button size="small" :icon="CopyDocument" @click="copyLogs">复制</el-button>
                </el-tooltip>
                <el-tooltip :content="isLogCollapsed ? '展开日志' : '折叠日志'" placement="top">
                  <el-button size="small" :icon="isLogCollapsed ? ArrowDown : ArrowUp" @click="isLogCollapsed = !isLogCollapsed" />
                </el-tooltip>
                <el-tooltip :content="isLogFullscreen ? '退出全屏' : '全屏日志'" placement="top">
                  <el-button size="small" :icon="isLogFullscreen ? ScaleToOriginal : FullScreen" @click="isLogFullscreen = !isLogFullscreen" />
                </el-tooltip>
              </div>

              <!-- Saved Logs Toolbar (Visible on saved_logs tab) -->
              <div v-else style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <el-button size="small" :icon="Refresh" @click="fetchSavedLogs">刷新</el-button>
                <el-button size="small" :icon="CopyDocument" :disabled="!analysisResult" @click="copyAnalysisSummary">复制摘要</el-button>
              </div>
            </div>
          </template>

          <!-- Saved Logs Analysis View -->
          <div v-if="activeLogTab === 'saved_logs'" style="min-height:330px">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">
              <el-select v-model="selectedSavedLog" placeholder="选择 Saved/Logs 历史日志文件..." style="flex:1;min-width:200px" size="small" @change="doAnalyzeLog">
                <el-option v-for="item in savedLogsList" :key="item.name" :label="item.name + ' (' + item.size_fmt + ' - ' + item.mtime + ')'" :value="item.name" />
              </el-select>
              <el-button size="small" type="primary" :icon="Search" :loading="isAnalyzing" @click="doAnalyzeLog">一键分析提取</el-button>
              <el-button size="small" type="danger" plain :icon="Delete" :disabled="!selectedSavedLog" @click="doDeleteSavedLog">删除</el-button>
            </div>

            <div v-if="isAnalyzing" style="text-align:center;padding:40px 0;color:#8fa7b8">
              <el-icon class="is-loading" :size="28"><Loading /></el-icon>
              <p style="margin-top:10px;font-size:13px">正在读取并智能分析日志数据...</p>
            </div>

            <div v-else-if="!analysisResult" style="text-align:center;padding:30px 0;color:#8fa7b8">
              <el-empty description="请选择上方日志文件并点击「一键分析提取」" :image-size="50" />
            </div>

            <div v-else style="display:flex;flex-direction:column;gap:10px">
              <!-- Cheat Summary Badge -->
              <el-alert
                :title="analysisResult.cheats_count === 0 ? '作弊总结: 未发现作弊者' : ('作弊总结: 发现 ' + analysisResult.cheats_count + ' 条异常/可疑行为')"
                :type="analysisResult.cheats_count === 0 ? 'success' : 'warning'"
                :closable="false"
                show-icon
              />

              <!-- Logins List -->
              <div style="background:#080e16;border:1px solid #162434;border-radius:6px;padding:8px 12px">
                <div style="font-size:12px;font-weight:600;color:#38bdf8;margin-bottom:6px;display:flex;align-items:center;gap:6px">
                  <el-icon><User /></el-icon>
                  <span>登录请求 ({{ analysisResult.logins.length }} 人)</span>
                </div>
                <div v-if="analysisResult.logins.length === 0" style="color:#64748b;font-size:12px">暂无登录记录</div>
                <div v-else style="max-height:105px;overflow-y:auto;font-size:11.5px;line-height:1.6">
                  <div v-for="(p, idx) in analysisResult.logins" :key="idx" style="border-bottom:1px solid #111a26;padding:3px 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px">
                    <div>
                      <strong style="color:#f1f5f9">{{ p.name }}</strong>
                      <span style="color:#64748b;margin-left:6px">用户ID: {{ p.userId }}</span>
                    </div>
                    <div style="color:#8fa7b8">
                      <el-tag size="small" type="info">ip:{{ p.ip }}</el-tag>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Summary Text Output -->
              <div class="cmd-box" style="max-height:110px;font-size:11px;line-height:1.45;color:#c9d8e6;white-space:pre-wrap">{{ analysisResult.summary_text }}</div>
            </div>
          </div>

          <!-- Server / Injector Terminal View -->
          <div v-else :class="['terminal-box', isLogCollapsed ? 'collapsed' : '', isLogFullscreen ? 'fullscreen' : '']" ref="logPreRef" @scroll="onLogScroll">{{ filteredLog }}</div>
        </el-card>
      </el-col>

      <!-- Plugins Table Column -->
      <el-col :xs="24" :sm="24" :md="10" :lg="10">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header-title">
              <div style="display:flex;align-items:center;gap:6px">
                <el-icon color="#E6A23C"><Files /></el-icon>
                <span>插件与补丁管理</span>
              </div>
              <div style="display:flex;align-items:center;gap:8px">
                <el-tag size="small" effect="plain">目录: {{ config.patch_source || 'Linux 插件' }}/</el-tag>
                <el-upload
                  accept=".js"
                  :show-file-list="false"
                  :before-upload="handlePluginUpload"
                >
                  <el-button type="success" size="small" :icon="Upload">上传 JS 插件</el-button>
                </el-upload>
              </div>
            </div>
          </template>
          <el-table :data="patches" stripe size="small" height="330" style="width:100%">
            <el-table-column prop="name" label="插件名称" min-width="140" show-overflow-tooltip>
              <template #default="scope">
                <div style="display:flex;align-items:center;gap:5px">
                  <el-icon color="#409EFF"><Document /></el-icon>
                  <strong>{{ scope.row.name }}</strong>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="70">
              <template #default="scope">
                {{ (scope.row.size / 1024).toFixed(1) }}K
              </template>
            </el-table-column>
            <el-table-column label="状态" width="75">
              <template #default="scope">
                <el-tag size="small" :type="scope.row.active ? 'success' : 'info'">
                  {{ scope.row.active ? '已启用' : '未启用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="135" align="center">
              <template #default="scope">
                <div style="display:flex;align-items:center;justify-content:center;gap:4px">
                  <el-button v-if="scope.row.is_script" size="small" type="primary" :icon="Edit" @click="openPatchEditor(scope.row)">
                    编辑
                  </el-button>
                  <el-button size="small" :type="scope.row.active ? 'danger' : 'success'" :icon="scope.row.active ? CloseBold : Select" @click="togglePatch(scope.row)">
                    {{ scope.row.active ? '停用' : '启用' }}
                  </el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- Plugin Code Editor Dialog -->
    <el-dialog v-model="showEditorDialog" :title="'📝 编辑插件: ' + editingPatchName" width="75%" top="3vh" :close-on-click-modal="false">
      <!-- Top Action Bar -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;background:#141e2b;padding:8px 12px;border-radius:6px;border:1px solid #1f3042;flex-wrap:wrap;gap:8px">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <el-tag size="small" type="primary">{{ editingPatchName }}</el-tag>
          <el-tag size="small" type="info">{{ (editorContent||'').length }} 字符</el-tag>
          <span style="font-size:12px;color:#8fa7b8">💡 保存后可点击「保存并重启注入器」实现热更新</span>
        </div>
        <div style="display:flex;gap:8px">
          <el-button size="small" @click="showEditorDialog = false">取 消</el-button>
          <el-button type="primary" size="small" :icon="Check" :loading="isSaving" @click="savePatchContent">保 存</el-button>
          <el-button type="warning" size="small" :icon="Cpu" :loading="isSaving" @click="saveAndRestartInjector">保存并重启注入器</el-button>
        </div>
      </div>
      <el-input
        v-model="editorContent"
        type="textarea"
        :rows="19"
        placeholder="正在读取插件源码..."
        style="font-family:'Cascadia Code',Consolas,monospace;font-size:13px"
      />
      <template #footer>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <el-button @click="showEditorDialog = false">关闭窗口</el-button>
          <div style="display:flex;gap:8px">
            <el-button type="primary" :icon="Check" :loading="isSaving" @click="savePatchContent">保 存</el-button>
            <el-button type="warning" :icon="Cpu" :loading="isSaving" @click="saveAndRestartInjector">保存并重启注入器</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</div>

<script>
const { createApp, ref, reactive, computed, onMounted, nextTick, watch } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;
const {
  VideoPlay, SwitchButton, Refresh, Cpu, RefreshRight, Check, Close, Search,
  ArrowUp, ArrowDown, FullScreen, ScaleToOriginal, CopyDocument, Bottom, CircleClose, Delete, Loading, User,
  Monitor, Setting, Document, Lightning, Files, Compass, Operation, Key, Select, CloseBold, Edit, Upload, DataAnalysis
} = ElementPlusIconsVue;

const app = createApp({
  setup() {
    const isLoggedIn = ref(true);
    const loginPwd = ref('');
    const isLoggingIn = ref(false);

    const status = reactive({ running: false, pid: null, port: 9100, root: '', command: [] });
    const config = reactive({
      map: 'Departure_Persistent',
      server_port: 9100,
      maxplayers: 8,
      thralls: 2,
      dayminutes: 9,
      daysbeforeblizzard: 3,
      predatordamage: 1.0,
      coalburnrate: 1.0,
      hungerrate: 1.0,
      coldintensity: 1.0,
      extra_args: '',
      patch_source: 'Linux 插件'
    });
    const injector = reactive({ running: false, pids: [] });
    const patches = ref([]);
    const activeLogTab = ref('server');
    const serverLog = ref('');
    const injectorLog = ref('');
    const logFilter = ref('');
    const tailLines = ref(300);
    const autoScroll = ref(true);
    const isLogCollapsed = ref(false);
    const isLogFullscreen = ref(false);
    const logPreRef = ref(null);

    // Code Editor State
    const showEditorDialog = ref(false);
    const editingPatchName = ref('');
    const editorContent = ref('');
    const isSaving = ref(false);

    // Saved Logs State
    const savedLogsList = ref([]);
    const selectedSavedLog = ref('');
    const isAnalyzing = ref(false);
    const analysisResult = ref(null);

    const mapOptions = [
      { label: '出发地 (Departure)', value: 'Departure_Persistent' },
      { label: '近道 (Approach)', value: 'Approach_Persistent' },
      { label: '峰顶 (Summit)', value: 'Summit_Persistent' },
      { label: '群岛 (Archipelago)', value: 'Archipelago_Persistent' },
      { label: '开拓者 (Expedition)', value: 'Expedition_Persistent' }
    ];

    const isUserAtBottom = ref(true);
    const configLoaded = ref(false);

    const filteredLog = computed(() => {
      const raw = activeLogTab.value === 'server' ? serverLog.value : injectorLog.value;
      if (!logFilter.value.trim()) return raw || '暂无日志内容';
      const q = logFilter.value.trim().toLowerCase();
      const lines = (raw || '').split('\n').filter(l => l.toLowerCase().includes(q));
      return lines.length ? lines.join('\n') : '(未找到匹配的日志内容)';
    });

    function onLogScroll(e) {
      const el = e.target;
      if (!el) return;
      // 距底部 40px 以内视为处于底部，否则视为用户正在向上翻阅历史日志
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= 40;
      isUserAtBottom.value = atBottom;
    }

    function scrollToBottom(force = false) {
      nextTick(() => {
        if (logPreRef.value) {
          logPreRef.value.scrollTop = logPreRef.value.scrollHeight;
          if (force) {
            isUserAtBottom.value = true;
          }
        }
      });
    }

    function manualScrollToBottom() {
      scrollToBottom(true);
      ElMessage.success('已滑至底部');
    }

    function toggleAutoScroll() {
      autoScroll.value = !autoScroll.value;
      if (autoScroll.value) {
        scrollToBottom(true);
        ElMessage.success('已开启自动滑底');
      } else {
        ElMessage.info('已关闭自动滑底');
      }
    }

    async function api(url, options = {}) {
      options.headers = options.headers || {};
      const token = localStorage.getItem('mgr_token');
      if (token) {
        options.headers['Authorization'] = 'Bearer ' + token;
      }
      const r = await fetch(url, options);
      if (r.status === 401) {
        isLoggedIn.value = false;
        throw new Error('需要密码认证');
      }
      let d = {};
      try { d = await r.json(); } catch(e) {}
      if (!r.ok || d.error) throw new Error(d.error || ('HTTP ' + r.status));
      return d;
    }

    async function doLogin() {
      if (!loginPwd.value) {
        ElMessage.warning('请输入密码');
        return;
      }
      isLoggingIn.value = true;
      try {
        const res = await api('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: loginPwd.value })
        });
        if (res.token) {
          localStorage.setItem('mgr_token', res.token);
        }
        isLoggedIn.value = true;
        loginPwd.value = '';
        ElMessage.success('登录成功');
        await refresh(true);
      } catch(e) {
        ElMessage.error(e.message);
      } finally {
        isLoggingIn.value = false;
      }
    }

    async function doLogout() {
      localStorage.removeItem('mgr_token');
      isLoggedIn.value = false;
      try {
        await api('/api/logout', { method: 'POST' });
      } catch(e) {}
      ElMessage.info('已登出管理器');
    }

    async function refreshState(forceConfig = false) {
      const s = await api('/api/state');
      Object.assign(status, s.status || {});
      Object.assign(injector, s.injector || {});
      patches.value = s.patches || [];
      // 仅在首次加载或用户点击重置/保存成功后才同步服务端配置，避免轮询定时器覆盖正在编辑的表单
      if (s.config && (!configLoaded.value || forceConfig)) {
        Object.keys(s.config).forEach(k => {
          if (k === 'extra_args' && Array.isArray(s.config[k])) {
            config[k] = s.config[k].join(' ');
          } else {
            config[k] = s.config[k];
          }
        });
        configLoaded.value = true;
      }
    }

    async function resetConfig() {
      try {
        await refreshState(true);
        ElMessage.success('已重新从服务器读取配置');
      } catch(e) {
        ElMessage.error('读取配置失败: ' + e.message);
      }
    }

    async function refreshLogs() {
      let serverUpdated = false;
      let injectorUpdated = false;
      try {
        const l = await api('/api/logs?tail=' + tailLines.value);
        const newServer = l.content || '';
        if (newServer !== serverLog.value) {
          serverLog.value = newServer;
          serverUpdated = true;
        }
      } catch(e) {}
      try {
        const il = await api('/api/injector/logs?tail=' + tailLines.value);
        const newInjector = il.content || '';
        if (newInjector !== injectorLog.value) {
          injectorLog.value = newInjector;
          injectorUpdated = true;
        }
      } catch(e) {}

      const activeHasNew = activeLogTab.value === 'server' ? serverUpdated : injectorUpdated;
      // 仅在开启自动滑底、当前 Tab 确实有新日志、且用户当前处于底部（非向上翻看历史）时才滚动
      if (autoScroll.value && activeHasNew && isUserAtBottom.value) {
        scrollToBottom();
      }
    }

    async function refresh(forceConfig = false) {
      try {
        await refreshState(forceConfig);
        await refreshLogs();
        isLoggedIn.value = true;
      } catch(e) {
        // Handled in api()
      }
    }

    async function action(url, name) {
      try {
        await api(url, { method: 'POST' });
        ElMessage.success(`${name} 操作指令已执行`);
        await refresh();
      } catch(e) {
        ElMessage.error(e.message);
      }
    }

    async function saveConfig() {
      try {
        const payload = { ...config };
        if (typeof payload.extra_args === 'string') {
          payload.extra_args = payload.extra_args.trim() ? payload.extra_args.trim().split(/\s+/) : [];
        }
        await api('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        ElMessage.success('配置已保存 (重启服务器后生效)');
        await refresh(true);
      } catch(e) {
        ElMessage.error(e.message);
      }
    }

    async function togglePatch(p) {
      const op = p.active ? 'deactivate' : 'activate';
      try {
        await api('/api/patch/' + op, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: p.name })
        });
        ElMessage.success(`插件 ${p.name} 已${p.active ? '停用' : '启用'}`);
        await refresh();
      } catch(e) {
        ElMessage.error(e.message);
      }
    }

    async function openPatchEditor(p) {
      editingPatchName.value = p.name;
      editorContent.value = '正在加载源码...';
      showEditorDialog.value = true;
      try {
        const res = await api('/api/patch/content?name=' + encodeURIComponent(p.name));
        editorContent.value = res.content || '';
      } catch(e) {
        ElMessage.error('读取插件失败: ' + e.message);
      }
    }

    async function savePatchContent() {
      isSaving.value = true;
      try {
        await api('/api/patch/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: editingPatchName.value, content: editorContent.value })
        });
        ElMessage.success(`插件 ${editingPatchName.value} 保存成功`);
        await refresh();
        return true;
      } catch(e) {
        ElMessage.error('保存失败: ' + e.message);
        return false;
      } finally {
        isSaving.value = false;
      }
    }

    async function saveAndRestartInjector() {
      const ok = await savePatchContent();
      if (ok) {
        await action('/api/injector/restart', '重启注入器');
        showEditorDialog.value = false;
      }
    }

    function handlePluginUpload(file) {
      if (!file.name.toLowerCase().endsWith('.js')) {
        ElMessage.error('只允许上传 .js 格式的插件文件！');
        return false;
      }
      const reader = new FileReader();
      reader.onload = async (e) => {
        const text = e.target.result;
        try {
          await api('/api/patch/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: file.name, content: text })
          });
          ElMessage.success(`插件 ${file.name} 上传成功并已自动启用`);
          await refresh();
        } catch(err) {
          ElMessage.error('上传失败: ' + err.message);
        }
      };
      reader.readAsText(file);
      return false; // 阻止组件默认上传行为
    }

    function copyLogs() {
      const text = filteredLog.value;
      navigator.clipboard.writeText(text).then(() => {
        ElMessage.success('日志已复制到剪贴板');
      }).catch(() => {
        ElMessage.warning('请手动选择复制');
      });
    }

    function handleLogTabChange(tab) {
      if (tab === 'saved_logs') {
        fetchSavedLogs();
      } else {
        scrollToBottom(true);
      }
    }

    async function fetchSavedLogs() {
      try {
        const list = await api('/api/saved_logs');
        savedLogsList.value = list;
        if (!selectedSavedLog.value && list.length > 0) {
          selectedSavedLog.value = list[0].name;
          await doAnalyzeLog();
        }
      } catch(e) {
        console.error('获取历史日志列表失败', e);
      }
    }

    async function doAnalyzeLog() {
      if (!selectedSavedLog.value) {
        ElMessage.warning('请先选择日志文件');
        return;
      }
      isAnalyzing.value = true;
      try {
        const res = await api(`/api/saved_logs/analyze?file=${encodeURIComponent(selectedSavedLog.value)}`);
        analysisResult.value = res;
      } catch(e) {
        ElMessage.error('分析失败: ' + e.message);
      } finally {
        isAnalyzing.value = false;
      }
    }

    function copyAnalysisSummary() {
      if (!analysisResult.value || !analysisResult.value.summary_text) return;
      navigator.clipboard.writeText(analysisResult.value.summary_text).then(() => {
        ElMessage.success('分析摘要已复制到剪贴板');
      }).catch(() => {
        ElMessage.warning('请手动选择复制');
      });
    }

    async function doDeleteSavedLog() {
      if (!selectedSavedLog.value) return;
      try {
        await ElMessageBox.confirm(`确定要永久删除日志文件 ${selectedSavedLog.value} 吗？`, '删除确认', {
          type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消'
        });
        await api('/api/saved_logs/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: selectedSavedLog.value })
        });
        ElMessage.success('日志已删除');
        selectedSavedLog.value = '';
        analysisResult.value = null;
        await fetchSavedLogs();
      } catch(e) {
        if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message);
      }
    }

    onMounted(async () => {
      await refresh(true);
      setInterval(() => {
        if (isLoggedIn.value) {
          refresh(false);
        }
      }, 2500);
    });

    return {
      isLoggedIn, loginPwd, isLoggingIn,
      status, config, injector, patches,
      activeLogTab, serverLog, injectorLog, logFilter, filteredLog,
      tailLines, autoScroll, isLogCollapsed, isLogFullscreen, logPreRef,
      mapOptions, showEditorDialog, editingPatchName, editorContent, isSaving,
      savedLogsList, selectedSavedLog, isAnalyzing, analysisResult,
      VideoPlay, SwitchButton, Refresh, Cpu, RefreshRight, Check, Close, Search,
      ArrowUp, ArrowDown, FullScreen, ScaleToOriginal, CopyDocument, Bottom, CircleClose, Delete, Loading, User,
      Monitor, Setting, Document, Lightning, Files, Compass, Operation, Key, Select, CloseBold, Edit, Upload, DataAnalysis,
      doLogin, doLogout, refresh, action, saveConfig, resetConfig, togglePatch, openPatchEditor, savePatchContent, saveAndRestartInjector, handlePluginUpload, copyLogs, refreshLogs, scrollToBottom, manualScrollToBottom, toggleAutoScroll, onLogScroll,
      handleLogTabChange, fetchSavedLogs, doAnalyzeLog, copyAnalysisSummary, doDeleteSavedLog
    };
  }
});
app.use(ElementPlus, { locale: ElementPlusLocaleZhCn });
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}
app.mount('#app');
</script>
</body>
</html>'''


def handler_factory(manager: ServerManager, password: Optional[str] = None):
    _pwd_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
    _tokens = set()

    class ManagerHandler(BaseHTTPRequestHandler):
        server_version = "DreadHungerLinuxManager/" + APP_VERSION

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _is_authed(self) -> bool:
            if _pwd_hash is None:
                return True
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer ") and auth_header[7:].strip() in _tokens:
                return True
            cookie = self.headers.get("Cookie", "")
            return any(("mgr_token=" + token) in cookie for token in _tokens)

        def _require_auth(self) -> bool:
            if not self._is_authed():
                self.send_json({"error": "未认证，请先登录"}, 401)
                return False
            return True

        def _handle_login(self) -> None:
            body = self.body_json()
            if _pwd_hash is not None:
                pwd = str(body.get("password", ""))
                if not hmac.compare_digest(hashlib.sha256(pwd.encode()).hexdigest(), _pwd_hash):
                    self.send_json({"error": "密码错误"}, 401)
                    return
                token = secrets.token_urlsafe(32)
                _tokens.add(token)
            else:
                token = "open"
            self.send_response(200)
            self.send_header(
                "Set-Cookie",
                "mgr_token=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000" % token,
            )
            self.send_header("Content-Type", "application/json; charset=utf-8")
            data = json.dumps({"ok": True, "token": token}).encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _handle_logout(self) -> None:
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                _tokens.discard(auth_header[7:].strip())
            self.send_json({"ok": True, "result": "已登出"})

        def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, value: Any, status: int = 200) -> None:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_bytes(data, "application/json; charset=utf-8", status)

        def error(self, message: str, status: int = 400) -> None:
            self.send_json({"error": message}, status)

        def body_json(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    raise ManagerError("请求过大")
                value = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                raise ManagerError("JSON 请求无效: " + str(exc))
            if not isinstance(value, dict):
                raise ManagerError("请求必须是 JSON 对象")
            return value

        def do_GET(self) -> None:
            route = urlsplit(self.path)
            try:
                if route.path == "/":
                    self.send_bytes(html_page().encode("utf-8"), "text/html; charset=utf-8")
                    return
                if not self._require_auth():
                    return
                if route.path == "/api/state":
                    self.send_json(manager.state())
                elif route.path == "/api/logs":
                    query = parse_qs(route.query)
                    tail = int(query.get("tail", ["300"])[0])
                    requested = query.get("file", [None])[0]
                    self.send_json(manager.read_log(tail, requested))
                elif route.path == "/api/injector/status":
                    self.send_json(manager.injector_status())
                elif route.path == "/api/injector/logs":
                    query = parse_qs(route.query)
                    tail = int(query.get("tail", ["200"])[0])
                    self.send_json(manager.read_injector_log(tail))
                elif route.path == "/api/patch/content":
                    query = parse_qs(route.query)
                    name = query.get("name", [""])[0]
                    self.send_json(manager.get_patch_content(name))
                elif route.path == "/api/saved_logs":
                    self.send_json(manager.list_saved_logs())
                elif route.path == "/api/saved_logs/analyze":
                    query = parse_qs(route.query)
                    filename = query.get("file", [""])[0]
                    self.send_json(manager.analyze_saved_log(filename))
                else:
                    self.error("Not found", 404)
            except ManagerError as exc:
                self.error(str(exc))
            except Exception as exc:
                self.error("内部错误: " + str(exc), 500)

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            try:
                if route == "/api/login":
                    self._handle_login()
                    return
                if route == "/api/logout":
                    self._handle_logout()
                    return
                if not self._require_auth():
                    return
                if route == "/api/start":
                    result = manager.start()
                elif route == "/api/stop":
                    result = manager.stop()
                elif route == "/api/restart":
                    result = manager.restart()
                elif route == "/api/config":
                    result = manager.save_config(self.body_json())
                elif route == "/api/injector/restart":
                    result = manager.restart_injector()
                elif route == "/api/patch/activate":
                    result = manager.activate_patch(str(self.body_json().get("name", "")))
                elif route == "/api/patch/deactivate":
                    result = manager.deactivate_patch(str(self.body_json().get("name", "")))
                elif route == "/api/patch/save":
                    body = self.body_json()
                    result = manager.save_patch_content(
                        str(body.get("name", "")),
                        str(body.get("content", ""))
                    )
                elif route == "/api/patch/upload":
                    body = self.body_json()
                    result = manager.upload_patch(
                        str(body.get("filename", "")),
                        str(body.get("content", ""))
                    )
                elif route == "/api/saved_logs/delete":
                    body = self.body_json()
                    result = manager.delete_saved_log(str(body.get("filename", "")))
                else:
                    self.error("Not found", 404)
                    return
                self.send_json({"ok": True, "result": result})
            except ManagerError as exc:
                self.error(str(exc), 409)
            except Exception as exc:
                self.error("内部错误: " + str(exc), 500)

    return ManagerHandler


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dread Hunger Linux 独立开服器")
    parser.add_argument("--root", type=Path, help="LinuxServer 目录")
    parser.add_argument("--host", default="0.0.0.0", help="管理面板监听地址(默认 0.0.0.0 允许 IP 远程访问)")
    parser.add_argument("--web-port", type=int, default=8800, help="管理面板端口")
    parser.add_argument(
        "--password",
        default=os.environ.get("DH_MANAGER_PASSWORD"),
        help="管理面板密码；也可通过 DH_MANAGER_PASSWORD 环境变量设置",
    )
    parser.add_argument("--check", action="store_true", help="检查文件，不启动面板")
    args = parser.parse_args(argv)
    if not 1 <= args.web_port <= 65535:
        parser.error("--web-port 必须在 1-65535 范围内")

    try:
        root = discover_root(args.root)
        manager = ServerManager(root)
    except ManagerError as exc:
        parser.error(str(exc))

    if args.check:
        print(json.dumps(manager.check(), ensure_ascii=False, indent=2))
        return 0

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("警告：管理面板暴露在非本机地址，请使用防火墙或 SSH 隧道保护。")
    server = ThreadingHTTPServer((args.host, args.web_port), handler_factory(manager, args.password))
    print("Dread Hunger Linux 管理器 %s" % APP_VERSION)
    print("根目录: %s" % root)
    print("面板: http://%s:%d" % (args.host, args.web_port))
    print("认证: %s" % ("已启用(需密码登录)" if args.password else "未启用(无密码)"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n管理器退出，服务器进程保持运行。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
