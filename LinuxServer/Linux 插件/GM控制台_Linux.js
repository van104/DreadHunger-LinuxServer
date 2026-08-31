/* GM控制台: Frida 插件端
 * 
 * 功能:
 *   1. 定时轮询 gm_commands.json 读取并执行 GM 指令
 *   2. 维护在线玩家列表 -> gm_player_list.json
 *
 * 指令格式 (gm_commands.json):
 *   { "commands": [ { "id": "uuid", "action": "end_game", "params": {...} }, ... ] }
 *
 * 配合 gm_console.py Web 面板使用。
 */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    /* ===== 配置 ===== */
    /* 注意: 游戏进程 cwd 是 DreadHunger/Binaries/Linux, 必须用绝对路径 */
    var CommandFile      = '/www/wwwroot/Dread Hunger/LinuxServer/gm_commands.json';
    var PlayerListFile   = '/www/wwwroot/Dread Hunger/LinuxServer/gm_player_list.json';
    var CommandPollMs    = 1000;
    var PlayerPollMs     = 3000;
    /* ================ */

    /* ── 游戏函数 (偏移量与现有 Linux 插件一致) ── */
    var FName_FName          = new NativeFunction(base.add(0x2B130F0), 'void',    ['pointer', 'pointer', 'int8']);
    var FText_FromName       = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var GetPlayerController  = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var ReceiveGameplayMsg   = new NativeFunction(base.add(0x282B4B0), 'void',    ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var ReceiveThrallMsg     = new NativeFunction(base.add(0x282B610), 'void',    ['pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var GameModeLogout       = new NativeFunction(base.add(0x43357F0), 'void',    ['pointer', 'pointer']);
    var K2_SetActorLocation  = new NativeFunction(base.add(0x2D6FA10), 'uint8',   ['pointer', 'pointer', 'uint8', 'pointer', 'uint8']);
    var ProcessEvent         = new NativeFunction(base.add(0x2C79C10), 'void',    ['pointer', 'pointer', 'pointer']);
    var GWorld               = base.add(0x5C9B6D0);

    /* ── 军械库密码豁免 Hook (同 Windows 插件 0xE73240，Linux 对应 0x278E6E0) ── */
    var gmArmoryUnlockedFlag = false;
    try {
        /* UDH_ArmoryLockComponent::HasCorrectCombination() const @ 0x278E6E0 */
        Interceptor.attach(base.add(0x278E6E0), {
            onLeave: function (retval) {
                if (gmArmoryUnlockedFlag) {
                    retval.replace(1);
                }
            }
        });
    } catch (eHook) {}

    /* ── 玩家生命与复活函数 ── */
    var ADH_HumanCharacter_Revive         = new NativeFunction(base.add(0x2693900), 'void', ['pointer']);
    var ADH_PlayerState_SetIsDead         = new NativeFunction(base.add(0x277EE70), 'void', ['pointer', 'uint8']);

    /* ── 文件 IO (frida File API + libc unlink 原子删除) ── */

    function readFileText(path) {
        try { return File.readAllText(path); } catch (e) { return null; }
    }

    function writeFileText(path, content) {
        try { File.writeAllText(path, content); return true; } catch (e) { return false; }
    }

    /* 扫描所有模块找 libc 导出 (此环境 Module.findExportByName(null,...) 不可用) */
    function findCExport(name) {
        var mods = Process.enumerateModules();
        for (var i = 0; i < mods.length; i++) {
            try {
                var p = mods[i].getExportByName(name);
                if (p) return p;
            } catch (e) {}
        }
        return null;
    }
    var _unlinkPtr = findCExport('unlink');
    var _unlink = _unlinkPtr ? new NativeFunction(_unlinkPtr, 'int', ['pointer']) : null;

    /* C 字符串安全分配 (避免 Memory.allocUtf8String GC bug) */
    function cstr(s) {
        var p = Memory.alloc(s.length + 1);
        p.writeUtf8String(s);
        return p;
    }

    /* 原子删除命令文件: unlink 是原子的, 不会与 gm_console.py 的 os.replace 拼接损坏 */
    function removeCommandFile() {
        try {
            if (_unlink) {
                var buf = cstr(CommandFile); /* 必须持有引用, 防止 GC 回收 */
                _unlink(buf);
            }
        } catch (e) {}
    }

    /* ── 辅助函数 ── */

    function newFName(text) {
        var buf = Memory.alloc(8);
        var str = Memory.alloc((text.length + 4) * 2);
        str.writeUtf16String(text);
        FName_FName(buf, str, 1);
        return buf;
    }

    function makeFText(text) {
        var out = Memory.alloc(24);
        FText_FromName(out, newFName(text));
        return out;
    }

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var size = fstring.add(8).readU32();
            if (size < 1 || size > 256 || data.isNull()) return null;
            var range = Process.findRangeByAddress(data);
            if (range === null || range.protection.indexOf('r') < 0) return null;
            return data.readUtf16String(size);
        } catch (e) { return null; }
    }

    /* 职业映射表 */
    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航'
    };

    function getRoleName(playerState) {
        try {
            var role = playerState.add(0x588).readPointer();
            if (role.isNull()) return '';
            var onlineName = readFString(role.add(0x48));
            if (!onlineName) return '';
            return RoleNames[onlineName] || onlineName;
        } catch (e) { return ''; }
    }

    function getPlayerName(playerState) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out) || '';
        } catch (e) { return ''; }
    }

    function getWorld() {
        try {
            var w = GWorld.readPointer();
            return w.isNull() ? null : w;
        } catch (e) { return null; }
    }

    function getGameMode() {
        try {
            var world = getWorld();
            if (!world) return null;
            var gm = world.add(0x118).readPointer();
            return gm.isNull() ? null : gm;
        } catch (e) { return null; }
    }

    function getGameState() {
        try {
            var gm = getGameMode();
            if (!gm) return null;
            var gs = gm.add(0x280).readPointer();
            return gs.isNull() ? null : gs;
        } catch (e) { return null; }
    }

    function getWarship() {
        try {
            var gs = getGameState();
            if (!gs) return null;
            /* ADH_GameStateBase::Warship at offset 0x2B0 */
            var warship = gs.add(0x2B0).readPointer();
            return warship.isNull() ? null : warship;
        } catch (e) { return null; }
    }

    /* 获取玩家列表: 返回 [{playerState, controller, name, role, isThrall, index}] */
    function getOnlinePlayers() {
        var result = [];
        try {
            var gs = getGameState();
            if (!gs) return result;
            var playerArray = gs.add(0x238);
            var num = playerArray.add(8).readU32();
            if (num < 1 || num > 64) return result;
            var data = playerArray.readPointer();
            if (data.isNull()) return result;

            for (var i = 0; i < num; i++) {
                var ps = data.add(i * 8).readPointer();
                if (ps.isNull()) continue;
                var name = getPlayerName(ps);
                var roleName = getRoleName(ps);
                /* ADH_PlayerState::bIsThrall，Linux ELF 偏移为 0x56A (Windows 偏移为 0x572) */
                var isThrall = ps.add(0x56A).readU8() !== 0;
                var controllerId = ps.add(0x224).readU8();
                var controller = GetPlayerController(ps, controllerId);
                result.push({
                    playerState: ps,
                    controller: controller,
                    name: name,
                    role: roleName || '',
                    isThrall: isThrall,
                    index: i
                });
            }
        } catch (e) {}
        return result;
    }

    /* 查找指定玩家 */
    function findPlayer(targetName) {
        var players = getOnlinePlayers();
        if (!targetName || targetName === '全部玩家' || targetName === 'all') return null;
        var lowerTarget = targetName.toLowerCase();
        for (var i = 0; i < players.length; i++) {
            if (players[i].name.toLowerCase() === lowerTarget) return players[i];
        }
        return null;
    }

    /* ── GM 操作实现 ── */

    /* 发送消息 */
    function gmSendMessage(params) {
        var text = params.message || '';
        if (!text) return { success: false, error: '消息为空' };

        var target = params.player || 'all';
        var msgText = makeFText(text);
        var titleText = makeFText(' ');

        if (target === 'all' || target === '全部玩家') {
            var players = getOnlinePlayers();
            var count = 0;
            for (var i = 0; i < players.length; i++) {
                try {
                    if (!players[i].controller.isNull()) {
                        ReceiveGameplayMsg(players[i].controller, msgText, ptr(0), ptr(0), titleText);
                        count++;
                    }
                } catch (e) {}
            }
            return { success: true, sent: count };
        } else {
            var p = findPlayer(target);
            if (!p) return { success: false, error: '未找到玩家: ' + target };
            if (p.controller.isNull()) return { success: false, error: '无法获取玩家控制器' };
            ReceiveGameplayMsg(p.controller, msgText, ptr(0), ptr(0), titleText);
            return { success: true, sent: 1 };
        }
    }

    /* 结束游戏: SetWinningTeam + hook ReadyToEndMatch (走游戏自然结算, 客户端不崩溃) */
    function gmEndGame(params) {
        var gm = getGameMode();
        var gs = getGameState();
        if (!gs || !gm) return { success: false, error: '无法获取 GameState/GameMode' };

        var team = params.team || 1;  /* 面板: 1=Explorers, 2=Thralls */
        try {
            /* ADH_GameState::SetWinningTeam(EPlayerTeam, EGameOverReason) @ 0x28c8920 (non-PIE 绝对地址)
             * EPlayerTeam: 1=Explorer, 2=Thrall; EGameOverReason 合法值 1/3/4 */
            var winner = team === 1 ? 1 : 2;
            var reason = team === 1 ? 1 : 3;
            var SetWinningTeam = new NativeFunction(ptr('0x28c8920'), 'void', ['pointer', 'int32', 'int32']);
            SetWinningTeam(gs, winner, reason);

            /* ADH_GameMode::ReadyToEndMatch_Implementation @ 0x28c8ef0: hook 强制返回 true
             * 游戏 Tick 检测到 ReadyToEndMatch=true -> 自然 EndMatch -> WaitingPostMatch
             * 完整结算(同自然结束), 客户端不会崩溃 */
            var listener = Interceptor.attach(ptr('0x28c8ef0'), {
                onEnter: function () {},
                onLeave: function (retval) {
                    if (!done) {
                        done = true;
                        retval.replace(1);
                        listener.detach();
                    }
                }
            });
            var done = false;

            return { success: true, team: team };
        } catch (e) {
            return { success: false, error: '结束游戏失败: ' + e };
        }
    }

    /* 开启军械库 */
    function gmOpenArmory(params) {
        /* 1. 设置军械库密码豁免标志: 引擎密码校验 HasCorrectCombination 永远返回 1
         * 与 Windows 插件 0xE73240 (开局开军械库.js) 原理完全相同，Linux 对应 0x278E6E0
         * 任何玩家转动密码轮或引擎判定时，自动触发原生开锁流程，绝不发生内存越界崩溃 */
        gmArmoryUnlockedFlag = true;

        /* 2. 广播消息通知 */
        gmSendMessage({ message: '军械库已开启', player: 'all' });

        return {
            success: true,
            opened: true,
            message: '成功开启军械库'
        };
    }

    /* 踢出玩家 */
    function gmKickPlayer(params) {
        var target = params.player;
        if (!target) return { success: false, error: '未指定玩家' };

        var p = findPlayer(target);
        if (!p) return { success: false, error: '未找到玩家: ' + target };
        if (p.controller.isNull()) return { success: false, error: '无法获取玩家控制器' };

        try {
            /* 先发通知 */
            var reason = params.reason || '被GM踢出';
            ReceiveThrallMsg(p.controller, makeFText('[GM] ' + reason), ptr(0));

            /* 延迟踢出, 让玩家看到消息 */
            setTimeout(function () {
                try {
                    var gm = getGameMode();
                    if (gm) {
                        GameModeLogout(gm, p.controller);
                    }
                } catch (e) {}
            }, 2000);

            return { success: true, kicked: target };
        } catch (e) {
            return { success: false, error: '踢出失败: ' + e };
        }
    }

    /* 复活玩家 */
    function gmRevivePlayer(params) {
        var target = params.player;
        if (!target) return { success: false, error: '未指定玩家' };

        var p = findPlayer(target);
        if (!p) return { success: false, error: '未找到玩家: ' + target };

        try {
            /* 1. 设置 PlayerState 的 bIsDead 为 false */
            try {
                ADH_PlayerState_SetIsDead(p.playerState, 0);
            } catch (e1) {}

            /* 2. 如果存在角色 Pawn，调用 ADH_HumanCharacter::Revive() */
            try {
                if (!p.controller.isNull()) {
                    var pawn = p.controller.add(0x258).readPointer();
                    if (!pawn.isNull()) {
                        ADH_HumanCharacter_Revive(pawn);
                    }
                }
            } catch (e2) {}

            /* 3. 通知 */
            if (!p.controller.isNull()) {
                ReceiveThrallMsg(p.controller, makeFText('[GM] 你已被复活'), ptr(0));
            }

            gmSendMessage({ message: '[GM] ' + p.name + ' 已被复活', player: 'all' });
            return { success: true, revived: target };
        } catch (e) {
            return { success: false, error: '复活失败: ' + e };
        }
    }

    /* 传送回船 */
    function gmTeleportToShip(params) {
        var target = params.player;
        if (!target) return { success: false, error: '未指定玩家' };

        var warship = getWarship();
        if (!warship) return { success: false, error: '无法获取战舰' };

        try {
            /* ADH_Warship::SpawnLocation at offset 0x03BC (FVector, 12 bytes) */
            var spawnX = warship.add(0x03BC).readFloat();
            var spawnY = warship.add(0x03C0).readFloat();
            var spawnZ = warship.add(0x03C4).readFloat();

            var doTeleport = function (player) {
                if (!player || player.controller.isNull()) return false;
                try {
                    /* 获取 Pawn */
                    var pawn = player.controller.add(0x258).readPointer();
                    if (pawn.isNull()) return false;

                    /* 构建 FVector */
                    var newLoc = Memory.alloc(12);
                    newLoc.writeFloat(spawnX);
                    newLoc.add(4).writeFloat(spawnY);
                    newLoc.add(8).writeFloat(spawnZ + 200); /* 稍高避免卡地形 */

                    var hitResult = Memory.alloc(256);

                    K2_SetActorLocation(pawn, newLoc, 0, hitResult, 1);
                    return true;
                } catch (e) { return false; }
            };

            if (target === 'all' || target === '全部玩家') {
                var players = getOnlinePlayers();
                var count = 0;
                for (var i = 0; i < players.length; i++) {
                    if (doTeleport(players[i])) count++;
                }
                gmSendMessage({ message: '[GM] 全部玩家已传送回船', player: 'all' });
                return { success: true, teleported: count };
            } else {
                var p = findPlayer(target);
                if (!p) return { success: false, error: '未找到玩家: ' + target };
                if (doTeleport(p)) {
                    if (!p.controller.isNull()) {
                        ReceiveThrallMsg(p.controller, makeFText('[GM] 你已被传送回船'), ptr(0));
                    }
                    return { success: true, teleported: 1 };
                }
                return { success: false, error: '传送失败' };
            }
        } catch (e) {
            return { success: false, error: '传送失败: ' + e };
        }
    }

    /* ── 指令分发 ── */

    var ActionHandlers = {
        'send_message':     gmSendMessage,
        'end_game':         gmEndGame,
        'open_armory':      gmOpenArmory,
        'kick_player':      gmKickPlayer,
        'revive_player':    gmRevivePlayer,
        'teleport_to_ship': gmTeleportToShip
    };

    /* ── 指令轮询 ── */

    function processCommands() {
        try {
            var text = readFileText(CommandFile);
            if (text === null) return;

            /* 原子删除命令文件(unlink), 防止与 gm_console.py 并发写冲突 */
            removeCommandFile();

            var data = null;
            try {
                data = JSON.parse(text);
            } catch (e) {
                /* 文件损坏(写入中断等), 已清空, 忽略本次 */
                return;
            }
            if (!data || !Array.isArray(data.commands)) return;

            for (var i = 0; i < data.commands.length; i++) {
                var cmd = data.commands[i];
                var handler = ActionHandlers[cmd.action];
                if (handler) {
                    try {
                        var result = handler(cmd.params || {});
                        send({
                            type: 'gm_result',
                            id: cmd.id || '',
                            action: cmd.action,
                            result: result
                        });
                    } catch (e) {
                        send({
                            type: 'gm_error',
                            id: cmd.id || '',
                            action: cmd.action,
                            error: String(e)
                        });
                    }
                } else {
                    send({
                        type: 'gm_error',
                        id: cmd.id || '',
                        action: cmd.action,
                        error: '未知操作: ' + cmd.action
                    });
                }
            }
        } catch (e) { send({type:'gm_debug', error:String(e), stack:e.stack||''}); }
    }

    /* ── 玩家列表更新 ── */

    function updatePlayerList() {
        try {
            var players = getOnlinePlayers();
            var list = [];
            for (var i = 0; i < players.length; i++) {
                /* 过滤已退出/控制器失效的玩家 (PlayerArray 移除有延迟) */
                if (players[i].controller.isNull()) continue;
                list.push({
                    name: players[i].name,
                    role: players[i].role || '',
                    index: players[i].index,
                    is_thrall: players[i].isThrall === true,
                    hasController: true
                });
            }
            var json = JSON.stringify({
                timestamp: Date.now(),
                count: list.length,
                players: list
            });
            /* 先删除旧文件再写入: File.writeAllText 对已存在文件不截断尾部, 会导致 JSON 残留损坏 */
            try {
                if (_unlink) {
                    var buf = cstr(PlayerListFile);
                    _unlink(buf);
                }
            } catch (e) {}
            writeFileText(PlayerListFile, json);
        } catch (e) {}
    }

    /* ── 启动 ── */

    setInterval(processCommands, CommandPollMs);
    setInterval(updatePlayerList, PlayerPollMs);

    /* 启动时立即更新一次玩家列表 */
    setTimeout(updatePlayerList, 500);

}
