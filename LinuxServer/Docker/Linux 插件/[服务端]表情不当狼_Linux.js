/*
   [服务端]表情不当狼: 打牌阶段长按Y选择表情发5次，自愿放弃当狼。
   仅在打牌阶段发送3次提示(分两条信息，间隔10秒)
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var SetIsThrall = new NativeFunction(base.add(0x277F060), 'void', ['pointer', 'uint8']);
    var GWorld = base.add(0x5C9B6D0);
    var HandleStartingNewPlayer = base.add(0x26CB970);

    var EmoteCounts = {};
    var OptOutThralls = {};
    var ReservedThralls = {};
    var LastEmoteTime = {};
    var IsBroadcastingTip = false;
    var BroadcastGeneration = 0;

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

    function newFName(text) {
        var nameBuffer = Memory.alloc(8);
        var source = Memory.alloc((text.length + 4) * 2);
        source.writeUtf16String(text);
        FName_FName(nameBuffer, source, 1);
        return nameBuffer;
    }

    function makeFText(text) {
        var textBuffer = Memory.alloc(24);
        FText_FromName(textBuffer, newFName(text));
        return textBuffer;
    }

    function getFString(fstring) {
        try {
            var num = fstring.add(8).readU32();
            if (num <= 0 || num > 4096) return '';
            var data = fstring.readPointer();
            if (data.isNull()) return '';
            return data.readUtf16String(num);
        } catch (e) { return ''; }
    }

    function getPlayerName(ps) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, ps);
            return getFString(out) || '玩家';
        } catch (e) { return '玩家'; }
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

    function isAlreadyThrall(playerState) {
        try {
            var flag = playerState.add(0x56A);
            return !isReadable(flag) || flag.readU8() !== 0;
        } catch (e) {
            /* 无法确认时不把该玩家放进候选池，避免重复或错误转交。 */
            return true;
        }
    }

    /* 单次向全员左侧消息通道发送两条提示信息 */
    function sendTipOnceToAll() {
        try {
            var gs = getGameState();
            if (!isReadable(gs)) return 0;
            var playerArray = gs.add(0x238);
            var count = playerArray.add(8).readU32();
            if (count === 0 || count > 64) return 0;

            var playerData = playerArray.readPointer();
            if (!isReadable(playerData)) return 0;

            var msg1 = makeFText('5次表情不当狼');
            var msg2 = makeFText('长按Y选择5次表情自愿放弃当狼');
            var recipients = 0;

            for (var i = 0; i < count; i++) {
                try {
                    var slot = playerData.add(i * Process.pointerSize);
                    if (!isReadable(slot)) continue;
                    var ps = slot.readPointer();
                    if (!isReadable(ps)) continue;
                    var controllerId = ps.add(0x224).readU8();
                    var ctrl = GetPlayerController(ps, controllerId);
                    if (!ctrl.isNull()) {
                        ReceiveThrallMessage(ctrl, msg1, ptr(0));
                        ReceiveThrallMessage(ctrl, msg2, ptr(0));
                        recipients++;
                    }
                } catch (eInner) {}
            }

            return recipients;
        } catch (e) {
            console.log('[不当狼] sendTipOnceToAll 异常: ' + e);
            return 0;
        }
    }

    /* 打牌阶段连续发送 3 次，每次间隔 10 秒 */
    function startOpeningBroadcast() {
        if (IsBroadcastingTip) return;
        IsBroadcastingTip = true;

        var generation = ++BroadcastGeneration;
        var timesSent = 0;
        var readinessAttempts = 0;
        function loop() {
            if (generation !== BroadcastGeneration) return;

            var recipients = sendTipOnceToAll();
            if (recipients > 0) {
                timesSent++;
                readinessAttempts = 0;
            } else {
                readinessAttempts++;
            }

            if (timesSent >= 3) {
                return;
            }

            if (recipients === 0 && readinessAttempts < 60) {
                /* 服务端自动分配职业发生得很早，等待 Controller/PlayerArray 就绪。 */
                setTimeout(loop, 500);
            } else if (recipients > 0) {
                setTimeout(loop, 10000);
            } else {
                IsBroadcastingTip = false;
                console.log('[不当狼] 等待玩家控制器超时，本次提示未启动，允许后续事件重试');
            }
        }

        /* 自动随机职业会在玩家进入流程早期触发，首次稍作延迟并允许继续重试。 */
        setTimeout(loop, 500);
    }

    /* 寻找未放弃当狼的候选人替补 */
    function reassignThrallToCandidate(excludedPS) {
        try {
            var gs = getGameState();
            if (gs.isNull()) return;
            var playerArray = gs.add(0x238);
            var num = playerArray.add(8).readU32();
            var playerData = playerArray.readPointer();
            if (num === 0 || num > 64 || !isReadable(playerData)) return;
            var candidates = [];
            for (var i = 0; i < num; i++) {
                var slot = playerData.add(i * Process.pointerSize);
                if (!isReadable(slot)) continue;
                var candidatePS = slot.readPointer();
                if (!isReadable(candidatePS) || candidatePS.equals(excludedPS)) continue;
                var cKey = candidatePS.toString();
                if (!OptOutThralls[cKey] && !ReservedThralls[cKey] && !isAlreadyThrall(candidatePS)) {
                    candidates.push(candidatePS);
                }
            }
            if (candidates.length > 0) {
                var pick = candidates[Math.floor(Math.random() * candidates.length)];
                var pickKey = pick.toString();
                /* SetIsThrall 延迟执行前立即预留，防止并发转交再次选中同一玩家。 */
                ReservedThralls[pickKey] = true;
                console.log('[不当狼] 狼人资格转交予候选人: ' + getPlayerName(pick));
                setTimeout(function () {
                    try {
                        SetIsThrall(pick, 1);
                    } catch (e) {
                        delete ReservedThralls[pickKey];
                        console.log('[不当狼] 设置替补狼人失败: ' + e);
                    }
                }, 150);
            } else {
                console.log('[不当狼] 无剩余候选人，本局成为无狼和平局');
            }
        } catch (e) {
            console.log('[不当狼] 转交狼人异常: ' + e);
        }
    }

    function handlePlayerEmote(pawn) {
        try {
            if (pawn.isNull()) return;

            var ctrl = ptr(0);
            var c1 = pawn.add(0x258).readPointer();
            var c2 = pawn.add(0x338).readPointer();
            ctrl = (c1 && !c1.isNull()) ? c1 : c2;

            var ps = ptr(0);
            if (!ctrl.isNull()) {
                ps = ctrl.add(0x228).readPointer();
            }
            if (ps.isNull()) {
                ps = pawn.add(0x240).readPointer();
            }
            if (ps.isNull()) return;

            if (ctrl.isNull()) {
                var controllerId = ps.add(0x224).readU8();
                ctrl = GetPlayerController(ps, controllerId);
            }
            if (ctrl.isNull()) return;

            var key = ps.toString();
            var now = Date.now();

            /* 防连击抖动 (500ms) */
            if (LastEmoteTime[key] && (now - LastEmoteTime[key]) < 500) return;
            LastEmoteTime[key] = now;

            var name = getPlayerName(ps);

            if (OptOutThralls[key]) {
                var infoDone = makeFText('不当狼：5/5 (已生效：本局放弃当狼)');
                ReceiveThrallMessage(ctrl, infoDone, ptr(0));
                return;
            }

            var count = (EmoteCounts[key] || 0) + 1;
            EmoteCounts[key] = count;

            if (count < 5) {
                var textStr = '不当狼：' + count + '/5';
                var msgThrall = makeFText(textStr);

                /* 左侧狼人消息通道私信推送 */
                ReceiveThrallMessage(ctrl, msgThrall, ptr(0));

            } else {
                OptOutThralls[key] = true;
                var successStr = '不当狼：5/5 (已成功放弃当狼！本局将作为好人)';
                var successThrall = makeFText(successStr);

                ReceiveThrallMessage(ctrl, successThrall, ptr(0));

                console.log('[不当狼] 玩家 [' + name + '] 成功达成 5 次表情，本局放弃当狼！');
            }
        } catch (e) {
            console.log('[不当狼] handlePlayerEmote 异常: ' + e);
        }
    }

    /* 1. Hook ADH_LobbyPawn::ServerPlayEmote_Implementation @ 0x272B060 */
    Interceptor.attach(base.add(0x272B060), {
        onEnter: function (args) {
            handlePlayerEmote(args[0]);
        }
    });

    /* 2. Hook ADH_LobbyPawn::PlayEmote @ 0x272ACE0 */
    Interceptor.attach(base.add(0x272ACE0), {
        onEnter: function (args) {
            handlePlayerEmote(args[0]);
        }
    });

    /* 3. Hook ADH_PrisonerPawn::ServerPlayEmote_Implementation @ 0x27915C0 */
    Interceptor.attach(base.add(0x27915C0), {
        onEnter: function (args) {
            handlePlayerEmote(args[0]);
        }
    });

    /* 4. 仅在选角/打牌阶段触发提示 (SetPlayerRole @ 0x2772770) */
    Interceptor.attach(base.add(0x2772770), {
        onEnter: function (args) {
            startOpeningBroadcast();
        }
    });

    /*
       随机职业跳过选人时，SetPlayerRole 会在 HandleStartingNewPlayer 内提前执行。
       在玩家进入流程完成后再次尝试启动；已有任务运行时不会重复创建。
    */
    Interceptor.attach(HandleStartingNewPlayer, {
        onLeave: function () {
            startOpeningBroadcast();
        }
    });

    /* 5. 游戏开局时重置状态 (HandleMatchHasStarted @ 0x26BDF30) -> 不再发送提示，仅清理数据 */
    Interceptor.attach(base.add(0x26BDF30), {
        onEnter: function (args) {
            BroadcastGeneration++;
            EmoteCounts = {};
            OptOutThralls = {};
            ReservedThralls = {};
            LastEmoteTime = {};
            IsBroadcastingTip = false;
        }
    });

    /* 6. Hook 狼人身份分配 (ADH_PlayerState::SetIsThrall @ 0x277F060) */
    Interceptor.attach(base.add(0x277F060), {
        onEnter: function (args) {
            try {
                var ps = args[0];
                var isThrall = args[1].toInt32();
                if (isThrall !== 0 && !ps.isNull()) {
                    var key = ps.toString();
                    if (OptOutThralls[key]) {
                        console.log('[不当狼] 拦截到放弃当狼玩家 [' + getPlayerName(ps) + '] 被系统选为狼人，已强制取消');
                        args[1] = ptr(0); // 强制取消当狼
                        delete ReservedThralls[key];

                        reassignThrallToCandidate(ps);
                    } else {
                        /* 记录系统已选和插件替补的狼人，后续转交不得重复选中。 */
                        ReservedThralls[key] = true;
                    }
                }
            } catch (e) {
                console.log('[不当狼] SetIsThrall hook 异常: ' + e);
            }
        }
    });
}
