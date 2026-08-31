# Dread Hunger Linux Windows 远程工具

这里包含两个 Windows 原生客户端：

- `DreadHungerLinuxRemoteManager.exe`：启动、停止、重启 Linux 游戏服，配置游戏参数、管理插件和查看日志。
- `DreadHungerLinuxGMConsole.exe`：查看在线玩家，发送消息，执行复活、传送、踢人、开军械库和结束对局等 GM 操作；也可按在线玩家一键拉黑，自动记录 Steam/EOS ID，并使用预设或自定义理由。
- `DreadHungerQuickJoin.exe`：输入游戏服 `IP:端口`，通过客户端已有的 `connect_client_win64.js` 游戏线程命令队列完成直连，不加载 `C:\SGDH\dhpow.dll`，也不需要管理员权限。服务器满员或暂时断开时会在船上大厅恢复稳定后自动重试。新版提供最近 20 条服务器历史、选择/删除/清空、可配置的本地公告，以及进服前云端黑名单检查。发现当前大厅有黑名单玩家时，会先在本机左侧狼人消息通道显示玩家名、理由和 Steam ID，等待 5 秒再连接。默认客户端为 `E:\Dread Hunger\DreadHunger.exe`。

程序会检查客户端 `DreadHunger\Binaries\Win64\Patches\connect_client_win64.js`；缺失时从程序包自动补齐，并提示重启客户端一次。连接和公告都通过该脚本已有的游戏线程队列执行，不再安装单独的公告 Hook。

为避免客户端在启动或地图切换期间被重复连接，自动重试只会在新的船上大厅加载完成并稳定 5 秒后执行；服务器响应并开始加载 `Departure` 地图后立即暂停重试。每次点击进服最多自动显示一次公告，后续连接重试不会重复刷屏。

## 黑名单使用流程

1. 打开 Web GM 面板或 `DreadHungerLinuxGMConsole.exe`，进入“黑名单”页。
2. 从在线玩家列表选择玩家，选预设理由或填写自定义理由，点击“一键拉黑”。系统会从游戏登录日志自动补全该玩家的 Steam ID、EOS ID 和完整用户 ID；再次拉黑同一身份会更新原记录。
3. 在黑名单页复制“只读查询令牌”。打开 `DreadHungerQuickJoin.exe`，勾选“进服前检查云端黑名单”，填写 GM 端口（默认 `9900`）并粘贴令牌。
4. 点击进入服务器。游戏大厅上层先持续显示“正在进入游戏，检查黑名单中……”，进服器随后读取本机 Steam/EOS 身份并查询 Linux 实时大厅。当前账号或大厅内任意玩家命中时，提示更新为“发现黑名单用户：玩家名；理由：原因”并保持数秒，同时停止连接；全部未命中时显示“检测完成，未发现黑名单用户”，1 秒后连接。提示同时尝试发送到游戏自带狼人消息通道，并用不抢游戏焦点的本地悬浮层兜底，避免原消息动画过短、文字被裁切或看不到结果。

只读查询令牌只能调用黑名单检查接口，不能发送 GM 指令、查看管理数据或修改黑名单。请勿在进服器中填写 GM 管理密码。

客户端采用浅色高 DPI 界面。地址既可以拆分填写 IP 与端口，也可以直接在地址框填写 `服务器IP:8800`；显式写在地址中的端口优先。

## Linux 端启动

开服管理 API（默认端口 `8800`）：

```bash
python3 开服器/DreadHungerLinuxManager.py --root . --host 0.0.0.0 --web-port 8800 --password "请设置强密码"
```

GM API（示例端口 `9900`）：

```bash
python3 GM控制台/gm_console.py --root . --host 0.0.0.0 --port 9900 --password "请设置另一个强密码"
```

在云服务器安全组/防火墙中只向可信管理 IP 放行 TCP 8800 和 9900。更安全的做法是让服务只监听 `127.0.0.1`，然后在 Windows 建 SSH 隧道：

```powershell
ssh -N -L 8800:127.0.0.1:8800 -L 9900:127.0.0.1:9900 user@服务器IP
```

此时两个客户端均连接 `127.0.0.1`，端口分别填写 `8800`、`9900`。

## Windows 打包

在 PowerShell 中运行：

```powershell
python -m pip install pyinstaller
.\build_exe.ps1
```

生成文件位于 `dist`。客户端配置保存在 `%APPDATA%\DreadHungerRemote`；只有勾选“记住密码”时才会保存密码。当前配置文件为普通 JSON，不应在公用电脑上记住密码。

只打包快速进服器：

```powershell
.\build_quick_join.ps1
```
