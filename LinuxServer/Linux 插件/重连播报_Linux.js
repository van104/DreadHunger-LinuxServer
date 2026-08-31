/*
   重连播报: 断线 10 分钟内重进广播“用户名（职业）重新连接服务器”。

   已核对 Linux 符号:
   - AGameMode::Logout(AController*)                 = base + 0x43357F0
   - AGameMode::PostLogin(APlayerController*)        = base + 0x4335480
   - AGameModeBase::PostLogin(APlayerController*)    = base + 0x4335680
   - ADH_LobbyGameMode::PostLogin(APlayerController*)= base + 0x2724320

   注意: base + 0x2790560 不是 PostLogin，而是 ADH_PrisonerPawn::Died()
   函数内部地址。禁止在该地址安装 Hook，否则牢房玩家长按 L 时会崩溃。
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');
var base = mod !== null ? mod.base : null;

if (base !== null) {
    var LogoutBase = base.add(0x43357F0);
    var PostLoginAddresses = [
        { name: 'AGameMode::PostLogin', address: base.add(0x4335480) },
        { name: 'AGameModeBase::PostLogin', address: base.add(0x4335680) },
        { name: 'ADH_LobbyGameMode::PostLogin', address: base.add(0x2724320) }
    ];
    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var ReceiveGameplayMessage = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var GWorld = base.add(0x5C9B6D0);

    var ReconnectWindowMs = 10 * 60 * 1000;

    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航'
    };

    var DisconnectedPlayers = {};
    var RecentReconnects = {};

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

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
            if (!isReadable(playerState) || !isReadable(playerState.add(0x10))) return '';
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out) || '';
        } catch (e) { return ''; }
    }

    function getRoleName(playerState) {
        try {
            if (!isReadable(playerState) || !isReadable(playerState.add(0x588))) return null;
            var role = playerState.add(0x588).readPointer();
            if (!isReadable(role) || !isReadable(role.add(0x48))) return null;
            var onlineName = readFString(role.add(0x48));
            if (!onlineName) return null;
            return RoleNames[onlineName] || onlineName;
        } catch (e) { return null; }
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
            /* 屏幕中间上方弹窗: 用 ReceiveGameplayMsg 通道 + 尾部空行推高(同赢牌对家开船逻辑) */
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

    function nameOfController(controller) {
        try {
            if (!isReadable(controller) || !isReadable(controller.add(0x228))) return '';
            var playerState = controller.add(0x228).readPointer();
            if (!isReadable(playerState)) return '';
            return getPlayerName(playerState);
        } catch (e) { return ''; }
    }

    /*
       延迟阶段不保留 Controller/PlayerState 裸指针。
       重连玩家可能在计时器触发前再次掉线，旧指针会变成悬空对象；
       每次都从当前 GameState.PlayerArray 重新查找在线 PlayerState。
    */
    function findCurrentPlayerStateByName(name) {
        try {
            var gameState = getGameState();
            if (!isReadable(gameState) || !isReadable(gameState.add(0x238))) return ptr(0);

            var playerArray = gameState.add(0x238);
            var data = playerArray.readPointer();
            var count = playerArray.add(8).readU32();
            if (!isReadable(data) || count > 64) return ptr(0);

            for (var i = 0; i < count; i++) {
                var slot = data.add(i * Process.pointerSize);
                if (!isReadable(slot)) continue;
                var playerState = slot.readPointer();
                if (!isReadable(playerState)) continue;
                if (getPlayerName(playerState) === name) return playerState;
            }
        } catch (e) {}
        return ptr(0);
    }

    Interceptor.attach(LogoutBase, {
        onEnter: function (args) {
            try {
                var controller = args[1];
                if (controller.isNull()) return;
                var name = nameOfController(controller);
                if (name) DisconnectedPlayers[name] = Date.now();
            } catch (e) {}
        }
    });

    function handlePostLogin(args) {
        try {
            var controller = args[1];
            if (controller.isNull()) return;
            var name = nameOfController(controller);
            if (!name) return;
            var now = Date.now();
            var disconnectedAt = DisconnectedPlayers[name];
            if (!disconnectedAt || now - disconnectedAt > ReconnectWindowMs) return;

            delete DisconnectedPlayers[name];

            if (RecentReconnects[name] && now - RecentReconnects[name] < 3000) return;
            RecentReconnects[name] = now;

            var attempts = 0;
            var timer = setInterval(function () {
                attempts++;
                try {
                    var ps = findCurrentPlayerStateByName(name);
                    var role = !ps.isNull() ? getRoleName(ps) : null;
                    if (role || attempts >= 5) {
                        clearInterval(timer);
                        var who = name;
                        if (role) who += '（' + role + '）';
                        broadcast(who + '重新连接服务器');
                    }
                } catch (e) { clearInterval(timer); }
            }, 1000);
        } catch (e) {}
    }

    PostLoginAddresses.forEach(function (hook) {
        try {
            Interceptor.attach(hook.address, {
                onEnter: function (args) { handlePostLogin(args); }
            });
        } catch (e) {
            console.log('[重连播报] Hook 安装失败: ' + hook.name + ', ' + e);
        }
    });
}
