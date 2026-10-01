#!/usr/bin/env python3
"""Move an old Docker deployment's state into data/ without overwriting files."""

from pathlib import Path


def migrate(root: Path) -> int:
    root = root.resolve()
    state = [
        ".runtime", ".gm_runtime", ".manager_backups", "manager_logs", "Patches",
        "deploy_config.json", "manager_config.json", "gm_blacklist.json",
        "gm_blacklist_check_token.txt", "gm_teleport_presets.json", "gm_winning_card_reward.json",
        "gm_commands.json", "frida_loader.log", "gm_console.log", "server.log", "output.log",
        "开服器/manager_config.json", "开服器/.dread_hunger_manager_state.json",
        "GM控制台/gm_announce.json", "GM控制台/gm_blacklist_check_token.txt",
    ]
    programs = [
        "开服器", "GM控制台", "Linux 插件", "dhctl.py", "frida_loader.py",
        "docker_entrypoint.py", "deploy_config.example.json", "Docker部署文档.md",
    ]
    moves = [(root / name, root / "data" / name) for name in state]
    moves += [(root / name, root / "legacy" / name) for name in programs]
    moves += [(path, root / "legacy" / path.name) for path in root.glob(".env.bak.*")]
    moves = [(source, target) for source, target in moves if source.exists() or source.is_symlink()]
    for source, target in moves:
        if not source.resolve().is_relative_to(root) or not target.resolve().is_relative_to(root):
            raise ValueError("目录超出部署根目录：" + str(source))
        if target.exists() or target.is_symlink():
            raise FileExistsError("目标已存在，未覆盖任何文件：" + str(target))
    for source, target in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    return len(moves)


if __name__ == "__main__":
    print("请先执行 docker compose down；此脚本保留 .env、游戏本体和新 app/ 目录。")
    try:
        count = migrate(Path(__file__).resolve().parent)
    except (OSError, ValueError) as exc:
        raise SystemExit("迁移失败：" + str(exc))
    print("已迁移 %d 项；旧程序保留在 legacy/，自定义插件可从中合并。" % count)
