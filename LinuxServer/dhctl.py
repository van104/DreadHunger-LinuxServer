#!/usr/bin/env python3
"""Start and stop the Linux manager, GM console, game server, and Frida injector."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "deploy_config.json"
RUNTIME_DIR = ROOT / ".runtime"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python3"
SERVER_BINARY = ROOT / "DreadHunger" / "Binaries" / "Linux" / "DreadHungerServer-Linux-Shipping"


class ControlError(RuntimeError):
    pass


def load_config() -> Dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ControlError("缺少 deploy_config.json，请先运行 ./install.sh") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ControlError("部署配置无法读取：%s" % exc) from exc
    if not isinstance(value, dict):
        raise ControlError("deploy_config.json 必须是 JSON 对象")

    required = ("public_host", "bind_host", "manager_port", "gm_port", "game_port", "manager_password", "gm_password")
    missing = [key for key in required if key not in value]
    if missing:
        raise ControlError("部署配置缺少字段：" + ", ".join(missing))
    for key in ("manager_port", "gm_port", "game_port"):
        try:
            value[key] = int(value[key])
        except (TypeError, ValueError) as exc:
            raise ControlError("%s 必须是端口数字" % key) from exc
        if not 1 <= value[key] <= 65535:
            raise ControlError("%s 必须在 1-65535 范围内" % key)
    manager_config = ROOT / "开服器" / "manager_config.json"
    try:
        manager_port = int(json.loads(manager_config.read_text(encoding="utf-8"))["server_port"])
        if 1 <= manager_port <= 65535:
            value["game_port"] = manager_port
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    if len({value["manager_port"], value["gm_port"], value["game_port"]}) != 3:
        raise ControlError("管理、GM、游戏端口不能重复")
    if len(str(value["manager_password"])) < 8 or len(str(value["gm_password"])) < 8:
        raise ControlError("管理密码和 GM 密码至少需要 8 个字符")
    return value


def python_executable() -> str:
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    raise ControlError("未找到 Linux Python 虚拟环境，请先运行 ./install.sh")


def pid_file(name: str) -> Path:
    return RUNTIME_DIR / (name + ".pid")


def log_file(name: str) -> Path:
    return RUNTIME_DIR / (name + ".log")


def process_matches(pid: int, marker: str) -> bool:
    if pid <= 0:
        return False
    cmdline = Path("/proc") / str(pid) / "cmdline"
    try:
        data = cmdline.read_bytes()
        return marker.encode("utf-8") in data
    except OSError:
        return False


def read_service_pid(name: str, marker: str) -> Optional[int]:
    path = pid_file(name)
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None
    if process_matches(pid, marker):
        return pid
    try:
        path.unlink()
    except OSError:
        pass
    return None


def start_service(name: str, marker: str, command: list[str], env: Dict[str, str]) -> int:
    existing = read_service_pid(name, marker)
    if existing is not None:
        return existing

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    output = log_file(name).open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        raise ControlError("%s 启动失败：%s" % (name, exc)) from exc
    finally:
        output.close()

    pid_file(name).write_text(str(process.pid) + "\n", encoding="ascii")
    time.sleep(0.3)
    if process.poll() is not None:
        raise ControlError("%s 启动后立即退出，请查看 %s" % (name, log_file(name)))
    return process.pid


def stop_service(name: str, marker: str) -> None:
    pid = read_service_pid(name, marker)
    if pid is None:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.time() + 5
    while time.time() < deadline and process_matches(pid, marker):
        time.sleep(0.1)
    if process_matches(pid, marker):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        pid_file(name).unlink()
    except OSError:
        pass


def wait_port(port: int, timeout: float = 12.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise ControlError("本机端口 %d 未在 %.0f 秒内就绪" % (port, timeout))


def api_request(port: int, path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, token: str = "") -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request("http://127.0.0.1:%d%s" % (port, path), data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read()
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            message = body.get("error", str(body)) if isinstance(body, dict) else str(body)
        except Exception:
            message = str(exc)
        raise ControlError("管理 API %s 失败：%s" % (path, message)) from exc
    except URLError as exc:
        raise ControlError("无法连接管理 API：%s" % exc.reason) from exc
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ControlError("管理 API 返回了无效 JSON") from exc


def manager_token(config: Dict[str, Any]) -> str:
    result = api_request(
        config["manager_port"],
        "/api/login",
        "POST",
        {"password": config["manager_password"]},
    )
    token = str(result.get("token", "")) if isinstance(result, dict) else ""
    if not token:
        raise ControlError("管理 API 登录成功但没有返回令牌")
    return token


def service_environment(config: Dict[str, Any]) -> Dict[str, str]:
    env = os.environ.copy()
    env["DH_MANAGER_PASSWORD"] = str(config["manager_password"])
    env["DH_GM_PASSWORD"] = str(config["gm_password"])
    return env


def print_access(config: Dict[str, Any], injector: Optional[Dict[str, Any]] = None) -> None:
    host = str(config["public_host"])
    print("\n启动完成")
    print("  开服器： http://%s:%d" % (host, config["manager_port"]))
    print("  GM控制台：http://%s:%d" % (host, config["gm_port"]))
    print("  游戏地址：%s:%d" % (host, config["game_port"]))
    if injector is not None:
        print("  注入器：  %s" % ("运行中" if injector.get("running") else "正在等待/未运行"))
    print("\n请让玩家下载配套的 DreadHungerQuickJoin.exe，并输入：")
    print("  %s:%d" % (host, config["game_port"]))


def start_all(config: Dict[str, Any]) -> None:
    if not SERVER_BINARY.is_file():
        raise ControlError("缺少游戏服务端文件：%s" % SERVER_BINARY)
    try:
        SERVER_BINARY.chmod(SERVER_BINARY.stat().st_mode | 0o755)
    except OSError as exc:
        raise ControlError("无法设置游戏服务端执行权限：%s" % exc) from exc

    python = python_executable()
    env = service_environment(config)
    start_service(
        "manager",
        "DreadHungerLinuxManager.py",
        [
            python,
            str(ROOT / "开服器" / "DreadHungerLinuxManager.py"),
            "--root",
            str(ROOT),
            "--host",
            str(config["bind_host"]),
            "--web-port",
            str(config["manager_port"]),
        ],
        env,
    )
    start_service(
        "gm",
        "gm_console.py",
        [
            python,
            str(ROOT / "GM控制台" / "gm_console.py"),
            "--root",
            str(ROOT),
            "--host",
            str(config["bind_host"]),
            "--port",
            str(config["gm_port"]),
        ],
        env,
    )

    wait_port(config["manager_port"])
    wait_port(config["gm_port"])
    token = manager_token(config)
    state = api_request(config["manager_port"], "/api/state", token=token)
    if not bool(state.get("running")):
        api_request(config["manager_port"], "/api/start", "POST", {}, token)
    injector = api_request(config["manager_port"], "/api/injector/status", token=token)
    print_access(config, injector if isinstance(injector, dict) else None)


def stop_all(config: Dict[str, Any]) -> None:
    if read_service_pid("manager", "DreadHungerLinuxManager.py") is not None:
        try:
            token = manager_token(config)
            api_request(config["manager_port"], "/api/stop", "POST", {}, token)
        except ControlError as exc:
            print("警告：无法通过管理 API 停服：%s" % exc, file=sys.stderr)
    stop_service("gm", "gm_console.py")
    stop_service("manager", "DreadHungerLinuxManager.py")
    print("开服器、GM 控制台、游戏服务端和注入器已停止。")


def show_status(config: Dict[str, Any]) -> None:
    manager_pid = read_service_pid("manager", "DreadHungerLinuxManager.py")
    gm_pid = read_service_pid("gm", "gm_console.py")
    print("开服器：%s" % ("运行中 (PID %d)" % manager_pid if manager_pid else "未运行"))
    print("GM控制台：%s" % ("运行中 (PID %d)" % gm_pid if gm_pid else "未运行"))
    if manager_pid:
        try:
            token = manager_token(config)
            state = api_request(config["manager_port"], "/api/state", token=token)
            injector = api_request(config["manager_port"], "/api/injector/status", token=token)
            print("游戏服务端：%s" % ("运行中" if state.get("running") else "未运行"))
            print("注入器：%s" % ("运行中" if injector.get("running") else "未运行"))
        except ControlError as exc:
            print("管理 API 状态读取失败：%s" % exc)
    print("玩家进服地址：%s:%d" % (config["public_host"], config["game_port"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dread Hunger Linux 一键控制器")
    parser.add_argument("command", choices=("start", "stop", "restart", "status"))
    args = parser.parse_args()
    try:
        config = load_config()
        if args.command == "start":
            start_all(config)
        elif args.command == "stop":
            stop_all(config)
        elif args.command == "restart":
            stop_all(config)
            time.sleep(0.5)
            start_all(config)
        else:
            show_status(config)
        return 0
    except ControlError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
