# Docker 部署

适用于 Linux x86_64 服务器，需要 Docker Engine 和 Compose v2。容器内运行游戏服、Frida、开服器和 GM 控制台，复用现有程序。游戏仍需使用与插件匹配的 Finale 1.2.4 Linux 服务端。

## 首次启动

上传 `Docker/` 工具目录和上一级已有的 `Engine/`、`DreadHunger/`，保留以下结构。Compose 将上一级的游戏目录挂载到容器，本工具目录无需再复制一份游戏本体：

```text
LinuxServer/
├── Engine/
├── DreadHunger/Binaries/Linux/DreadHungerServer-Linux-Shipping
└── Docker/
    ├── compose.yaml
    ├── Dockerfile
    ├── docker_entrypoint.py
    ├── 开服器/
    ├── GM控制台/
    └── Linux 插件/
```

在该 Linux 服务器执行：

```bash
cd /你的路径/LinuxServer/Docker
cp .env.example .env
chmod 600 .env
nano .env
```

填写 `.env` 中的公网 IP/域名和两个不同的密码，密码至少 8 位。含 `$` 或 `#` 的密码请用单引号包围，例如 `DH_MANAGER_PASSWORD='你的密码'`。文件中未提供的配置沿用已有 `deploy_config.json`；环境变量会覆盖对应部署字段。游戏端口以已有 `开服器/manager_config.json` 中的 `server_port` 为准，`DH_GAME_PORT` 仅用于首次生成游戏配置。

迁移已有裸机服务时，先在原工具目录（上一级 `LinuxServer/`）运行 `./dhctl.sh stop` 停服，再回到 `Docker/` 执行：

```bash
docker compose up -d --build
docker compose logs -f --tail=100
```

不需要执行 `install.sh`。镜像在构建时安装 Python 和固定版本的 Frida；游戏文件、真实配置、密码、日志与黑名单不会进入构建上下文。`Docker/` 挂载到 `/server`，上一级的 `Engine/` 和 `DreadHunger/` 分别挂载到 `/server/Engine` 和 `/server/DreadHunger`，容器使用宿主机上的源码与游戏文件。升级时需同步工具文件并重新构建。本目录提供配置模板，首次启动生成独立配置；原裸机部署的密码、黑名单与运行记录未复制进来。

默认访问地址：

| 用途 | 地址 |
|---|---|
| 开服器 | `http://服务器IP:8800` |
| GM 控制台 | `http://服务器IP:9900` |
| 玩家进服 | `服务器IP:9100`（UDP） |

放行游戏 UDP 端口；管理 TCP 端口仅允许管理员 IP 访问。当前使用 Linux 主机网络，直接监听配置的端口，无需添加 `ports:` 映射；同一台宿主机上的其他服务不能占用相同端口。[Docker 主机网络说明](https://docs.docker.com/engine/network/drivers/host/)

## 日常操作

```bash
# 状态
docker compose exec server /opt/venv/bin/python3 dhctl.py status

# 重启整个容器
docker compose restart

# 停止并移除容器，目录中的数据保留
docker compose down

# 注入记录；两个 Web 面板的日志在 .runtime/manager.log 和 .runtime/gm.log
docker compose exec server tail -n 100 frida_loader.log
```

在开服器页面可继续停止、启动游戏或重启注入器。容器不会因管理员手动停服而重启；若开服器或 GM 进程退出，入口退出并交给 Docker 重启。`docker compose down` 会复用现有停服逻辑，先解除 Frida 注入，再停止游戏和面板。

配置、插件、黑名单、`.gm_runtime/`、`manager_logs/` 和 `.runtime/` 均保留在宿主机的 `LinuxServer/Docker/` 目录，游戏存档与日志保留在上一级 `DreadHunger/Saved/` 中。每个实例必须使用独立的工具目录、游戏目录和不同端口，不能让两个容器共享同一个目录。

## 注入与权限

Compose 添加 `SYS_PTRACE` 并采用 Frida 官方示例中的 `seccomp:unconfined`。没有共享宿主机 PID 命名空间；注入器只扫描本容器的进程。[Frida Docker 说明](https://frida.re/docs/examples/linux/)、[Docker 权限说明](https://docs.docker.com/engine/containers/run/)

入口和注入器以容器 root 运行，以便附加到游戏进程；游戏以容器内的 `dhgame`（UID 1000）运行。入口仅调整 `.gm_runtime/` 和 `DreadHunger/Saved/` 及其内容的所属用户，供游戏读写，不会递归修改整个项目。若提示游戏用户无法访问文件，检查容器中 `/server`、`DreadHunger/` 及其子目录的读取和遍历权限。

## 验收

启动后查看 `dhctl.py status`、`.runtime/`、`manager_logs/` 与 `frida_loader.log`，确认游戏没有立即退出、插件实际加载成功；随后在新对局测试玩家进入和一条 GM 指令，再执行一次容器重启和停止。

若日志提示缺少动态库，可在容器内执行 `ldd DreadHunger/Binaries/Linux/DreadHungerServer-Linux-Shipping` 定位缺失项，再补充对应系统包。Docker 无法替代游戏版本与插件偏移的匹配检查。

本次开发在 Windows 上完成，本机没有 Docker 或可用 WSL Linux 环境；单元测试与语法检查不代表镜像已构建或实服注入已通过。上线前需完成上述 Linux 实服验收。
