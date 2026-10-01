/*
开局沉默 (Linux 服务端插件)
功能: 游戏开局对所有玩家(包括狼人)施放 2级 (45秒) 沉默法术。
     狼人可利用沉默期间进行开局战术交流。
法术等级对应时长:
  1 级 (参数 1): 30 秒
  2 级 (参数 2): 45 秒
  3 级 (参数 3): 60 秒
*/

var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    var FActorSpawnParametersCtor = new NativeFunction(base.add(0x478C420), 'void', ['pointer']);
    var UWorld_SpawnActor = new NativeFunction(base.add(0x43EDEE0), 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']);
    var StaticFindObject = new NativeFunction(base.add(0x2C95CA0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8']);
    var UClass_GetPrivateStaticClass = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var UDH_GameInstance_GetInstance = new NativeFunction(base.add(0x26BF1A0), 'pointer', ['pointer']);
    var ADH_GameMode_HasMatchStarted = new NativeFunction(base.add(0x26C6160), 'uint8', ['pointer']);

    var ADH_SpellManager_SetEquippedSpells = new NativeFunction(base.add(0x27A75D0), 'void', ['pointer', 'pointer']);
    var ADH_SpellManager_SetSpellChargeTier = new NativeFunction(base.add(0x27A7AA0), 'void', ['pointer', 'int8']);
    var ADH_SpellManager_CastSpell = new NativeFunction(base.add(0x27A6D00), 'pointer', ['pointer', 'pointer', 'pointer']);

    // ADH_GameStateBase::IsHushed
    var ADH_GameStateBase_IsHushed = new NativeFunction(base.add(0x26D61A0), 'uint8', ['pointer']);

    var FTransform_Identity = base.add(0x5A90730);
    var GWorld = base.add(0x5C9B6D0);


    function findClassByName(className) {
        try {
            var buffer = Memory.alloc((className.length + 1) * 2);
            buffer.writeUtf16String(className);
            return StaticFindObject(UClass_GetPrivateStaticClass(), ptr(0xFFFFFFFFFFFFFFFF), buffer, 0);
        } catch (e) {
            return ptr(0);
        }
    }

    function spawnActor(world, clazz, position, owner) {
        var params = Memory.alloc(0x30);
        FActorSpawnParametersCtor(params);
        params.add(0x10).writePointer(owner);
        return UWorld_SpawnActor(world, clazz, position, params);
    }

    function getGameState() {
        try {
            var world = GWorld.readPointer();
            if (world.isNull()) return ptr(0);
            var authorityGameMode = world.add(0x118).readPointer();
            if (authorityGameMode.isNull()) return ptr(0);
            var gameState = authorityGameMode.add(0x280).readPointer();
            return (gameState && !gameState.isNull()) ? gameState : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function getGameMode() {
        try {
            var world = GWorld.readPointer();
            if (world.isNull()) return ptr(0);
            var gameMode = world.add(0x118).readPointer();
            return gameMode.isNull() ? ptr(0) : gameMode;
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

    function getHushSpellClass(gameInstance) {
        // 通道 1: 从 GameInstance.ThrallSpells (0x440) 直接读取第5个法术 (TS_Hush)
        try {
            if (gameInstance && !gameInstance.isNull()) {
                var thrallSpells = gameInstance.add(0x440);
                var count = thrallSpells.add(8).readU32();
                var data = thrallSpells.readPointer();
                if (count >= 5 && !data.isNull()) {
                    var hushClass = data.add(4 * Process.pointerSize).readPointer();
                    if (!hushClass.isNull()) return hushClass;
                }
            }
        } catch (e) {}

        // 通道 2: StaticFindObject
        return findClassByName('/Game/Blueprints/Game/Totems/TS_Hush.TS_Hush_C');
    }

    function castSilenceSpell(gameState) {
        try {
            if (!gameState || gameState.isNull()) return false;
            var world = GWorld.readPointer();
            if (world.isNull()) return false;

            var spellManagerClass = findClassByName('/Game/Blueprints/Game/Totems/BP_PlayerSpellManager.BP_PlayerSpellManager_C');
            if (spellManagerClass.isNull()) return false;

            var gameInstance = UDH_GameInstance_GetInstance(gameState);
            if (gameInstance.isNull()) return false;

            var hushSpellClass = getHushSpellClass(gameInstance);
            if (hushSpellClass.isNull()) return false;

            // 生成 SpellManager，以 GameState 为 Owner
            var spellManager = spawnActor(world, spellManagerClass, FTransform_Identity, gameState);
            if (spellManager.isNull()) return false;

            var thrallSpells = gameInstance.add(0x440);
            ADH_SpellManager_SetEquippedSpells(spellManager, thrallSpells);

            // 设置为 2 级 (45 秒):
            // 参数说明: 1=30秒, 2=45秒, 3=60秒
            ADH_SpellManager_SetSpellChargeTier(spellManager, 2);

            // 施放沉默术 (Target 为 ptr(0) 全局释放)
            var spellInstance = ADH_SpellManager_CastSpell(spellManager, hushSpellClass, ptr(0));
            return !spellInstance.isNull();
        } catch (e) {
            console.log('[开局沉默] 施法异常: ' + e);
            return false;
        }
    }

    var MatchSequence = 0;
    var MatchActive = false;
    var SilenceApplied = false;
    var RetryExhausted = false;
    var RetryTimer = null;
    var RetryAttempts = 0;
    var RetryIntervalMs = 250;
    var MaxRetryAttempts = 80; // 最多等待 20 秒

    function stopRetry() {
        if (RetryTimer !== null) {
            clearTimeout(RetryTimer);
            RetryTimer = null;
        }
    }

    function endObservedMatch() {
        if (!MatchActive) return;
        MatchActive = false;
        SilenceApplied = false;
        RetryExhausted = false;
        RetryAttempts = 0;
        stopRetry();
    }

    function scheduleSilenceAttempt(source, sequence) {
        if (!MatchActive || SilenceApplied || RetryExhausted || sequence !== MatchSequence || RetryTimer !== null) return;

        RetryTimer = setTimeout(function () {
            RetryTimer = null;
            if (!MatchActive || SilenceApplied || sequence !== MatchSequence) return;

            RetryAttempts++;
            try {
                /* HandleMatchHasStarted 的 onEnter 可能略早于状态写入，因此在这里再次确认。 */
                if (hasMatchStarted()) {
                    var gameState = getGameState();
                    if (!gameState.isNull()) {
                        if (ADH_GameStateBase_IsHushed(gameState) !== 0) {
                            SilenceApplied = true;
                            send('[开局沉默] 已确认当前对局处于沉默状态 [' + source + ']');
                            return;
                        }

                        if (castSilenceSpell(gameState)) {
                            SilenceApplied = true;
                            send(
                                '[开局沉默] 成功施放开局沉默 (2级, 45秒)' +
                                '，第 ' + RetryAttempts + ' 次尝试 [' + source + ']'
                            );
                            return;
                        }
                    }
                }
            } catch (e) {
                console.log('[开局沉默] 第 ' + RetryAttempts + ' 次尝试异常: ' + e);
            }

            if (RetryAttempts >= MaxRetryAttempts) {
                RetryExhausted = true;
                console.log('[开局沉默] 等待开局资源超时，本局未能施放沉默');
                return;
            }
            scheduleSilenceAttempt(source, sequence);
        }, RetryIntervalMs);
    }

    function beginObservedMatch(source, forceNewMatch) {
        if (forceNewMatch || !MatchActive) {
            MatchSequence++;
            MatchActive = true;
            SilenceApplied = false;
            RetryExhausted = false;
            RetryAttempts = 0;
            stopRetry();
        }
        scheduleSilenceAttempt(source, MatchSequence);
    }

    // 1. 对局开始 Hook: ADH_GameMode::HandleMatchHasStarted (0x26BDF30)
    // Hook 是最快触发通道；真实开局状态会在重试函数中再次确认。
    Interceptor.attach(base.add(0x26BDF30), {
        onEnter: function () {
            try {
                beginObservedMatch('MatchStarted', true);
            } catch (e) {
                console.log('[开局沉默] MatchStarted Hook 异常: ' + e);
            }
        }
    });

    // 2. 玩家生成 Hook: ADH_HumanCharacter::AddStartingInventory (0x26931D0)
    // 仅在游戏确认已经开局后作为补充触发，避免在大厅提前施法并消耗沉默时间。
    Interceptor.attach(base.add(0x26931D0), {
        onEnter: function (args) {
            try {
                var character = args[0];
                if (character.isNull()) return;
                if (hasMatchStarted()) beginObservedMatch('PlayerSpawn', false);
            } catch (e) {
                console.log('[开局沉默] PlayerSpawn Hook 异常: ' + e);
            }
        }
    });

    /* 状态监控负责补偿漏掉 Hook、注入较晚以及无玩家重新生成的情况。 */
    setInterval(function () {
        try {
            if (hasMatchStarted()) {
                beginObservedMatch('StateMonitor', false);
            } else {
                endObservedMatch();
            }
        } catch (e) {
            console.log('[开局沉默] 状态监控异常: ' + e);
        }
    }, 1000);
}
