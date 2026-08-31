/*
========================================
 公告推送插件 (Linux 服务端)
 模拟 GM 控制台的发送功能, 从 gm_announce.json 读取消息
 使用 ReceiveGameplayMessage (居中顶部显示, 与 GM 控制台一致)
========================================
 配置文件: gm_announce.json
 格式: { "message": "消息内容(支持\\n换行)", "interval": 10, "repeat": 3, "delay": 10 }
*/

var base = Process.findModuleByName('DreadHungerServer-Linux-Shipping').base;

/* ===== 配置文件路径 (绝对路径) ===== */
var AnnounceFile = '/www/wwwroot/Dread Hunger/LinuxServer/gm_announce.json';
var PollIntervalSec = 2;        // 检测新玩家间隔(秒)
/* ============================ */

/* ===== 偏移表 (Linux) ===== */
var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
var UGameplayStatics_GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
var ReceiveGameplayMsg = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
var GWorld = base.add(0x5C9B6D0);

/* ===== libc unlink (原子删除) ===== */
var _unlinkPtr = null;
try {
    var mods = Process.enumerateModules();
    for (var i = 0; i < mods.length; i++) {
        if (mods[i].name.indexOf('libc') !== -1) {
            _unlinkPtr = Module.findExportByName(mods[i].name, 'unlink');
            if (_unlinkPtr) break;
        }
    }
} catch (e) {}
var _unlink = _unlinkPtr ? new NativeFunction(_unlinkPtr, 'int32', ['pointer']) : null;

function newFName(Name) {
    var FName_Buffer = Memory.alloc(8);
    var Buffer = Memory.alloc((Name.length + 4) * 2);
    Buffer.writeUtf16String(Name);
    FName_FName(FName_Buffer, Buffer, 1);
    return FName_Buffer;
}

function FNameToFText(FName) {
    var FText_Buffer = Memory.alloc(24);
    FText_FromName(FText_Buffer, FName);
    return FText_Buffer;
}

function makeFText(text) {
    return FNameToFText(newFName(text));
}

function getGameState() {
    var World = GWorld.readPointer();
    if (World.isNull()) return ptr(0);
    var GameMode = World.add(0x118).readPointer();
    if (GameMode.isNull()) return ptr(0);
    return GameMode.add(0x280).readPointer();
}

/* 读取公告配置文件 */
function readAnnounceConfig() {
    try {
        var text = File.readAllText(AnnounceFile);
        if (!text || !text.trim()) return null;
        return JSON.parse(text);
    } catch (e) { return null; }
}

/* 发送消息给单个玩家 (完全模拟 GM 控制台的 gmSendMessage) */
function sendMessageToPlayer(PC, message) {
    if (PC.isNull() || !message) return;
    try {
        var msgText = makeFText(message);
        var titleText = makeFText(' ');
        ReceiveGameplayMsg(PC, msgText, ptr(0), ptr(0), titleText);
    } catch (e) { /* 玩家状态不稳, 跳过 */ }
}

/* 发送消息给所有在线玩家 */
function sendMessageToAll(message) {
    if (!message) return 0;
    var GameState = getGameState();
    if (GameState.isNull()) return 0;
    var PlayerArray = GameState.add(0x238);
    var Num = PlayerArray.add(8).readU32();
    var count = 0;
    for (var i = 0; i < Num; i++) {
        var PS = PlayerArray.readPointer().add(i * 8).readPointer();
        if (PS.isNull()) continue;
        try {
            var idx = PS.add(0x224).readU8();
            var PC = UGameplayStatics_GetPlayerController(PS, idx);
            if (!PC.isNull()) {
                sendMessageToPlayer(PC, message);
                count++;
            }
        } catch (e) {}
    }
    return count;
}

// 玩家是否还在线
function isPlayerOnline(PS) {
    try {
        var GameState = getGameState();
        if (GameState.isNull()) return false;
        var PlayerArray = GameState.add(0x238);
        var Num = PlayerArray.add(8).readU32();
        for (var i = 0; i < Num; i++) {
            var p = PlayerArray.readPointer().add(i * 8).readPointer();
            if (!p.isNull() && p.equals(PS)) return true;
        }
    } catch (e) {}
    return false;
}

var KnownPlayers = {};

// 玩家进服: 从配置文件读取消息, 延迟后推送 + 间隔重复
function announceToPlayer(PC, PS) {
    var config = readAnnounceConfig();
    if (!config || !config.message) return;

    var delay = (config.delay || 10) * 1000;
    var interval = (config.interval || 10) * 1000;
    var repeat = config.repeat || 3;
    var message = config.message;

    setTimeout(function () {
        if (!isPlayerOnline(PS)) return;
        sendMessageToPlayer(PC, message);
        var count = 1;
        var iv = setInterval(function () {
            if (!isPlayerOnline(PS)) { clearInterval(iv); return; }
            // 每次重新读取配置 (支持热更新)
            var cfg = readAnnounceConfig();
            var msg = (cfg && cfg.message) ? cfg.message : message;
            sendMessageToPlayer(PC, msg);
            count++;
            if (count >= repeat) clearInterval(iv);
        }, interval);
    }, delay);
}

// 轮询检测新玩家进入
setInterval(function () {
    var GameState = getGameState();
    if (GameState.isNull()) return;
    var PlayerArray = GameState.add(0x238);
    var Num = PlayerArray.add(8).readU32();

    var online = {};
    for (var i = 0; i < Num; i++) {
        var PS = PlayerArray.readPointer().add(i * 8).readPointer();
        if (PS.isNull()) continue;
        var key = PS.toString();
        online[key] = true;
        if (KnownPlayers[key]) continue;

        KnownPlayers[key] = true;
        var idx = PS.add(0x224).readU8();
        var PC = UGameplayStatics_GetPlayerController(PS, idx);
        if (PC.isNull()) continue;
        announceToPlayer(PC, PS);
    }
    // 清理已离开玩家
    for (var k in KnownPlayers) {
        if (!online[k]) delete KnownPlayers[k];
    }
}, PollIntervalSec * 1000);
