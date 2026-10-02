/* 快速进服器：进服后在本机左侧狼人消息通道显示一次自定义公告。 */
(function () {
    var module = Process.findModuleByName('DreadHunger-Win64-Shipping.exe');
    if (module === null) return;
    var base = module.base;

    var modulePath = module.path.replace(/\//g, '\\');
    var TriggerFile = modulePath.substring(0, modulePath.lastIndexOf('\\')) + '\\quick_join_announce.json';
    var ResultFile = modulePath.substring(0, modulePath.lastIndexOf('\\')) + '\\quick_join_announce_result.json';
    var FText_FromString = new NativeFunction(base.add(0x110DC60), 'pointer', ['pointer', 'pointer'], 'win64');
    var LastTriggerId = '';
    var PendingAnnouncement = null;

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
        // 新消息置顶，逆序发送保持原文从上到下的顺序。
        text.split(/\r\n|\r|\n/).reverse().forEach(function (line) {
            if (line.trim()) receive(controller, makeFText(line), ptr(0));
        });
    }

    function writeResult(id, success, error) {
        var file = new File(ResultFile, 'w');
        try {
            file.write(JSON.stringify({id: id, success: success, error: error || ''}));
            file.flush();
        } finally {
            file.close();
        }
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
            if (!triggerId || triggerId === LastTriggerId || !text || Array.from(text).length > 1000) return;
            var expiresAt = Number(command.expires_at || 0);
            if (!Number.isFinite(expiresAt) || expiresAt < Date.now()) {
                LastTriggerId = triggerId;
                clearTrigger();
                writeResult(triggerId, false, '原生公告已过期');
                return;
            }
            LastTriggerId = triggerId;
            clearTrigger();
            PendingAnnouncement = {
                id: triggerId,
                text: text,
                expiresAt: expiresAt
            };
            logInfo('已接收公告，等待本机 PlayerController 游戏线程');
        } catch (e) {
            /* 文件不存在或正在原子替换时等待下次轮询。 */
        }
    }

    Interceptor.attach(base.add(0xECA910), {
        onEnter: function (args) {
            this.controller = args[0];
        },
        onLeave: function () {
            if (PendingAnnouncement === null) return;
            if (PendingAnnouncement.expiresAt < Date.now()) {
                writeResult(PendingAnnouncement.id, false, '等待游戏原生提示超时');
                PendingAnnouncement = null;
                return;
            }
            var controller = this.controller;
            if (!readable(controller)) return;
            var announcement = PendingAnnouncement;
            PendingAnnouncement = null;
            try {
                sendAnnouncement(controller, announcement.text);
                writeResult(announcement.id, true, '');
                logInfo('已在游戏线程显示公告：' + announcement.text.replace(/\r?\n/g, ' / '));
            } catch (e) {
                writeResult(announcement.id, false, e.message);
                logInfo('公告显示失败：' + e.message);
            }
        }
    });

    setInterval(pollTrigger, 100);
    logInfo('Hook 已加载（游戏线程安全模式）');
})();
