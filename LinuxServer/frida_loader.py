#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frida 注入器: 把 Linux 插件(.js)注入 DreadHungerServer-Linux-Shipping
用法:
    python3 frida_loader.py --root /path/to/LinuxServer
加载目录: <root>/Linux 插件/*.js
服务器进程重启后自动重新注入。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path


def log(msg: str) -> None:
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def find_server_pid() -> int | None:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return None
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmdline = entry / "cmdline"
        try:
            data = cmdline.read_bytes()
        except OSError:
            continue
        if not data:
            continue
        text = data.replace(b"\x00", b" ").decode("utf-8", "replace")
        if "DreadHungerServer-Linux-Shipping" in text:
            return int(entry.name)
    return None


def get_process_uptime(pid: int) -> float:
    """获取目标进程已运行秒数"""
    try:
        stat_path = Path("/proc") / str(pid) / "stat"
        if not stat_path.is_file():
            return 9999.0
        with open(stat_path, "r", encoding="utf-8", errors="ignore") as f:
            parts = f.read().split()
        starttime_ticks = int(parts[21])
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_sec = float(f.read().split()[0])
        clk_tck = os.sysconf(os.sysconf_names.get('SC_CLK_TCK', 100)) if hasattr(os, 'sysconf') else 100
        proc_start_sec = starttime_ticks / clk_tck
        proc_uptime = max(0.0, uptime_sec - proc_start_sec)
        return proc_uptime
    except Exception:
        return 9999.0


def get_log_candidates(root_dir: Path, pid: int) -> List[Path]:
    log_candidates = [
        root_dir / "output.log",
        root_dir / "server.log",
        root_dir / "DreadHunger" / "Binaries" / "Linux" / "output.log",
        root_dir / "DreadHunger" / "Saved" / "Logs" / "DreadHunger.log",
        root_dir / "DreadHunger" / "Binaries" / "Linux" / "player.log",
    ]
    proc_fd_dir = Path("/proc") / str(pid) / "fd"
    if proc_fd_dir.is_dir():
        try:
            for fd_entry in proc_fd_dir.iterdir():
                try:
                    target = Path(os.readlink(str(fd_entry)))
                    if target.is_file() and target not in log_candidates:
                        if target.suffix in (".log", ".txt") or "output" in target.name or "player" in target.name or "server" in target.name:
                            log_candidates.append(target)
                except OSError:
                    continue
        except OSError:
            pass
    return log_candidates


def check_engine_ready(root_dir: Path, pid: int, since_offsets: Optional[Dict[Path, int]] = None) -> bool:
    """检查服务端日志中是否已出现虚幻引擎初始化完成的标志 (LogLoad: (Engine Initialization) Total time)"""
    log_candidates = get_log_candidates(root_dir, pid)
    for log_path in log_candidates:
        if not log_path.is_file():
            continue
        try:
            size = log_path.stat().st_size
            if since_offsets is not None and log_path in since_offsets:
                offset = max(0, since_offsets[log_path])
            else:
                offset = max(0, size - 150_000)
            if size <= offset:
                continue
            with open(log_path, "rb") as f:
                f.seek(offset)
                data = f.read().decode("utf-8", "replace")
            # 严格匹配引擎最终初始化完成的唯一官方标志
            if "LogLoad: (Engine Initialization)" in data:
                return True
        except OSError:
            continue
    return False


MATCH_END_MARKERS = (
    b"Match State Changed from InProgress to WaitingPostMatch",
    b"FPlatformMisc::RequestExit",
)


def capture_log_offsets(root_dir: Path, pid: int) -> Dict[Path, int]:
    """记录注入完成时的日志位置，避免把上一局的结算日志当成当前对局。"""
    offsets: Dict[Path, int] = {}
    for log_path in get_log_candidates(root_dir, pid):
        try:
            offsets[log_path] = log_path.stat().st_size
        except OSError:
            continue
    return offsets


def match_end_detected(root_dir: Path, pid: int, offsets: Dict[Path, int]) -> bool:
    """只读取注入后新增的日志；进入结算后尽快解除 Hook，避免卡在 CleanupWorld。"""
    for log_path in get_log_candidates(root_dir, pid):
        try:
            size = log_path.stat().st_size
        except OSError:
            continue

        previous = offsets.get(log_path)
        if previous is None:
            offsets[log_path] = size
            continue

        start = 0 if size < previous else previous
        # 异常日志爆量时只扫描最后 512 KiB，避免监控线程反过来制造 I/O 压力。
        start = max(start, size - 512 * 1024)
        offsets[log_path] = size
        if size <= start:
            continue
        try:
            with open(log_path, "rb") as log_file:
                log_file.seek(start)
                data = log_file.read(size - start)
        except OSError:
            continue
        if any(marker in data for marker in MATCH_END_MARKERS):
            return True
    return False


def wait_for_server_ready(root_dir: Path, pid: int, max_wait_sec: float = 25.0) -> None:
    """如果服务器已就绪则立即开始注入；否则实时监测日志标志，一旦就绪立即秒连注入"""
    uptime = get_process_uptime(pid)
    # 如果进程已稳定运行超过 15 秒，说明早已完成初始化，可直接秒注入
    if uptime >= 15.0 and check_engine_ready(root_dir, pid):
        log("服务器已就绪，开始注入插件...")
        return

    # 刚启动的服务器（运行时间 < 15 秒），记录当前日志偏移量，防止被上一局的历史旧日志误导
    log_candidates = get_log_candidates(root_dir, pid)
    start_offsets = {}
    for p in log_candidates:
        if p.is_file():
            try:
                start_offsets[p] = p.stat().st_size
            except OSError:
                pass

    log("服务器 PID %d 冷启动中，等待引擎就绪..." % pid)
    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        time.sleep(0.4)
        if find_server_pid() != pid:
            log("等待期间服务器进程已退出或变更")
            return
        if check_engine_ready(root_dir, pid, since_offsets=start_offsets):
            elapsed = time.time() - start_time
            log("引擎已就绪 (%.1f 秒)，开始注入插件..." % elapsed)
            time.sleep(1.5)  # 给首帧网络与地图对象 1.5 秒就绪缓冲，彻底避免 nullptr 崩溃
            return

    log("等待超时 (%d 秒)，将直接尝试连接注入..." % int(max_wait_sec))


def prepare_plugin_source(script_path: Path, root_dir: Path) -> str:
    source = script_path.read_text(encoding="utf-8")
    return "var DH_LINUX_ROOT = %s;\n%s" % (json.dumps(str(root_dir), ensure_ascii=False), source)


def load_plugins(root_dir: Path, plugins_dir: Path) -> None:
    waiting_for_server_logged = False
    while True:
        pid = find_server_pid()
        if pid is None:
            if not waiting_for_server_logged:
                log("等待服务器进程...")
                waiting_for_server_logged = True
            time.sleep(3)
            continue

        # 智能检测游戏引擎初始化状态: 已初始化立即注入，未完成则监听标志一出立即注入
        wait_for_server_ready(root_dir, pid, max_wait_sec=20.0)

        if find_server_pid() != pid:
            log("等待期间服务器已退出, 重新等待")
            continue
        try:
            import frida

            session = frida.attach(pid)
        except Exception as exc:
            log("attach 失败(%s), 3 秒后重试" % exc)
            time.sleep(3)
            continue

        # 每次建立 Frida 会话前重新扫描插件目录。
        script_paths = sorted(plugins_dir.glob("*.js"))
        if not script_paths:
            log("插件目录没有 .js 文件: %s" % plugins_dir)
            try:
                session.detach()
            except Exception:
                pass
            time.sleep(3)
            continue

        scripts = []
        failed = 0
        for script_path in script_paths:
            try:
                source = prepare_plugin_source(script_path, root_dir)
                script = session.create_script(source)
                script.on("message", lambda message, data, name=script_path.name: on_message(name, message, data))
                script.load()
                scripts.append((script_path.name, script))
            except Exception as exc:
                failed += 1
                log("插件失败(跳过): %s - %s" % (script_path.name, exc))
        if failed:
            log("有 %d 个插件注入失败, 其余插件继续运行" % failed)

        log("插件注入完成: %d/%d，正在监听..." % (len(scripts), len(script_paths)))
        log_offsets = capture_log_offsets(root_dir, pid)
        detach_for_match_end = False
        try:
            while find_server_pid() == pid:
                if match_end_detected(root_dir, pid, log_offsets):
                    detach_for_match_end = True
                    log("检测到对局结束，正在主动卸载插件并解除注入...")
                    break
                time.sleep(0.5)
        finally:
            for name, script in scripts:
                try:
                    script.unload()
                except Exception:
                    pass
            try:
                session.detach()
            except Exception:
                pass
        if detach_for_match_end:
            log("已解除注入，等待游戏进程完成退出...")
            # 不要在游戏自动退出前再次注入，否则会重新引入同一个清理死锁。
            while find_server_pid() == pid:
                time.sleep(0.5)
        log("服务器已退出, 注入器退出")
        return


def on_message(script_name: str, message: dict, data: bytes | None) -> None:
    level = message.get("type", "?")
    if level == "error":
        log("[%s] 错误: %s" % (script_name, message.get("stack", message.get("description", ""))))
    elif level == "send":
        log("[%s] %s" % (script_name, json.dumps(message.get("payload"), ensure_ascii=False)))
    else:
        log("[%s] %s" % (script_name, message))


def discover_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    for candidate in [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]:
        if (candidate / "Linux 插件").is_dir() or (candidate / "DreadHunger").is_dir():
            return candidate.resolve()
    return Path.cwd().resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dread Hunger Linux frida 注入器")
    parser.add_argument("--root", type=Path, default=None, help="LinuxServer 目录 (默认自动从当前目录和脚本目录查找)")
    parser.add_argument("--plugins-dir", type=Path, default=None, help="插件目录 (默认 <root>/Linux 插件)")
    parser.add_argument("--check", action="store_true", help="检查环境, 不启动注入")
    args = parser.parse_args()

    root = discover_root(args.root)
    plugins_dir = (args.plugins_dir.expanduser().resolve() if args.plugins_dir else None) or (root / "Linux 插件")
    if not plugins_dir.is_dir():
        print("错误: 插件目录不存在: %s" % plugins_dir)
        return 1

    paths = sorted(plugins_dir.glob("*.js"))
    if not paths:
        print("错误: 插件目录没有 .js 文件: %s" % plugins_dir)
        return 1

    if args.check:
        print("root:", root)
        print("plugins_dir:", plugins_dir)
        for p in paths:
            print("  -", p.name, p.stat().st_size)
        try:
            import frida
            print("frida 版本:", frida.__version__)
        except ImportError:
            print("frida 未安装: pip3 install frida")
            return 1
        pid = find_server_pid()
        print("服务器进程:", pid if pid else "未运行")
        return 0

    if not (root / "Linux 插件").is_dir() and plugins_dir != root / "Linux 插件":
        pass
    log("注入器已启动，发现 %d 个插件" % len(paths))

    while True:
        try:
            load_plugins(root, plugins_dir)
        except KeyboardInterrupt:
            log("注入器退出")
            return 0
        except Exception as exc:
            log("异常: %s, 5 秒后重试" % exc)
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
