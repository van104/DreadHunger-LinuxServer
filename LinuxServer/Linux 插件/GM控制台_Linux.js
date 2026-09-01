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
    /* DH_LINUX_ROOT 由 frida_loader.py 根据实际安装目录注入 */
    var RuntimeDir       = DH_LINUX_ROOT + '/.gm_runtime';
    var CommandFile      = RuntimeDir + '/gm_commands.json';
    var PlayerListFile   = RuntimeDir + '/gm_player_list.json';
    var ResultDir        = RuntimeDir + '/gm_results';
    var CommandPollMs    = 1000;
    var PlayerPollMs     = 1000;
    /* ================ */

    /* ── 游戏函数 (偏移量与现有 Linux 插件一致) ── */
    var FName_FName          = new NativeFunction(base.add(0x2B130F0), 'void',    ['pointer', 'pointer', 'int8']);
    var FText_FromName       = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveGameplayMsg   = new NativeFunction(base.add(0x282B4B0), 'void',    ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var ReceiveThrallMsg     = new NativeFunction(base.add(0x282B610), 'void',    ['pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var GameModeLogout       = new NativeFunction(base.add(0x43357F0), 'void',    ['pointer', 'pointer']);
    /* FVector 在 Linux SysV ABI 下按值传递，不能传 FVector 指针。 */
    var K2_SetActorLocation  = new NativeFunction(base.add(0x40A0430), 'uint8',   ['pointer', ['float', 'float', 'float'], 'uint8', 'pointer', 'uint8']);
    var ADH_Warship_BP_GetSkipperLocation = new NativeFunction(base.add(0x284FEA0), ['float', 'float', 'float'], ['pointer']);
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
    var ADH_HumanCharacter_Died           = new NativeFunction(base.add(0x269E8A0), 'void', ['pointer', 'pointer', 'pointer', 'float']);
    var ADH_PlayerState_SetIsDead         = new NativeFunction(base.add(0x277EE70), 'void', ['pointer', 'uint8']);
    var AGameModeBase_RestartPlayer       = new NativeFunction(base.add(0x433B4D0), 'void', ['pointer', 'pointer']);
    var UClass_GetPrivateStaticClass      = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var StaticFindObject                  = new NativeFunction(base.add(0x2C95CA0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8']);
    var StaticLoadObject                  = new NativeFunction(base.add(0x2C97F00), 'pointer', ['pointer', 'pointer', 'pointer', 'pointer', 'uint32', 'pointer', 'uint8', 'pointer']);
    var UDH_InventoryManager_AddInventory = new NativeFunction(base.add(0x270CA50), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'uint8', 'pointer']);

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

    function writeCommandResult(cmd, result) {
        var id = String(cmd.id || '');
        if (!/^[0-9a-fA-F-]{8,64}$/.test(id)) return false;
        return writeFileText(ResultDir + '/' + id + '.json', JSON.stringify({
            id: id,
            action: cmd.action || '',
            timestamp: Date.now(),
            result: result
        }));
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

    function getRoleInfo(playerState) {
        try {
            var role = playerState.add(0x588).readPointer();
            if (role.isNull()) return { id: '', name: '' };
            var onlineName = readFString(role.add(0x48));
            if (!onlineName) return { id: '', name: '' };
            return { id: onlineName, name: RoleNames[onlineName] || onlineName };
        } catch (e) { return { id: '', name: '' }; }
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
            /* ADH_GameStateBase::SetWarship 写入 +0x2A8；+0x2B0 是 EscapeVolume。 */
            var warship = gs.add(0x2A8).readPointer();
            return warship.isNull() ? null : warship;
        } catch (e) { return null; }
    }

    function getPawn(controller) {
        try {
            if (!controller || controller.isNull()) return null;
            var pawn = controller.add(0x250).readPointer();
            return pawn.isNull() ? null : pawn;
        } catch (e) { return null; }
    }

    function getPlayerLocation(player) {
        try {
            var pawn = getPawn(player.controller);
            if (!pawn) return null;
            var root = pawn.add(0x130).readPointer();
            if (root.isNull()) return null;
            var x = root.add(0x1D0).readFloat();
            var y = root.add(0x1D4).readFloat();
            var z = root.add(0x1D8).readFloat();
            if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
            return { x: x, y: y, z: z };
        } catch (e) { return null; }
    }

    function getSceneLocation(component) {
        try {
            if (!component || component.isNull()) return null;
            var x = component.add(0x1D0).readFloat();
            var y = component.add(0x1D4).readFloat();
            var z = component.add(0x1D8).readFloat();
            if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
            return { x: x, y: y, z: z };
        } catch (e) { return null; }
    }

    function isNearShip(location, shipLocation) {
        if (!location || !shipLocation) return false;
        var dx = location.x - shipLocation.x;
        var dy = location.y - shipLocation.y;
        var dz = location.z - shipLocation.z;
        return dx * dx + dy * dy + dz * dz <= 10000 * 10000;
    }

    function getShipReturnLocations(warship) {
        var locations = [];
        var root = null;
        try { root = warship.add(0x130).readPointer(); } catch (e) {}
        var shipLocation = getSceneLocation(root);

        try {
            var skipper = ADH_Warship_BP_GetSkipperLocation(warship);
            var skipperLocation = { x: Number(skipper[0]), y: Number(skipper[1]), z: Number(skipper[2]) + 100 };
            if (isNearShip(skipperLocation, shipLocation)) locations.push(skipperLocation);
        } catch (e) {}

        /* BP_Warship 的 8 个 PlayerStart 组件，世界坐标会随船体移动。 */
        var playerStartOffsets = [0x898, 0x8A0, 0x8A8, 0x8B0, 0x670, 0x8B8, 0x890, 0x678];
        for (var i = 0; i < playerStartOffsets.length; i++) {
            try {
                var component = warship.add(playerStartOffsets[i]).readPointer();
                var location = getSceneLocation(component);
                if (isNearShip(location, shipLocation)) {
                    location.z += 100;
                    locations.push(location);
                }
            } catch (e) {}
        }

        if (locations.length === 0 && shipLocation) {
            locations.push({ x: shipLocation.x, y: shipLocation.y, z: shipLocation.z + 300 });
        }
        return locations;
    }

    function isPlayerDead(player, pawn) {
        try {
            if (player.playerState.add(0x568).readU8() !== 0) return true;
            return pawn !== null && pawn.add(0x818).readU8() !== 0;
        } catch (e) { return true; }
    }

    /* 获取玩家列表: 返回 [{playerState, controller, name, role, roleId, isThrall, index}] */
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
                try {
                    var name = getPlayerName(ps);
                    var roleInfo = getRoleInfo(ps);
                    /* ADH_PlayerState::bIsThrall，Linux ELF 偏移为 0x56A (Windows 偏移为 0x572) */
                    var isThrall = ps.add(0x56A).readU8() !== 0;
                    var controller = ADH_PlayerState_GetOwningController(ps);
                    result.push({
                        playerState: ps,
                        controller: controller,
                        name: name,
                        role: roleInfo.name,
                        roleId: roleInfo.id,
                        isThrall: isThrall,
                        index: i
                    });
                } catch (playerError) {}
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

    function resolvePlayer(params) {
        var players = getOnlinePlayers();
        var roleId = params && params.role ? String(params.role) : '';
        if (roleId) {
            var matches = [];
            for (var i = 0; i < players.length; i++) {
                if (players[i].roleId === roleId) matches.push(players[i]);
            }
            if (matches.length === 0) return { error: '所选职业当前不在线: ' + roleId };
            if (matches.length > 1) return { error: '同一职业匹配到多个玩家，已拒绝执行' };
            return { player: matches[0] };
        }
        var targetName = params ? params.player : '';
        if (!targetName || targetName === 'all' || targetName === '全部玩家') {
            return { error: '未指定玩家' };
        }
        var player = findPlayer(String(targetName));
        return player ? { player: player } : { error: '未找到玩家: ' + targetName };
    }

    function loadItemClass(classPath) {
        var buffer = Memory.alloc((classPath.length + 1) * 2);
        buffer.writeUtf16String(classPath);
        var uclass = UClass_GetPrivateStaticClass();
        var itemClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
        if (!itemClass.isNull()) return itemClass;
        itemClass = StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
        return itemClass.isNull() ? null : itemClass;
    }

    function initInventoryItemState(state) {
        state.writeU32(0xffffffff);
        state.add(0x4).writeU8(1);
        state.add(0x8).writeFloat(1.0);
        state.add(0xC).writeU8(0);
        state.add(0xD).writeU8(0);
        state.add(0xE).writeU8(0);
        state.add(0x10).writePointer(ptr(0));
        state.add(0x18).writePointer(ptr(0));
        state.add(0x20).writePointer(ptr(0));
        state.add(0x28).writePointer(ptr(0));
        state.add(0x30).writePointer(ptr(0));
    }

    function teleportPlayer(player, x, y, z) {
        var pawn = getPawn(player.controller);
        if (!pawn) return { success: false, error: '目标玩家没有可传送的角色 Pawn' };
        if (isPlayerDead(player, pawn)) return { success: false, error: '目标玩家已死亡或处于倒地状态' };
        var hitResult = Memory.alloc(256);
        var moved = K2_SetActorLocation(pawn, [x, y, z], 0, hitResult, 1);
        if (!moved) return { success: false, error: '游戏拒绝了传送请求' };
        var location = getPlayerLocation(player);
        if (!location || Math.abs(location.x - x) > 5 || Math.abs(location.y - y) > 5 || Math.abs(location.z - z) > 5) {
            return { success: false, error: '传送后坐标校验失败' };
        }
        return { success: true, location: location };
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

    function gmSendTopMessage(text) {
        var padding = '';
        for (var i = 0; i < 10; i++) padding += '\n';
        return gmSendMessage({ message: text + padding, player: 'all' });
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
        gmSendTopMessage('军械库已开启');

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
        var resolved = resolvePlayer(params);
        if (!resolved.player) return { success: false, error: resolved.error };
        var p = resolved.player;
        if (p.controller.isNull()) return { success: false, error: '无法获取玩家控制器' };

        try {
            var wasDead = p.playerState.add(0x568).readU8() !== 0;
            var pawn = getPawn(p.controller);
            if (wasDead || !pawn) {
                var gm = getGameMode();
                if (!gm) return { success: false, error: '无法获取 GameMode' };
                ADH_PlayerState_SetIsDead(p.playerState, 0);
                AGameModeBase_RestartPlayer(gm, p.controller);
                pawn = getPawn(p.controller);
                if (!pawn) return { success: false, error: '重生后未生成角色 Pawn' };
            } else {
                ADH_HumanCharacter_Revive(pawn);
            }

            var isDead = p.playerState.add(0x568).readU8() !== 0;
            var deathState = pawn.add(0x818).readU8();
            var health = pawn.add(0x94C).readFloat();
            if (isDead || deathState !== 0 || !Number.isFinite(health) || health <= 0) {
                return { success: false, error: '复活后的生命状态校验失败' };
            }
            ReceiveThrallMsg(p.controller, makeFText('[GM] 你已被复活'), ptr(0));
            gmSendMessage({ message: '[GM] ' + p.name + ' 已被复活', player: 'all' });
            return { success: true, revived: p.name, role: p.roleId, health: health, message: '玩家已实际复活' };
        } catch (e) {
            return { success: false, error: '复活失败: ' + e };
        }
    }

    /* 传送回船 */
    function gmTeleportToShip(params) {
        var target = params.player || '';
        var allPlayers = target === 'all' || target === '全部玩家';
        if (!allPlayers && !target && !params.role) return { success: false, error: '未指定玩家' };

        var warship = getWarship();
        if (!warship) return { success: false, error: '无法获取战舰' };

        try {
            var returnLocations = getShipReturnLocations(warship);
            if (returnLocations.length === 0) return { success: false, error: '无法读取战舰当前世界位置' };
            if (allPlayers) {
                var players = getOnlinePlayers();
                var count = 0;
                for (var i = 0; i < players.length; i++) {
                    var targetLocation = returnLocations[i % returnLocations.length];
                    if (teleportPlayer(players[i], targetLocation.x, targetLocation.y, targetLocation.z).success) count++;
                }
                if (count === 0) return { success: false, error: '没有玩家被成功传送' };
                gmSendMessage({ message: '[GM] 全部玩家已传送回船', player: 'all' });
                return { success: true, teleported: count, location: returnLocations[0], message: '玩家已传送到战舰当前真实位置' };
            } else {
                var resolved = resolvePlayer(params);
                if (!resolved.player) return { success: false, error: resolved.error };
                var p = resolved.player;
                var shipLocation = returnLocations[0];
                var result = teleportPlayer(p, shipLocation.x, shipLocation.y, shipLocation.z);
                if (!result.success) return result;
                ReceiveThrallMsg(p.controller, makeFText('[GM] 你已被传送回船'), ptr(0));
                return { success: true, teleported: 1, player: p.name, location: result.location, message: '玩家已传送到战舰当前真实位置' };
            }
        } catch (e) {
            return { success: false, error: '传送失败: ' + e };
        }
    }

    /* 传送到指定世界坐标 */
    function gmTeleportPlayer(params) {
        var resolved = resolvePlayer(params);
        if (!resolved.player) return { success: false, error: resolved.error };
        var x = Number(params.x), y = Number(params.y), z = Number(params.z);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
            return { success: false, error: '坐标必须是有限数字' };
        }
        if (Math.abs(x) > 10000000 || Math.abs(y) > 10000000 || Math.abs(z) > 10000000) {
            return { success: false, error: '坐标超出安全范围' };
        }
        try {
            var result = teleportPlayer(resolved.player, x, y, z);
            if (!result.success) return result;
            ReceiveThrallMsg(resolved.player.controller, makeFText('[GM] 你已被传送到指定坐标'), ptr(0));
            return {
                success: true,
                teleported: 1,
                player: resolved.player.name,
                role: resolved.player.roleId,
                location: result.location,
                message: '玩家已传送到指定坐标'
            };
        } catch (e) {
            return { success: false, error: '坐标传送失败: ' + e };
        }
    }

    function giveItemToPlayer(player, itemClass, params, quantity) {
        try {
            var pawn = getPawn(player.controller);
            if (!pawn) return { success: false, error: '没有角色 Pawn', added: 0 };
            if (isPlayerDead(player, pawn)) return { success: false, error: '已死亡或处于倒地状态', added: 0 };
            var inventory = pawn.add(0x808).readPointer();
            if (inventory.isNull()) return { success: false, error: '无法获取背包', added: 0 };

            var stateSize = 56;
            var states = Memory.alloc(16 + stateSize * quantity);
            states.writePointer(states.add(16));
            states.add(8).writeU32(quantity);
            states.add(12).writeU32(quantity);
            for (var i = 0; i < quantity; i++) initInventoryItemState(states.add(16 + stateSize * i));

            var output = Memory.alloc(8);
            output.writeS32(0);
            output.add(4).writeS32(-1);
            UDH_InventoryManager_AddInventory(inventory, itemClass, states, output, output.add(4), 0, pawn);
            var added = output.readS32();
            if (added <= 0) return { success: false, error: '背包已满或该物品不能加入背包', added: 0 };
            ReceiveThrallMsg(player.controller, makeFText('[GM] 已发放 ' + (params.item_name || params.item) + ' x' + added), ptr(0));
            return { success: true, added: added, partial: added < quantity };
        } catch (e) {
            return { success: false, error: String(e), added: 0 };
        }
    }

    /* 实时发送物品：role=all 时对每位在线玩家分别加入背包。 */
    function gmGiveItem(params) {
        var quantity = Number(params.quantity);
        var classPath = String(params.item_class || '');
        if (!Number.isInteger(quantity) || quantity < 1 || quantity > 20) {
            return { success: false, error: '物品数量必须是 1 到 20 的整数' };
        }
        if (classPath.indexOf('/Game/') !== 0 || classPath.indexOf('_Inventory') < 0) {
            return { success: false, error: '物品资源路径无效' };
        }
        try {
            var itemClass = loadItemClass(classPath);
            if (!itemClass) return { success: false, error: '当前服务器未装载该物品资源: ' + (params.item_name || params.item) };

            if (params.role === 'all') {
                var players = getOnlinePlayers();
                if (players.length === 0) return { success: false, error: '当前没有在线玩家' };
                var results = [];
                var successCount = 0;
                var totalAdded = 0;
                for (var i = 0; i < players.length; i++) {
                    var playerResult = giveItemToPlayer(players[i], itemClass, params, quantity);
                    if (playerResult.success) successCount++;
                    totalAdded += playerResult.added || 0;
                    results.push({
                        player: players[i].name,
                        role: players[i].roleId,
                        success: playerResult.success,
                        added: playerResult.added || 0,
                        error: playerResult.error || ''
                    });
                }
                if (successCount === 0) {
                    return { success: false, error: '没有玩家成功收到物品', requested_per_player: quantity, results: results };
                }
                return {
                    success: true,
                    target: 'all',
                    item: params.item,
                    item_name: params.item_name || params.item,
                    requested_per_player: quantity,
                    player_count: players.length,
                    success_count: successCount,
                    added: totalAdded,
                    partial: successCount < players.length || totalAdded < quantity * players.length,
                    results: results,
                    message: '已向 ' + successCount + '/' + players.length + ' 名玩家发放，共加入 ' + totalAdded + ' 个物品'
                };
            }

            var resolved = resolvePlayer(params);
            if (!resolved.player) return { success: false, error: resolved.error };
            var result = giveItemToPlayer(resolved.player, itemClass, params, quantity);
            if (!result.success) return { success: false, error: result.error, requested: quantity, added: 0 };
            return {
                success: true,
                player: resolved.player.name,
                role: resolved.player.roleId,
                item: params.item,
                item_name: params.item_name || params.item,
                requested: quantity,
                added: result.added,
                partial: result.partial,
                message: result.partial ? ('背包空间不足，实际加入 ' + result.added + ' 个') : ('已加入 ' + result.added + ' 个物品')
            };
        } catch (e) {
            return { success: false, error: '发送物品失败: ' + e };
        }
    }

    /* 处决玩家并在死亡同步后踢出 */
    function gmExecutePlayer(params) {
        var resolved = resolvePlayer(params);
        if (!resolved.player) return { success: false, error: resolved.error };
        var player = resolved.player;
        if (player.controller.isNull()) return { success: false, error: '无法获取玩家控制器' };
        try {
            var pawn = getPawn(player.controller);
            if (!pawn) return { success: false, error: '目标玩家没有角色 Pawn' };
            if (player.playerState.add(0x568).readU8() !== 0 || pawn.add(0x818).readU8() !== 0) {
                return { success: false, error: '目标玩家已经死亡' };
            }
            ADH_HumanCharacter_Died(pawn, ptr(0), ptr(0), 999999.0);
            var isDead = player.playerState.add(0x568).readU8() !== 0;
            var deathState = pawn.add(0x818).readU8();
            if (!isDead || deathState === 0) return { success: false, error: '处决后的死亡状态校验失败' };
            setTimeout(function () {
                try {
                    var gm = getGameMode();
                    if (gm) GameModeLogout(gm, player.controller);
                } catch (kickError) {
                    send({ type: 'gm_debug', error: '处决后踢出失败: ' + kickError });
                }
            }, 1000);
            return {
                success: true,
                player: player.name,
                role: player.roleId,
                death_state: deathState,
                kick_delay_ms: 1000,
                message: '玩家已死亡，将在 1 秒后踢出服务器'
            };
        } catch (e) {
            return { success: false, error: '处决失败: ' + e };
        }
    }

    /* ── 指令分发 ── */

    var ActionHandlers = {
        'send_message':     gmSendMessage,
        'end_game':         gmEndGame,
        'open_armory':      gmOpenArmory,
        'kick_player':      gmKickPlayer,
        'revive_player':    gmRevivePlayer,
        'teleport_to_ship': gmTeleportToShip,
        'give_item':        gmGiveItem,
        'teleport_player':  gmTeleportPlayer,
        'execute_player':   gmExecutePlayer
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
                        writeCommandResult(cmd, result);
                        send({
                            type: 'gm_result',
                            id: cmd.id || '',
                            action: cmd.action,
                            result: result
                        });
                    } catch (e) {
                        var failed = { success: false, error: String(e) };
                        writeCommandResult(cmd, failed);
                        send({
                            type: 'gm_error',
                            id: cmd.id || '',
                            action: cmd.action,
                            error: String(e)
                        });
                    }
                } else {
                    writeCommandResult(cmd, { success: false, error: '未知操作: ' + cmd.action });
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
                var pawn = getPawn(players[i].controller);
                var location = getPlayerLocation(players[i]);
                list.push({
                    name: players[i].name,
                    role: players[i].role || '',
                    role_id: players[i].roleId || '',
                    index: players[i].index,
                    is_thrall: players[i].isThrall === true,
                    hasController: true,
                    has_pawn: pawn !== null,
                    is_dead: isPlayerDead(players[i], pawn),
                    x: location ? Math.round(location.x * 100) / 100 : null,
                    y: location ? Math.round(location.y * 100) / 100 : null,
                    z: location ? Math.round(location.z * 100) / 100 : null
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
