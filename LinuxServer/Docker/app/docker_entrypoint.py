#!/usr/bin/env python3
"""Run the existing toolkit in the foreground for Docker."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import dhctl


def write_json(path: Path, value: dict, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.chmod(mode)
    temp.replace(path)


def prepare_config() -> dict:
    root = dhctl.ROOT
    if not dhctl.CONFIG_PATH.is_file():
        required = ("DH_PUBLIC_HOST", "DH_MANAGER_PASSWORD", "DH_GM_PASSWORD")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise dhctl.ControlError("首次 Docker 启动缺少环境变量：" + ", ".join(missing))
    templates = Path(__file__).resolve().parent.parent / "config"
    source = dhctl.CONFIG_PATH if dhctl.CONFIG_PATH.is_file() else templates / "deploy_config.example.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise dhctl.ControlError("部署配置必须是 JSON 对象")
    for key in ("public_host", "bind_host", "manager_port", "gm_port", "game_port", "manager_password", "gm_password"):
        env_name = "DH_" + key.upper()
        if env_name in os.environ:
            value[key] = os.environ[env_name]
    config = dhctl.load_config(value)
    if not str(config["public_host"]).strip():
        raise dhctl.ControlError("DH_PUBLIC_HOST 不能为空")
    if config["manager_password"] == config["gm_password"]:
        raise dhctl.ControlError("开服器与 GM 控制台请使用不同密码")
    write_json(dhctl.CONFIG_PATH, config, 0o600)

    manager_path = root / "开服器" / "manager_config.json"
    if not manager_path.is_file() and not (root / "manager_config.json").is_file():
        manager = json.loads((templates / "manager_config.example.json").read_text(encoding="utf-8"))
        manager["server_port"] = config["game_port"]
        write_json(manager_path, manager)
    announce = root / "GM控制台" / "gm_announce.json"
    if not announce.is_file():
        write_json(announce, json.loads((templates / "gm_announce.example.json").read_text(encoding="utf-8")))
    return config


def prepare_permissions() -> None:
    import pwd

    user = os.environ["DH_SERVER_USER"]
    account = pwd.getpwnam(user)
    for directory in (dhctl.ROOT / ".gm_runtime", dhctl.ROOT / "DreadHunger" / "Saved"):
        directory.mkdir(parents=True, exist_ok=True)
        for path in [directory, *directory.rglob("*")]:
            os.chown(path, account.pw_uid, account.pw_gid, follow_symlinks=False)
    runtime = dhctl.ROOT / ".gm_runtime"
    runtime.chmod(0o770)
    dhctl.SERVER_BINARY.chmod(dhctl.SERVER_BINARY.stat().st_mode | 0o755)
    for flag, path in (("-r", dhctl.SERVER_BINARY), ("-w", runtime)):
        result = subprocess.run(["runuser", "-u", user, "--", "test", flag, str(path)])
        if result.returncode:
            raise dhctl.ControlError("游戏用户无法访问 %s，请检查该文件及父目录权限" % path)


def run_foreground(config: dict) -> None:
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda signum, frame: stopping.set())
    try:
        dhctl.start_all(config)
        while not stopping.wait(1):
            for name, marker in (("manager", "DreadHungerLinuxManager.py"), ("gm", "gm_console.py")):
                if dhctl.read_service_pid(name, marker) is None:
                    raise dhctl.ControlError("%s 已退出，请查看 %s" % (name, dhctl.log_file(name)))
    finally:
        # Keep the existing order: detach Frida, then stop Unreal and the panels.
        dhctl.stop_all(config)


def main() -> int:
    try:
        if os.name != "posix" or os.geteuid() != 0:
            raise dhctl.ControlError("此入口应由 Linux Docker 容器以 root 启动；游戏进程会降权运行")
        if not dhctl.SERVER_BINARY.is_file() or not (dhctl.ROOT / "Engine").is_dir():
            raise dhctl.ControlError("请先将匹配版本的 DreadHunger/ 和 Engine/ 放入 LinuxServer/")
        launcher = dhctl.ROOT / "DreadHungerServer.sh"
        if not launcher.exists() and not launcher.is_symlink():
            launcher.symlink_to(Path(__file__).resolve().parents[1] / "DreadHungerServer.sh")
        config = prepare_config()
        prepare_permissions()
        run_foreground(config)
        return 0
    except (dhctl.ControlError, OSError, ValueError, KeyError) as exc:
        print("Docker 启动失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
