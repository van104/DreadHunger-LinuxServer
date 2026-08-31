# Dread Hunger Linux Server Toolkit

这是一个面向 Linux Dread Hunger 私服的管理工具包，包含：

- Linux Web 开服器：启动、停止、配置服务器和管理插件。
- Linux GM Web 控制台：查看玩家并执行 GM 指令。
- Frida 注入器与服务端插件。
- Windows 开服器客户端、GM 客户端和快速进服器。
- Linux 一键安装、启动、停止和状态检查脚本。

> 兼容性提示：当前插件内存偏移针对 Dread Hunger Finale 1.2.4 Linux 服务端构建。游戏二进制更新后必须重新核对偏移，不能直接注入未知版本。

## 不包含的文件

仓库和 Release **不包含** Dread Hunger 游戏本体、Linux 服务端 `Engine/`、`DreadHunger/`、PAK、调试符号、`DHConnector.exe` 或 `dhpow.dll`。请使用你合法取得且版本匹配的文件。

完整 Linux 目录应当类似：

```text
LinuxServer/
├── Engine/                         # 用户自行提供
├── DreadHunger/                    # 用户自行提供
│   └── Binaries/Linux/
│       └── DreadHungerServer-Linux-Shipping
├── Linux 插件/
├── 开服器/
├── GM控制台/
├── install.sh
└── dhctl.sh
```

## Linux 一键部署

1. 从 GitHub Releases 下载 `DreadHunger-Linux-Toolkit.tar.gz` 并解压。
2. 把匹配版本的 `Engine/` 与 `DreadHunger/` 放入 `LinuxServer/`。
3. 在 Linux 服务器运行：

```bash
cd LinuxServer
chmod +x install.sh dhctl.sh
./install.sh
```

安装程序会：

1. 检查 Python 3.10+ 和完整游戏服务端文件。
2. 创建隔离的 `.venv` 并安装固定版本的 Frida。
3. 询问公网 IP/域名、三个端口及两个独立密码。
4. 启动开服器和 GM 控制台。
5. 通过开服器启动游戏服务端；开服器会自动启动 Frida 注入器。
6. 在终端显示 Windows 客户端和快速进服器需要填写的地址。

以后使用：

```bash
./dhctl.sh start
./dhctl.sh status
./dhctl.sh restart
./dhctl.sh stop
```

重新设置 IP、端口或密码：

```bash
DH_RECONFIGURE=1 ./install.sh
```

无人值守安装也可以提前设置 `DH_PUBLIC_HOST`、`DH_MANAGER_PORT`、`DH_GM_PORT`、`DH_GAME_PORT`、`DH_MANAGER_PASSWORD` 和 `DH_GM_PASSWORD`。

## 端口与 Windows 客户端

默认端口用途不同，不要混用：

| 用途 | 默认端口 | 协议 | Windows 工具填写内容 |
|---|---:|---|---|
| 开服管理 API | 8800 | TCP | `服务器IP:8800` + 开服器密码 |
| GM API | 9900 | TCP | `服务器IP:9900` + GM 密码 |
| 游戏服务端 | 9100 | UDP | 快速进服器填写 `服务器IP:9100` |

云服务器安全组必须放行游戏 UDP 端口。管理端口 8800 和 9900 建议只允许管理员公网 IP 访问，不要向全网开放。

玩家从 GitHub Release 下载 `DreadHungerQuickJoin.exe`，输入安装完成时显示的游戏地址即可。快速进服器仍要求玩家电脑已经安装兼容的 `DHConnector.exe` 与 `dhpow.dll`，本项目不会分发这两个第三方组件。

## 从源码构建 Windows EXE

在 Windows PowerShell 中运行：

```powershell
cd WindowsRemote
python -m pip install pyinstaller
.\build_exe.ps1
.\build_quick_join.ps1
```

生成结果位于 `WindowsRemote/dist/`。

## 创建 GitHub Release

仓库自带 `.github/workflows/release.yml`。推送 `v` 开头的版本标签后，GitHub Actions 会构建三个 Windows EXE、打包 Linux 工具包并上传到对应 Release：

```bash
git tag v1.0.0
git push origin v1.0.0
```

本项目自行编写的代码采用 MIT License，详见根目录 [LICENSE](LICENSE)。游戏本体及其他第三方组件不属于本许可证范围。

## 安全说明

- 安装生成的 `deploy_config.json` 保存管理密码，权限会设置为 `600`，并已加入 `.gitignore`。
- 密码通过环境变量传给后台服务，不会出现在进程命令行或 GM 日志中。
- 不要提交 `.runtime/`、日志、`manager_config.json`、`gm_commands.json`、游戏二进制或插件备份。
- 对公网提供管理服务时，建议再使用云防火墙、VPN 或反向代理 HTTPS。
