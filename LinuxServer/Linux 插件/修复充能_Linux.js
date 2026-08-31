/* 修复充能: 狼人生成时稳定补充法术充能 +0.07
   当前 Linux 服务端二进制:
   - ADH_PlayerState::SpellManager = PlayerState + 0x480
   - ADH_PlayerState::ModifySpellChargeLevel(float) = base + 0x277FA90
   不再固定等待 5 秒后直接写内存，而是等待 SpellManager 就绪后调用游戏原生函数。 */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;
    var ADH_HumanCharacter_AddStartingInventory_addr = base.add(0x26931D0);
    var ADH_GameMode_HandleMatchHasStarted_addr = base.add(0x26BDF30);
    var ADH_PlayerState_ModifySpellChargeLevel = new NativeFunction(
        base.add(0x277FA90),
        'void',
        ['pointer', 'float']
    );
    var ADH_PlayerState_GetSpellChargeLevel = new NativeFunction(
        base.add(0x277FAF0),
        'float',
        ['pointer']
    );

    var PlayerStateOffset = 0x240;
    var SpellManagerOffset = 0x480;
    var ChargeDelta = 0.07;
    var RetryIntervalMs = 500;
    var MaxAttempts = 40; // 最多等待 20 秒

    var MatchGeneration = 0;
    var PendingPlayers = Object.create(null);
    var AppliedPlayers = Object.create(null);

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

    function clearMatchState() {
        MatchGeneration++;
        AppliedPlayers = Object.create(null);
        /* 不清理 PendingPlayers：部分地图会先发背包、后触发正式开局，
           取消等待会让这一局永久错过 SpellManager。 */
    }

    function waitAndApplyCharge(playerState) {
        if (!isReadable(playerState)) return;

        var playerKey = playerState.toString();
        if (PendingPlayers[playerKey] || AppliedPlayers[playerKey] === MatchGeneration) return;

        var attempts = 0;
        PendingPlayers[playerKey] = true;

        function attempt() {
            attempts++;
            try {
                var managerAddress = playerState.add(SpellManagerOffset);
                if (!isReadable(managerAddress)) {
                    delete PendingPlayers[playerKey];
                    console.log('[修复充能] PlayerState 已失效，停止本次充能');
                    return;
                }

                var spellManager = managerAddress.readPointer();
                if (!spellManager.isNull() && isReadable(spellManager)) {
                    var before = ADH_PlayerState_GetSpellChargeLevel(playerState);
                    ADH_PlayerState_ModifySpellChargeLevel(playerState, ChargeDelta);
                    var after = ADH_PlayerState_GetSpellChargeLevel(playerState);

                    /* 使用实际执行时所在的对局编号；等待期间可能刚好切换到新对局。 */
                    AppliedPlayers[playerKey] = MatchGeneration;
                    delete PendingPlayers[playerKey];
                    console.log(
                        '[修复充能] 已补充充能（等待 ' +
                        (attempts * RetryIntervalMs) + 'ms）'
                    );
                    return;
                }
            } catch (e) {
                delete PendingPlayers[playerKey];
                console.log('[修复充能] 执行异常: ' + e);
                return;
            }

            if (attempts >= MaxAttempts) {
                delete PendingPlayers[playerKey];
                console.log('[修复充能] 等待 SpellManager 超时，本次未修改');
                return;
            }

            setTimeout(attempt, RetryIntervalMs);
        }

        setTimeout(attempt, RetryIntervalMs);
    }

    /* 对局开始时允许同一 PlayerState 在新一局再次获得修复。 */
    Interceptor.attach(ADH_GameMode_HandleMatchHasStarted_addr, {
        onEnter: function () {
            clearMatchState();
        }
    });

    Interceptor.attach(ADH_HumanCharacter_AddStartingInventory_addr, {
        onEnter: function (args) {
            try {
                var character = args[0];
                if (!isReadable(character)) return;

                var playerStateAddress = character.add(PlayerStateOffset);
                if (!isReadable(playerStateAddress)) return;

                var playerState = playerStateAddress.readPointer();
                if (playerState.isNull()) return;
                waitAndApplyCharge(playerState);
            } catch (e) {
                console.log('[修复充能] AddStartingInventory 异常: ' + e);
            }
        }
    });
}
