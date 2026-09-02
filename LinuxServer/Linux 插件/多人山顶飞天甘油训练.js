/*
  多人山顶飞天甘油训练 (Linux 服务端插件)

  功能:
  1. 开局把在线玩家传送到山顶训练点。
  2. 在山顶出生点持续保留一个可拾取的硝化甘油。
  3. 玩家无敌，并停止饥饿与寒冷消耗。
  4. 狼人只保留 1 级灵界行走，其他技能无法用于破坏训练。
  5. 玩家离开山顶 25 米活动范围后，10 秒自动回到训练点。
  6. 自动清除训练点 60 米内的捕食者控制器及其 Pawn（包括附近的熊）。
  7. 对局时间固定在中午 12 点，不再进入黑夜。
  8. 灵界行走在效果结束后立即清除冷却，可以连续练习。
  9. 开局把船移动到训练水域；每次复位时恢复船体与受损浮冰。
  10. 刷新点的甘油被拿走或滚远后自动生成下一枚。
  11. 每名玩家独立计时复位；只有真正飞出山顶的玩家返回后，才统一重置一次船和浮冰。

  注意:
  - 多人版与单人版互斥；启用本插件前必须先停用单人版。
  - 使用本插件时应停用“狼人无限技能”，否则两个插件会争用技能充能等级。
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    /* ===== 训练参数 ===== */
    var TrainingPosition = { x: 4434.21, y: 6397.93, z: 7297.65 };
    var NitroRefreshPosition = { x: 4434.21, y: 6397.93, z: 7347.65 };
    var ShipPosition = { x: 3942.55, y: 171.26, z: 99.9 };
    var MountainActivityRadius = 2500.0;
    var FlightDistance = 2500.0;
    var FlightDropHeight = 500.0;
    var ResetDelayMs = 10000;
    var IceRespawnDelayMs = 100;
    var NitroRefreshRadius = 250.0;
    var PredatorClearRadius = 6000.0;
    var MonitorIntervalMs = 500;
    var PredatorPollMs = 2000;
    var DaytimeRefreshMs = 5000;
    var FixedTimeOfDay = 12.0;
    var NitroPickupClassPath = '/Game/Blueprints/Environment/Nitro/BP_Nitro_Pickup.BP_Nitro_Pickup_C';
    var NitroInventoryClassPath = '/Game/Blueprints/Environment/Nitro/BP_Nitro_Inventory.BP_Nitro_Inventory_C';
    var SpiritWalkClassPath = '/Game/Blueprints/Game/Totems/TS_SpiritWalk.TS_SpiritWalk_C';
    /* ==================== */

    var GWorld = base.add(0x5C9B6D0);
    var ADH_GameMode_HasMatchStarted = new NativeFunction(base.add(0x26C6160), 'uint8', ['pointer']);
    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var ADH_PlayerState_SetSpellChargeTier = new NativeFunction(base.add(0x277FAD0), 'void', ['pointer', 'int8']);
    var ADH_SpellManager_SetEquippedSpells = new NativeFunction(base.add(0x27A75D0), 'void', ['pointer', 'pointer']);
    var ADH_SpellManager_SetSpellChargeTier = new NativeFunction(base.add(0x27A7AA0), 'void', ['pointer', 'int8']);
    var ADH_GameStateBase_SetTimeOfDay = new NativeFunction(
        base.add(0x26D4120),
        'void',
        ['pointer', 'float', 'uint8']
    );
    var ADH_Warship_SetEnableAutoMove = new NativeFunction(base.add(0x279FD60), 'void', ['pointer', 'uint8']);
    var ADH_Warship_OnRep_CurrentHullIntegrity = new NativeFunction(base.add(0x279FCA0), 'void', ['pointer']);
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
    var UGameplayStatics_GetAllActorsOfClass = new NativeFunction(
        base.add(0x433F490),
        'void',
        ['pointer', 'pointer', 'pointer']
    );
    var ADH_AIControllerPredator_StaticClass = new NativeFunction(base.add(0x27D1C40), 'pointer', []);
    var ADH_PackIce_StaticClass = new NativeFunction(base.add(0x2827C00), 'pointer', []);
    var ADH_HullBreach_StaticClass = new NativeFunction(base.add(0x2802760), 'pointer', []);
    var ADH_InventoryPickup_Launch = new NativeFunction(base.add(0x26EC670), 'void', ['pointer', 'uint8']);
    var AActor_Destroy = new NativeFunction(base.add(0x40950A0), 'uint8', ['pointer', 'uint8', 'uint8']);
    var FActorSpawnParametersCtor = new NativeFunction(base.add(0x478C420), 'void', ['pointer']);
    var UWorld_SpawnActor = new NativeFunction(
        base.add(0x43EDEE0),
        'pointer',
        ['pointer', 'pointer', 'pointer', 'pointer']
    );
    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);
    var UpdateSpellCharge = base.add(0x27A6580);
    var CastSpell = base.add(0x27A6D00);
    var RemoveActiveSpell = base.add(0x27A73C0);

    var HungerUpdateOffset = 0xA30;
    var WarmthUpdateOffset = 0xA31;
    var RootComponentOffset = 0x130;
    var PawnOffset = 0x250;
    /* ADH_GameStateBase::SetWarship 写入 +0x2A8；+0x2B0 是 EscapeVolume。 */
    var WarshipOffset = 0x2A8;
    var CurrentHullIntegrityOffset = 0x2A0;
    var MaxHullIntegrityOffset = 0x2A8;
    var PackIceRemovedCountOffset = 0x350;
    var ActorClassOffset = 0x10;
    var ActorTransformOffset = 0x1C0;
    var ActorTransformSize = 48;
    var PickupInventoryClassOffset = 0x248;
    var PickupDropMethodOffset = 0x2F0;
    var PlayerStateSpellManagerOffset = 0x480;
    var EquippedSpellsOffset = 0x288;
    /* ETotemSpellTiers: 0=TST_UNDEFINED, 1=TST_ZERO, 2=TST_ONE。 */
    var SpellTierOne = 2;
    var CooldownMultiplierOffset = 0x280;
    var SpellChargeLevelOffset = 0x284;
    var TierOneChargeLevel = 0.34;
    var SpellCooldownDataOffset = 0x2A8;
    var SpellCooldownCountOffset = 0x2B0;
    var SpellCooldownEntrySize = 0x10;
    var SpellClassOffset = 0x10;

    var MatchActive = false;
    var MatchSequence = 0;
    var Trainees = Object.create(null);
    var WorldResetPending = false;
    var ShipReady = false;
    var NitroPickupClass = ptr(0);
    var NitroInventoryClass = ptr(0);
    var SpiritWalkClass = ptr(0);
    var PredatorClass = ptr(0);
    var PackIceClass = ptr(0);
    var HullBreachClass = ptr(0);
    var PackIceSnapshots = [];
    var PackIceSnapshotsReady = false;
    var PredatorActors = Memory.alloc(16);
    PredatorActors.writePointer(ptr(0));
    PredatorActors.add(8).writeU32(0);
    PredatorActors.add(12).writeU32(0);
    var PackIceActors = Memory.alloc(16);
    PackIceActors.writePointer(ptr(0));
    PackIceActors.add(8).writeU32(0);
    PackIceActors.add(12).writeU32(0);
    var NitroPickupActors = Memory.alloc(16);
    NitroPickupActors.writePointer(ptr(0));
    NitroPickupActors.add(8).writeU32(0);
    NitroPickupActors.add(12).writeU32(0);
    var HullBreachActors = Memory.alloc(16);
    HullBreachActors.writePointer(ptr(0));
    HullBreachActors.add(8).writeU32(0);
    HullBreachActors.add(12).writeU32(0);
    /* 客户端轮盘保留 3 个方向槽位；每个槽位都绑定同一个灵界行走。 */
    var ThrallSpellSlots = 3;
    var SpiritWalkSpellData = Memory.alloc(Process.pointerSize * ThrallSpellSlots);
    var SpiritWalkOnlyArray = Memory.alloc(16);
    SpiritWalkOnlyArray.writePointer(SpiritWalkSpellData);
    SpiritWalkOnlyArray.add(8).writeU32(ThrallSpellSlots);
    SpiritWalkOnlyArray.add(12).writeU32(ThrallSpellSlots);

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

    function getWarship() {
        try {
            var gameState = getGameState();
            if (gameState.isNull()) return ptr(0);
            var warship = gameState.add(WarshipOffset).readPointer();
            return isReadable(warship) ? warship : ptr(0);
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

    function horizontalDistanceSquared(location, target) {
        var dx = location.x - target.x;
        var dy = location.y - target.y;
        return dx * dx + dy * dy;
    }

    function isOutsideMountainActivity(location) {
        return horizontalDistanceSquared(location, TrainingPosition) >
            MountainActivityRadius * MountainActivityRadius;
    }

    function isTrueFlight(location) {
        return location.z < TrainingPosition.z - FlightDropHeight &&
            distanceSquared(location, TrainingPosition) > FlightDistance * FlightDistance;
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

    function setActorLocation(actor, target) {
        try {
            if (!isReadable(actor)) return false;
            var hitResult = Memory.alloc(256);
            K2_SetActorLocation(actor, [target.x, target.y, target.z], 0, hitResult, 1);
            var location = getLocation(actor);
            return location !== null && distanceSquared(location, target) <= 25.0;
        } catch (e) {
            return false;
        }
    }

    function clearHullBreaches() {
        try {
            var world = getWorld();
            if (world.isNull()) return;
            if (HullBreachClass.isNull()) HullBreachClass = ADH_HullBreach_StaticClass();
            if (HullBreachClass.isNull()) return;

            UGameplayStatics_GetAllActorsOfClass(world, HullBreachClass, HullBreachActors);
            var count = HullBreachActors.add(8).readU32();
            var data = HullBreachActors.readPointer();
            if (count > 256 || (count > 0 && !isReadable(data))) return;
            for (var i = 0; i < count; i++) {
                var breach = data.add(i * Process.pointerSize).readPointer();
                if (isReadable(breach)) AActor_Destroy(breach, 0, 1);
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 清除船体破口失败: ' + e);
        }
    }

    function resetWarship() {
        try {
            var warship = getWarship();
            if (warship.isNull()) return false;
            ADH_Warship_SetEnableAutoMove(warship, 0);
            clearHullBreaches();
            var maxHullIntegrity = warship.add(MaxHullIntegrityOffset).readFloat();
            if (!Number.isFinite(maxHullIntegrity) || maxHullIntegrity <= 0.0) return false;
            warship.add(CurrentHullIntegrityOffset).writeFloat(maxHullIntegrity);
            ADH_Warship_OnRep_CurrentHullIntegrity(warship);
            return setActorLocation(warship, ShipPosition);
        } catch (e) {
            console.log('[山顶飞天甘油] 复位船只失败: ' + e);
            return false;
        }
    }

    function capturePackIce() {
        if (PackIceSnapshotsReady) return;
        try {
            var world = getWorld();
            if (world.isNull()) return;
            if (PackIceClass.isNull()) PackIceClass = ADH_PackIce_StaticClass();
            if (PackIceClass.isNull()) return;

            UGameplayStatics_GetAllActorsOfClass(world, PackIceClass, PackIceActors);
            var count = PackIceActors.add(8).readU32();
            var data = PackIceActors.readPointer();
            if (count < 1 || count > 256 || !isReadable(data)) return;

            var snapshots = [];
            for (var i = 0; i < count; i++) {
                var actor = data.add(i * Process.pointerSize).readPointer();
                if (!isReadable(actor)) continue;
                var actorClass = actor.add(ActorClassOffset).readPointer();
                var root = actor.add(RootComponentOffset).readPointer();
                if (!isReadable(actorClass) || !isReadable(root)) continue;
                var transform = Memory.alloc(ActorTransformSize);
                Memory.copy(transform, root.add(ActorTransformOffset), ActorTransformSize);
                snapshots.push({ actor: actor, actorClass: actorClass, transform: transform });
            }
            if (snapshots.length > 0) {
                PackIceSnapshots = snapshots;
                PackIceSnapshotsReady = true;
                console.log('[山顶飞天甘油] 已记录 ' + snapshots.length + ' 块浮冰初始状态');
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 记录浮冰失败: ' + e);
        }
    }

    function restoreDamagedPackIce(sequence) {
        if (!PackIceSnapshotsReady) return;
        var damaged = [];
        for (var i = 0; i < PackIceSnapshots.length; i++) {
            var snapshot = PackIceSnapshots[i];
            try {
                var valid = isReadable(snapshot.actor) &&
                    snapshot.actor.add(ActorClassOffset).readPointer().equals(snapshot.actorClass);
                var removedCount = valid ? snapshot.actor.add(PackIceRemovedCountOffset).readS32() : 1;
                if (removedCount <= 0) continue;
                if (valid) AActor_Destroy(snapshot.actor, 0, 1);
                snapshot.actor = ptr(0);
                damaged.push(snapshot);
            } catch (e) {
                snapshot.actor = ptr(0);
                damaged.push(snapshot);
            }
        }
        if (damaged.length < 1) return;

        setTimeout(function () {
            if (!MatchActive || sequence !== MatchSequence) return;
            var world = getWorld();
            if (world.isNull()) return;
            for (var i = 0; i < damaged.length; i++) {
                var params = Memory.alloc(0x30);
                FActorSpawnParametersCtor(params);
                var actor = UWorld_SpawnActor(world, damaged[i].actorClass, damaged[i].transform, params);
                if (isReadable(actor)) {
                    damaged[i].actor = actor;
                } else {
                    console.log('[山顶飞天甘油] 浮冰重建失败，将在下次复位时重试');
                }
            }
        }, IceRespawnDelayMs);
    }

    function resetTrainingWorld() {
        ShipReady = resetWarship();
        restoreDamagedPackIce(MatchSequence);
    }

    function tryResetTrainingWorld() {
        if (!WorldResetPending) return;
        var keys = Object.keys(Trainees);
        for (var i = 0; i < keys.length; i++) {
            var record = Trainees[keys[i]];
            if (!record.teleported || (record.resetScheduled && record.resetWorld)) return;
            var location = getLocation(record.pawn);
            if (location === null || isTrueFlight(location)) return;
        }
        WorldResetPending = false;
        resetTrainingWorld();
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
            if (!isReadable(playerState)) return;
            ADH_PlayerState_SetSpellChargeTier(playerState, SpellTierOne);
            var spellManager = playerState.add(PlayerStateSpellManagerOffset).readPointer();
            if (isReadable(spellManager)) {
                ADH_SpellManager_SetSpellChargeTier(spellManager, SpellTierOne);
                spellManager.add(SpellChargeLevelOffset).writeFloat(TierOneChargeLevel);
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 锁定一级技能失败: ' + e);
        }
    }

    function loadSpiritWalkClass() {
        if (!SpiritWalkClass.isNull()) return SpiritWalkClass;
        try {
            var buffer = Memory.alloc((SpiritWalkClassPath.length + 1) * 2);
            buffer.writeUtf16String(SpiritWalkClassPath);
            var uclass = UClass_GetPrivateStaticClass();
            SpiritWalkClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
            if (SpiritWalkClass.isNull()) {
                SpiritWalkClass = StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
            }
        } catch (e) {
            SpiritWalkClass = ptr(0);
        }
        return SpiritWalkClass;
    }

    function lockSpiritWalkOnly(playerState) {
        try {
            if (!isReadable(playerState)) return false;
            var spellManager = playerState.add(PlayerStateSpellManagerOffset).readPointer();
            if (!isReadable(spellManager)) return false;
            var spellClass = loadSpiritWalkClass();
            if (spellClass.isNull()) return false;

            var equippedSpells = spellManager.add(EquippedSpellsOffset);
            var equippedData = equippedSpells.readPointer();
            var equippedCount = equippedSpells.add(8).readU32();
            if (equippedCount === ThrallSpellSlots && isReadable(equippedData)) {
                var allSpiritWalk = true;
                for (var j = 0; j < ThrallSpellSlots; j++) {
                    if (!equippedData.add(j * Process.pointerSize).readPointer().equals(spellClass)) {
                        allSpiritWalk = false;
                        break;
                    }
                }
                if (allSpiritWalk) return true;
            }

            for (var i = 0; i < ThrallSpellSlots; i++) {
                SpiritWalkSpellData.add(i * Process.pointerSize).writePointer(spellClass);
            }
            ADH_SpellManager_SetEquippedSpells(spellManager, SpiritWalkOnlyArray);
            return true;
        } catch (e) {
            console.log('[山顶飞天甘油] 锁定灵界行走失败: ' + e);
            return false;
        }
    }

    function loadNitroPickupClass() {
        if (!NitroPickupClass.isNull()) return NitroPickupClass;
        try {
            var buffer = Memory.alloc((NitroPickupClassPath.length + 1) * 2);
            buffer.writeUtf16String(NitroPickupClassPath);
            var uclass = UClass_GetPrivateStaticClass();
            NitroPickupClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
            if (NitroPickupClass.isNull()) {
                NitroPickupClass = StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
            }
        } catch (e) {
            NitroPickupClass = ptr(0);
        }
        return NitroPickupClass;
    }

    function loadNitroInventoryClass() {
        if (!NitroInventoryClass.isNull()) return NitroInventoryClass;
        try {
            var buffer = Memory.alloc((NitroInventoryClassPath.length + 1) * 2);
            buffer.writeUtf16String(NitroInventoryClassPath);
            var uclass = UClass_GetPrivateStaticClass();
            NitroInventoryClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
            if (NitroInventoryClass.isNull()) {
                NitroInventoryClass = StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
            }
        } catch (e) {
            NitroInventoryClass = ptr(0);
        }
        return NitroInventoryClass;
    }

    function makeSpawnTransform(position) {
        var transform = Memory.alloc(48);
        transform.writeFloat(0.0);
        transform.add(0x4).writeFloat(0.0);
        transform.add(0x8).writeFloat(0.0);
        transform.add(0xC).writeFloat(1.0);
        transform.add(0x10).writeFloat(position.x);
        transform.add(0x14).writeFloat(position.y);
        transform.add(0x18).writeFloat(position.z);
        transform.add(0x1C).writeFloat(0.0);
        transform.add(0x20).writeFloat(1.0);
        transform.add(0x24).writeFloat(1.0);
        transform.add(0x28).writeFloat(1.0);
        transform.add(0x2C).writeFloat(0.0);
        return transform;
    }

    function hasNitroAtRefreshPoint(world, nitroClass) {
        UGameplayStatics_GetAllActorsOfClass(world, nitroClass, NitroPickupActors);
        var count = NitroPickupActors.add(8).readU32();
        var data = NitroPickupActors.readPointer();
        if (count > 256 || (count > 0 && !isReadable(data))) return true;
        for (var i = 0; i < count; i++) {
            var actor = data.add(i * Process.pointerSize).readPointer();
            var location = getLocation(actor);
            if (
                location !== null &&
                distanceSquared(location, NitroRefreshPosition) <= NitroRefreshRadius * NitroRefreshRadius
            ) {
                return true;
            }
        }
        return false;
    }

    function ensureNitroPickup() {
        try {
            var world = getWorld();
            if (world.isNull()) return false;
            var nitroClass = loadNitroPickupClass();
            var inventoryClass = loadNitroInventoryClass();
            if (nitroClass.isNull() || inventoryClass.isNull()) return false;
            if (hasNitroAtRefreshPoint(world, nitroClass)) return true;

            var params = Memory.alloc(0x30);
            FActorSpawnParametersCtor(params);
            var actor = UWorld_SpawnActor(world, nitroClass, makeSpawnTransform(NitroRefreshPosition), params);
            if (!isReadable(actor)) return false;
            actor.add(PickupInventoryClassOffset).writePointer(inventoryClass);
            actor.add(PickupDropMethodOffset).writeU8(1);
            ADH_InventoryPickup_Launch(actor, 0);
            return true;
        } catch (e) {
            console.log('[山顶飞天甘油] 刷新甘油失败: ' + e);
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
            lockSpiritWalkOnly(record.playerState);
            if (!teleportToTrainingPoint(pawn)) {
                record.resetScheduled = false;
                return;
            }

            var resetWorld = record.resetWorld;
            record.controller = controller;
            record.pawn = pawn;
            record.teleported = true;
            record.resetScheduled = false;
            record.resetWorld = false;
            if (resetWorld) WorldResetPending = true;
            ensureNitroPickup();
            notify(controller, '[训练] 已复位到山顶，可以继续练习');
            tryResetTrainingWorld();
        } catch (e) {
            record.resetScheduled = false;
            console.log('[山顶飞天甘油] 复位失败: ' + e);
        }
    }

    function scheduleReset(key, record, trueFlight) {
        if (record.resetScheduled) {
            if (trueFlight) record.resetWorld = true;
            return;
        }
        record.resetScheduled = true;
        record.resetWorld = trueFlight;
        var sequence = MatchSequence;
        notify(
            record.controller,
            trueFlight
                ? '[训练] 已检测到飞离，10 秒后返回山顶'
                : '[训练] 已离开山顶活动范围，10 秒后返回出生点'
        );
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
                WorldResetPending = false;
                ShipReady = false;
                PackIceSnapshots = [];
                PackIceSnapshotsReady = false;
            }
            return;
        }

        if (!MatchActive) {
            MatchActive = true;
            MatchSequence++;
            Trainees = Object.create(null);
            WorldResetPending = false;
            ShipReady = false;
            PackIceSnapshots = [];
            PackIceSnapshotsReady = false;
        }

        capturePackIce();
        if (!ShipReady) ShipReady = resetWarship();
        ensureNitroPickup();

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
                    resetScheduled: false,
                    resetWorld: false
                };
                Trainees[key] = record;
            }

            applyProtection(player.pawn);
            lockLevelOne(player.playerState);
            lockSpiritWalkOnly(player.playerState);

            if (!record.teleported) {
                record.teleported = teleportToTrainingPoint(player.pawn);
                if (record.teleported) {
                    notify(player.controller, '[训练] 已到达山顶；活动范围 25 米，仅可使用 1 级灵界行走');
                }
            }

            var location = getLocation(player.pawn);
            if (record.teleported && location !== null) {
                if (isTrueFlight(location)) {
                    scheduleReset(key, record, true);
                } else if (!record.resetScheduled && isOutsideMountainActivity(location)) {
                    scheduleReset(key, record, false);
                }
            }
        }

        var keys = Object.keys(Trainees);
        for (var j = 0; j < keys.length; j++) {
            if (!online[keys[j]]) delete Trainees[keys[j]];
        }
        tryResetTrainingWorld();
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

    function applyNoCooldown(spellManager) {
        try {
            if (isReadable(spellManager)) spellManager.add(CooldownMultiplierOffset).writeFloat(0.0);
        } catch (e) {
            console.log('[山顶飞天甘油] 设置无冷却失败: ' + e);
        }
    }

    function clampChargeTierOne(spellManager) {
        try {
            if (!isReadable(spellManager)) return;
            spellManager.add(SpellChargeLevelOffset).writeFloat(TierOneChargeLevel);
            ADH_SpellManager_SetSpellChargeTier(spellManager, SpellTierOne);
        } catch (e) {}
    }

    /* 只在法术效果结束后删除冷却项，不能在施法时清除，否则客户端效果计时会卡住。 */
    function clearFinishedSpellCooldown(spellManager, spell) {
        try {
            if (!isReadable(spellManager) || !isReadable(spell)) return;
            var spellClass = spell.add(SpellClassOffset).readPointer();
            var cooldownData = spellManager.add(SpellCooldownDataOffset).readPointer();
            var cooldownCountAddress = spellManager.add(SpellCooldownCountOffset);
            var cooldownCount = cooldownCountAddress.readS32();
            if (spellClass.isNull() || cooldownData.isNull() || cooldownCount <= 0 || cooldownCount > 64) return;

            for (var i = 0; i < cooldownCount; i++) {
                var entry = cooldownData.add(i * SpellCooldownEntrySize);
                if (!entry.readPointer().equals(spellClass)) continue;

                for (var j = i + 1; j < cooldownCount; j++) {
                    var source = cooldownData.add(j * SpellCooldownEntrySize);
                    var target = source.sub(SpellCooldownEntrySize);
                    target.writePointer(source.readPointer());
                    target.add(8).writeU64(source.add(8).readU64());
                }
                cooldownCountAddress.writeS32(cooldownCount - 1);
                return;
            }
        } catch (e) {
            console.log('[山顶飞天甘油] 清除技能冷却失败: ' + e);
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

    Interceptor.attach(UpdateSpellCharge, {
        onEnter: function (args) {
            this.spellManager = args[0];
            applyNoCooldown(this.spellManager);
        },
        onLeave: function () {
            applyNoCooldown(this.spellManager);
            clampChargeTierOne(this.spellManager);
        }
    });

    Interceptor.attach(CastSpell, {
        onEnter: function (args) {
            this.spellManager = args[0];
            /* 必须在原函数计算本次冷却前先置零倍率。 */
            applyNoCooldown(this.spellManager);
        },
        onLeave: function () {
            applyNoCooldown(this.spellManager);
        }
    });

    Interceptor.attach(RemoveActiveSpell, {
        onEnter: function (args) {
            this.spellManager = args[0];
            this.spell = args[1];
        },
        onLeave: function () {
            clearFinishedSpellCooldown(this.spellManager, this.spell);
            applyNoCooldown(this.spellManager);
            clampChargeTierOne(this.spellManager);
        }
    });

    setInterval(updateTrainees, MonitorIntervalMs);
    setInterval(clearNearbyPredators, PredatorPollMs);
    setInterval(keepDaylight, DaytimeRefreshMs);
    setTimeout(updateTrainees, 500);
    setTimeout(keepDaylight, 500);
    send('多人山顶飞天甘油训练: 已加载（仅灵界行走，山顶活动范围 25 米）');
}
