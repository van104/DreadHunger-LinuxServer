/* 赢牌对家开船: 摊牌后对家获得开船权并广播 (Linux 偏移) */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    /* ===== 配置区 ===== */
    var NoticeTitle = ' ';
    var RoleNamesCN = {
        'Captain': '船长', 'Cook': '厨师', 'Chaplain': '牧师', 'Doctor': '医生',
        'Engineer': '工程师', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航员'
    };
    var OpponentDelaySec = 0;
    var RepeatTimes = 5;
    var RepeatIntervalSec = 5;
    var UseThrallChannel = false;
    var NoticePadding = 10;   // 提示后插入的空行数, 值越大提示越靠上
    /* ================== */

    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var UGameplayStatics_GetPlayerController = new NativeFunction(base.add(0x433C920), 'pointer', ['pointer', 'int32']);
    var UGameplayStatics_GetAllActorsOfClass = new NativeFunction(base.add(0x433F490), 'void', ['pointer', 'pointer', 'pointer', 'pointer']);
    var ADH_PlayerController_ReceiveGameplayMessage = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var ADH_PlayerController_ReceiveThrallMessage = new NativeFunction(base.add(0x282B610), 'void', ['pointer', 'pointer', 'pointer']);
    var StaticFindObject = new NativeFunction(base.add(0x2C95CA0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8']);
    var UClass_GetPrivateStaticClass = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var ADH_RoleDealer_Showdown = base.add(0x272E980);
    var GWorld = base.add(0x5C9B6D0);

    var OFF_Players = 0x330;
    var OFF_WinningPlayer = 0x468;
    var OFF_Pawn_Controller = 0x258;
    var OFF_Controller_PlayerState = 0x228;

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

    function getFString(FString) {
        try {
            var Num = FString.add(8).readU32();
            if (Num <= 0 || Num > 4096) return '';
            var data = FString.readPointer();
            if (data.isNull()) return '';
            return data.readUtf16String(Num);
        } catch (e) { return ''; }
    }

    function getPlayerName(ps) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, ps);
            return getFString(out);
        } catch (e) { return ''; }
    }

    function getArraySize(TArray) {
        return TArray.add(8).readU32();
    }

    function getGameState() {
        try {
            var World = GWorld.readPointer();
            if (World.isNull()) return ptr(0);
            var GameMode = World.add(0x118).readPointer();
            if (GameMode.isNull()) return ptr(0);
            return GameMode.add(0x280).readPointer();
        } catch (e) { return ptr(0); }
    }

    function getPawnPos(pawn) {
        try {
            var root = pawn.add(0x130).readPointer();
            if (root.isNull()) return null;
            var x = root.add(0x1D0).readFloat();
            var y = root.add(0x1D4).readFloat();
            if (isFinite(x) && isFinite(y) &&
                Math.abs(x) < 1000000 && Math.abs(y) < 1000000 &&
                (Math.abs(x) > 0.1 || Math.abs(y) > 0.1)) {
                return { x: x, y: y };
            }
            x = root.add(0x11C).readFloat();
            y = root.add(0x120).readFloat();
            if (isFinite(x) && isFinite(y) &&
                Math.abs(x) < 1000000 && Math.abs(y) < 1000000 &&
                (Math.abs(x) > 0.1 || Math.abs(y) > 0.1)) {
                return { x: x, y: y };
            }
            return null;
        } catch (e) { return null; }
    }

    function getPawnInfo(LobbyPawn) {
        if (LobbyPawn.isNull()) return null;
        var ctrl = ptr(0);
        try {
            var c1 = LobbyPawn.add(OFF_Pawn_Controller).readPointer();
            var c2 = LobbyPawn.add(0x338).readPointer();
            ctrl = (c1 && !c1.isNull()) ? c1 : c2;
        } catch (e) {}
        if (ctrl.isNull()) return null;
        var ps = ctrl.add(OFF_Controller_PlayerState).readPointer();
        if (ps.isNull()) return null;
        var name = getPlayerName(ps);
        var role = '';
        try {
            var rolePtr = ps.add(0x588).readPointer();
            if (!rolePtr.isNull()) role = getFString(rolePtr.add(0x48));
        } catch (e) {}
        return { name: name, role: role, ps: ps };
    }

    function broadcastToAll(MessageText, TitleText) {
        try {
            var GameState = getGameState();
            if (GameState.isNull()) return;
            var PlayerArray = GameState.add(0x238);
            var Num = getArraySize(PlayerArray);
            for (var i = 0; i < Num; i++) {
                try {
                    var PS = PlayerArray.readPointer().add(i * 8).readPointer();
                    if (PS.isNull()) continue;
                    var PC = UGameplayStatics_GetPlayerController(PS, PS.add(0x224).readU8());
                    if (PC.isNull()) continue;
                    if (UseThrallChannel) {
                        ADH_PlayerController_ReceiveThrallMessage(PC, MessageText, ptr(0));
                    } else {
                        ADH_PlayerController_ReceiveGameplayMessage(PC, MessageText, ptr(0), ptr(0), TitleText);
                    }
                } catch (e) {}
            }
        } catch (e) {}
    }

    function computeOppositePairs(seats) {
        var N = seats.length;
        var cx = 0, cy = 0;
        for (var i = 0; i < N; i++) { cx += seats[i].x; cy += seats[i].y; }
        cx /= N; cy /= N;

        var dists = [];
        for (var j = 0; j < N; j++) {
            var ddx = seats[j].x - cx, ddy = seats[j].y - cy;
            dists.push(Math.sqrt(ddx * ddx + ddy * ddy));
        }
        var sortedDists = dists.slice().sort(function (a, b) { return a - b; });
        var medDist = sortedDists[Math.floor(N / 2)];
        var filtered = [];
        for (var f = 0; f < N; f++) {
            if (dists[f] >= medDist * 0.5 && dists[f] <= medDist * 1.8) filtered.push(seats[f]);
        }
        if (filtered.length < 4) filtered = seats.slice();
        seats = filtered;
        N = seats.length;

        var fcx = 0, fcy = 0;
        for (var a = 0; a < N; a++) { fcx += seats[a].x; fcy += seats[a].y; }
        fcx /= N; fcy /= N;
        var sxx = 0, syy = 0, sxy = 0;
        for (var b = 0; b < N; b++) {
            var ex = seats[b].x - fcx, ey = seats[b].y - fcy;
            sxx += ex * ex; syy += ey * ey; sxy += ex * ey;
        }
        var theta = 0.5 * Math.atan2(2 * sxy, sxx - syy);
        var lx = Math.cos(theta), ly = Math.sin(theta);

        for (var k = 0; k < N; k++) {
            var fx = seats[k].x - fcx, fy = seats[k].y - fcy;
            seats[k].t = fx * lx + fy * ly;
            seats[k].origIdx = (seats[k].pidx !== undefined) ? seats[k].pidx : k;
        }

        var sorted = seats.slice().sort(function (a, b) { return a.t - b.t; });

        var gaps = [];
        for (var m = 1; m < N; m++) gaps.push(sorted[m].t - sorted[m - 1].t);
        var sortedGaps = gaps.slice().sort(function (a, b) { return a - b; });
        var bestJump = 0, bestThresh = 0;
        for (var gj = 0; gj + 1 < sortedGaps.length; gj++) {
            var jump = sortedGaps[gj + 1] - sortedGaps[gj];
            if (jump > bestJump) {
                bestJump = jump;
                bestThresh = (sortedGaps[gj + 1] + sortedGaps[gj]) / 2;
            }
        }
        if (bestJump < 1e-4) {
            var medGap2 = sortedGaps[Math.floor(gaps.length / 2)];
            bestThresh = medGap2 * 0.6;
        }
        var gapThresh = bestThresh;

        var columns = [];
        var cur = [sorted[0]];
        for (var n2 = 1; n2 < N; n2++) {
            if (sorted[n2].t - sorted[n2 - 1].t > gapThresh) {
                columns.push(cur);
                cur = [];
            }
            cur.push(sorted[n2]);
        }
        columns.push(cur);

        var pairs = [];
        var singles = [];
        for (var c = 0; c < columns.length; c++) {
            if (columns[c].length === 2) {
                pairs.push([columns[c][0].origIdx, columns[c][1].origIdx]);
            } else if (columns[c].length === 1) {
                singles.push(columns[c][0]);
            } else {
                for (var cc = 0; cc + 1 < columns[c].length; cc += 2) {
                    pairs.push([columns[c][cc].origIdx, columns[c][cc + 1].origIdx]);
                }
                if (columns[c].length % 2 === 1) singles.push(columns[c][columns[c].length - 1]);
            }
        }
        if (singles.length === 2) {
            pairs.push([singles[0].origIdx, singles[1].origIdx]);
        } else if (singles.length > 2) {
            for (var s1 = 0; s1 + 1 < singles.length; s1 += 2) {
                pairs.push([singles[s1].origIdx, singles[s1 + 1].origIdx]);
            }
        }

        var map = [];
        for (var mi = 0; mi < N; mi++) map[mi] = -1;
        for (var pi = 0; pi < pairs.length; pi++) {
            map[pairs[pi][0]] = pairs[pi][1];
            map[pairs[pi][1]] = pairs[pi][0];
        }
        return map;
    }

    var LastDealer = ptr(0);
    var LastOpponent = ptr(0);
    var LastWinnerInfo = null;
    var HandledShowdown = false;
    var SnapshotPlayers = [];
    var OpponentRetry = 0;
    var NoticePulseCount = 0;

    Interceptor.attach(ADH_RoleDealer_Showdown, {
        onEnter: function (args) {
            try {
                LastDealer = args[0];
                HandledShowdown = false;
                SnapshotPlayers = [];
                var playersArr = args[0].add(OFF_Players);
                var n = getArraySize(playersArr);
                var arrPtr = playersArr.readPointer();
                for (var i = 0; i < n; i++) {
                    try {
                        var pawn = arrPtr.add(i * 8).readPointer();
                        if (pawn.isNull()) continue;
                        var pos = getPawnPos(pawn);
                        var info = getPawnInfo(pawn);
                        SnapshotPlayers.push({
                            pawn: pawn,
                            pos: pos,
                            name: info ? info.name : ''
                        });
                    } catch (e) {}
                }
            } catch (e) {}
        },
        onLeave: function (retval) {
            try {
                if (LastDealer.isNull() || HandledShowdown) return;

                var winner = LastDealer.add(OFF_WinningPlayer).readPointer();
                if (winner.isNull()) return;

                var players = SnapshotPlayers;
                if (players.length < 2) return;

                var winnerIdx = -1;
                for (var w0 = 0; w0 < players.length; w0++) {
                    if (players[w0].pawn.equals(winner)) { winnerIdx = w0; break; }
                }
                if (winnerIdx < 0) {
                    var wpos = getPawnPos(winner);
                    players.push({ pawn: winner, pos: wpos, name: '' });
                    winnerIdx = players.length - 1;
                }

                var opponent = ptr(0);
                var pairMap = null;
                if (players.length >= 4) {
                    var ok = true;
                    for (var pi = 0; pi < players.length; pi++) {
                        if (!players[pi].pos) { ok = false; break; }
                    }
                    if (ok) {
                        var tmp = players.map(function (s, pi2) {
                            return { x: s.pos.x, y: s.pos.y, pidx: pi2 };
                        });
                        pairMap = computeOppositePairs(tmp);
                    }
                }

                if (pairMap) {
                    var oppIdx = pairMap[winnerIdx];
                    if (oppIdx !== undefined && oppIdx >= 0 && oppIdx < players.length) {
                        opponent = players[oppIdx].pawn;
                        if (opponent.isNull() || opponent.equals(winner)) opponent = ptr(0);
                    }
                }

                if (opponent.isNull()) {
                    var oppJ = (winnerIdx + Math.floor(players.length / 2)) % players.length;
                    opponent = players[oppJ].pawn;
                }

                if (opponent.isNull() || opponent.equals(winner)) return;

                LastOpponent = opponent;
                HandledShowdown = true;

                LastDealer.add(OFF_WinningPlayer).writePointer(opponent);
                var wi = getPawnInfo(winner);
                LastWinnerInfo = wi;

                setTimeout(pushOpponentNotice, OpponentDelaySec * 1000);
            } catch (e) {}
        }
    });

    function pushNoticeBlock() {
        var info = getPawnInfo(LastOpponent);
        if (info === null || info.name === '') {
            if (OpponentRetry < 10) {
                OpponentRetry++;
                setTimeout(pushNoticeBlock, 1000);
            }
            return;
        }
        OpponentRetry = 0;
        var RoleCN = RoleNamesCN[info.role] || info.role;
        var padding = '';
        for (var i = 0; i < NoticePadding; i++) padding += '\n';
        var MsgText = FNameToFText(newFName('' + info.name + ' (' + RoleCN + ') 开船' + padding));
        var TitleText = FNameToFText(newFName(NoticeTitle));
        broadcastToAll(MsgText, TitleText);
    }

    function pushOpponentNotice() {
        try {
            if (LastOpponent.isNull()) return;
            pushNoticeBlock();
            NoticePulseCount++;
            if (NoticePulseCount < RepeatTimes) {
                setTimeout(pushOpponentNotice, RepeatIntervalSec * 1000);
            } else {
                NoticePulseCount = 0;
            }
        } catch (e) {}
    }
}
