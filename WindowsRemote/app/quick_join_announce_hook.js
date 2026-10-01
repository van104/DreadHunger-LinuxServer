/* 快速进服器：进服后在本机左侧狼人消息通道显示一次自定义公告。 */
(function () {
    var module = Process.findModuleByName('DreadHunger-Win64-Shipping.exe');
    if (module === null) return;
    var base = module.base;

    var modulePath = module.path.replace(/\//g, '\\');
    var TriggerFile = modulePath.substring(0, modulePath.lastIndexOf('\\')) + '\\quick_join_announce.json';
    var FText_FromString = new NativeFunction(base.add(0x110DC60), 'pointer', ['pointer', 'pointer'], 'win64');
    var LastTriggerId = '';
    var PendingAnnouncement = null;
    var LastController = ptr(0);
    var StableControllerTicks = 0;

    function logInfo(text) {
        try {
            var file = new File('output.log', 'a');
            file.write('[快速进服公告] ' + text + '\n');
            file.close();
        } catch (e) {}
    }

    function readable(pointer) {
        if (!pointer || pointer.isNull()) return false;
        try {
            var range = Process.findRangeByAddress(pointer);
            return range !== null && range.protection.indexOf('r') >= 0;
        } catch (e) {
            return false;
        }
    }

    function executable(pointer) {
        if (!pointer || pointer.isNull()) return false;
        try {
            var range = Process.findRangeByAddress(pointer);
            return range !== null && range.protection.indexOf('x') >= 0;
        } catch (e) {
            return false;
        }
    }

    function getLocalController() {
        try {
            var slot = base.add(0x4C70908).readPointer();
            if (!readable(slot)) return ptr(0);
            var inputComponent = slot.readPointer();
            if (!readable(inputComponent)) return ptr(0);
            var pawn = inputComponent.add(0x20).readPointer();
            if (!readable(pawn)) return ptr(0);
            var controller = pawn.add(0x258).readPointer();
            return readable(controller) ? controller : ptr(0);
        } catch (e) {
            return ptr(0);
        }
    }

    function makeFText(text) {
        var source = Memory.alloc((text.length + 1) * 2);
        source.writeUtf16String(text);
        var fstring = Memory.alloc(16);
        fstring.writePointer(source);
        fstring.add(8).writeU32(text.length + 1);
        fstring.add(12).writeU32(text.length + 1);
        var ftext = Memory.alloc(24);
        FText_FromString(ftext, fstring);
        return ftext;
    }

    function sendAnnouncement(controller, text) {
        var vtable = controller.readPointer();
        var receiveAddress = vtable.add(0xE70).readPointer();
        if (!executable(receiveAddress)) throw new Error('ReceiveThrallMessage 地址无效');
        var receive = new NativeFunction(receiveAddress, 'void', ['pointer', 'pointer', 'pointer'], 'win64');
        receive(controller, makeFText(text), ptr(0));
    }

    function clearTrigger() {
        try {
            var file = new File(TriggerFile, 'w');
            file.write('{}');
            file.flush();
            file.close();
        } catch (e) {}
    }

    function readTrigger() {
        var file = new File(TriggerFile, 'r');
        var raw = file.readText();
        file.close();
        return raw;
    }

    function pollTrigger() {
        try {
            var raw = readTrigger();
            var command = JSON.parse(raw);
            var triggerId = String(command.id || '');
            var text = String(command.text || '').trim();
            if (!triggerId || triggerId === LastTriggerId || !text) return;
            if (Number(command.expires_at || 0) < Date.now()) {
                LastTriggerId = triggerId;
                clearTrigger();
                return;
            }
            LastTriggerId = triggerId;
            clearTrigger();
            PendingAnnouncement = {
                text: text,
                notBefore: Date.now() + 3000,
                expiresAt: Number(command.expires_at || 0)
            };
            LastController = ptr(0);
            StableControllerTicks = 0;
            logInfo('已接收公告，等待游戏线程和角色控制器稳定');
        } catch (e) {
            /* 文件不存在或正在原子替换时等待下次轮询。 */
        }
    }

    Interceptor.attach(base.add(0xEEB100), {
        onLeave: function () {
            if (PendingAnnouncement === null || Date.now() < PendingAnnouncement.notBefore) return;
            if (PendingAnnouncement.expiresAt < Date.now()) {
                PendingAnnouncement = null;
                return;
            }
            var controller = getLocalController();
            if (controller.isNull()) {
                LastController = ptr(0);
                StableControllerTicks = 0;
                return;
            }
            if (!LastController.isNull() && controller.equals(LastController)) {
                StableControllerTicks += 1;
            } else {
                LastController = controller;
                StableControllerTicks = 1;
            }
            if (StableControllerTicks < 30) return;
            var announcement = PendingAnnouncement;
            PendingAnnouncement = null;
            try {
                sendAnnouncement(controller, announcement.text);
                logInfo('已在游戏线程显示公告：' + announcement.text.replace(/\r?\n/g, ' / '));
            } catch (e) {
                logInfo('公告显示失败：' + e.message);
            }
        }
    });

    setInterval(pollTrigger, 500);
    logInfo('Hook 已加载（游戏线程安全模式）');
})();
