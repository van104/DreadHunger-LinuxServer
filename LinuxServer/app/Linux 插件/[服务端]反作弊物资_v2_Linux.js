/*
 * 服务端反作弊（Linux Finale 1.2.4）：仅检测远距离交互、未挖掘取物、刷箭、无限子弹和传送。
 * 交互/取物阈值为 10 米，原生直连与日志后备共用类型白名单。
 * v1 拦截并公告；v2 在游戏线程核对在线身份后公告、踢出并登记账号黑名单。
 */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');
var AutoKick = true; // v2 执行版：核对在线身份后，在游戏线程公告、登记账号黑名单并踢出。

if (mod !== null) {
    var base = mod.base;
    // Linux ELF build ID 与新增 Hook 入口均已从本地 Shipping 二进制核对。
    function checkBytes(offset, expected) {
        var bytes = new Uint8Array(base.add(offset).readByteArray(expected.length / 2));
        var actual = '';
        for (var i = 0; i < bytes.length; i++) actual += ('0' + bytes[i].toString(16)).slice(-2);
        if (actual !== expected) throw new Error('反作弊版本不匹配，停止加载：RVA 0x' + offset.toString(16));
    }
    checkBytes(0x32C, 'cd762268d82e378f');
    checkBytes(0x27CB540, '4156534883ec28f30f114424044885ff');
    checkBytes(0x2721780, '554157415653504989d74989f64889fb');
    checkBytes(0x26891D0, '554157415641554154534881ecc80000');
    checkBytes(0x2712200, '55415741564154534883ec3080bf7103');
    checkBytes(0x2721A70, '554157415641554154534881ec880100');
    checkBytes(0x26A0D00, '534889fb4881c7c80e0000e8b0ee0700');
    checkBytes(0x409E270, '41574156534883ec204989cf4989d648');
    checkBytes(0x280AD20, '50488b0578be21034885c0740259c3bf');
    checkBytes(0x27647E0, '554157415641554154534881ec980000');
    checkBytes(0x27E1260, '50488b05500924034885c0740259c3bf');
    checkBytes(0x27D7D10, '50488b05d09524034885c0740259');
    checkBytes(0x27D2100, '50488b05f0e024034885c0740259');
    checkBytes(0x2703DB0, '415741564154534881ec480100004885');
    checkBytes(0x43E1420, '4885ff742f8b8708010000894608');
    checkBytes(0x27650A0, '554157415653504989fe4885f60f8408');
    checkBytes(0x45AB920, '415653504989d64889f38b4608894208');
    checkBytes(0x2721600, '41574156534883bf68020000000f8481');
    checkBytes(0x27073C0, '534883ec104889fb8b871c05000080bf');
    checkBytes(0x2854EE0, '534883ec104889fbc644240800488b35');
    checkBytes(0x270E270, '554157415641554154534881ec280300');
    checkBytes(0x26F96E0, '0fb687b00800004084f674062b87b408');
    checkBytes(0x26F5140, '41565350488b87980200004885c00f');
    checkBytes(0x27EB690, '50488b05587d23034885c0740259c3');
    checkBytes(0x433F490, '415741564154534883ec684989d449');
    checkBytes(0x29D7620, '534885ff74284889fb488b3dd0be0d');
    checkBytes(0x2CA9080, '534889fb4885f674118b760c8933bf');
    checkBytes(0x2CA9210, '8b4f0485c9743b8b1731c085d2783d');
    if (AutoKick) checkBytes(0x4346570, '41574156534885f674324989f7488b9e');
    checkBytes(0x459F3C0, '415653504989f64889fbc78770020000');
    var KickPlayer = AutoKick ? new NativeFunction(base.add(0x4346570), 'uint8', ['pointer', 'pointer', 'pointer']) : null;
    var AntiCheatEventsFile = DH_LINUX_ROOT + '/.gm_runtime/anti_cheat_events.json';
    var BlacklistFile = DH_LINUX_ROOT + '/gm_blacklist.json';
    var UniqueIdToStringFunctions = {};
    var AlertCooldownMs = 10000;
    var NativeAlertCooldownMs = 60000;
    var InteractionRangeCm = 1000; // 交互、物资转移、拾取共用 10 米检测阈值。

    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveGameplayMsg = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var AGameMode_Tick = base.add(0x4336360);
    var GWorld = base.add(0x5C9B6D0);
    var RecordCheatAddress = base.add(0x27CB540);
    var RangedUseAddress = base.add(0x2721780);
    var RangedUse = new NativeFunction(RangedUseAddress, 'uint8', ['pointer', 'pointer', 'pointer']);
    var TransferAddress = base.add(0x26891D0);
    var TransferInventory = new NativeFunction(TransferAddress, 'void',
        ['pointer', 'pointer', 'int', 'pointer', 'int', 'int', 'uint8', 'uint8']);
    var PickupAddress = base.add(0x2712200);
    var PickUp = new NativeFunction(PickupAddress, 'pointer', ['pointer', 'pointer', 'int']);
    var HitAddress = base.add(0x2721A70);
    var HitActor = new NativeFunction(HitAddress, 'void', ['pointer', 'pointer']);
    var GetActorBounds = new NativeFunction(base.add(0x409E270), 'void',
        ['pointer', 'uint8', 'pointer', 'pointer', 'uint8']);
    var GetInventoryClass = new NativeFunction(base.add(0x280AD20), 'pointer', []);
    var InteractAddress = base.add(0x27647E0);
    var Interact = new NativeFunction(InteractAddress, 'void', ['pointer', 'pointer', 'int']);
    var GetClimbableClass = new NativeFunction(base.add(0x27E1260), 'pointer', []);
    var GetCharacterClass = new NativeFunction(base.add(0x27D7D10), 'pointer', []);
    var GetAnimalClass = new NativeFunction(base.add(0x27D2100), 'pointer', []);
    var GetComponentBounds = new NativeFunction(base.add(0x43E1420), 'void',
        ['pointer', 'pointer', 'pointer', 'pointer']);
    var InteractCompleteAddress = base.add(0x27650A0);
    var PickupInteractions = {};
    var ActivePickupCompletions = {};
    var ClosestCollisionPoint = new NativeFunction(base.add(0x45AB920), 'float',
        ['pointer', 'pointer', 'pointer', 'uint64']);
    var RangedReloadAddress = base.add(0x2721600);
    var RangedReload = new NativeFunction(RangedReloadAddress, 'void', ['pointer']);
    var CompleteReloadAddress = base.add(0x27073C0);
    var CompleteReload = new NativeFunction(CompleteReloadAddress, 'void', ['pointer']);
    var ReloadingConsumesAmmo = new NativeFunction(base.add(0x2854EE0), 'uint8', ['pointer']);
    var FindInventory = new NativeFunction(base.add(0x270E270), 'pointer', ['pointer', 'pointer', 'int']);
    var StackCount = new NativeFunction(base.add(0x26F96E0), 'int', ['pointer', 'uint8']);
    var GetDigSiteClass = new NativeFunction(base.add(0x27EB690), 'pointer', []);
    var GetAllActorsOfClass = new NativeFunction(base.add(0x433F490), 'void', ['pointer', 'pointer', 'pointer']);
    var FreeNativeMemory = new NativeFunction(base.add(0x29D7620), 'void', ['pointer']);
    var SetWeakObject = new NativeFunction(base.add(0x2CA9080), 'void', ['pointer', 'pointer']);
    var GetWeakObject = new NativeFunction(base.add(0x2CA9210), 'pointer', ['pointer']);
    var BuriedActors = {}, BuriedActorsWorld = ptr(0);
    var TrapKilledCorpses = {}, TrapKilledCorpsesWorld = ptr(0);
    var ActiveRangedUses = {};
    var RangedShots = {};
    var ActiveReloads = {};
    var ProjectileFlightWindowMs = 30000;
    var CombatWarmupUntil = Date.now() + ProjectileFlightWindowMs;

    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程师', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航员'
    };


    var LastAlerts = {};
    var HandledServerEventIds = {};
    var HandledServerEventOrder = [];
    var LastNativeAlerts = {};
    var NextServerEventPollAt = 0;
    var PendingNativeEvents = {};
    var PendingNativeEventCount = 0;
    var LastDirectAlerts = {};
    var CompletedKicks = {};

    function newFName(text) {
        var out = Memory.alloc(8);
        var buffer = Memory.alloc((text.length + 4) * 2);
        buffer.writeUtf16String(text);
        FName_FName(out, buffer, 1);
        return out;
    }

    function makeFText(text) {
        var out = Memory.alloc(24);
        FText_FromName(out, newFName(text));
        return out;
    }

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var length = fstring.add(8).readU32();
            if (length < 1 || length > 256 || data.isNull()) return '';
            var range = Process.findRangeByAddress(data);
            if (range === null || range.protection.indexOf('r') < 0) return '';
            return data.readUtf16String(length) || '';
        } catch (e) { return ''; }
    }

    function getGameState() {
        try {
            var world = GWorld.readPointer();
            if (world.isNull()) return null;
            var gameMode = world.add(0x118).readPointer();
            if (gameMode.isNull()) return null;
            var gameState = gameMode.add(0x280).readPointer();
            return gameState.isNull() ? null : gameState;
        } catch (e) { return null; }
    }

    function getPlayerName(playerState) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out);
        } catch (e) { return ''; }
    }

    function readPlayerAccount(playerState) {
        var output = Memory.alloc(16);
        output.writePointer(ptr(0));
        try {
            // APlayerState::SetUniqueId 的 Linux 机器码确认 UniqueId 位于 +0x258。
            var uniqueId = playerState.add(0x258).readPointer();
            if (uniqueId.isNull()) return '';
            var address = uniqueId.readPointer().add(0x38).readPointer();
            var range = Process.findRangeByAddress(address);
            if (!range || range.protection.indexOf('x') < 0) return '';
            var key = address.toString();
            if (!UniqueIdToStringFunctions[key]) {
                // FString 返回值使用 Linux SysV 隐藏输出参数。
                UniqueIdToStringFunctions[key] = new NativeFunction(address, 'void', ['pointer', 'pointer']);
            }
            UniqueIdToStringFunctions[key](output, uniqueId);
            var id = readFString(output).replace(/\u0000+$/g, '').replace(/^EOSPlus:/, '').toLowerCase();
            return /^(?:\d{17}(?:_\+_\|[0-9a-f]{32})?|[0-9a-f]{32})$/.test(id) ? id : '';
        } catch (e) { return ''; }
        finally {
            var data = output.readPointer();
            if (!data.isNull()) FreeNativeMemory(data);
        }
    }

    function requestPlayerBlacklist(player, reason) {
        var id = readPlayerAccount(player.playerState);
        if (!id) {
            console.log('[反作弊][黑名单登记失败] ' + player.name + ' / 未取得有效账号 ID，仍执行踢出');
            return;
        }
        try { send({type: 'anti_cheat_blacklist', player: player.name.substring(0, 80), user_id: id, reason: reason}); }
        catch (e) { console.log('[反作弊][黑名单登记失败] ' + player.name + ' / ' + e); }
    }

    function enforceServerBlacklist(players, attempted) {
        var data;
        try { data = JSON.parse(File.readAllText(BlacklistFile)); }
        catch (e) { return; }
        if (!data || !Array.isArray(data.entries) || data.entries.length === 0) return;
        for (var i = 0; i < players.length; i++) {
            var player = players[i], previous = CompletedKicks[player.playerState.toString()];
            if (attempted[player.playerState.toString()]) continue;
            if (previous && GetWeakObject(previous.player_state_weak).equals(player.playerState) &&
                GetWeakObject(previous.controller_weak).equals(player.controller)) continue;
            var id = readPlayerAccount(player.playerState);
            if (!id) continue;
            var parts = id.split('_+_|');
            var matched = data.entries.some(function (entry) {
                if (!entry || typeof entry !== 'object') return false;
                return ['user_id', 'steam_id', 'eos_id'].some(function (key) {
                    var value = String(entry[key] || '').replace(/^EOSPlus:/, '').toLowerCase();
                    return value && (value === id || parts.indexOf(value) >= 0);
                });
            });
            if (!matched) continue;
            var event = {player_state: player.playerState.toString(), world: GWorld.readPointer().toString(),
                player_state_weak: Memory.alloc(8), controller_weak: Memory.alloc(8)};
            SetWeakObject(event.player_state_weak, player.playerState);
            SetWeakObject(event.controller_weak, player.controller);
            kickDetectedPlayer(player, event, '服务器黑名单');
        }
    }

    function getRoleName(playerState) {
        try {
            var role = playerState.add(0x588).readPointer();
            if (role.isNull()) return '';
            var roleId = readFString(role.add(0x48));
            return RoleNames[roleId] || roleId || '';
        } catch (e) { return ''; }
    }

    function getOnlinePlayers() {
        var players = [];
        try {
            var gameState = getGameState();
            if (!gameState) return players;
            var playerArray = gameState.add(0x238);
            var count = playerArray.add(8).readU32();
            var data = playerArray.readPointer();
            if (count < 1 || count > 64 || data.isNull()) return players;
            for (var i = 0; i < count; i++) {
                var playerState = data.add(i * 8).readPointer();
                if (playerState.isNull()) continue;
                var controller = ADH_PlayerState_GetOwningController(playerState);
                if (controller.isNull()) continue;
                var pawn = controller.add(0x250).readPointer();
                if (pawn.isNull()) continue;
                var inventory = pawn.add(0x808).readPointer();
                players.push({
                    playerState: playerState,
                    controller: controller,
                    pawn: pawn,
                    inventory: inventory,
                    name: getPlayerName(playerState),
                    role: getRoleName(playerState)
                });
            }
        } catch (e) {}
        return players;
    }

    function findPlayer(pawn, inventory) {
        var players = getOnlinePlayers();
        var livePawns = {};
        for (var online = 0; online < players.length; online++) livePawns[players[online].pawn.toString()] = true;
        for (var interactionKey in PickupInteractions) {
            if (!livePawns[PickupInteractions[interactionKey].pawn.toString()]) delete PickupInteractions[interactionKey];
        }
        for (var i = 0; i < players.length; i++) {
            if (players[i].pawn.equals(pawn) || (!inventory.isNull() && players[i].inventory.equals(inventory))) {
                return players[i];
            }
        }
        return null;
    }

    function findPlayerByName(name) {
        var players = getOnlinePlayers();
        var found = null;
        for (var i = 0; i < players.length; i++) {
            if (players[i].name !== name) continue;
            if (found !== null) return null; // 同名日志不能归到其中一个玩家。
            found = players[i];
        }
        return found;
    }

    function broadcast(text) {
        var players = getOnlinePlayers();
        if (players.length < 1) return;
        var message = makeFText(text);
        var title = makeFText('反作弊');
        for (var i = 0; i < players.length; i++) {
            try {
                ReceiveGameplayMsg(players[i].controller, message, ptr(0), ptr(0), title);
            } catch (e) {}
        }
    }

    function rememberServerEvent(id) {
        HandledServerEventIds[id] = true;
        HandledServerEventOrder.push(id);
        if (HandledServerEventOrder.length > 400) {
            delete HandledServerEventIds[HandledServerEventOrder.shift()];
        }
    }

    function formatNativeAntiCheatReason(event) {
        var type = String(event.cheat_type || '').replace(/[\r\n]/g, ' ').trim();
        var labels = {
            'Teleporting': '传送/瞬移',
            'Cross Map Interacts': '跨地图交互/远程摸尸',
            'Infinite Ammo': '无限弹药',
            'Remote Loot': '远程摸物资/摸尸',
            'Remote Interaction': '远程交互',
            'Arrow Duplication': '刷箭/伪造弓箭命中',
            'Buried Loot': '未挖掘取物'
        };
        return labels[type] || '游戏原生反作弊异常';
    }

    function kickDetectedPlayer(player, event, reason) {
        try {
            var world = GWorld.readPointer();
            if (world.isNull() || world.toString() !== event.world ||
                !GetWeakObject(event.player_state_weak).equals(player.playerState) ||
                !GetWeakObject(event.controller_weak).equals(player.controller)) return false;
            var gameMode = world.add(0x118).readPointer();
            var session = gameMode.isNull() ? ptr(0) : gameMode.add(0x278).readPointer();
            if (session.isNull()) throw new Error('GameSession 尚未就绪');
            if (!KickPlayer(session, player.controller, makeFText('反作弊：' + reason))) {
                throw new Error('原生 KickPlayer 返回失败');
            }
            CompletedKicks[event.player_state] = event;
            console.log('[反作弊][踢出] ' + player.name + ' / ' + reason);
            return true;
        } catch (e) {
            console.log('[反作弊][踢出失败] ' + player.name + ' / ' + e);
            return false;
        }
    }

    function processNativeAntiCheatEvents() {
        var now = Date.now();
        if (now < NextServerEventPollAt) return;
        NextServerEventPollAt = now + 1000;
        for (var shotKey in RangedShots) {
            RangedShots[shotKey] = RangedShots[shotKey].filter(function (at) { return now - at <= ProjectileFlightWindowMs; });
            if (RangedShots[shotKey].length === 0) delete RangedShots[shotKey];
        }

        // 只保留指针值和名字快照；Tick 中重新匹配在线数组，避免解引用离线对象。
        var pending = PendingNativeEvents;
        PendingNativeEvents = {};
        PendingNativeEventCount = 0;
        var players = getOnlinePlayers();
        var currentWorld = GWorld.readPointer().toString();
        for (var completedKey in CompletedKicks) {
            var completed = CompletedKicks[completedKey];
            if (completed.world !== currentWorld || GetWeakObject(completed.player_state_weak).isNull() ||
                GetWeakObject(completed.controller_weak).isNull()) delete CompletedKicks[completedKey];
        }
        var attempted = {};
        for (var key in pending) {
            var direct = pending[key];
            var matched = null;
            for (var p = 0; p < players.length; p++) {
                if (players[p].playerState.toString() === direct.player_state && players[p].name === direct.player_name) {
                    matched = players[p];
                    break;
                }
            }
            if (!matched) continue;
            if (AutoKick) {
                if (direct.world !== currentWorld || !GetWeakObject(direct.player_state_weak).equals(matched.playerState) ||
                    !GetWeakObject(direct.controller_weak).equals(matched.controller) || attempted[direct.player_state]) continue;
                var previous = CompletedKicks[direct.player_state];
                if (previous && GetWeakObject(previous.player_state_weak).equals(matched.playerState) &&
                    GetWeakObject(previous.controller_weak).equals(matched.controller)) continue;
                attempted[direct.player_state] = true;
            }
            var directAlertKey = direct.player_state + ':' + direct.cheat_type;
            var directReason = formatNativeAntiCheatReason(direct);
            var lastAlert = LastDirectAlerts[directAlertKey];
            var sameSession = !AutoKick || (lastAlert && lastAlert.event.world === currentWorld &&
                GetWeakObject(lastAlert.event.player_state_weak).equals(matched.playerState) &&
                GetWeakObject(lastAlert.event.controller_weak).equals(matched.controller));
            if (!lastAlert || !sameSession || now - lastAlert.at >= NativeAlertCooldownMs) {
                LastDirectAlerts[directAlertKey] = {at: now, event: AutoKick ? direct : null};
                LastNativeAlerts[matched.name + ':' + direct.cheat_type] = now;
                console.log('[反作弊][原生直连] ' + matched.name + ' / ' + matched.role + ' / ' + directReason);
                console.log('[反作弊][证据] ' + matched.name + ' / ' + direct.cheat_type + ' / ' + direct.detail);
                broadcast('发现 ' + matched.name + ' ' + (matched.role || '未知职业') + ' 作弊\n理由：' + directReason +
                    (AutoKick ? '\n处理：自动踢出游戏' : ''));
            }
            if (AutoKick) {
                requestPlayerBlacklist(matched, directReason);
                kickDetectedPlayer(matched, direct, directReason);
            }
        }

        if (AutoKick) enforceServerBlacklist(players, attempted);

        var data;
        try { data = JSON.parse(File.readAllText(AntiCheatEventsFile)); }
        catch (e) { return; }
        if (!data || !Array.isArray(data.events)) return;

        for (var i = 0; i < data.events.length; i++) {
            var event = data.events[i];
            if (!event || typeof event.id !== 'string' || HandledServerEventIds[event.id]) continue;
            rememberServerEvent(event.id);
            if (ignoredCheatType(event.cheat_type)) continue;

            var name = String(event.player_name || '未知用户').replace(/[\r\n]/g, ' ').trim() || '未知用户';
            var player = findPlayerByName(name);
            var role = player && player.role ? player.role : '未知职业';
            var alertKey = name + ':' + String(event.cheat_type || '');
            if (LastNativeAlerts[alertKey] && now - LastNativeAlerts[alertKey] < NativeAlertCooldownMs) {
                console.log('[反作弊][原生] 已抑制重复公告: ' + alertKey);
                continue;
            }
            LastNativeAlerts[alertKey] = now;
            var reason = formatNativeAntiCheatReason(event);
            console.log('[反作弊][原生] ' + name + ' / ' + role + ' / ' + reason);
            console.log('[反作弊][证据] ' + name + ' / ' + event.cheat_type + ' / ' + (event.detail || ''));
            // 日志后备只有昵称，无法证明当前连接身份；两个版本都只公告，不按昵称踢人。
            broadcast('发现 ' + name + ' ' + role + ' 作弊\n理由：' + reason);
        }
    }

    function ignoredCheatType(type) {
        // 仅接收这五类；原生 Long Range Interacts 的旧阈值由 10 米入口检查替代。
        return ['Remote Interaction', 'Remote Loot', 'Cross Map Interacts', 'Buried Loot',
            'Arrow Duplication', 'Infinite Ammo', 'Teleporting'].indexOf(String(type || '').trim()) === -1;
    }

    function queueEvidence(playerState, type, detail) {
        if (playerState.isNull() || !type || ignoredCheatType(type)) return;
        var stateKey = playerState.toString();
        var key = stateKey + ':' + type;
        if (PendingNativeEvents[key] || PendingNativeEventCount >= 128) return;
        var event = {
            player_state: stateKey,
            player_name: getPlayerName(playerState),
            cheat_type: type,
            detail: detail || ''
        };
        if (AutoKick) {
            var controller = ADH_PlayerState_GetOwningController(playerState);
            if (controller.isNull()) return;
            event.player_state_weak = Memory.alloc(8);
            event.controller_weak = Memory.alloc(8);
            SetWeakObject(event.player_state_weak, playerState);
            SetWeakObject(event.controller_weak, controller);
            event.world = GWorld.readPointer().toString();
        }
        PendingNativeEvents[key] = event;
        PendingNativeEventCount++;
    }

    function reportBlocked(player, type, detail) {
        queueEvidence(player.playerState, type, detail);
        var key = player.playerState.toString() + ':' + type;
        var now = Date.now();
        if (LastAlerts[key] && now - LastAlerts[key] < AlertCooldownMs) return;
        LastAlerts[key] = now;
        console.log('[反作弊][拦截] ' + player.name + ' / ' + type + ' / ' + detail);
    }

    function remoteLootReason(player, actor) {
        if (actor.isNull() || actor.equals(player.pawn)) return '';
        if (isTrapKilledCorpse(actor)) return '';
        var root = player.pawn.add(0x130).readPointer();
        var interact = player.controller.add(0x680).readPointer();
        if (root.isNull() || interact.isNull()) return '';
        var range = InteractionRangeCm;
        var origin = Memory.alloc(12), extent = Memory.alloc(12);
        var corpseMesh = getCorpseMesh(actor);
        if (!corpseMesh.isNull()) GetComponentBounds(corpseMesh, origin, extent, Memory.alloc(4));
        else GetActorBounds(actor, 0, origin, extent, 0);
        var squared = 0;
        for (var i = 0; i < 3; i++) {
            var position = root.add(0x1D0 + i * 4).readFloat();
            var center = origin.add(i * 4).readFloat(), half = extent.add(i * 4).readFloat();
            if (!Number.isFinite(position) || !Number.isFinite(center) || !Number.isFinite(half) || half < 0) return '';
            var delta = Math.max(0, Math.abs(position - center) - half);
            squared += delta * delta;
        }
        return squared > range * range ? '距离 ' + (Math.sqrt(squared) / 100).toFixed(2) +
            ' 米，允许 ' + (range / 100).toFixed(2) + ' 米' : '';
    }

    function rememberBuriedActor(site) {
        if (site.isNull() || site.add(0xF0).readU8() !== 3) return;
        var actor = site.add(0x298).readPointer();
        if (actor.isNull()) return;
        var siteWeak = Memory.alloc(8), actorWeak = Memory.alloc(8);
        SetWeakObject(siteWeak, site);
        SetWeakObject(actorWeak, actor);
        BuriedActors[actor.toString()] = {site: siteWeak, actor: actorWeak};
    }

    function buriedLootReason(actor) {
        if (actor.isNull()) return '';
        var world = GWorld.readPointer();
        if (world.isNull()) return '';
        if (!world.equals(BuriedActorsWorld)) {
            // 每个 World 首次取物时枚举一次，覆盖热加载；后续生成/流式加载由 OnRep_BuriedActor 补入。
            BuriedActors = {};
            var sites = Memory.alloc(16);
            sites.writeByteArray(new Uint8Array(16));
            try {
                GetAllActorsOfClass(world, GetDigSiteClass(), sites);
                var data = sites.readPointer(), count = sites.add(8).readS32();
                for (var i = 0; i < count; i++) rememberBuriedActor(data.add(i * 8).readPointer());
                BuriedActorsWorld = world;
            } finally {
                var allocation = sites.readPointer();
                if (!allocation.isNull()) FreeNativeMemory(allocation);
            }
        }
        var key = actor.toString(), entry = BuriedActors[key];
        if (!entry) return '';
        var site = GetWeakObject(entry.site), storedActor = GetWeakObject(entry.actor);
        if (site.isNull() || !storedActor.equals(actor) || !site.add(0x298).readPointer().equals(actor)) {
            delete BuriedActors[key];
            return '';
        }
        return site.add(0x2A0).readU8() === 0 ? '目标雪下物资尚未挖掘完成' : '';
    }

    Interceptor.attach(base.add(0x26F5140), {
        onEnter: function (args) { this.site = args[0]; },
        onLeave: function () {
            try { rememberBuriedActor(this.site); }
            catch (e) { console.log('[反作弊] 雪下物资登记失败: ' + e); }
        }
    });

    function classIsChildOf(child, parent) {
        if (child.isNull() || parent.isNull()) return false;
        if (child.equals(parent)) return true;
        var index = parent.add(0x38).readS32(), chain = child.add(0x30).readPointer();
        return index >= 0 && index <= 256 && child.add(0x38).readS32() >= index && !chain.isNull() &&
            chain.add(index * 8).readPointer().equals(parent.add(0x30));
    }

    function getCorpseMesh(actor) {
        if (actor.isNull() || actor.add(0xF0).readU8() !== 3 ||
            !classIsChildOf(actor.add(0x10).readPointer(), GetCharacterClass())) return ptr(0);
        var deathState = actor.add(0x818).readU8();
        if (deathState !== 1 && deathState !== 2) return ptr(0);
        // 尸体物理运动后，胶囊/交互组件可能仍在死亡处；只读取当前死亡阶段的模型。
        var mesh = actor.add(deathState === 2 ? 0x5A8 : 0x280).readPointer();
        return !mesh.isNull() && mesh.add(0xA0).readPointer().equals(actor) ? mesh : ptr(0);
    }

    function isTrapKilledCorpse(actor) {
        var world = GWorld.readPointer();
        if (!world.equals(TrapKilledCorpsesWorld)) {
            TrapKilledCorpses = {};
            TrapKilledCorpsesWorld = world;
        }
        if (actor.isNull()) return false;
        var key = actor.toString(), weak = TrapKilledCorpses[key];
        if (!weak) return false;
        if (GetWeakObject(weak).equals(actor)) {
            var deathState = actor.add(0x818).readU8();
            if (actor.add(0xF0).readU8() === 3 && (deathState === 1 || deathState === 2)) return true;
        }
        delete TrapKilledCorpses[key];
        return false;
    }

    // 专服不模拟尸体布娃娃、也不创建 CarcassMesh，旧边界不能证明客户端尸体超距。
    // 只登记 Trap 原生调用中由活体变为尸体的动物；被夹住后再被武器击杀不获得例外。
    Interceptor.attach(base.add(0x2703DB0), {
        onEnter: function (args) {
            this.animal = null;
            try {
                var actor = args[1];
                if (args[0].add(0xF0).readU8() !== 3 || actor.isNull() ||
                    actor.add(0xF0).readU8() !== 3 || actor.add(0x818).readU8() !== 0 ||
                    !classIsChildOf(actor.add(0x10).readPointer(), GetAnimalClass())) return;
                this.world = GWorld.readPointer();
                this.animal = Memory.alloc(8);
                SetWeakObject(this.animal, actor);
            } catch (e) { console.log('[反作弊] 捕兽夹击杀开始读取失败: ' + e); }
        },
        onLeave: function () {
            try {
                if (!this.animal || this.world.isNull() || !GWorld.readPointer().equals(this.world)) return;
                var actor = GetWeakObject(this.animal);
                if (actor.isNull()) return;
                var deathState = actor.add(0x818).readU8();
                if (deathState !== 1 && deathState !== 2) return;
                isTrapKilledCorpse(actor); // 同步 World，并清掉同地址的过期对象。
                TrapKilledCorpses[actor.toString()] = this.animal;
                console.log('[反作弊][捕兽夹尸体] 已登记距离检查例外 / ' + actor);
            } catch (e) { console.log('[反作弊] 捕兽夹击杀登记失败: ' + e); }
        }
    });

    function getManagerActor(manager) {
        // HumanOwner 由服务端 InventoryManager 初始化；背包取物使用持有者位置。
        var owner = manager.add(0xD8).readPointer();
        if (owner.isNull()) owner = manager.add(0xA0).readPointer();
        if (!owner.isNull()) {
            var inventoryClass = GetInventoryClass(), ownerClass = owner.add(0x10).readPointer();
            if (!inventoryClass.isNull() && !ownerClass.isNull()) {
                var index = inventoryClass.add(0x38).readS32();
                var chain = ownerClass.add(0x30).readPointer();
                if (index >= 0 && index <= 256 && ownerClass.add(0x38).readS32() >= index && !chain.isNull() &&
                    chain.add(index * 8).readPointer().equals(inventoryClass.add(0x30))) {
                    var holder = owner.add(0x268).readPointer();
                    if (!holder.isNull()) owner = holder;
                }
            }
        }
        return owner;
    }

    function managerLootReason(player, manager) {
        if (manager.isNull() || manager.equals(player.inventory)) return '';
        return remoteLootReason(player, getManagerActor(manager));
    }

    // 直接交互按目标组件的碰撞表面测距，船体 Actor 的巨大包围盒不能用于船上按钮。
    Interceptor.replace(InteractAddress, new NativeCallback(function (component, target, slot) {
        var key = component.toString();
        delete PickupInteractions[key];
        try {
            if (!component.isNull() && !target.isNull()) {
                var controller = component.add(0xA0).readPointer();
                var player = controller.isNull() ? null : findPlayer(controller.add(0x250).readPointer(), ptr(0));
                if (player && player.controller.equals(controller) &&
                    controller.add(0x680).readPointer().equals(component) && player.pawn.add(0xF0).readU8() === 3) {
                    var actor = target.add(0xA0).readPointer();
                    var buried = buriedLootReason(actor);
                    if (buried) { reportBlocked(player, 'Buried Loot', buried); return; }
                    // 已登记的夹子致死动物跳过距离检查；其他尸体沿用模型边界，攀爬沿用整体边界。
                    var climbable = !actor.isNull() && classIsChildOf(actor.add(0x10).readPointer(), GetClimbableClass());
                    var useBodyBounds = climbable || isTrapKilledCorpse(actor) || !getCorpseMesh(actor).isNull();
                    if (useBodyBounds) {
                        var bodyDistance = remoteLootReason(player, actor);
                        if (bodyDistance) { reportBlocked(player, 'Remote Interaction', bodyDistance); return; }
                    }
                    var root = player.pawn.add(0x130).readPointer();
                    var range = InteractionRangeCm;
                    if (!root.isNull() && !useBodyBounds) {
                        var origin = root.add(0x1D0), point = Memory.alloc(12);
                        var distance = ClosestCollisionPoint(target, origin, point, 0);
                        if (distance < 0) point = target.add(0x1D0); // 无简单碰撞时使用组件世界位置。
                        var squared = 0;
                        for (var axis = 0; axis < 3; axis++) {
                            var delta = origin.add(axis * 4).readFloat() - point.add(axis * 4).readFloat();
                            squared += delta * delta;
                        }
                        if (Number.isFinite(squared) && squared > range * range) {
                            reportBlocked(player, 'Remote Interaction', '距离 ' + (Math.sqrt(squared) / 100).toFixed(2) +
                                ' 米，允许 ' + (range / 100).toFixed(2) + ' 米');
                            return;
                        }
                        if (Number.isFinite(squared)) {
                            PickupInteractions[key] = {pawn: player.pawn, controller: controller,
                                target: target, actor: target.add(0xA0).readPointer(), slot: slot, used: false};
                        }
                    }
                }
            }
        } catch (e) { console.log('[反作弊] 交互距离校验失败: ' + e); }
        Interact(component, target, slot);
        // 原版拒绝/取消交互时 InstigatingCharacter 为空，不保留拾取许可。
        if (PickupInteractions[key] && !component.add(0x198).readPointer().equals(PickupInteractions[key].pawn)) {
            delete PickupInteractions[key];
        }
    }, 'void', ['pointer', 'pointer', 'int']));

    // E 开始时已检查距离。仅原版完成同一交互期间放行一次对应拾取，避免物理移动/抓取后的二次测距误报。
    Interceptor.attach(InteractCompleteAddress, {
        onEnter: function (args) {
            this.previous = ActivePickupCompletions[this.threadId];
            delete ActivePickupCompletions[this.threadId];
            try {
                var component = args[0], pending = PickupInteractions[component.toString()];
                delete PickupInteractions[component.toString()];
                if (pending && pending.target.equals(args[1]) && pending.slot === args[2].toInt32() &&
                    component.add(0x198).readPointer().equals(pending.pawn) &&
                    component.add(0xA0).readPointer().equals(pending.controller) &&
                    pending.controller.add(0x680).readPointer().equals(component) &&
                    pending.controller.add(0x250).readPointer().equals(pending.pawn) &&
                    pending.pawn.add(0xF0).readU8() === 3) {
                    ActivePickupCompletions[this.threadId] = pending;
                }
            } catch (e) { console.log('[反作弊] 原生拾取完成核验失败: ' + e); }
        },
        onLeave: function () {
            if (this.previous) ActivePickupCompletions[this.threadId] = this.previous;
            else delete ActivePickupCompletions[this.threadId];
        }
    });

    function isTrackedRanged(weapon) {
        var type = weapon.add(0x290).readU8();
        return type === 26 || type === 27 || type === 36; // 手枪、步枪、弓。
    }

    function weaponPlayer(weapon) {
        if (weapon.isNull() || weapon.add(0xF0).readU8() !== 3) return null;
        return findPlayer(weapon.add(0x268).readPointer(), ptr(0));
    }

    function weaponKey(player, weapon) {
        return player.pawn.toString() + ':' + weapon.toString();
    }

    function limitedAmmo(player, weapon) {
        return weapon.add(0x51C).readS32() > 0 && player.inventory.add(0x200).readU8() === 0;
    }

    Interceptor.replace(RangedReloadAddress, new NativeCallback(function (weapon) {
        var key = '', previous = null;
        try {
            var player = weaponPlayer(weapon);
            if (player && isTrackedRanged(weapon) && limitedAmmo(player, weapon)) {
                key = weaponKey(player, weapon);
                var consumes = ReloadingConsumesAmmo(weapon) !== 0;
                var ammo = consumes ? FindInventory(player.inventory, weapon.add(0x928).readPointer(),
                    weapon.add(0x870).readS32()) : ptr(0);
                previous = ActiveReloads[key];
                ActiveReloads[key] = {player: player, consumes: consumes, ammo: ammo,
                    count: ammo.isNull() ? 0 : StackCount(ammo, 0), completed: false};
            }
        } catch (e) { console.log('[反作弊] 装填来源读取失败: ' + e); }
        try { RangedReload(weapon); }
        finally {
            if (key) {
                if (previous) ActiveReloads[key] = previous;
                else delete ActiveReloads[key];
            }
        }
    }, 'void', ['pointer']));

    // 在原生写入满弹之前检查实际扣弹，防止先填满弹药再回滚造成 Blueprint 副作用。
    Interceptor.replace(CompleteReloadAddress, new NativeCallback(function (weapon) {
        try {
            var player = weaponPlayer(weapon);
            if (player && isTrackedRanged(weapon) && limitedAmmo(player, weapon)) {
                var context = ActiveReloads[weaponKey(player, weapon)];
                if (!context) {
                    if (Date.now() >= CombatWarmupUntil) {
                        reportBlocked(player, 'Infinite Ammo', '补弹未经过消耗背包弹药的装填入口');
                        return;
                    }
                } else if (context.completed || (context.consumes && (context.ammo.isNull() || context.count <= 0 ||
                    StackCount(context.ammo, 0) !== context.count - 1))) {
                    reportBlocked(player, 'Infinite Ammo', '补弹未匹配背包弹药消耗');
                    return;
                } else context.completed = true;
            }
        } catch (e) { console.log('[反作弊] 装填扣弹校验失败: ' + e); }
        CompleteReload(weapon);
    }, 'void', ['pointer']));

    Interceptor.replace(TransferAddress, new NativeCallback(function (pawn, source, sourceSlot, target, targetSlot,
                                                                 quantity, autoSlot, quickLoot) {
        try {
            if (!pawn.isNull() && pawn.add(0xF0).readU8() === 3 && quantity > 0) {
                var player = findPlayer(pawn, ptr(0));
                if (player) {
                    var buried = buriedLootReason(getManagerActor(source)) || buriedLootReason(getManagerActor(target));
                    if (buried) { reportBlocked(player, 'Buried Loot', buried); return; }
                    var reason = managerLootReason(player, source) || managerLootReason(player, target);
                    if (reason) { reportBlocked(player, 'Remote Loot', reason); return; }
                }
            }
        } catch (e) { console.log('[反作弊] 转移距离校验失败: ' + e); }
        TransferInventory(pawn, source, sourceSlot, target, targetSlot, quantity, autoSlot, quickLoot);
    }, 'void', ['pointer', 'pointer', 'int', 'pointer', 'int', 'int', 'uint8', 'uint8']));

    Interceptor.replace(PickupAddress, new NativeCallback(function (pickup, controller, slot) {
        try {
            if (!pickup.isNull() && !controller.isNull() && pickup.add(0xF0).readU8() === 3) {
                var player = findPlayer(controller.add(0x250).readPointer(), ptr(0));
                if (player) {
                    var buried = buriedLootReason(pickup);
                    if (buried) { reportBlocked(player, 'Buried Loot', buried); return ptr(0); }
                    var completion = ActivePickupCompletions[Process.getCurrentThreadId()];
                    var authorized = completion && !completion.used && completion.actor.equals(pickup) &&
                        completion.controller.equals(controller) && completion.pawn.equals(player.pawn) && completion.slot === slot;
                    if (authorized) completion.used = true;
                    var reason = authorized ? '' : remoteLootReason(player, pickup);
                    if (reason) { reportBlocked(player, 'Remote Loot', reason); return ptr(0); }
                }
            }
        } catch (e) { console.log('[反作弊] 拾取距离校验失败: ' + e); }
        return PickUp(pickup, controller, slot);
    }, 'pointer', ['pointer', 'pointer', 'int']));

    Interceptor.attach(RecordCheatAddress, {
        onEnter: function (args) {
            try {
                if (args[0].isNull()) return;
                var type = readFString(args[1]);
                if (!type) return;
                queueEvidence(args[0], type, '');
            } catch (e) { console.log('[反作弊] 原生事件读取失败: ' + e); }
        }
    });

    Interceptor.replace(RangedUseAddress, new NativeCallback(function (weapon, transform, statePointer) {
        var pawnKey = '', previous = null;
        try {
            if (!weapon.isNull() && weapon.add(0xF0).readU8() === 3 && isTrackedRanged(weapon) &&
                weapon.add(0x51C).readS32() > 0) {
                pawnKey = weapon.add(0x268).readPointer().toString();
                previous = ActiveRangedUses[pawnKey];
                ActiveRangedUses[pawnKey] = {weapon: weapon, uses: weapon.add(0x8CC).readU8(),
                    maxUses: weapon.add(0x51C).readS32(), issued: false};
            }
            return RangedUse(weapon, transform, statePointer);
        } finally {
            if (pawnKey) {
                if (previous) ActiveRangedUses[pawnKey] = previous;
                else delete ActiveRangedUses[pawnKey];
            }
        }
    }, 'uint8', ['pointer', 'pointer', 'pointer']));

    // Dedicated Server 的 Fire 返回空投射物，但仍递增发射 Flash；不能用返回值计数。
    Interceptor.attach(base.add(0x26A0D00), {
        onEnter: function (args) {
            try {
                var context = ActiveRangedUses[args[0].toString()];
                if (!context || context.issued || args[1].isNull() || context.maxUses <= 0 || context.uses <= 0 ||
                    context.weapon.add(0x8CC).readU8() !== context.uses - 1) return;
                context.issued = true;
                var key = args[0].toString() + ':' + context.weapon.toString();
                var now = Date.now();
                var shots = (RangedShots[key] || []).filter(function (at) { return now - at <= ProjectileFlightWindowMs; });
                shots.push(now);
                RangedShots[key] = shots;
            } catch (e) { console.log('[反作弊] 投射物发射读取失败: ' + e); }
        }
    });

    // 原版先调用 OnProjectileHitActor，再检查活体/弹药。必须在入口拒绝，防止尸体生成回收箭。
    Interceptor.replace(HitAddress, new NativeCallback(function (weapon, hit) {
        try {
            if (!weapon.isNull() && weapon.add(0xF0).readU8() === 3 && isTrackedRanged(weapon) &&
                weapon.add(0x51C).readS32() > 0) {
                var pawn = weapon.add(0x268).readPointer();
                var player = findPlayer(pawn, ptr(0));
                if (player && player.inventory.add(0x200).readU8() === 0) {
                    var key = pawn.toString() + ':' + weapon.toString();
                    var now = Date.now();
                    var shots = (RangedShots[key] || []).filter(function (at) { return now - at <= ProjectileFlightWindowMs; });
                    RangedShots[key] = shots;
                    if (shots.length > 0) shots.shift();
                    else if (now >= CombatWarmupUntil) {
                        reportBlocked(player, weapon.add(0x290).readU8() === 36 ? 'Arrow Duplication' : 'Infinite Ammo',
                            '未匹配服务端消耗弹药的发射');
                        return;
                    }
                }
            }
        } catch (e) { console.log('[反作弊] 投射物命中校验失败: ' + e); }
        HitActor(weapon, hit);
    }, 'void', ['pointer', 'pointer']));

    /* 文件轮询只做读取；公告的 Unreal 调用固定在游戏线程执行。 */
    Interceptor.attach(AGameMode_Tick, {
        onEnter: function () { processNativeAntiCheatEvents(); }
    });

    console.log('[反作弊] 已启动 ' + (AutoKick ? 'v2 自动踢出版' : 'v1 开发版') + '：仅保留远距离交互、未挖掘取物、刷箭、无限子弹、传送；交互检测距离=10.00 米；捕兽夹致死动物尸体跳过测距；原生拾取完成核对；射击/补弹核对实际弹药消耗；热加载宽限 30 秒；' + (AutoKick ? '检测后公告、踢出并加入账号黑名单' : '仅公告，不踢人'));
}
