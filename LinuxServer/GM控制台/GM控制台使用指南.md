# Dread Hunger Linux GM 控制台 - 操作指南

## 一、文件说明

| 文件 | 位置 | 用途 |
|------|------|------|
| `gm_console.py` | LinuxServer/ | Web 面板服务，提供浏览器操作界面 |
| `GM控制台_Linux.js` | LinuxServer/Linux 插件/ | Frida 插件，在游戏进程内执行 GM 操作 |

运行时自动生成的文件：

| 文件 | 说明 |
|------|------|
| `gm_commands.json` | Web 面板写入的 GM 指令队列，Frida 读取后自动删除 |
| `gm_player_list.json` | Frida 插件维护的在线玩家列表，Web 面板读取展示 |
| `gm_blacklist.json` | 黑名单记录；保存姓名、完整用户 ID、Steam/EOS ID、理由和时间 |
| `gm_blacklist_check_token.txt` | 自动生成的只读查询令牌；供快速进服器检查大厅使用 |

---

## 二、部署步骤

### 1. 上传文件

将以下文件上传到 Linux 服务器对应目录：

```
LinuxServer/
├── gm_console.py                    ← 上传到这里
├── Linux 插件/
│   ├── GM控制台_Linux.js            ← 上传到这里
│   ├── 黑名单_Linux.js              (已有)
│   ├── 系统公告_Linux.js            (已有)
│   └── ...
├── frida_loader.py                  (已有)
├── DreadHungerLinuxManager.py       (已有)
└── DreadHungerServer.sh             (已有)
```

### 2. 启动游戏服务器

按你原来的方式启动游戏服务器（通过管理器或手动）。

### 3. 启动 Frida 注入器

如果你用的是 `DreadHungerLinuxManager.py`，点"重启注入器"即可。
`frida_loader.py` 会自动扫描 `Linux 插件/` 目录并注入 `GM控制台_Linux.js`。

手动启动：
```bash
python3 frida_loader.py --root /path/to/LinuxServer
```

看到以下日志说明 GM 插件加载成功：
```
[HH:MM:SS] 已注入: GM控制台_Linux.js
[HH:MM:SS] {"type":"gm_console","action":"loaded","message":"GM控制台插件已加载"}
```

### 4. 启动 GM 控制台

```bash
# 基本启动（默认密码 admin，端口 9900）
python3 gm_console.py

# 指定密码（强烈建议）
python3 gm_console.py --password 你的密码

# 完整参数
python3 gm_console.py --root /path/to/LinuxServer --host 0.0.0.0 --port 9900 --password MySecretPass
```

启动成功输出：
```
[GM控制台] Dread Hunger GM Console v1.0.0
[GM控制台] 根目录: /path/to/LinuxServer
[GM控制台] 面板: http://0.0.0.0:9900
[GM控制台] 密码: MySecretPass
```

### 5. 后台运行（推荐）

```bash
# 使用 nohup
nohup python3 gm_console.py --password 你的密码 > gm_console.log 2>&1 &

# 或使用 screen
screen -S gm
python3 gm_console.py --password 你的密码
# Ctrl+A D 分离
# screen -r gm 恢复
```

---

## 三、使用方法

### 1. 登录

浏览器打开 `http://你的服务器IP:9900`，输入密码登录。

### 2. 操作面板

左侧是操作列表和在线玩家，右侧是操作表单。

#### 发送消息
- 选择目标：`全部玩家` 或指定某个玩家
- 输入消息内容
- 点击"发送"
- 消息会以游戏内弹窗形式显示

#### 查看本局狼人
- 打开“查看狼人”页签，点击“查看本局狼人”
- 面板会读取当前服务端玩家的 `IsThrall` 阵营标记并列出狼人姓名和职业
- 结果默认隐藏，点击后才显示；可随时刷新或再次隐藏
- 如果尚未开局或阵营还未分配，列表会提示暂未检测到狼人

#### 结束游戏
- 选择获胜队伍：`探险者` 或 `叛徒`
- 点击"结束游戏"
- 会设置游戏胜利状态并全服广播

#### 开启军械库
- 直接点击"开启军械库"
- 会打开船上的军械库门并全服通知

#### 踢出玩家
- 从下拉框选择要踢出的玩家
- 可选填踢出原因
- 玩家会先收到通知，2 秒后断开连接

#### 复活玩家
- 选择要复活的玩家
- 点击"复活"

#### 传送回船
- 选择目标：`全部玩家` 或指定玩家
- 点击"传送"
- 玩家会被传送到战舰出生点上方

#### 黑名单管理
- 打开“黑名单”页，从在线玩家中选择目标
- 选择“死一次退、恶意摆烂、使用外挂”等预设理由，或填写自定义理由
- 点击“一键拉黑”；系统从当前游戏日志自动记录 Steam ID、EOS ID 和完整用户 ID
- 对同一身份再次操作会更新姓名和理由，不会生成重复记录
- 可在黑名单表中查看或移除记录
- 将页面上的“只读查询令牌”复制到快速进服器；该令牌只能检查当前大厅，不能执行 GM 操作

#### 独立黑名单管理中心
- 从 GM 控制台顶部或“黑名单”标签页点击“黑名单中心”进入，也可直接访问 `/blacklist`
- 独立页面完整显示所有历史档案，不受在线玩家列表影响
- 支持按玩家名、曾用名、Steam/EOS ID、理由搜索，并按违规分类筛选和排序
- 支持查看完整身份详情、复制 ID、修改显示名称与理由、移除记录
- 支持分页和导出当前筛选结果为 JSON，顶部提供总数、作弊类、消极行为和近 7 天更新统计
- 玩家离线后仍可编辑历史档案；Steam/EOS 身份不会因改名或编辑理由而改变

快速进服器点击进入后会先在游戏大厅显示“正在进入游戏，检查黑名单中……”至少 2.5 秒，再调用 `/api/blacklist/preflight`，同时核对本机 Steam/EOS 身份和目标服务器实时大厅。本人或大厅任意玩家命中时，游戏内使用“发现黑名单用户：玩家名；理由：原因”的单行格式并停止连接，避免大厅消息控件裁掉换行内容；全部未命中时显示检测完成，1 秒后连接。本机身份无法读取、名单过期或接口不可用时也会在游戏内提示并停止。

---

## 四、启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--root` | 当前目录 | LinuxServer 根目录路径 |
| `--host` | `0.0.0.0` | 监听地址，`0.0.0.0` 表示所有网卡 |
| `--port` | `9900` | Web 面板端口 |
| `--password` | `admin` | 登录密码 |

---

## 五、防火墙配置

确保服务器防火墙放行 9900 端口：

```bash
# iptables
iptables -A INPUT -p tcp --dport 9900 -j ACCEPT

# firewalld
firewall-cmd --add-port=9900/tcp --permanent
firewall-cmd --reload

# ufw
ufw allow 9900/tcp
```

如果是云服务器，还需要在云控制台的安全组中放行 9900 端口。

---

## 六、注意事项

1. **启动顺序**：先启动游戏服务器 → 再启动 Frida 注入器 → 最后启动 GM 控制台
2. **密码安全**：默认密码是 `admin`，生产环境务必修改
3. **偏移量版本**：GM 插件中的内存偏移量与现有 Linux 插件一致。如果游戏更新导致偏移变化，需要同步更新 `GM控制台_Linux.js` 中的地址
4. **端口冲突**：9900 端口不能被其他服务占用。管理器默认用 8800，游戏默认用 9100，不会冲突
5. **多次执行**：指令是一次性的，Frida 读取 `gm_commands.json` 后会立即删除文件，不会重复执行

---

## 七、故障排查

| 问题 | 排查方法 |
|------|----------|
| 面板打不开 | 检查端口 9900 是否被防火墙拦截；检查 `gm_console.py` 是否在运行 |
| 登录后显示空白 | 清浏览器缓存，或换浏览器试试 |
| 在线玩家显示 0 | 检查 Frida 注入器是否正常运行；检查注入器日志有没有报错 |
| 操作没有效果 | 查看 `frida_loader.log` 中 GM 插件的输出；确认游戏服务器正在运行 |
| "指令已发送"但没反应 | 说明 Web 面板写入成功但 Frida 没读取，检查注入器是否正常加载了 `GM控制台_Linux.js` |
