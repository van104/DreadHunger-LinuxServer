#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
VENV_DIR="$SCRIPT_DIR/.venv"
CONFIG_FILE="$SCRIPT_DIR/deploy_config.json"
SERVER_BINARY="$SCRIPT_DIR/DreadHunger/Binaries/Linux/DreadHungerServer-Linux-Shipping"
MANAGER_CONFIG="$SCRIPT_DIR/开服器/manager_config.json"
MANAGER_EXAMPLE="$SCRIPT_DIR/开服器/manager_config.example.json"
ANNOUNCE_CONFIG="$SCRIPT_DIR/GM控制台/gm_announce.json"
ANNOUNCE_EXAMPLE="$SCRIPT_DIR/GM控制台/gm_announce.example.json"

say() {
    printf '%s\n' "$*"
}

die() {
    printf '错误：%s\n' "$*" >&2
    exit 1
}

run_admin() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        die "需要安装系统依赖，但当前不是 root 且找不到 sudo"
    fi
}

install_python_packages() {
    if command -v apt-get >/dev/null 2>&1; then
        run_admin apt-get update
        run_admin apt-get install -y python3 python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        run_admin dnf install -y python3 python3-pip
    elif command -v yum >/dev/null 2>&1; then
        run_admin yum install -y python3 python3-pip
    else
        die "无法自动安装 Python；请手动安装 Python 3.10+、venv 和 pip"
    fi
}

python_ready() {
    command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

prompt_value() {
    local variable_name=$1
    local prompt_text=$2
    local default_value=$3
    local current_value=${!variable_name:-}
    local entered
    if [ -n "$current_value" ]; then
        return
    fi
    read -r -p "$prompt_text [$default_value]: " entered
    printf -v "$variable_name" '%s' "${entered:-$default_value}"
}

prompt_password() {
    local variable_name=$1
    local prompt_text=$2
    local current_value=${!variable_name:-}
    local entered
    while [ "${#current_value}" -lt 8 ]; do
        read -r -s -p "$prompt_text（至少8位）: " entered
        printf '\n'
        current_value=$entered
        if [ "${#current_value}" -lt 8 ]; then
            say "密码过短，请重新输入。"
        fi
    done
    printf -v "$variable_name" '%s' "$current_value"
}

valid_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

say "Dread Hunger Linux 一键部署"
say "安装目录：$SCRIPT_DIR"

[ -f "$SERVER_BINARY" ] || die "未找到 Linux 游戏服务端。请先把合法取得的 DreadHunger/ 与 Engine/ 放入 $SCRIPT_DIR"
[ -d "$SCRIPT_DIR/Engine" ] || die "未找到 Engine/ 目录，请先放入完整 Linux 游戏服务端文件"

if ! python_ready; then
    say "正在安装 Python 3、venv 与 pip..."
    install_python_packages
fi
python_ready || die "需要 Python 3.10 或更高版本"

if ! python3 -m venv "$VENV_DIR" >/dev/null 2>&1; then
    say "首次创建虚拟环境失败，尝试补装 venv..."
    install_python_packages
    python3 -m venv "$VENV_DIR"
fi

say "正在安装 Frida 运行依赖..."
"$VENV_DIR/bin/python3" -m pip install --disable-pip-version-check --upgrade pip
"$VENV_DIR/bin/python3" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements-linux.txt"

if [ -f "$CONFIG_FILE" ] && [ "${DH_RECONFIGURE:-0}" != "1" ]; then
    say "检测到已有 deploy_config.json，将保留现有密码和端口。"
else
    PUBLIC_HOST=${DH_PUBLIC_HOST:-}
    BIND_HOST=${DH_BIND_HOST:-}
    MANAGER_PORT=${DH_MANAGER_PORT:-}
    GM_PORT=${DH_GM_PORT:-}
    GAME_PORT=${DH_GAME_PORT:-}
    MANAGER_PASSWORD=${DH_MANAGER_PASSWORD:-}
    GM_PASSWORD=${DH_GM_PASSWORD:-}

    prompt_value PUBLIC_HOST "服务器公网 IP 或域名" "server.example.com"
    prompt_value BIND_HOST "管理服务监听地址" "0.0.0.0"
    prompt_value MANAGER_PORT "开服器端口" "8800"
    prompt_value GM_PORT "GM 控制台端口" "9900"
    prompt_value GAME_PORT "游戏端口（快速进服器填写此端口）" "9100"

    valid_port "$MANAGER_PORT" || die "开服器端口无效"
    valid_port "$GM_PORT" || die "GM 控制台端口无效"
    valid_port "$GAME_PORT" || die "游戏端口无效"
    [ "$MANAGER_PORT" != "$GM_PORT" ] && [ "$MANAGER_PORT" != "$GAME_PORT" ] && [ "$GM_PORT" != "$GAME_PORT" ] || die "三个端口不能重复"

    prompt_password MANAGER_PASSWORD "设置开服器密码"
    prompt_password GM_PASSWORD "设置 GM 控制台密码"
    [ "$MANAGER_PASSWORD" != "$GM_PASSWORD" ] || die "开服器与 GM 控制台请使用不同密码"

    export DH_INSTALL_PUBLIC_HOST="$PUBLIC_HOST"
    export DH_INSTALL_BIND_HOST="$BIND_HOST"
    export DH_INSTALL_MANAGER_PORT="$MANAGER_PORT"
    export DH_INSTALL_GM_PORT="$GM_PORT"
    export DH_INSTALL_GAME_PORT="$GAME_PORT"
    export DH_INSTALL_MANAGER_PASSWORD="$MANAGER_PASSWORD"
    export DH_INSTALL_GM_PASSWORD="$GM_PASSWORD"
    export DH_INSTALL_CONFIG_FILE="$CONFIG_FILE"

    "$VENV_DIR/bin/python3" - <<'PY'
import json
import os
from pathlib import Path

value = {
    "public_host": os.environ["DH_INSTALL_PUBLIC_HOST"],
    "bind_host": os.environ["DH_INSTALL_BIND_HOST"],
    "manager_port": int(os.environ["DH_INSTALL_MANAGER_PORT"]),
    "gm_port": int(os.environ["DH_INSTALL_GM_PORT"]),
    "game_port": int(os.environ["DH_INSTALL_GAME_PORT"]),
    "manager_password": os.environ["DH_INSTALL_MANAGER_PASSWORD"],
    "gm_password": os.environ["DH_INSTALL_GM_PASSWORD"],
}
path = Path(os.environ["DH_INSTALL_CONFIG_FILE"])
path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY
fi

export DH_INSTALL_DEPLOY_CONFIG="$CONFIG_FILE"
export DH_INSTALL_MANAGER_CONFIG="$MANAGER_CONFIG"
export DH_INSTALL_MANAGER_EXAMPLE="$MANAGER_EXAMPLE"
"$VENV_DIR/bin/python3" - <<'PY'
import json
import os
from pathlib import Path

deploy = json.loads(Path(os.environ["DH_INSTALL_DEPLOY_CONFIG"]).read_text(encoding="utf-8"))
target = Path(os.environ["DH_INSTALL_MANAGER_CONFIG"])
example = Path(os.environ["DH_INSTALL_MANAGER_EXAMPLE"])
source = target if target.is_file() else example
manager = json.loads(source.read_text(encoding="utf-8"))
manager["server_port"] = int(deploy["game_port"])
target.write_text(json.dumps(manager, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [ ! -f "$ANNOUNCE_CONFIG" ]; then
    cp "$ANNOUNCE_EXAMPLE" "$ANNOUNCE_CONFIG"
fi

chmod 700 "$SCRIPT_DIR/install.sh" "$SCRIPT_DIR/dhctl.sh"
chmod 755 "$SERVER_BINARY" "$SCRIPT_DIR/DreadHungerServer.sh"

say "依赖与配置安装完成，正在启动全部服务..."
"$SCRIPT_DIR/dhctl.sh" start

GAME_PORT=$("$VENV_DIR/bin/python3" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["game_port"])' "$CONFIG_FILE")
MANAGER_PORT=$("$VENV_DIR/bin/python3" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["manager_port"])' "$CONFIG_FILE")
GM_PORT=$("$VENV_DIR/bin/python3" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["gm_port"])' "$CONFIG_FILE")

say ""
say "还需要在云厂商安全组/防火墙放行："
say "  UDP $GAME_PORT（玩家进服）"
say "  TCP $MANAGER_PORT（Windows 开服器，建议只允许管理员 IP）"
say "  TCP $GM_PORT（Windows GM 控制台，建议只允许管理员 IP）"
say ""
say "以后使用：./dhctl.sh start|stop|restart|status"
