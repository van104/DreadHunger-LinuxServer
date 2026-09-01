# Dread Hunger Linux GM 控制台 — 插件开发指南

> 基于 Frida 注入 `GM控制台_Linux.js`，与 `gm_console.py` Web 面板配合使用。
> 游戏二进制：`DreadHungerServer-Linux-Shipping`（2024-01-25，non-PIE ELF EXEC）

---

## 一、地址体系核心知识

游戏二进制是 **non-PIE ELF EXEC 类型**，符号地址是**绝对虚拟地址（VMA）**。

```
ELF base（frida mod.base）= 0x200000
.text 段起始 VMA = 0x20f4000
```

### 两种偏移来源，调用方式完全不同

| 来源 | 调用方式 | 说明 |
|---|---|---|
| 现有插件继承的偏移 | `base.add(RVA)` | RVA = 符号 VMA − 0x200000 |
| 从 nm / 符号表获取的新偏移 | `ptr('0xVMA')` | 符号 VMA 即为内存地址，直接用 |

**判断方法**：若 `base.add(VMA − 0x200000)` 读到的值与 `ptr('0xVMA')` 一致，两种方式等价。

```js
// 示例：GWorld — nm 报 VMA=0x5e9b6d0，RVA=0x5C9B6D0
// base.add(0x5C9B6D0) = 0x5e9b6d0 = 内存地址 ✓（RVA 风格）
// 示例：SetWinningTeam — nm 报 VMA=0x28c8920
// base.add(0x28c8920) = 0x2ac8920 ≠ 内存地址 ✗（必须用 ptr）
var GWorld = base.add(0x5C9B6D0);             // RVA 风格
var SetWinningTeam = new NativeFunction(ptr('0x28c8920'), ...); // 绝对 VMA
```

### 验证新地址的步骤

```bash
# 1. nm 查符号地址（VMA）
nm -C DreadHungerServer-Linux-Shipping.debug | grep 'FunctionName'

# 2. objdump 反汇编确认（文件 VMA 空间）
objdump -d --start-address=0xVMA --stop-address=0xVMA+0x80 \
  DreadHungerServer-Linux-Shipping

# 3. frida 运行时字节比对（验证内存地址）
// ptr('0xVMA').readByteArray(N) 的字节 应与 objdump 输出一致
```

**调试符号文件**：`DreadHungerServer-Linux-Shipping.debug`（1.5GB，not stripped），可直接用 nm / objdump 解析。

---

## 二、游戏对象与关键字段偏移

### 对象获取链

```
GWorld（全局指针）
  └─ UWorld
       └─ +0x118 : AuthorityGameMode  (AGameMode / ADH_GameMode)
            └─ +0x280 : GameState      (AGameState / ADH_GameState)
                 └─ +0x2A8 : Warship   (ADH_Warship)
```

```js
var GWorld = base.add(0x5C9B6D0);
var world  = GWorld.readPointer();
var gm     = world.add(0x118).readPointer();   // UWorld::AuthorityGameMode
var gs     = gm.add(0x280).readPointer();      // AGameMode::GameState
```

### ADH_GameState 字段

| 偏移 | 类型 | 说明 |
|---|---|---|
| `+0x238` | TArray | PlayerArray（`+0`=Data 指针，`+8`=Num 数量） |
| `+0x26C` | int32 | MatchState（枚举值） |
| `+0x2A8` | pointer | Warship（ADH_Warship*；`SetWarship` 写入位置） |
| `+0x2B0` | pointer | EscapeVolume（不能当作 Warship） |
| `+0x415` | byte | SetWinningTeam 内部检查标志位 |
| `+0x420` | int32 | SetWinningTeam 检查（==8 才调 OnRep） |
| `+0x514` | byte | **EPlayerTeam**（0=未设置，1=Explorer，2=Thrall） |

### ADH_GameMode 字段

| 偏移 | 类型 | 说明 |
|---|---|---|
| `+0x3E0` | pointer | GameState（ReadyToEndMatch_Implementation 读取） |

### APlayerController 字段

| 偏移 | 类型 | 说明 |
|---|---|---|
| `+0x250` | pointer | Pawn（Linux；ACharacter*，用于传送等位置操作） |

### ADH_Warship 字段

| 偏移 | 类型 | 说明 |
|---|---|---|
| `+0x0338` | pointer | ArmoryDoor（ADH_ArmoryDoor*） |
| `+0x03BC` | float | SpawnLocation.x |
| `+0x03C0` | float | SpawnLocation.y |
| `+0x03C4` | float | SpawnLocation.z |

> `SpawnLocation` 是战舰初始生成坐标，船移动后不能用于“传送回船”。当前实现优先调用 `ADH_Warship::BP_GetSkipperLocation()`，并以 `BP_Warship` 的动态 PlayerStart 世界坐标作为备用落点。

### ADH_ArmoryDoor 字段（待精确定位）

| 偏移 | 类型 | 说明 |
|---|---|---|
| `+0x03A8` | pointer | LockComponent（推测） |
| `+0x360~0x3A0` | byte | 可能含 bIsOpen（当前遍历写 1 尝试开门） |

---

## 三、已验证函数地址

### 绝对地址函数（`ptr` 调用）

| 符号 | 地址 | 签名 | 说明 |
|---|---|---|---|
| `ADH_GameState::SetWinningTeam` | `0x28c8920` | `void (ptr gs, i32 team, i32 reason)` | 设置获胜队伍，写 gs+0x514 |
| `ADH_GameMode::ReadyToEndMatch_Implementation` | `0x28c8ef0` | `bool (ptr gm)` | 检查 gs+0x514 != 0 |
| `ADH_GameState::OnRep_WinningTeam` | `0x28d1570` | `void (ptr gs)` | 获胜队伍复制通知 |
| `AGameMode::EndMatch` | `0x4535fc0` | `void (ptr gm)` | 直接调用客户端会崩 |
| `AActor::K2_SetActorLocation` | `0x42a0430` | `u8 (ptr actor, FVector value, u8 sweep, ptr hit, u8 teleport)` | Linux SysV ABI 下 FVector 按值传递 |
| `UObject::ProcessEvent` | `0x2e79900` | `void (ptr obj, ptr ufunc, ptr params)` | UE 反射调用 |

### RVA 风格函数（`base.add` 调用）

| 符号 | RVA | 绝对地址 | 签名 | 说明 |
|---|---|---|---|---|
| `FName::FName` | `0x2B130F0` | `0x2d130f0` | `void (ptr out, ptr str, i8 findType)` | 构造 FName |
| `FText::FromName` | `0x2A13190` | `0x2c13190` | `ptr (ptr fname)` | FName → FText |
| `ReceiveGameplayMsg` | `0x282B4B0` | `0x2a2b4b0` | `void (ptr ctrl, ptr msg, p0, p0, ptr title)` | 游戏内弹窗通知 |
| `ReceiveThrallMsg` | `0x282B610` | `0x2a2b610` | `void (ptr ctrl, ptr msg, ptr p0)` | 简单消息 |
| `AGameMode::Logout` | `0x43357F0` | `0x45357f0` | `void (ptr gm, ptr ctrl)` | 踢出玩家 |
| `APlayerState::GetPlayerName` | `0x459E030` | `0x479e030` | `void (ptr ps, ptr out_fstring)` | 获取玩家名 |
| `ADH_PlayerState::GetOwningController` | `0x277E4F0` | `0x297e4f0` | `ptr (ptr ps)` | 获取 PlayerState 的控制器 |
| `ADH_HumanCharacter::Revive` | `0x2693900` | `0x2893900` | `void (ptr pawn)` | 解除倒地状态 |
| `ADH_HumanCharacter::Died` | `0x269E8A0` | `0x289e8a0` | `void (ptr pawn, ptr instigator, ptr damageType, float damage)` | 执行完整死亡流程 |
| `ADH_PlayerState::SetIsDead` | `0x277EE70` | `0x297ee70` | `void (ptr ps, u8 dead)` | 修改死亡状态 |
| `AGameModeBase::RestartPlayer` | `0x433B4D0` | `0x453b4d0` | `void (ptr gm, ptr controller)` | 为死亡玩家重新生成 Pawn |
| `UDH_InventoryManager::AddInventory` | `0x270CA50` | `0x290ca50` | 短参数重载 | 向背包加入物品并返回实际数量 |
| `ADH_GameMode::HasMatchStarted` | `0x26C6160` | `0x28c6160` | `u8 (ptr gm)` | 验证是否已进入正式 Match |
| `ADH_RoleDealer::EndGame` | `0x2730050` | `0x2930050` | `void (ptr dealer, u8 immediate)` | 立即结束打牌并清理牌局 |
| `ADH_GameMode::RandomizeThralls` | `0x26CB250` | `0x28cb250` | `void (ptr gm)` | 按本局设置随机分配狼人 |
| `AGameMode::StartMatch` | `0x4335A40` | `0x4535a40` | `void (ptr gm)` | 进入正式 Match |

---

## 四、关键枚举值

### EPlayerTeam（gs+0x514）

| 值 | 阵营 |
|---|---|
| 0 | 未设置（默认 / 无获胜者） |
| 1 | **Explorer**（探险者 / 好人） |
| 2 | **Thrall**（叛徒 / 狼人） |

### EGameOverReason（SetWinningTeam 第三参数）

| 值 | 说明 |
|---|---|
| 1 | 原因 A（Explorer 相关） |
| 3 | 原因 B（Thrall 相关，游戏内部 `28c8960` 用此值） |
| 4 | 原因 C |

> 0 和 2 无对应结算文本处理（`28d12f0` 里跳过），会导致结算文本缺失。

---

## 五、开发要点

### 1. 结束游戏的标准模式

**不能**直接调 `AGameMode::EndMatch()`，会客户端崩溃。必须用 SetWinningTeam + ReadyToEndMatch hook：

```js
// ① 设置获胜队伍（写 gs+0x514）
var SetWinningTeam = new NativeFunction(
    ptr('0x28c8920'), 'void', ['pointer', 'int32', 'int32']
);
SetWinningTeam(gs, winner, reason);
// winner: 1=Explorer, 2=Thrall
// reason: 1 / 3 / 4（合法值，见枚举表）

// ② hook ReadyToEndMatch_Implementation 强制返回 true
//    游戏 Tick 检测到 true → 自然 EndMatch → WaitingPostMatch → 完整结算
var rtmImpl = ptr('0x28c8ef0');
var done = false;
Interceptor.attach(rtmImpl, {
    onEnter: function () {},
    onLeave: function (retval) {
        if (!done) {
            done = true;
            retval.replace(1);
            this.detach();
        }
    }
});
```

**原理**：`ReadyToEndMatch_Implementation` 检查 `gs+0x514 != 0`，返回 true 后游戏 `AGameMode::Tick` 走自然结算流程（与自然结束完全相同），客户端不会崩溃。

> **注意**：`SetWinningTeam` 有幂等检查（`gs+0x514 == winner` 时直接返回），但 winner=1 时 gs+0x514 默认为 0，不会触发幂等；只有同一局重复设置相同阵营时才幂等跳过。hook 强制返回 true 保证结算一定触发。

打牌阶段尚未进入正式 Match，`ReadyToEndMatch` 不会被 Tick 调用。此时结束游戏必须先执行与游戏原生流程一致的过渡：`RoleDealer::EndGame(true)` → `RandomizeThralls()` → 写入赛前完成标志 `GameMode+0x488` → `AGameMode::StartMatch()`；验证 Match 已开始后再设置获胜阵营并等待自然结算。

### 2. 消息发送

| 函数 | 效果 | 适用场景 |
|---|---|---|
| `ReceiveGameplayMsg` | 游戏内弹窗通知（标题 + 正文） | 全局广播 |
| `ReceiveThrallMsg` | 简单消息（可能带 Thrall 频道样式） | 点对点通知 |

```js
// 全局弹窗
ReceiveGameplayMsg(controller, makeFText('消息内容'), ptr(0), ptr(0), makeFText('标题'));
// 单人通知
ReceiveThrallMsg(controller, makeFText('[GM] 通知内容'), ptr(0));
```

### 3. 文件路径

游戏进程的 cwd 是 `DreadHunger/Binaries/Linux`，命令文件和玩家列表**必须用绝对路径**：

```js
var RuntimeDir     = DH_LINUX_ROOT + '/.gm_runtime';
var CommandFile    = RuntimeDir + '/gm_commands.json';
var PlayerListFile = RuntimeDir + '/gm_player_list.json';
var ResultDir       = RuntimeDir + '/gm_results';
```

### 4. 添加新功能

在 `ActionHandlers` 对象注册新 action 即可：

```js
var ActionHandlers = {
    'send_message':     gmSendMessage,
    'end_game':         gmEndGame,
    'open_armory':      gmOpenArmory,
    'kick_player':      gmKickPlayer,
    'revive_player':    gmRevivePlayer,
    'teleport_to_ship': gmTeleportToShip,
    'give_item':        gmGiveItem,
    'teleport_player':  gmTeleportPlayer,
    'execute_player':   gmExecutePlayer,
    'new_action':       gmNewAction   // ← 新增
};
```

对应 `gm_console.py` 面板端添加 API 端点和前端表单即可。

### GM HTTP API

所有接口沿用 GM 登录令牌认证：

| 方法 | 路径 | 请求体 / 返回值 |
|---|---|---|
| `GET` | `/api/gm/items` | 返回分类物品目录、风险标记和单次数量上限 |
| `GET` | `/api/gm/teleport_presets` | 返回持久化 XYZ 预设点位 |
| `POST` | `/api/gm/teleport_presets/save` | 新增或按同名覆盖预设点位 |
| `POST` | `/api/gm/teleport_presets/remove` | 删除指定名称的预设点位 |
| `POST` | `/api/gm/give_item` | `{"role":"Captain","item":"flintlock","quantity":5}` |
| `POST` | `/api/gm/teleport_player` | `{"player":"玩家名","x":100,"y":200,"z":300}`；继续兼容旧 `role` 参数 |
| `POST` | `/api/gm/execute_player` | `{"role":"Captain"}` |
| `POST` | `/api/gm/skip_poker` | `{}`；结束牌局、分配狼人并直接进入正式游戏 |

`revive_player` 和 `teleport_to_ship` 同时接受新的 `role` 与旧的 `player` 参数。原生成功返回 `200`，原生失败返回 `409`，3 秒内未收到 Frida 结果返回 `202 queued`。

---

## 六、功能改进建议

### 开启军械库（当前：遍历尝试，不精确）

**改进方案**：

- **方案 A（符号表）**：`nm -C` 查 `ADH_ArmoryDoor` 或 `ADH_DoorActor` 的 `OpenDoor` / `SetDoorOpen` / `bIsOpen` 相关函数，直接调用
- **方案 B（反射）**：遍历 ArmoryDoor 对象的 UClass → Children 找 `bIsOpen` / `IsLocked` 属性的精确偏移
- **方案 C（运行时 hook）**：hook ArmoryDoor 的 `OpenDoor` UFUNCTION，直接调用

### 其他可扩展功能

- **修改天气 / 时间**：操控 GameState 或 GameMode 中的天气 / 时间字段
- **设置无敌 / 无限弹药**：修改 Character 属性
- **查看详细玩家信息**：读取 PlayerState 的 HP、队伍、装备等字段

---

## 七、已知陷阱

| 陷阱 | 说明 |
|---|---|
| `base.add(绝对VMA)` | 多加 0x200000 调到错误地址，必须 `ptr('0xVMA')` |
| 直接调 `EndMatch()` | 跳过状态机同步，客户端崩溃 |
| EPlayerTeam 0/1 | 旧映射 winner=0（Explorer）SetWinningTeam 幂等返回不生效 |
| EGameOverReason 0/2 | 无对应结算文本，会导致结算显示异常 |
| `File.writeAllText` 不截断 | 写入前必须先 `unlink` 旧文件，否则 JSON 残留损坏 |
| CWD 非项目目录 | 文件路径必须用绝对路径 |
| 段偏移差异 | `.text` 段和 `.data/.bss` 段的 VMA 与文件偏移不同，nm 报的是运行时 VMA |
| `Interceptor.attach` 一次性 | hook 后 `detach` 保证只触发一次；多局结束需在每局重新安装 hook |

---

## 八、调试工具速查

### frida 一次性诊断脚本模板

```python
#!/usr/bin/env python3
import glob, json, sys, time, frida

def find_pid():
    for p in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            d = open(p, 'rb').read().replace(b'\x00', b' ')
        except OSError:
            continue
        if b'DreadHungerServer-Linux-Shipping' in d:
            return int(p.split('/')[2])
    return None

pid = find_pid()
if not pid:
    sys.exit(1)

JS = r"""
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');
var base = mod.base;
// 在这里写诊断逻辑，用 send() 返回结果
send({ base: base.toString() });
"""

session = frida.attach(pid)
script = session.create_script(JS)
msgs = []
script.on('message', lambda m, d: msgs.append(m))
script.load()
time.sleep(1)
session.detach()
print(json.dumps(msgs, indent=1))
```

### 常用 nm 查询

```bash
# 查单个函数
nm -C DreadHungerServer-Linux-Shipping.debug | grep 'SetWinningTeam'

# 查某类所有函数
nm -C DreadHungerServer-Linux-Shipping.debug | grep -E 'ADH_GameState::' | grep -v 'exec\|Z_Construct'

# 查全局变量
nm -C DreadHungerServer-Linux-Shipping.debug | grep -E ' (B|b) ' | grep 'GWorld'
```

### 管理器 API

```bash
# 启动服务器
curl -X POST http://127.0.0.1:8800/api/start

# 停止服务器
curl -X POST http://127.0.0.1:8800/api/stop

# 重启服务器
curl -X POST http://127.0.0.1:8800/api/restart

# 重启注入器（重载插件，无需重启游戏）
curl -X POST http://127.0.0.1:8800/api/injector/restart

# 查看服务器状态
curl http://127.0.0.1:8800/api/state
```

---

*文档版本：v1.3 | 2026-09-02 增加大厅立即结算和跳过打牌原生流程 | 游戏二进制日期：2024-01-25*
