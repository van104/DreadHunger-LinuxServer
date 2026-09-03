/*
 * 阵营词语·血咒玩法（Dread Hunger Finale 1.2.4 Linux）
 *
 * 本插件是一个独立的 7 人训练局：A/B 各 3 名好人，1 名狼人。
 * 原版职业仍由“随机职业 Plus”分配；本文件只维护自定义阵营、词语和规则。
 *
 * 重要：所有会改变 UObject 状态的调用都在 AGameMode::Tick Hook 中执行。
 * 请停用开局沉默、狼人无限技能、修复充能、表情不当狼和山顶训练插件。
 */

var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    /* ===== 可直接编辑的玩法参数 ===== */
    var CONFIG = {
        requiredPlayers: 7,
        countdownSeconds: 10,
        silenceJitterMinSeconds: 0,
        silenceJitterMaxSeconds: 30,
        silenceDurationSeconds: 60,
        spiritWalkTier: 4,       // ETotemSpellTiers: 4 = 3 级
        spiritWalkDurationSeconds: 60,
        wordPairs: [
            { a: '可乐', b: '雪碧' },
            { a: '苹果', b: '橘子' },
            { a: '大海', b: '湖泊' }
        ],
        announcement: {
            waiting: '[血咒玩法] 等待 7 名玩家，当前 {count}/7。',
            countdown: '[血咒玩法] 阵营已分配，{seconds} 秒后开始行动。',
            started: '[血咒玩法] 训练开始：活人禁止直接说出词语，只能模糊描述。',
            lateJoin: '[血咒玩法] 本局已有 7 名玩家，当前玩家等待下一局。',
            silenceStart: '[沉默阶段] {phase}开始，全体玩家沉默 {seconds} 秒。',
            silenceEnd: '[沉默阶段] 沉默结束，可以正常交流。',
            bloodCurse: '[血咒] 发生队友误杀，凶手将受到血咒。',
            winnerA: '[结算] A 阵营获胜。',
            winnerB: '[结算] B 阵营获胜。',
            winnerWolf: '[结算] 狼人获胜。',
            draw: '[结算] 所有阵营均已覆灭，本局平局。'
        }
    };

    /* ===== Finale 1.2.4 Linux 地址 ===== */
    var GWorld = base.add(0x5C9B6D0);
    var AGameMode_Tick = base.add(0x4336360);
    var AGameMode_SetMatchState = new NativeFunction(base.add(0x43360E0), 'void', ['pointer', 'uint64']);
    var AGameMode_StartMatch = new NativeFunction(base.add(0x4335A40), 'void', ['pointer']);
    var ADH_GameMode_HasMatchStarted = new NativeFunction(base.add(0x26C6160), 'uint8', ['pointer']);
    var ADH_RoleDealer_EndGame = new NativeFunction(base.add(0x2730050), 'void', ['pointer', 'uint8']);
    var ADH_GameMode_RandomizeThralls = new NativeFunction(base.add(0x26CB250), 'void', ['pointer']);
    var ADH_GameMode_NotifyDeath = base.add(0x26CA7D0);
    var ADH_GameMode_HandleMatchHasStarted = base.add(0x26BDF30);
    var ADH_GameMode_HandleStartingNewPlayer = base.add(0x26CB970);
    var ADH_GameMode_ReadyToEndMatch = base.add(0x26C8EF0);
    var ADH_GameState_OnNewDayStarted = base.add(0x26D2700);

    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var ADH_PlayerState_SetIsThrall = new NativeFunction(base.add(0x277F060), 'void', ['pointer', 'uint8']);
    var ADH_PlayerState_SetIsDead = new NativeFunction(base.add(0x277EE70), 'void', ['pointer', 'uint8']);
    var ADH_PlayerState_SetSpellChargeTier = new NativeFunction(base.add(0x277FAD0), 'void', ['pointer', 'int8']);
    var ADH_PlayerState_SetHushed = new NativeFunction(base.add(0x27807E0), 'void', ['pointer', 'uint8']);
    var ADH_GameStateBase_SetHushOnPlayers = new NativeFunction(base.add(0x26D62A0), 'void', ['pointer', 'uint8']);

    var ADH_SpellManager_SetEquippedSpells = new NativeFunction(base.add(0x27A75D0), 'void', ['pointer', 'pointer']);
    var ADH_PlayerController_CastTotemSpell = base.add(0x2771FD0);

    var ADH_HumanCharacter_Died = new NativeFunction(base.add(0x269E8A0), 'void', ['pointer', 'pointer', 'pointer', 'float']);
    var ADH_HumanCharacter_Revive = new NativeFunction(base.add(0x2693900), 'void', ['pointer']);
    var ADH_HumanCharacter_SetIncapacitated = new NativeFunction(base.add(0x2693DD0), 'void', ['pointer', 'uint8']);
    var ADH_HumanCharacter_SetIsSpiritWalking = new NativeFunction(base.add(0x2691610), 'void', ['pointer', 'uint8', 'float']);
    var AController_SetIgnoreMoveInput = new NativeFunction(base.add(0x446CD10), 'void', ['pointer', 'uint8']);
    var AController_SetIgnoreLookInput = new NativeFunction(base.add(0x446CD50), 'void', ['pointer', 'uint8']);
    var AActor_SetCanBeDamaged = new NativeFunction(base.add(0x408CCF0), 'void', ['pointer', 'uint8']);

    /* ADH_GameState::SetWinningTeam：debug VMA 0x28c8920，Frida RVA 0x26c8920。 */
    var ADH_GameState_SetWinningTeam = new NativeFunction(base.add(0x26C8920), 'void', ['pointer', 'int32', 'int32']);
    var ADH_GameMode_AddCoalPickup = new NativeFunction(base.add(0x26CACE0), 'void', ['pointer', 'pointer']);
    var ADH_GameMode_RemoveCoalPickup = new NativeFunction(base.add(0x26CAD40), 'void', ['pointer', 'pointer']);
    var ADH_InventoryPickup_Launch = new NativeFunction(base.add(0x26EC670), 'void', ['pointer', 'uint8']);
    var FActorSpawnParametersCtor = new NativeFunction(base.add(0x478C420), 'void', ['pointer']);
    var UWorld_SpawnActor = new NativeFunction(base.add(0x43EDEE0), 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']);
    var UClass_GetPrivateStaticClass = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var StaticFindObject = new NativeFunction(base.add(0x2C95CA0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8']);
    var StaticLoadObject = new NativeFunction(base.add(0x2C97F00), 'pointer', ['pointer', 'pointer', 'pointer', 'pointer', 'uint32', 'pointer', 'uint8', 'pointer']);

    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);

    var MatchState_PokerGame = base.add(0x5A1B978);
    var PlayerStateOffset = 0x228;
    var PawnOffset = 0x250;
    var GameStateOffset = 0x280;
    var PlayerArrayOffset = 0x238;
    var RoleDealerOffset = 0x3A8;
    var PregameReadyOffset = 0x488;
    var SpellManagerOffset = 0x480;
    var SpellEquippedOffset = 0x288;
    var SpellMaxOffset = 0x228;
    var PlayerDeadOffset = 0x568;
    var PlayerThrallOffset = 0x56A;
    var HumanIncapacitatedOffset = 0xE10;
    var HumanRootOffset = 0x130;
    var RootLocationOffset = 0x1D0;
    var WarshipOffset = 0x2A8;
    var CurrentTimeOfDayOffset = 0x348;
    var PickupInventoryClassOffset = 0x248;
    var PickupDropMethodOffset = 0x2F0;

    var COAL_PICKUP_PATH = '/Game/Blueprints/Inventory/Coal/BP_Coal_Pickup.BP_Coal_Pickup_C';
    var COAL_INVENTORY_PATH = '/Game/Blueprints/Inventory/Coal/BP_Coal_Inventory.BP_Coal_Inventory_C';
    var HUSH_PATH = '/Game/Blueprints/Game/Totems/TS_Hush.TS_Hush_C';
    var CANNIBALS_PATH = '/Game/Blueprints/Game/Totems/TS_CannibalAttack.TS_CannibalAttack_C';

    var CoalPickupClass = ptr(0);
    var CoalInventoryClass = ptr(0);
    var HushClass = ptr(0);
    var CannibalsClass = ptr(0);

    var state = {
        phase: 'idle',
        worldKey: '',
        roster: Object.create(null),
        rosterKeys: [],
        wolfKey: '',
        wordPair: null,
        countdownEndMs: 0,
        countdownAnnounced: false,
        countdownLastShown: -1,
        coalActor: ptr(0),
        startAttempted: false,
        waitingNoticeSent: false,
        pendingTasks: [],
        pendingSelfRescue: null,
        pendingBloodDeaths: [],
        targetHushes: Object.create(null),
        deathGuard: Object.create(null),
        selfRescueTriggered: false,
        silenceAtMs: 0,
        silenceEndMs: 0,
        silenceActive: false,
        silenceLabel: '',
        lastTimeOfDay: null,
        daySerial: 0,
        silenceDayKeys: Object.create(null),
        ending: false,
        winner: 0,
        forceReady: false
    };

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            if (!Process.findRangeByAddress) return true;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') >= 0;
        } catch (e) { return false; }
    }

    function same(a, b) {
        try { return !!a && !!b && a.equals(b); } catch (e) { return false; }
    }

    function getWorld() {
        try {
            var world = GWorld.readPointer();
            return isReadable(world) ? world : ptr(0);
        } catch (e) { return ptr(0); }
    }

    function getGameMode() {
        try {
            var world = getWorld();
            if (world.isNull()) return ptr(0);
            var gameMode = world.add(0x118).readPointer();
            return isReadable(gameMode) ? gameMode : ptr(0);
        } catch (e) { return ptr(0); }
    }

    function getGameState() {
        try {
            var gameMode = getGameMode();
            if (gameMode.isNull()) return ptr(0);
            var gameState = gameMode.add(GameStateOffset).readPointer();
            return isReadable(gameState) ? gameState : ptr(0);
        } catch (e) { return ptr(0); }
    }

    function getPawn(controller) {
        try {
            if (!isReadable(controller)) return ptr(0);
            var pawn = controller.add(PawnOffset).readPointer();
            return isReadable(pawn) ? pawn : ptr(0);
        } catch (e) { return ptr(0); }
    }

    function getPlayerState(controller) {
        try {
            if (!isReadable(controller)) return ptr(0);
            var ps = controller.add(PlayerStateOffset).readPointer();
            return isReadable(ps) ? ps : ptr(0);
        } catch (e) { return ptr(0); }
    }

    function listPlayers() {
        var result = [];
        try {
            var gameState = getGameState();
            if (gameState.isNull()) return result;
            var array = gameState.add(PlayerArrayOffset);
            var count = array.add(8).readU32();
            var data = array.readPointer();
            if (count < 1 || count > 64 || !isReadable(data)) return result;
            for (var i = 0; i < count; i++) {
                var ps = data.add(i * Process.pointerSize).readPointer();
                if (!isReadable(ps)) continue;
                var controller = ADH_PlayerState_GetOwningController(ps);
                if (!isReadable(controller)) continue;
                result.push({
                    playerState: ps,
                    controller: controller,
                    pawn: getPawn(controller)
                });
            }
        } catch (e) {
            console.log('[血咒玩法] 枚举玩家失败: ' + e);
        }
        return result;
    }

    function isDead(playerState) {
        try { return isReadable(playerState) && playerState.add(PlayerDeadOffset).readU8() !== 0; }
        catch (e) { return false; }
    }

    function isIncapacitated(pawn) {
        try {
            if (!isReadable(pawn)) return false;
            return pawn.add(HumanIncapacitatedOffset).readU8() !== 0;
        } catch (e) { return false; }
    }

    function getLocation(actor) {
        try {
            if (!isReadable(actor)) return null;
            var root = actor.add(HumanRootOffset).readPointer();
            if (!isReadable(root)) return null;
            return {
                x: root.add(RootLocationOffset).readFloat(),
                y: root.add(RootLocationOffset + 4).readFloat(),
                z: root.add(RootLocationOffset + 8).readFloat()
            };
        } catch (e) { return null; }
    }

    function findClass(path) {
        try {
            var buffer = Memory.alloc((path.length + 1) * 2);
            buffer.writeUtf16String(path);
            var uclass = UClass_GetPrivateStaticClass();
            var found = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
            if (found && !found.isNull()) return found;
            return StaticLoadObject(uclass, ptr(0), buffer, ptr(0), 0, ptr(0), 1, ptr(0));
        } catch (e) { return ptr(0); }
    }

    function loadClasses() {
        if (CoalPickupClass.isNull()) CoalPickupClass = findClass(COAL_PICKUP_PATH);
        if (CoalInventoryClass.isNull()) CoalInventoryClass = findClass(COAL_INVENTORY_PATH);
        if (HushClass.isNull()) HushClass = findClass(HUSH_PATH);
        if (CannibalsClass.isNull()) CannibalsClass = findClass(CANNIBALS_PATH);
    }

    function makeFText(text) {
        var nameBuffer = Memory.alloc(8);
        var source = Memory.alloc((text.length + 4) * 2);
        source.writeUtf16String(text);
        FName_FName(nameBuffer, source, 1);
        var result = Memory.alloc(24);
        FText_FromName(result, nameBuffer);
        return result;
    }

    function notify(controller, text) {
        try {
            if (isReadable(controller)) ReceiveThrallMessage(controller, makeFText(text), ptr(0));
        } catch (e) {}
    }

    function broadcast(text) {
        var keys = state.rosterKeys.slice();
        for (var i = 0; i < keys.length; i++) {
            var record = state.roster[keys[i]];
            if (record) notify(record.controller, text);
        }
    }

    function broadcastPlayers(players, text) {
        for (var i = 0; i < players.length; i++) notify(players[i].controller, text);
    }

    function broadcastAll(text) {
        broadcastPlayers(listPlayers(), text);
    }

    function format(text, values) {
        var result = text;
        for (var key in values) {
            if (Object.prototype.hasOwnProperty.call(values, key)) {
                result = result.split('{' + key + '}').join(String(values[key]));
            }
        }
        return result;
    }

    function shuffle(values) {
        for (var i = values.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var tmp = values[i];
            values[i] = values[j];
            values[j] = tmp;
        }
        return values;
    }

    function isPokerGameState(gameMode) {
        try {
            return gameMode.add(0x2C0).readU64().toString() === MatchState_PokerGame.readU64().toString();
        } catch (e) { return false; }
    }

    function hasMatchStarted(gameMode) {
        try { return !gameMode.isNull() && ADH_GameMode_HasMatchStarted(gameMode) !== 0; }
        catch (e) { return false; }
    }

    function enqueue(task) {
        if (typeof task === 'function') state.pendingTasks.push(task);
    }

    function processQueue() {
        var count = 0;
        while (state.pendingTasks.length > 0 && count < 32) {
            var task = state.pendingTasks.shift();
            try { task(); } catch (e) { console.log('[血咒玩法] 游戏线程任务失败: ' + e); }
            count++;
        }
    }

    function resetRound() {
        try {
            var oldGameMode = getGameMode();
            if (state.phase === 'ended' && !oldGameMode.isNull() && state.coalActor &&
                !state.coalActor.isNull() && isReadable(state.coalActor)) {
                ADH_GameMode_RemoveCoalPickup(oldGameMode, state.coalActor);
            }
        } catch (e) {}
        state.phase = 'idle';
        state.roster = Object.create(null);
        state.rosterKeys = [];
        state.wolfKey = '';
        state.wordPair = null;
        state.countdownEndMs = 0;
        state.countdownAnnounced = false;
        state.countdownLastShown = -1;
        state.coalActor = ptr(0);
        state.startAttempted = false;
        state.waitingNoticeSent = false;
        state.pendingSelfRescue = null;
        state.pendingBloodDeaths = [];
        state.targetHushes = Object.create(null);
        state.deathGuard = Object.create(null);
        state.selfRescueTriggered = false;
        state.silenceAtMs = 0;
        state.silenceEndMs = 0;
        state.silenceActive = false;
        state.silenceLabel = '';
        state.lastTimeOfDay = null;
        state.daySerial = 0;
        state.silenceDayKeys = Object.create(null);
        state.ending = false;
        state.winner = 0;
        state.forceReady = false;
    }

    function ensureWorld() {
        var world = getWorld();
        if (world.isNull()) return false;
        var key = world.toString();
        if (state.worldKey === '') state.worldKey = key;
        if (state.worldKey !== key) {
            state.worldKey = key;
            resetRound();
        }
        return true;
    }

    function getRecordByPlayerState(playerState) {
        if (!playerState || playerState.isNull()) return null;
        return state.roster[playerState.toString()] || null;
    }

    function getRecordByController(controller) {
        return getRecordByPlayerState(getPlayerState(controller));
    }

    function getRecordByPawn(pawn) {
        if (!pawn || pawn.isNull()) return null;
        for (var i = 0; i < state.rosterKeys.length; i++) {
            var record = state.roster[state.rosterKeys[i]];
            if (record && same(record.pawn, pawn)) return record;
        }
        return null;
    }

    function refreshRecords(players) {
        for (var i = 0; i < players.length; i++) {
            var item = players[i];
            var key = item.playerState.toString();
            var record = state.roster[key];
            if (!record) continue;
            record.controller = item.controller;
            if (!item.pawn.isNull()) record.pawn = item.pawn;
            if (isDead(record.playerState)) record.dead = true;
        }
    }

    function assignRoster(players) {
        if (state.rosterKeys.length > 0 || players.length < CONFIG.requiredPlayers) return false;
        var selected = players.slice(0, CONFIG.requiredPlayers);
        var shuffled = shuffle(selected.slice());
        var pairIndex = Math.floor(Math.random() * CONFIG.wordPairs.length);
        state.wordPair = CONFIG.wordPairs[pairIndex] || CONFIG.wordPairs[0];
        for (var i = 0; i < shuffled.length; i++) {
            var item = shuffled[i];
            var faction = i < 3 ? 'A' : (i < 6 ? 'B' : 'W');
            var number = faction === 'A' ? i + 1 : (faction === 'B' ? i - 2 : 0);
            var key = item.playerState.toString();
            var record = {
                playerState: item.playerState,
                controller: item.controller,
                pawn: item.pawn,
                faction: faction,
                identity: faction === 'W' ? '狼人' : (faction + '-' + number + '号'),
                word: faction === 'A' ? state.wordPair.a : (faction === 'B' ? state.wordPair.b : ''),
                dead: isDead(item.playerState),
                usedPoison: false,
                usedAntidote: false,
                selfRescueTriggered: false,
                privateSent: false,
                lateJoin: false
            };
            state.roster[key] = record;
            state.rosterKeys.push(key);
            if (faction === 'W') state.wolfKey = key;
        }
        return true;
    }

    function sendPrivateIdentities() {
        for (var i = 0; i < state.rosterKeys.length; i++) {
            var record = state.roster[state.rosterKeys[i]];
            if (!record || record.privateSent) continue;
            var text;
            if (record.faction === 'W') {
                text = '[身份] 你是狼人。你没有词语；你有 1 次解药/沉默和 1 次毒药/食尸鬼。';
            } else {
                text = '[身份] 你是 ' + record.identity + '，阵营词语是：' + record.word +
                    '。寻找队友，但活着时不得直接说出完整词语。';
            }
            notify(record.controller, text);
            record.privateSent = true;
        }
    }

    function applyMovementLock(record, locked) {
        try {
            if (!record || !isReadable(record.controller)) return;
            AController_SetIgnoreMoveInput(record.controller, locked ? 1 : 0);
            AController_SetIgnoreLookInput(record.controller, locked ? 1 : 0);
            if (!record.pawn.isNull()) AActor_SetCanBeDamaged(record.pawn, locked ? 0 : 1);
        } catch (e) {}
    }

    function makeTransform(position) {
        var transform = Memory.alloc(48);
        transform.writeFloat(0.0);
        transform.add(4).writeFloat(0.0);
        transform.add(8).writeFloat(0.0);
        transform.add(12).writeFloat(1.0);
        transform.add(16).writeFloat(position.x);
        transform.add(20).writeFloat(position.y);
        transform.add(24).writeFloat(position.z);
        transform.add(28).writeFloat(0.0);
        transform.add(32).writeFloat(1.0);
        transform.add(36).writeFloat(1.0);
        transform.add(40).writeFloat(1.0);
        transform.add(44).writeFloat(0.0);
        return transform;
    }

    function addOneCoal(gameMode) {
        if (!state.coalActor.isNull()) return;
        loadClasses();
        if (CoalPickupClass.isNull() || CoalInventoryClass.isNull()) return;
        try {
            var world = getWorld();
            if (world.isNull()) return;
            var gameState = getGameState();
            if (gameState.isNull()) return;
            var ship = gameState.add(WarshipOffset).readPointer();
            var position = getLocation(ship) || { x: 0, y: 0, z: 0 };
            var params = Memory.alloc(0x30);
            FActorSpawnParametersCtor(params);
            var actor = UWorld_SpawnActor(world, CoalPickupClass, makeTransform(position), params);
            if (!isReadable(actor)) return;
            actor.add(PickupInventoryClassOffset).writePointer(CoalInventoryClass);
            actor.add(PickupDropMethodOffset).writeU8(1);
            ADH_GameMode_AddCoalPickup(gameMode, actor);
            ADH_InventoryPickup_Launch(actor, 0);
            state.coalActor = actor; // 保持本局引用，避免重复生成和 GC 悬空。
            console.log('[血咒玩法] 已为本局添加一块煤');
        } catch (e) {
            console.log('[血咒玩法] 添加煤炭失败: ' + e);
        }
    }

    function applyWolfLoadout(record) {
        if (!record || record.faction !== 'W') return false;
        loadClasses();
        if (HushClass.isNull() || CannibalsClass.isNull()) return false;
        try {
            var manager = record.playerState.add(SpellManagerOffset).readPointer();
            if (!isReadable(manager)) return false;
            var equipped = manager.add(SpellEquippedOffset);
            var existingData = equipped.readPointer();
            var existingCount = equipped.add(8).readU32();
            if (existingCount === 2 && isReadable(existingData) &&
                same(existingData.readPointer(), HushClass) &&
                same(existingData.add(Process.pointerSize).readPointer(), CannibalsClass)) {
                manager.add(SpellMaxOffset).writeU32(2);
                return true;
            }
            var data = Memory.alloc(Process.pointerSize * 2);
            data.writePointer(HushClass);
            data.add(Process.pointerSize).writePointer(CannibalsClass);
            var array = Memory.alloc(16);
            array.writePointer(data);
            array.add(8).writeU32(2);
            array.add(12).writeU32(2);
            ADH_SpellManager_SetEquippedSpells(manager, array);
            manager.add(SpellMaxOffset).writeU32(2);
            return true;
        } catch (e) {
            console.log('[血咒玩法] 锁定狼人技能失败: ' + e);
            return false;
        }
    }

    function forceThrallFlags() {
        for (var i = 0; i < state.rosterKeys.length; i++) {
            var record = state.roster[state.rosterKeys[i]];
            if (!record) continue;
            var expected = record.faction === 'W' ? 1 : 0;
            var actual = 255;
            try { actual = record.playerState.add(PlayerThrallOffset).readU8(); } catch (e) {}
            if (record.lastThrallValue !== expected || actual !== expected) {
                try { ADH_PlayerState_SetIsThrall(record.playerState, expected); }
                catch (e) {}
                record.lastThrallValue = expected;
            }
            if (record.faction === 'W') applyWolfLoadout(record);
        }
    }

    function beginCountdown(players) {
        if (!assignRoster(players)) return false;
        state.phase = 'countdown';
        state.countdownEndMs = Date.now() + CONFIG.countdownSeconds * 1000;
        state.countdownAnnounced = true;
        state.countdownLastShown = CONFIG.countdownSeconds;
        sendPrivateIdentities();
        forceThrallFlags();
        for (var i = 0; i < state.rosterKeys.length; i++) applyMovementLock(state.roster[state.rosterKeys[i]], true);
        addOneCoal(getGameMode());
        broadcast(format(CONFIG.announcement.countdown, { seconds: CONFIG.countdownSeconds }));
        return true;
    }

    function startFromPoker(gameMode) {
        if (state.startAttempted || !isPokerGameState(gameMode)) return;
        var players = listPlayers();
        if (players.length < CONFIG.requiredPlayers) return;
        var roleDealer = ptr(0);
        try { roleDealer = gameMode.add(RoleDealerOffset).readPointer(); } catch (e) {}
        if (roleDealer.isNull()) return;
        state.startAttempted = true;
        try {
            AGameMode_SetMatchState(gameMode, MatchState_PokerGame.readU64());
            ADH_RoleDealer_EndGame(roleDealer, 1);
            ADH_GameMode_RandomizeThralls(gameMode);
            gameMode.add(PregameReadyOffset).writeU8(1);
            AGameMode_StartMatch(gameMode);
        } catch (e) {
            state.startAttempted = false;
            console.log('[血咒玩法] 跳过打牌失败，将重试: ' + e);
        }
    }

    function scheduleSilence(label, dayKey) {
        if (state.phase !== 'active' || state.silenceActive) return;
        var key = String(dayKey) + ':' + label;
        if (state.silenceDayKeys[key]) return;
        state.silenceDayKeys[key] = true;
        var min = CONFIG.silenceJitterMinSeconds;
        var max = CONFIG.silenceJitterMaxSeconds;
        var delay = min + Math.floor(Math.random() * (Math.max(min, max) - min + 1));
        state.silenceAtMs = Date.now() + delay * 1000;
        state.silenceLabel = label;
    }

    function tickSilence(now) {
        if (state.phase !== 'active') return;
        if (!state.silenceActive && state.silenceAtMs > 0 && now >= state.silenceAtMs) {
            state.silenceAtMs = 0;
            state.silenceActive = true;
            state.silenceEndMs = now + CONFIG.silenceDurationSeconds * 1000;
            var gameState = getGameState();
            if (!gameState.isNull()) ADH_GameStateBase_SetHushOnPlayers(gameState, 1);
            broadcastAll(format(CONFIG.announcement.silenceStart, {
                phase: state.silenceLabel,
                seconds: CONFIG.silenceDurationSeconds
            }));
        }
        if (state.silenceActive && now >= state.silenceEndMs) {
            state.silenceActive = false;
            state.silenceEndMs = 0;
            var stateObject = getGameState();
            if (!stateObject.isNull()) ADH_GameStateBase_SetHushOnPlayers(stateObject, 0);
            broadcastAll(CONFIG.announcement.silenceEnd);
        }
    }

    function tickDayNight() {
        if (state.phase !== 'active') return;
        var gameState = getGameState();
        if (gameState.isNull()) return;
        try {
            var current = gameState.add(CurrentTimeOfDayOffset).readFloat();
            if (!Number.isFinite(current)) return;
            if (state.lastTimeOfDay !== null) {
                var previousBucket = Math.floor(state.lastTimeOfDay / 6);
                var currentBucket = Math.floor(current / 6);
                if (currentBucket !== previousBucket) {
                    if (current < state.lastTimeOfDay - 12) state.daySerial++;
                    if (currentBucket === 1) scheduleSilence('早晨', state.daySerial);
                    if (currentBucket === 3) scheduleSilence('夜晚', state.daySerial);
                }
            }
            state.lastTimeOfDay = current;
        } catch (e) {}
    }

    function getTargetRecord(target) {
        var direct = getRecordByPawn(target);
        if (direct) return direct;
        try {
            var ps = target.add(0x370).readPointer();
            return getRecordByPlayerState(ps);
        } catch (e) { return null; }
    }

    function isValidAntidoteTarget(target) {
        var record = getTargetRecord(target);
        if (!record || record.faction === 'W') return null;
        if (isIncapacitated(target)) return record;
        return null;
    }

    function applyTargetHush(record) {
        try {
            ADH_PlayerState_SetHushed(record.playerState, 1);
            state.targetHushes[record.playerState.toString()] =
                Date.now() + CONFIG.spiritWalkDurationSeconds * 1000;
        } catch (e) {}
    }

    function tickTargetHushes(now) {
        var keys = Object.keys(state.targetHushes);
        for (var i = 0; i < keys.length; i++) {
            if (now < state.targetHushes[keys[i]]) continue;
            var record = state.roster[keys[i]];
            if (record) {
                try { ADH_PlayerState_SetHushed(record.playerState, 0); } catch (e) {}
            }
            delete state.targetHushes[keys[i]];
        }
    }

    function reviveWithSpiritWalk(record) {
        if (!record) return false;
        var controller = ADH_PlayerState_GetOwningController(record.playerState);
        var pawn = getPawn(controller);
        if (pawn.isNull()) pawn = record.pawn;
        if (pawn.isNull()) return false;
        try {
            ADH_PlayerState_SetIsDead(record.playerState, 0);
            ADH_HumanCharacter_Revive(pawn);
            ADH_HumanCharacter_SetIncapacitated(pawn, 0);
            ADH_PlayerState_SetSpellChargeTier(record.playerState, CONFIG.spiritWalkTier);
            ADH_HumanCharacter_SetIsSpiritWalking(pawn, 1, CONFIG.spiritWalkDurationSeconds);
            record.dead = false;
            record.controller = controller;
            record.pawn = pawn;
            return true;
        } catch (e) {
            console.log('[血咒玩法] 复活失败: ' + e);
            return false;
        }
    }

    function useAntidote(wolf, target) {
        if (!wolf || wolf.usedAntidote) return false;
        var targetRecord = isValidAntidoteTarget(target);
        if (!targetRecord) return false;
        wolf.usedAntidote = true;
        enqueue(function () {
            applyTargetHush(targetRecord);
            reviveWithSpiritWalk(targetRecord);
        });
        return true;
    }

    function usePoison(wolf, target) {
        if (!wolf || wolf.usedPoison) return false;
        var targetRecord = getTargetRecord(target);
        if (!targetRecord || targetRecord.faction === 'W' || targetRecord.dead) return false;
        wolf.usedPoison = true;
        enqueue(function () {
            try {
                if (!targetRecord.dead) ADH_HumanCharacter_Died(targetRecord.pawn, wolf.controller, ptr(0), 0.0);
            } catch (e) { console.log('[血咒玩法] 毒药击杀失败: ' + e); }
        });
        return true;
    }

    function handleCastTotemSpell(args) {
        try {
            var controller = args[0];
            var spell = args[1];
            var target = args[2];
            if (HushClass.isNull() || CannibalsClass.isNull()) loadClasses();
            if (!same(spell, HushClass) && !same(spell, CannibalsClass)) return;
            var wolf = getRecordByController(controller);
            if (!wolf || wolf.faction !== 'W' || state.phase !== 'active') {
                args[1] = ptr(0);
                args[2] = ptr(0);
                return;
            }
            if (same(spell, HushClass)) {
                if (!useAntidote(wolf, target)) {
                    args[1] = ptr(0);
                    args[2] = ptr(0);
                    return;
                }
                args[1] = ptr(0); // 自定义复活/沉默/灵界流程，阻止原版目标逻辑
                args[2] = ptr(0);
                return;
            }
            if (!usePoison(wolf, target)) {
                args[1] = ptr(0);
                args[2] = ptr(0);
                return;
            }
            /* 目标置空后原版 DoSpellEffects 不会调用 SummonAI；死亡在 Tick 中执行。 */
            args[2] = ptr(0);
        } catch (e) { console.log('[血咒玩法] 拦截狼人技能失败: ' + e); }
    }

    function processSelfRescue() {
        var record = state.pendingSelfRescue;
        if (!record) return;
        state.pendingSelfRescue = null;
        if (record.usedAntidote || !record.selfRescueTriggered) return;
        record.usedAntidote = true;
        if (!reviveWithSpiritWalk(record)) record.dead = true;
    }

    function processBloodDeaths() {
        while (state.pendingBloodDeaths.length > 0) {
            var item = state.pendingBloodDeaths.shift();
            if (!item || !item.record || state.deathGuard[item.key]) continue;
            state.deathGuard[item.key] = true;
            try {
                if (!item.record.dead) ADH_HumanCharacter_Died(item.record.pawn, item.killerController, ptr(0), 0.0);
            } catch (e) { console.log('[血咒玩法] 血咒死亡失败: ' + e); }
        }
    }

    function countAlive() {
        var result = { A: 0, B: 0, W: 0 };
        for (var i = 0; i < state.rosterKeys.length; i++) {
            var record = state.roster[state.rosterKeys[i]];
            if (!record || record.dead || isDead(record.playerState)) continue;
            result[record.faction]++;
        }
        return result;
    }

    function finishGame(winner) {
        if (state.ending || state.phase !== 'active') return;
        state.ending = true;
        state.winner = winner;
        state.forceReady = true;
        if (winner === 1) broadcast(CONFIG.announcement.winnerA);
        else if (winner === 2) broadcast(CONFIG.announcement.winnerB);
        else if (winner === 3) broadcast(CONFIG.announcement.winnerWolf);
        else broadcast(CONFIG.announcement.draw);
        enqueue(function () {
            var gameState = getGameState();
            if (gameState.isNull()) return;
            /* 原生只有 Explorer/Thrall；A/B/平局使用 Explorer 占位，公告为准。 */
            var nativeTeam = winner === 3 ? 2 : 1;
            var reason = winner === 3 ? 2 : (winner === 0 ? 0 : 1);
            ADH_GameState_SetWinningTeam(gameState, nativeTeam, reason);
        });
        state.phase = 'ended';
    }

    function evaluateWin() {
        if (state.phase !== 'active' || state.ending || state.pendingSelfRescue) return;
        var alive = countAlive();
        if (alive.A > 0 && alive.B === 0) return finishGame(1);
        if (alive.B > 0 && alive.A === 0) return finishGame(2);
        if (alive.A === 0 && alive.B === 0 && alive.W > 0) return finishGame(3);
        if (alive.A === 0 && alive.B === 0 && alive.W === 0) return finishGame(0);
    }

    function tickRound(gameMode) {
        var players = listPlayers();
        if (!hasMatchStarted(gameMode)) {
            if (players.length >= CONFIG.requiredPlayers && isPokerGameState(gameMode)) startFromPoker(gameMode);
            if (state.phase === 'ended') resetRound();
            return;
        }

        if (state.phase === 'idle' || state.phase === 'waiting') {
            if (players.length < CONFIG.requiredPlayers) {
                state.phase = 'waiting';
                if (!state.waitingNoticeSent) {
                    broadcastPlayers(players, format(CONFIG.announcement.waiting, { count: players.length }));
                    state.waitingNoticeSent = true;
                }
                return;
            }
            state.waitingNoticeSent = false;
            beginCountdown(players);
        }

        refreshRecords(players);
        if (state.phase === 'countdown') {
            forceThrallFlags();
            for (var i = 0; i < state.rosterKeys.length; i++) applyMovementLock(state.roster[state.rosterKeys[i]], true);
            var remaining = Math.max(0, Math.ceil((state.countdownEndMs - Date.now()) / 1000));
            if (remaining > 0 && remaining !== state.countdownLastShown &&
                (remaining <= 3 || remaining === 5)) {
                state.countdownLastShown = remaining;
                broadcast(format(CONFIG.announcement.countdown, { seconds: remaining }));
            }
            if (remaining <= 0) {
                state.phase = 'active';
                for (var j = 0; j < state.rosterKeys.length; j++) applyMovementLock(state.roster[state.rosterKeys[j]], false);
                broadcast(CONFIG.announcement.started);
            }
            return;
        }

        if (state.phase === 'active') {
            forceThrallFlags();
            tickDayNight();
            var now = Date.now();
            tickSilence(now);
            tickTargetHushes(now);
            processSelfRescue();
            processBloodDeaths();
            evaluateWin();
        }
    }

    /* 开局时把已锁定名单之外的玩家标记为等待下一局。 */
    try {
        Interceptor.attach(ADH_GameMode_HandleMatchHasStarted, {
            onEnter: function () {
                if (state.phase === 'idle') state.phase = 'waiting';
            }
        });
    } catch (e) {}

    try {
        Interceptor.attach(ADH_GameMode_HandleStartingNewPlayer, {
            onEnter: function (args) {
                try {
                    var controller = args[1];
                    var record = getRecordByController(controller);
                    if ((state.phase === 'countdown' || state.phase === 'active') && !record) {
                        notify(controller, CONFIG.announcement.lateJoin);
                    }
                } catch (e) {}
            }
        });
    } catch (e) {}

    /* 强制自定义狼人为唯一原生 Thrall，其他玩家保持 Explorer。 */
    try {
        Interceptor.attach(base.add(0x277F060), {
            onEnter: function (args) {
                try {
                    var record = getRecordByPlayerState(args[0]);
                    if (record) args[1] = record.faction === 'W' ? ptr(1) : ptr(0);
                } catch (e) {}
            }
        });
    } catch (e) {}

    /* 狼人两技能入口：自定义一次性药瓶，置空原版目标防止食尸鬼召唤帮手。 */
    try {
        Interceptor.attach(ADH_PlayerController_CastTotemSpell, {
            onEnter: function (args) { handleCastTotemSpell(args); }
        });
    } catch (e) {}

    /* 血咒、自救和胜负均只记录事件，真正死亡/复活在下一次 Tick 执行。 */
    try {
        Interceptor.attach(ADH_GameMode_NotifyDeath, {
            onEnter: function (args) {
                try {
                    if (state.phase !== 'active') return;
                    var victimPawn = args[1];
                    var killerController = args[2];
                    var victim = getRecordByPawn(victimPawn);
                    if (!victim) return;
                    victim.dead = true;
                    if (victim.faction === 'W' && !victim.usedAntidote && !victim.selfRescueTriggered) {
                        victim.selfRescueTriggered = true;
                        state.pendingSelfRescue = victim;
                    }
                    var killer = getRecordByController(killerController);
                    if (killer && killer !== victim && killer.faction === victim.faction &&
                        (killer.faction === 'A' || killer.faction === 'B') && !killer.dead) {
                        broadcast(CONFIG.announcement.bloodCurse);
                        state.pendingBloodDeaths.push({
                            key: killer.playerState.toString(),
                            record: killer,
                            killerController: killerController
                        });
                    }
                } catch (e) { console.log('[血咒玩法] NotifyDeath 处理失败: ' + e); }
            }
        });
    } catch (e) {}

    /* 早晨原生事件；夜晚由时间桶变化检测。 */
    try {
        Interceptor.attach(ADH_GameState_OnNewDayStarted, {
            onEnter: function () {
                if (state.phase === 'active') scheduleSilence('早晨', state.daySerial);
            }
        });
    } catch (e) {}

    /* 结算安全门：只让原生 Tick 自然结束，不直接调用 EndMatch。 */
    try {
        Interceptor.attach(ADH_GameMode_ReadyToEndMatch, {
            onLeave: function (retval) {
                if (state.forceReady) retval.replace(1);
            }
        });
    } catch (e) {}

    /* 唯一游戏线程入口。 */
    try {
        Interceptor.attach(AGameMode_Tick, {
            onEnter: function (args) {
                try {
                    var gameMode = getGameMode();
                    if (gameMode.isNull() || !same(args[0], gameMode)) return;
                    ensureWorld();
                    processQueue();
                    tickRound(gameMode);
                } catch (e) { console.log('[血咒玩法] Tick 处理失败: ' + e); }
            }
        });
    } catch (e) {
        console.log('[血咒玩法] Tick Hook 安装失败: ' + e);
    }

    send('阵营词语血咒玩法: 已加载（固定 7 人，A/B 词语，狼人双药，血咒与早晚沉默）');
}
