/* 死亡播报: 第一次"坐牢了!", 之后"死透了!" (死亡后延迟 7 秒播放) */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');
var base = mod !== null ? mod.base : null;

if (base !== null) {
    var Died = base.add(0x2683AD0);
    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var ReceiveGameplayMessage = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var APlayerState_GetControlledDoppelganger = new NativeFunction(base.add(0x2981910), 'pointer', ['pointer']);
    var GWorld = base.add(0x5C9B6D0);

    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程师', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航'
    };

    var DeathCounts = {};
    var RecentDeaths = {};

    function makeFText(text) {
        var nameBuffer = Memory.alloc(8);
        var textBuffer = Memory.alloc(24);
        var source = Memory.alloc((text.length + 4) * 2);
        source.writeUtf16String(text);
        FName_FName(nameBuffer, source, 1);
        FText_FromName(textBuffer, nameBuffer);
        return textBuffer;
    }

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var size = fstring.add(8).readU32();
            if (size < 1 || size > 80 || data.isNull()) return null;
            var range = Process.findRangeByAddress(data);
            if (range === null || range.protection.indexOf('r') < 0) return null;
            return data.readUtf16String(size);
        } catch (e) { return null; }
    }

    function getPlayerName(playerState) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out) || '';
        } catch (e) { return ''; }
    }

    function getRoleName(playerState) {
        try {
            var role = playerState.add(0x588).readPointer();
            if (role.isNull()) return null;
            var onlineName = readFString(role.add(0x48));
            if (!onlineName) return null;
            return RoleNames[onlineName] || onlineName;
        } catch (e) { return null; }
    }

    function isControlledDoppelgangerDeath(character, playerState) {
        try {
            var doppelganger = APlayerState_GetControlledDoppelganger(playerState);
            return !doppelganger.isNull() && doppelganger.equals(character);
        } catch (e) {
            /* 判断失败时保留原死亡流程，避免漏报真实死亡。 */
            return false;
        }
    }

    function getGameState() {
        try {
            var world = GWorld.readPointer();
            if (world.isNull()) return ptr(0);
            var gameMode = world.add(0x118).readPointer();
            if (gameMode.isNull()) return ptr(0);
            return gameMode.add(0x280).readPointer();
        } catch (e) { return ptr(0); }
    }

    function broadcast(text) {
        try {
            var gameState = getGameState();
            if (gameState.isNull()) return;
            var playerArray = gameState.add(0x238);
            var count = playerArray.add(8).readU32();
            if (count > 64) return;
            /* 屏幕中间上方弹窗: 用 ReceiveGameplayMsg 通道 + 尾部空行推高 */
            var title = makeFText(' ');
            var padding = '';
            for (var i = 0; i < 10; i++) padding += '\n';
            var message = makeFText(text + padding);
            for (var j = 0; j < count; j++) {
                try {
                    var playerState = playerArray.readPointer().add(j * 8).readPointer();
                    if (playerState.isNull()) continue;
                    var controllerId = playerState.add(0x224).readU8();
                    var controller = GetPlayerController(playerState, controllerId);
                    if (!controller.isNull()) ReceiveGameplayMessage(controller, message, ptr(0), ptr(0), title);
                } catch (e) {}
            }
        } catch (e) {}
    }

    Interceptor.attach(Died, {
        onEnter: function (args) {
            try {
                var character = args[0];
                if (character.isNull()) return;
                var playerState = character.add(0x240).readPointer();
                if (playerState.isNull()) return;

                /* 分身与本体共享 PlayerState；分身死亡不代表玩家本体死亡。 */
                if (isControlledDoppelgangerDeath(character, playerState)) return;

                var key = playerState.toString();
                var now = Date.now();
                if (RecentDeaths[key] && now - RecentDeaths[key] < 7000) return;
                RecentDeaths[key] = now;

                var deathCount = DeathCounts[key] || 0;
                DeathCounts[key] = deathCount + 1;

                var name = getPlayerName(playerState);
                var role = getRoleName(playerState);
                var suffix = deathCount === 0 ? '坐牢了！' : '死透了！';

                var who = name || '玩家';
                if (role) who += '（' + role + '）';
                var text = who + suffix;

                setTimeout(function () {
                    try {
                        broadcast(text);
                    } catch (e) {}
                }, 7000);
            } catch (e) {}
        }
    });
}
