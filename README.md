# Dread Hunger Linux Server Toolkit

**简体中文** | [English](README_EN.md)

这是一个面向 Linux Dread Hunger 恐惧饥荒（海上狼人杀）私服的管理工具包，包含：

- Linux Web 开服器：启动、停止、配置服务器和管理插件。
- Linux GM Web 控制台：查看玩家并执行 GM 指令。
- Frida 注入器与服务端插件。
- Windows 开服器客户端、GM 客户端和快速进服器。
- Linux 一键安装、启动、停止和状态检查脚本。

> 兼容性提示：当前插件内存偏移针对 Dread Hunger Finale 1.2.4 Linux 服务端构建。游戏二进制更新后必须重新核对偏移，不能直接注入未知版本。

## 部署要求

- 建议至少 4 GB 内存；内存较小时请配置 Swap，游戏服、两个 Web 服务和 Frida 会同时占用内存。
- 需要 Python 3.10+、`venv` 和 `pip`。缺少依赖时安装脚本会调用 `apt-get`、`dnf` 或 `yum`，因此需要 root 或可用的 `sudo`。
- 安装 Frida 需要访问 PyPI。国内网络可在运行安装脚本前设置标准的 `PIP_INDEX_URL` 镜像变量。
- 安装脚本只检查服务端目录和二进制是否存在，不校验游戏版本。启动前请人工确认服务端为 Finale 1.2.4；其他版本不要注入本仓库插件。

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

当安装程序以 root 运行且系统存在宝塔常用的 `www` 用户时，游戏和 Frida 会以 `www` 运行。安装程序会自动创建仅用于 GM 通信的 `.gm_runtime/` 可写目录，不会要求把整个项目目录交给 `www`。如果项目位于 `/root` 等 `www` 无法访问的父目录，安装会给出明确错误；请把项目移动到 `/opt`、`/srv` 或 `/www/wwwroot` 下再安装。

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

无人值守安装必须一次性提供以下全部变量；缺少任何一项时安装程序会列出缺失变量并退出：

```bash
DH_PUBLIC_HOST=服务器IP或域名 \
DH_BIND_HOST=0.0.0.0 \
DH_MANAGER_PORT=8800 \
DH_GM_PORT=9900 \
DH_GAME_PORT=9100 \
DH_MANAGER_PASSWORD='至少8位的管理密码' \
DH_GM_PASSWORD='另一个至少8位的GM密码' \
./install.sh
```

## 端口与 Windows 客户端

默认端口用途不同，不要混用：

| 用途 | 默认端口 | 协议 | Windows 工具填写内容 |
|---|---:|---|---|
| 开服管理 API | 8800 | TCP | `服务器IP:8800` + 开服器密码 |
| GM API | 9900 | TCP | `服务器IP:9900` + GM 密码 |
| 游戏服务端 | 9100 | UDP | 快速进服器填写 `服务器IP:9100` |

云服务器安全组、系统防火墙以及宝塔“安全”页面都要放行对应端口：游戏端口使用 UDP，管理和 GM 端口使用 TCP。管理端口 8800 和 9900 建议只允许管理员公网 IP 访问，不要向全网开放。

```bash
# Ubuntu/Debian 使用 ufw 的示例
sudo ufw allow 9100/udp
sudo ufw allow from 管理员公网IP to any port 8800 proto tcp
sudo ufw allow from 管理员公网IP to any port 9900 proto tcp

# CentOS/RHEL 使用 firewalld 的游戏端口示例
sudo firewall-cmd --permanent --add-port=9100/udp
sudo firewall-cmd --reload
```

开服器页面保存 `server_port` 后会自动同步 `deploy_config.json` 中的 `game_port`，`dhctl status` 和进服地址会使用实际游戏端口。升级自旧版后如两处端口不一致，请在开服器页面重新保存一次配置。

玩家从 GitHub Release 下载 `DreadHungerQuickJoin.exe`，输入安装完成时显示的游戏地址即可。快速进服器仍要求玩家电脑已经安装兼容的 `DHConnector.exe` 与 `dhpow.dll`，本项目不会分发这两个第三方组件。

## 插件修改与升级

- 注入器只在建立 Frida 会话时读取插件文件。新增、删除、改名或修改插件内容后，需要在开服器点击“重启注入器”，或等待本局结束后下一次注入，改动才会生效。
- 升级前先执行 `./dhctl.sh stop`，并备份 `deploy_config.json`、`开服器/manager_config.json`、GM 黑名单和自定义插件；替换程序文件后重新运行 `./install.sh`。
- 当前注入器按进程名查找游戏服，同一台机器不支持可靠运行多个实例。请避免同时启动多个服务端；否则即使端口不同，也可能注入到错误进程。

### 常驻山顶飞天甘油训练房间

多人训练插件现在会在首名玩家进入后，于 Unreal 游戏线程自动执行“结束打牌 → 分配狼人 → 开始正式对局”，不需要 GM 再手动点击跳过打牌。后续玩家由 `[服务端]随机职业Plus_Linux.js` 在 `HandleStartingNewPlayer` 中直接分配职业，加入已开始的对局后会被训练插件传送到山顶。

开服器的最大玩家输入范围已扩展到 1–64；将 `开服器/manager_config.json` 的 `maxplayers` 设置为 `64` 并重启服务端即可把 64 写入启动参数。64 是网络/房间容量上限，游戏原生职业池仍只有 8 个职业；超过 8 名玩家是否能被游戏版本接受，必须在目标服务器实测，插件不会伪造不存在的职业。

此改动不负责创建 Steam/EOS 公共会话。客户端联机大厅能否发现专用服取决于服务端构建的在线子系统和会话发布；若大厅不显示，仍需使用快速进服器或 IP 直连。要实现公共大厅发布，需要另行确认该 Finale 1.2.4 二进制的会话注册入口后再做原生 Hook，不能仅靠 `maxplayers` 参数保证。

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

## 许可证与禁止商业使用

本项目中有权授权的原创代码、文档及资源采用 **PolyForm Noncommercial License 1.0.0**。根目录 [LICENSE](LICENSE) 保留[官方英文条款](https://polyformproject.org/licenses/noncommercial/1.0.0)原文，并附本项目的 `Required Notice:` 版权声明。这是源码可用的非商业许可证，不是 OSI 定义的开源许可证。以下说明仅帮助理解，不增减或替代许可证条款。

- 允许非商业目的的使用、修改及依条款分发，包括无预期商业应用的个人学习、实验、私人娱乐和业余项目。
- 普通个人或公司利用本项目售卖工具、收费开服、销售 VIP、收费代搭建或广告变现，通常属于商业用途，不在一般非商业许可范围内；具体使用须结合完整条款判断，修改或编译不会自动获得商业授权。
- 官方条款明确允许慈善组织、教育机构、公共科研组织、公共安全或卫生组织、环保组织及政府机构使用，不受其资金来源或资助义务影响；不能把本许可证解释为对所有主体一概禁止商业使用。
- 分发任何部分时，须向接收者提供许可条款或其网址，以及许可人提供的全部 `Required Notice:` 声明。第三方材料仍须遵守其自身许可要求。
- 首次收到书面违规通知后，若在 32 天内完全合规并采取实际措施纠正以往违规，授权可以继续；否则按许可证的 Violations 条款终止。
- 捐赠、成本分摊及赞助等情形须按实际目的和完整条款判断，本说明不另设统一的允许或禁止规则。

游戏本体、Frida、Python 及其他第三方组件适用各自许可证，本项目不能替其授权。贡献者提交代码前应确认自己有权按本项目许可证授权，并保留第三方来源与许可信息。

**历史许可边界：** 提交 `78f6a37` 曾采用 MIT；`9648808` 将其改为非商业条款。本次变更不能撤回此前已经有效授出的 MIT 权利，也不能禁止他人依据旧许可证商业使用相应旧代码。后续新增内容不会自动获得旧 MIT 授权。版权归属及第三方授权仍需以实际来源为准，仓库内声明不等于完成权属审查。

## 安全说明

- 安装生成的 `deploy_config.json` 保存管理密码，权限会设置为 `600`，并已加入 `.gitignore`。
- 密码通过环境变量传给后台服务，不会出现在进程命令行或 GM 日志中。
- 不要提交 `.runtime/`、日志、`manager_config.json`、`gm_commands.json`、游戏二进制或插件备份。
- 对公网提供管理服务时，建议再使用云防火墙、VPN 或反向代理 HTTPS。
