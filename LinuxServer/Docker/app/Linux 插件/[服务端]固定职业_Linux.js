/*
 * 使用快速进服器上传的“玩家 UID -> 大厅职业”名单自动分配职业。
 * 名单保存在 <root>/.gm_runtime/fixed_roles.json，十分钟后自动失效。
 *
 * Finale 1.2.4 Linux:
 * - AGameMode::Tick                                      = base + 0x4336360
 * - ADH_GameMode::HandleStartingNewPlayer_Implementation = base + 0x26CB970
 * - ADH_PlayerState::SetPlayerRole                      = base + 0x2772770
 * - UDH_PlayerRoleData::FindByType                      = base + 0x275CEE0
 * - UDH_GameplayStatics::IsRoleTaken                    = base + 0x27C8750
 * - APlayerState::UniqueId                              = PlayerState + 0x258
 * - ADH_PlayerState::SelectedRole                       = PlayerState + 0x588
 */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;
    var FixedRolesFile = DH_LINUX_ROOT + '/.gm_runtime/fixed_roles.json';

    var GameModeTickAddress = base.add(0x4336360);
    var HandleStartingNewPlayerAddress = base.add(0x26CB970);
    var SetPlayerRoleAddress = base.add(0x2772770);
    var FindByType = new NativeFunction(base.add(0x275CEE0), 'pointer', ['int8', 'pointer']);
    var IsRoleTaken = new NativeFunction(base.add(0x27C8750), 'uint8', ['pointer', 'pointer', 'pointer']);
    var SetPlayerRole = new NativeFunction(SetPlayerRoleAddress, 'void', ['pointer', 'pointer', 'uint8']);

    var PlayerStateOffset = 0x228;
    var UniqueIdOffset = 0x258;
    var SelectedRoleOffset = 0x588;
    var RoleTypeOffset = 0x58;
    var UniqueIdToStringVTableOffset = 0x38;

    var CurrentUploadId = '';
    var LockedRoleByPlayerState = Object.create(null);
    var PendingControllers = Object.create(null);
    var ToStringFunctions = Object.create(null);
    var RetryIntervalMs = 250;
    var RetryTimeoutMs = 10000;

    var RoleNames = {
        1: '船长', 2: '工程', 3: '猎人', 4: '厨子',
        5: '导航', 6: '牧师', 7: '枪手', 8: '医生'
    };

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

    function isExecutable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('x') !== -1;
        } catch (e) {
            return false;
        }
    }

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var size = fstring.add(8).readU32();
            if (size < 1 || size > 256 || data.isNull() || !isReadable(data)) return '';
            return (data.readUtf16String(size) || '').replace(/\u0000+$/g, '');
        } catch (e) {
            return '';
        }
    }

    function readPlayerState(controller) {
        try {
            if (!isReadable(controller)) return ptr(0);
            var address = controller.add(PlayerStateOffset);
            if (!isReadable(address)) return ptr(0);
            var playerState = address.readPointer();
            return playerState.isNull() ? ptr(0) : playerState;
        } catch (e) {
            return ptr(0);
        }
    }

    function readUniqueId(playerState) {
        try {
            var uniqueId = playerState.add(UniqueIdOffset).readPointer();
            if (!isReadable(uniqueId)) return '';
            var vtable = uniqueId.readPointer();
            if (!isReadable(vtable.add(UniqueIdToStringVTableOffset))) return '';
            var functionAddress = vtable.add(UniqueIdToStringVTableOffset).readPointer();
            if (!isExecutable(functionAddress)) return '';

            var key = functionAddress.toString();
            if (!ToStringFunctions[key]) {
                /* FString 返回值由 Linux SysV ABI 通过第一个隐藏参数传回。 */
                ToStringFunctions[key] = new NativeFunction(functionAddress, 'void', ['pointer', 'pointer']);
            }
            var output = Memory.alloc(16);
            ToStringFunctions[key](output, uniqueId);
            return readFString(output);
        } catch (e) {
            return '';
        }
    }

    function identityKeys(value) {
        var text = String(value || '').trim().toLowerCase();
        if (text.indexOf('eosplus:') === 0) text = text.substring(8);
        if (!text) return [];
        var keys = [text];
        var separator = text.indexOf('_+_|');
        if (separator > 0) {
            keys.push(text.substring(0, separator));
            keys.push(text.substring(separator + 4));
        }
        return keys;
    }

    function sameIdentity(left, right) {
        var leftKeys = identityKeys(left);
        var rightKeys = identityKeys(right);
        for (var i = 0; i < leftKeys.length; i++) {
            if (rightKeys.indexOf(leftKeys[i]) >= 0) return true;
        }
        return false;
    }

    function loadPayload() {
        try {
            var payload = JSON.parse(File.readAllText(FixedRolesFile));
            if (!payload || !Array.isArray(payload.roles)) return null;
            if (Number(payload.expires_at || 0) <= Date.now()) return null;

            var uploadId = String(payload.upload_id || '');
            if (uploadId && uploadId !== CurrentUploadId) {
                CurrentUploadId = uploadId;
                LockedRoleByPlayerState = Object.create(null);
            }
            return payload;
        } catch (e) {
            return null;
        }
    }

    function findFixedRole(payload, userId) {
        for (var i = 0; i < payload.roles.length; i++) {
            var entry = payload.roles[i];
            var roleType = Number(entry && entry.role);
            if (roleType >= 1 && roleType <= 8 && sameIdentity(userId, entry.user_id)) {
                return roleType;
            }
        }
        return 0;
    }

    function readSelectedRole(playerState) {
        try {
            var address = playerState.add(SelectedRoleOffset);
            if (!isReadable(address)) return ptr(0);
            var role = address.readPointer();
            return role.isNull() ? ptr(0) : role;
        } catch (e) {
            return ptr(0);
        }
    }

    function readRoleType(roleObject) {
        try {
            if (!isReadable(roleObject.add(RoleTypeOffset))) return 0;
            return roleObject.add(RoleTypeOffset).readU8();
        } catch (e) {
            return 0;
        }
    }

    function assignFixedRole(controller) {
        var payload = loadPayload();
        if (payload === null) return 'skip';

        var playerState = readPlayerState(controller);
        if (playerState.isNull()) return 'retry';
        var userId = readUniqueId(playerState);
        if (!userId) return 'retry';

        var roleType = findFixedRole(payload, userId);
        if (roleType === 0) {
            console.log('[固定职业] 名单中未找到玩家 ' + userId + '，保留原选人流程');
            return 'skip';
        }

        try {
            var key = playerState.toString();
            var selectedRole = readSelectedRole(playerState);
            if (!selectedRole.isNull() && readRoleType(selectedRole) === roleType) {
                LockedRoleByPlayerState[key] = selectedRole;
                return 'assigned';
            }

            var roleObject = FindByType(roleType, playerState);
            if (roleObject.isNull()) return 'retry';
            if (IsRoleTaken(playerState, roleObject, playerState) !== 0) return 'retry';

            LockedRoleByPlayerState[key] = roleObject;
            SetPlayerRole(playerState, roleObject, 1);

            selectedRole = readSelectedRole(playerState);
            if (selectedRole.isNull() || readRoleType(selectedRole) !== roleType) {
                delete LockedRoleByPlayerState[key];
                return 'retry';
            }

            send('[固定职业] 已按大厅选择为玩家 ' + userId + ' 分配' + (RoleNames[roleType] || roleType));
            return 'assigned';
        } catch (e) {
            return 'retry';
        }
    }

    function queueFixedRole(controller) {
        var key = controller.toString();
        if (!PendingControllers[key]) {
            PendingControllers[key] = {
                controller: controller,
                nextAttemptAt: 0,
                deadline: Date.now() + RetryTimeoutMs
            };
        }
    }

    function attemptFixedRole(controller) {
        var key = controller.toString();
        var result = assignFixedRole(controller);
        if (result === 'retry') {
            queueFixedRole(controller);
        } else {
            delete PendingControllers[key];
        }
        return result;
    }

    function processPendingFixedRoles() {
        var now = Date.now();
        var keys = Object.keys(PendingControllers);
        for (var i = 0; i < keys.length; i++) {
            var key = keys[i];
            var pending = PendingControllers[key];
            if (!pending || now < pending.nextAttemptAt) continue;
            if (now >= pending.deadline) {
                delete PendingControllers[key];
                console.log('[固定职业] 玩家状态或目标职业在 10 秒内未就绪，停止自动分配');
                continue;
            }
            pending.nextAttemptAt = now + RetryIntervalMs;
            var result = assignFixedRole(pending.controller);
            if (result !== 'retry') delete PendingControllers[key];
        }
    }

    Interceptor.attach(SetPlayerRoleAddress, {
        onEnter: function (args) {
            try {
                var key = args[0].toString();
                var lockedRole = LockedRoleByPlayerState[key];
                if (lockedRole && !lockedRole.isNull()) args[1] = lockedRole;
            } catch (e) {}
        }
    });

    Interceptor.attach(HandleStartingNewPlayerAddress, {
        onEnter: function (args) {
            try {
                this.controller = args[1];
                if (!this.controller.isNull()) attemptFixedRole(this.controller);
            } catch (e) {
                console.log('[固定职业] HandleStartingNewPlayer Hook 异常: ' + e);
            }
        },
        onLeave: function () {
            try {
                if (this.controller && !this.controller.isNull()) attemptFixedRole(this.controller);
            } catch (e) {
                console.log('[固定职业] HandleStartingNewPlayer 返回后重试异常: ' + e);
            }
        }
    });

    Interceptor.attach(GameModeTickAddress, {
        onEnter: function () {
            processPendingFixedRoles();
        }
    });

    send('[固定职业] 插件已加载，等待快速进服器同步大厅职业名单（状态未就绪时自动重试）');
}
