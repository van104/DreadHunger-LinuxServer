/*
  仅观察并记录角色销毁事件，不阻止销毁，也不保留掉线角色。

  Linux symbols (基址 0x200000):
    UWorld::DestroyActor                  0x43F14F0  (void, AActor*, bool, bool)
    ADH_PlayerController::PawnLeavingGame 0x276D250  (void)
    APlayerController::PawnLeavingGame    0x458E540  (void)
    APlayerState::GetPlayerName           0x459E030
*/

var base = Process.findModuleByName('DreadHungerServer-Linux-Shipping').base;

if (base === null) {
    send('离线显示: 找不到 Linux 服务器模块');
} else {
    var DestroyActor = base.add(0x43F14F0);
    var ADH_PawnLeavingGame = base.add(0x276D250);
    var PawnLeavingGame = base.add(0x458E540);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);

    // APawn::PlayerState=0x240
    var PawnPlayerStateOffset = 0x240;

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var size = fstring.add(8).readU32();
            if (size < 1 || size > 80 || data.isNull()) return null;
            var range = Process.findRangeByAddress(data);
            if (range === null || range.protection.indexOf('r') < 0) return null;
            return data.readUtf16String(size);
        } catch (e) {
            return null;
        }
    }

    function getPlayerName(playerState) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out) || '';
        } catch (e) {
            return '';
        }
    }

    function describeActor(actor) {
        try {
            var playerState = actor.add(PawnPlayerStateOffset).readPointer();
            if (playerState.isNull()) return null;
            var name = getPlayerName(playerState);
            return { playerState: playerState.toString(), name: name };
        } catch (e) {
            return null;
        }
    }

    Interceptor.attach(DestroyActor, {
        onEnter: function (args) {
            try {
                var actor = args[1];
                if (actor.isNull()) return;
                var info = describeActor(actor);
                if (info === null || !info.name) return;
                send('[离线显示] 检测到玩家角色销毁: ' + info.name);
            } catch (e) {
                send('离线显示[观察] DestroyActor onEnter 错误: ' + e);
            }
        }
    });

    function pawnLeavingHook(name) {
        return {
            onEnter: function (args) {
                try {
                    var controller = args[0];
                    var pawn = null;
                    if (!controller.isNull()) {
                        // AController::Pawn 不可靠；默认不输出底层 Controller 地址。
                    }
                } catch (e) {
                    send('离线显示[观察] ' + name + ' onEnter 错误: ' + e);
                }
            }
        };
    }

    Interceptor.attach(ADH_PawnLeavingGame, pawnLeavingHook('ADH_PawnLeavingGame'));
    Interceptor.attach(PawnLeavingGame, pawnLeavingHook('PawnLeavingGame'));
}
