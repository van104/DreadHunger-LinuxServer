/*
  山顶飞天甘油训练 (Linux 服务端插件)

  第一阶段功能:
  1. 开局把在线玩家传送到山顶训练点。
  2. 保证玩家背包内有一个硝化甘油。
  3. 玩家无敌，并停止饥饿与寒冷消耗。
  4. 将狼人技能充能锁定为 1 级。
  5. 玩家离开训练点 25 米后，10 秒自动回到训练点并补充甘油。
  6. 自动清除训练点 60 米内的捕食者控制器及其 Pawn（包括附近的熊）。
  7. 对局时间固定在中午 12 点，不再进入黑夜。

  注意:
  - 本阶段不移动船只，也不处理船只伤害。
  - 使用本插件时应停用“狼人无限技能”，否则两个插件会争用技能充能等级。
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    /* ===== 训练参数 ===== */
    var TrainingPosition = { x: 4434.21, y: 6397.93, z: 7297.65 };
    var FlightDistance = 2500.0;
    var ResetDelayMs = 10000;
    var PredatorClearRadius = 6000.0;
    var MonitorIntervalMs = 500;
    var PredatorPollMs = 2000;
    var DaytimeRefreshMs = 5000;
    var FixedTimeOfDay = 12.0;
    var NitroClassPath = '/Game/Blueprints/Environment/Nitro/BP_Nitro_Inventory.BP_Nitro_Inventory_C';
    /* ==================== */

    var GWorld = base.add(0x5C9B6D0);
    var ADH_GameMode_HasMatchStarted = new NativeFunction(base.add(0x26C6160), 'uint8', ['pointer']);
    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var ADH_PlayerState_SetSpellChargeTier = new NativeFunction(base.add(0x277FAD0), 'void', ['pointer', 'int8']);
    var ADH_GameStateBase_SetTimeOfDay = new NativeFunction(
        base.add(0x26D4120),
        'void',
        ['pointer', 'float', 'uint8']
    );
    var K2_SetActorLocation = new NativeFunction(
        base.add(0x40A0430),
        'uint8',
        ['pointer', ['float', 'float', 'float'], 'uint8', 'pointer', 'uint8']
    );
    var AActor_SetCanBeDamaged = new NativeFunction(base.add(0x408CCF0), 'void', ['pointer', 'bool']);
    var UClass_GetPrivateStaticClass = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var StaticFindObject = new NativeFunction(
        base.add(0x2C95CA0),
        'pointer',
        ['pointer', 'pointer', 'pointer', 'int8']
    );
    var StaticLoadObject = new NativeFunction(
        base.add(0x2C97F00),
        'pointer',
        ['pointer', 'pointer', 'pointer', 'pointer', 'uint32', 'pointer', 'uint8', 'pointer']
    );
    var UDH_InventoryManager_FindInventory = new NativeFunction(
        base.add(0x270E270),
        'pointer',
        ['pointer', 'pointer', 'int32']
    );
    var UDH_InventoryManager_AddInventory = new NativeFunction(
        base.add(0x270CA50),
        'void',
        ['pointer', 'pointer', 'pointer', 'pointer', 'pointer', 'uint8', 'pointer']
    );
    var UGameplayStatics_GetAllActorsOfClass = new NativeFunction(
        base.add(0x433F490),
        'void',
        ['pointer', 'pointer', 'pointer']
    );
    var ADH_AIControllerPredator_StaticClass = new NativeFunction(base.add(0x27D1C40), 'pointer', []);
    var AActor_Destroy = new NativeFunction(base.add(0x40950A0), 'uint8', ['pointer', 'uint8', 'uint8']);
    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);

    var HungerUpdateOffset = 0xA30;
    var WarmthUpdateOffset = 0xA31;
    var InventoryManagerOffset = 0x808;
    var RootComponentOffset = 0x130;
    var PawnOffset = 0x250;
    /* ETotemSpellTiers: 0=TST_UNDEFINED, 1=TST_ZERO, 2=TST_ONE。 */
    var SpellTierOne = 2;

    var MatchActive = false;
    var MatchSequence = 0;
    var Trainees = Object.create(null);
    var NitroClass = ptr(0);
    var PredatorClass = ptr(0);
    var PredatorActors = Memory.alloc(16);
    PredatorActors.writePointer(ptr(0));
    PredatorActors.add(8).writeU32(0);
    PredatorActors.add(12).writeU32(0);

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

    function getWorld() {
        try {
            var world = GWorld.readPointer();
            return isReadable(world) ? world : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function getGameMode() {
        try {
            var world = getWorld();
            if (world.isNull()) return ptr(0);
            var gameMode = world.add(0x118).readPointer();
            return isReadable(gameMode) ? gameMode : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function hasMatchStarted() {
        try {
            var gameMode = getGameMode();
            return !gameMode.isNull() && ADH_GameMode_HasMatchStarted(gameMode) !== 0;
        } catch (e) {
            return false;
        }
    }

    function getGameState() {
        try {
            var gameMode = getGameMode();
            if (gameMode.isNull()) return ptr(0);
            var gameState = gameMode.add(0x280).readPointer();
            return isReadable(gameState) ? gameState : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function getPawn(controller) {
        try {
            if (!isReadable(controller)) return ptr(0);
            var pawn = controller.add(PawnOffset).readPointer();
            return isReadable(pawn) ? pawn : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function getLocation(actor) {
        try {
            if (!isReadable(actor)) return null;
            var root = actor.add(RootComponentOffset).readPointer();
            if (!isReadable(root)) return null;
            var x = root.add(0x1D0).readFloat();
            var y = root.add(0x1D4).readFloat();
            var z = root.add(0x1D8).readFloat();
            if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
            return { x: x, y: y, z: z };
        } catch (e) {
            return null;
        }
    }

    function distanceSquared(location, target) {
        var dx = location.x - target.x;
        var dy = location.y - target.y;
        var dz = location.z - target.z;
        return dx * dx + dy * dy + dz * dz;
    }

    function teleportToTrainingPoint(pawn) {
        try {
            var hitResult = Memory.alloc(256);
            var moved = K2_SetActorLocation(
                pawn,
                [TrainingPosition.x, TrainingPosition.y, TrainingPosition.z],
                0,
                hitResult,
                1
            );
            if (!moved) return false;
            var location = getLocation(pawn);
            return location !== null && distanceSquared(location, TrainingPosition) <= 25.0;
        } catch (e) {
            console.log('[山顶飞天甘油] 传送失败: ' + e);
            return false;
        }
    }

    function applyProtection(pawn) {
        try {
            if (!isReadable(pawn)) return;
            pawn.add(HungerUpdateOffset).writeU8(0);
            pawn.add(WarmthUpdateOffset).writeU8(0);
            AActor_SetCanBeDamaged(pawn, 0);
        } catch (e) {
            console.log('[山顶飞天甘油] 应用无敌状态失败: ' + e);
        }
    }

    function lockLevelOne(playerState) {
        try {
            if (isReadable(playerState)) ADH_PlayerState_SetSpellChargeTier(playerState, SpellTierOne);
        } catch (e) {
            console.log('[山顶飞天甘油] 锁定一级技能失败: ' + e);
        }
    }

    function loadNitroClass() {
        if (!NitroClass.isNull()) return NitroClass;
        try {
            var buffer = Memory.alloc((NitroClassPath.length + 1) * 2);
            buffer.writeUtf16String(NitroClassPath);
            var uclass = UClass_GetPrivateStaticClass();
            NitroClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
            if (NitroClass.isNull()) {
                NitroClass = StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
            }
        } catch (e) {
            NitroClass = ptr(0);
        }
        return NitroClass;
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

    function ensureNitro(pawn) {
        try {
            var nitroClass = loadNitroClass();
            if (nitroClass.isNull()) return false;
            var inventory = pawn.add(InventoryManagerOffset).readPointer();
            if (!isReadable(inventory)) return false;

            var existing = UDH_InventoryManager_FindInventory(inventory, nitroClass, -1);
            if (!existing.isNull()) return true;

            var states = Memory.alloc(72);
            states.writePointer(states.add(16));
            states.add(8).writeU32(1);
            states.add(12).writeU32(1);
            initInventoryItemState(states.add(16));

            var output = Memory.alloc(8);
            output.writeS32(0);
            output.add(4).writeS32(-1);
            UDH_InventoryManager_AddInventory(inventory, nitroClass, states, output, output.add(4), 0, pawn);
            return output.readS32() > 0;
        } catch (e) {
            console.log('[山顶飞天甘油] 补充甘油失败: ' + e);
            return false;
        }
    }

    function makeFText(text) {
        var name = Memory.alloc(8);
        var textBuffer = Memory.alloc((text.length + 4) * 2);
        textBuffer.writeUtf16String(text);
        FName_FName(name, textBuffer, 1);
        var result = Memory.alloc(24);
        FText_FromName(result, name);
        return result;
    }

    function notify(controller, text) {
        try {
            if (isReadable(controller)) ReceiveThrallMessage(controller, makeFText(text), ptr(0));
        } catch (e) {}
    }

    function listPlayers() {
        var result = [];
        try {
            var gameState = getGameState();
            if (gameState.isNull()) return result;
            var playerArray = gameState.add(0x238);
            var count = playerArray.add(8).readU32();
            var data = playerArray.readPointer();
            if (count < 1 || count > 64 || !isReadable(data)) return result;

            for (var i = 0; i < count; i++) {
                var playerState = data.add(i * Process.pointerSize).readPointer();
                if (!isReadable(playerState)) continue;
                var controller = ADH_PlayerState_GetOwningController(playerState);
                var pawn = getPawn(controller);
                if (pawn.isNull()) continue;
                result.push({ playerState: playerState, controller: controller, pawn: pawn });
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 枚举玩家失败: ' + e);
        }
        return result;
    }

    function resetTrainee(key, record, sequence) {
        if (!MatchActive || sequence !== MatchSequence || Trainees[key] !== record) return;
        try {
            var controller = ADH_PlayerState_GetOwningController(record.playerState);
            var pawn = getPawn(controller);
            if (pawn.isNull()) {
                record.resetScheduled = false;
                return;
            }

            applyProtection(pawn);
            lockLevelOne(record.playerState);
            if (!teleportToTrainingPoint(pawn)) {
                record.resetScheduled = false;
                return;
            }

            record.controller = controller;
            record.pawn = pawn;
            record.teleported = true;
            record.nitroReady = ensureNitro(pawn);
            record.resetScheduled = false;
            notify(controller, '[训练] 已复位到山顶，可以继续练习');
        } catch (e) {
            record.resetScheduled = false;
            console.log('[山顶飞天甘油] 复位失败: ' + e);
        }
    }

    function scheduleReset(key, record) {
        if (record.resetScheduled) return;
        record.resetScheduled = true;
        var sequence = MatchSequence;
        notify(record.controller, '[训练] 已检测到飞离，10 秒后返回山顶');
        setTimeout(function () {
            resetTrainee(key, record, sequence);
        }, ResetDelayMs);
    }

    function updateTrainees() {
        if (!hasMatchStarted()) {
            if (MatchActive) {
                MatchActive = false;
                MatchSequence++;
                Trainees = Object.create(null);
            }
            return;
        }

        if (!MatchActive) {
            MatchActive = true;
            MatchSequence++;
            Trainees = Object.create(null);
        }

        var players = listPlayers();
        var online = Object.create(null);
        for (var i = 0; i < players.length; i++) {
            var player = players[i];
            var key = player.playerState.toString();
            online[key] = true;
            var record = Trainees[key];
            if (!record || !record.pawn.equals(player.pawn)) {
                record = {
                    playerState: player.playerState,
                    controller: player.controller,
                    pawn: player.pawn,
                    teleported: false,
                    nitroReady: false,
                    resetScheduled: false
                };
                Trainees[key] = record;
            }

            applyProtection(player.pawn);
            lockLevelOne(player.playerState);

            if (!record.teleported) {
                record.teleported = teleportToTrainingPoint(player.pawn);
                if (record.teleported) {
                    notify(player.controller, '[训练] 已到达山顶，背包内已准备硝化甘油');
                }
            }
            if (record.teleported && !record.nitroReady) {
                record.nitroReady = ensureNitro(player.pawn);
            }

            var location = getLocation(player.pawn);
            if (
                record.teleported &&
                !record.resetScheduled &&
                location !== null &&
                distanceSquared(location, TrainingPosition) > FlightDistance * FlightDistance
            ) {
                scheduleReset(key, record);
            }
        }

        var keys = Object.keys(Trainees);
        for (var j = 0; j < keys.length; j++) {
            if (!online[keys[j]]) delete Trainees[keys[j]];
        }
    }

    function clearNearbyPredators() {
        if (!MatchActive) return;
        try {
            var world = getWorld();
            if (world.isNull()) return;
            if (PredatorClass.isNull()) PredatorClass = ADH_AIControllerPredator_StaticClass();
            if (PredatorClass.isNull()) return;

            UGameplayStatics_GetAllActorsOfClass(world, PredatorClass, PredatorActors);
            var count = PredatorActors.add(8).readU32();
            var data = PredatorActors.readPointer();
            if (count < 1 || count > 128 || !isReadable(data)) return;

            for (var i = 0; i < count; i++) {
                var controller = data.add(i * Process.pointerSize).readPointer();
                if (!isReadable(controller)) continue;
                var pawn = getPawn(controller);
                var location = getLocation(pawn);
                if (location === null) continue;
                if (distanceSquared(location, TrainingPosition) > PredatorClearRadius * PredatorClearRadius) continue;

                AActor_Destroy(pawn, 0, 1);
                AActor_Destroy(controller, 0, 1);
                console.log('[山顶飞天甘油] 已清除训练点附近捕食者');
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 清除捕食者失败: ' + e);
        }
    }

    function keepDaylight() {
        if (!MatchActive) return;
        try {
            var gameState = getGameState();
            if (!gameState.isNull()) ADH_GameStateBase_SetTimeOfDay(gameState, FixedTimeOfDay, 1);
        } catch (e) {
            console.log('[山顶飞天甘油] 固定白天失败: ' + e);
        }
    }

    setInterval(updateTrainees, MonitorIntervalMs);
    setInterval(clearNearbyPredators, PredatorPollMs);
    setInterval(keepDaylight, DaytimeRefreshMs);
    setTimeout(updateTrainees, 500);
    setTimeout(keepDaylight, 500);
    send('山顶飞天甘油训练: 已加载（第一阶段，不移动船只）');
}
