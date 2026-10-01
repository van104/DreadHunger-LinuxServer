# Dread Hunger 服务器 Docker 部署文档

适用于 Linux x86_64 服务器。容器内运行游戏服务端、Frida 注入器、开服器与 GM 控制台,复用宿主机上已有的游戏本体,不额外复制一份。

> 游戏本体需使用与插件匹配的 **Finale 1.2.4 Linux 服务端**。

已在以下环境验证通过:Docker `29.7.2`、Docker Compose `v5.4.0`、系统内核 `6.6.x`。

---

## 1. 前置要求

| 项目 | 要求 |
|---|---|
| 系统 | Linux x86_64 |
| Docker | Docker Engine(已验证 29.7.2) |
| Compose | Compose v2(`docker compose` 子命令,已验证 v5.4.0) |
| 磁盘 | 建议预留 5GB 以上 |
| 网络 | 构建时需能拉取 Docker Hub 与 PyPI |

检查是否就绪:

```bash
docker --version
docker compose version
docker info
```

---

## 2. 目录结构

上传 `Docker/` 工具目录,并与上一级已有的 `Engine/`、`DreadHunger/` 保持如下结构。**游戏本体保留在上一级,不要复制进 `Docker/`** —— Compose 会把上一级目录挂载进容器:

```text
LinuxServer/
├── Engine/
├── DreadHunger/Binaries/Linux/DreadHungerServer-Linux-Shipping
└── Docker/
    ├── compose.yaml
    ├── Dockerfile
    ├── .env.example
    ├── docker_entrypoint.py
    ├── frida_loader.py
    ├── 开服器/
    ├── GM控制台/
    └── Linux 插件/
```

> 本项目的目录名可能含空格(如 `Dread Hunger01`)。下文所有 `cd` 都**必须给路径加英文双引号**。

---

## 3. 部署步骤

### 从 GitHub 获取部署文件

Docker 部署文件已包含在 `main` 分支,可在 Linux 服务器获取:

```bash
git clone --depth 1 --branch main \
  https://github.com/van104/DreadHunger-LinuxServer.git "DreadHunger-LinuxServer"
cd "DreadHunger-LinuxServer/LinuxServer/Docker"
```

也可以从 [GitHub Releases](https://github.com/van104/DreadHunger-LinuxServer/releases) 下载含 Docker 的新版本 `DreadHunger-Linux-Toolkit.tar.gz` 并解压,进入包内的 `LinuxServer/Docker/`。旧版 Release 若没有该目录,请使用上述分支。

把匹配版本的游戏目录放到 `LinuxServer/Engine/` 和 `LinuxServer/DreadHunger/`,与 `Docker/` 平级。**需要上传完整的 `Docker/` 目录**,其中的 `frida_loader.py` 会由开服器自动启动。已有工具目录也可直接按下方步骤进入。

### 3.1 进入工具目录

```bash
cd "/www/wwwroot/Dread Hunger/LinuxServer/Docker"
```

### 3.2 准备配置文件

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

填写以下内容(**至少填前三项**):

```ini
# 公网 IP 或域名
DH_PUBLIC_HOST=你的公网IP或域名

# 两个密码必须不同,长度至少 8 位
DH_MANAGER_PASSWORD='manager-password-change-me'
DH_GM_PASSWORD='gm-password-change-me'

# 监听配置,一般保持默认
DH_BIND_HOST=0.0.0.0
DH_MANAGER_PORT=8800
DH_GM_PORT=9900
DH_GAME_PORT=9100
```

注意:

- **开服器密码与 GM 控制台密码必须不同**。若两者相同,容器会启动失败并不断重启(见 [第 7 节](#7-常见问题))。
- 密码含 `$`、`#` 等特殊字符时,用**单引号**包住整个值。
- `.env` 以明文保存密码,务必保持 `600` 权限(仅 root 可读)。
- `DH_GAME_PORT` 仅用于**首次**生成游戏配置;之后以开服器内保存的 `server_port` 为准。

### 3.3 构建镜像

```bash
docker compose build
```

- 首次构建会拉取 `python:3.11-slim-bookworm`,安装运行库并安装固定版本 Frida,通常需要数分钟(视网络速度,实测约 11 分钟)。
- **不需要**执行 `install.sh`。
- 游戏文件、真实配置、密码、日志与黑名单不会进入构建上下文。

### 3.4 启动服务

```bash
docker compose up -d
```

如需一步完成构建 + 启动,可合并执行:

```bash
docker compose up -d --build
```

### 3.5 验证部署

```bash
# 容器应为 Up
docker compose ps

# 查看启动日志,应出现「启动完成」并列出访问地址
docker compose logs --tail=50

# 容器内查看服务状态
docker compose exec server /opt/venv/bin/python3 dhctl.py status

# 宿主机确认端口已监听
ss -tulnp | grep -E ':(8800|9900|9100)'
```

正常启动后日志会输出开服器、GM 控制台、游戏地址与注入器状态。

---

## 4. 访问地址与端口

| 用途 | 地址 | 协议 |
|---|---|---|
| 开服器面板 | `http://服务器IP:8800` | TCP |
| GM 控制台 | `http://服务器IP:9900` | TCP |
| 玩家进服 | `服务器IP:9100` | UDP |

- 容器使用**主机网络**,直接监听上述端口,**无需**额外配置 `ports:` 映射。
- 请在防火墙/安全组**放行游戏 UDP 端口 9100**。
- 管理端口 **8800 / 9900 建议仅允许管理员 IP 访问**,不要对公网全开。
- 同一台宿主机上的其他服务不能占用这些端口。

---

## 5. 日常运维

```bash
# 查看服务状态
docker compose exec server /opt/venv/bin/python3 dhctl.py status

# 重启整个容器
docker compose restart

# 停止并移除容器(宿主机目录中的数据保留)
docker compose down

# 实时查看日志
docker compose logs -f --tail=100

# 查看 Frida 注入记录
docker compose exec server tail -n 100 frida_loader.log
```

两个 Web 面板日志分别位于 `.runtime/manager.log` 和 `.runtime/gm.log`。

说明:

- 在开服器页面可分别停止/启动游戏、重启注入器。
- 容器**不会**因管理员在面板手动停服而重启;若开服器或 GM 进程退出,入口会退出并由 Docker 重启。
- `docker compose down` 会复用停服逻辑:先解除 Frida 注入,再停止游戏与面板。
- 改过 `.env` 后需重建容器才生效:`docker compose up -d --force-recreate`。

---

## 6. 升级

升级时需同步更新 `Docker/` 下的工具文件,然后重新构建:

```bash
cd "/www/wwwroot/Dread Hunger01/LinuxServer/Docker"
docker compose up -d --build
```

---

## 7. 常见问题

### 7.1 容器不断重启

查看日志:

```bash
docker compose logs --tail=50
```

常见原因:

- **`开服器与 GM 控制台请使用不同密码`** —— 两个密码相同。修改 `.env` 中的 `DH_GM_PASSWORD`,再重建:
  ```bash
  docker compose up -d --force-recreate
  ```
- **`DH_PUBLIC_HOST 不能为空`** —— 未填写公网 IP/域名。
- **端口被占用** —— 宿主机上 8800/9900/9100 已被其他程序占用。

### 7.2 日志提示缺少动态库

在容器内定位缺失项:

```bash
docker compose exec server ldd DreadHunger/Binaries/Linux/DreadHungerServer-Linux-Shipping
```

再补充对应的系统包。

### 7.3 提示游戏用户无法访问文件

入口和注入器以容器 root 运行,游戏以容器内 `dhgame`(UID 1000)运行。若报权限错误,检查容器中 `/server`、`DreadHunger/` 及其子目录的读取与遍历权限。

### 7.4 注意

Docker 部署**无法替代**游戏版本与插件偏移的匹配检查。请确保使用与插件匹配的 Finale 1.2.4 服务端。

---

## 8. 数据、日志与备份

| 内容 | 位置 |
|---|---|
| 配置、插件、黑名单 | 宿主机 `LinuxServer/Docker/` |
| 运行记录 `.gm_runtime/`、`manager_logs/`、`.runtime/` | 宿主机 `LinuxServer/Docker/` |
| 游戏存档与日志 | 宿主机 `DreadHunger/Saved/` |

- 这些目录均保留在宿主机上,删除容器不会丢失数据。
- 首次启动会生成独立配置;若从原裸机部署迁移,原密码、黑名单与运行记录**不会**自动复制过来。
- 备份只需备份上述宿主机目录。
- **每个实例必须使用独立的工具目录、游戏目录和不同端口**,不能让两个容器共享同一目录。

---

## 9. 权限与安全

- Compose 为容器添加 `SYS_PTRACE` 并使用 `seccomp:unconfined`(Frida 注入所需)。
- 容器**不共享**宿主机 PID 命名空间,注入器只扫描本容器的进程。
- 入口仅调整 `.gm_runtime/` 和 `DreadHunger/Saved/` 及其内容的所属用户,不会递归修改整个项目。
- 妥善保管 `.env`(权限 600),不要在公网暴露管理面板端口。

---

## 10. 上线验收清单

- [ ] `docker compose ps` 显示容器 `Up`
- [ ] `dhctl.py status` 正常
- [ ] 日志出现「启动完成」,注入器状态为运行中
- [ ] `frida_loader.log` 确认插件**实际加载成功**(进程在跑 ≠ 插件生效)
- [ ] 新开一局,测试玩家能进入
- [ ] 在 GM 控制台执行一条指令
- [ ] 执行一次容器重启与停止,确认均正常
