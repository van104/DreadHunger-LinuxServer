/* 退出播报: 玩家退出/断开时广播"用户名 职业 退出了" */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');
var base = mod !== null ? mod.base : null;

if (base !== null) {
    var Logout = base.add(0x43357F0);
    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var GWorld = base.add(0x5C9B6D0);

    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程师', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航'
    };

    var RecentLogouts = {};

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
            var message = makeFText(text);
            for (var i = 0; i < count; i++) {
                try {
                    var playerState = playerArray.readPointer().add(i * 8).readPointer();
                    if (playerState.isNull()) continue;
                    var controllerId = playerState.add(0x224).readU8();
                    var controller = GetPlayerController(playerState, controllerId);
                    if (!controller.isNull()) ReceiveThrallMessage(controller, message, ptr(0));
                } catch (e) {}
            }
        } catch (e) {}
    }

    Interceptor.attach(Logout, {
        onEnter: function (args) {
            try {
                var controller = args[1];
                if (controller.isNull()) return;
                var key = controller.toString();
                var now = Date.now();
                if (RecentLogouts[key] && now - RecentLogouts[key] < 3000) return;
                RecentLogouts[key] = now;

                var playerState = controller.add(0x228).readPointer();
                if (playerState.isNull()) return;

                var name = getPlayerName(playerState);
                var role = getRoleName(playerState);

                var who = name || '玩家';
                if (role) who += '（' + role + '）';

                broadcast(who + '退出了服务器');
            } catch (e) {}
        }
    });
}
