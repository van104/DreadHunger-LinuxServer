/*
 * 使用快速进服器上传的“玩家 UID -> 大厅职业”名单自动分配职业。
 * 名单保存在 <root>/.gm_runtime/fixed_roles.json，十分钟后自动失效。
 *
 * Finale 1.2.4 Linux:
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
    var ToStringFunctions = Object.create(null);

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
        if (payload === null) return false;

        var playerState = readPlayerState(controller);
        if (playerState.isNull()) return false;
        var userId = readUniqueId(playerState);
        if (!userId) {
            console.log('[固定职业] 玩家进入时 UID 尚未就绪，保留原选人流程');
            return false;
        }

        var roleType = findFixedRole(payload, userId);
        if (roleType === 0) {
            console.log('[固定职业] 名单中未找到玩家 ' + userId + '，保留原选人流程');
            return false;
        }

        try {
            var roleObject = FindByType(roleType, playerState);
            if (roleObject.isNull()) return false;
            if (IsRoleTaken(playerState, roleObject, playerState) !== 0) {
                console.log('[固定职业] ' + (RoleNames[roleType] || roleType) + ' 已被占用，拒绝重复分配');
                return false;
            }

            var key = playerState.toString();
            LockedRoleByPlayerState[key] = roleObject;
            SetPlayerRole(playerState, roleObject, 1);

            var selectedRole = readSelectedRole(playerState);
            if (selectedRole.isNull() || readRoleType(selectedRole) !== roleType) {
                delete LockedRoleByPlayerState[key];
                console.log('[固定职业] 玩家 ' + userId + ' 自动分配失败，保留原选人流程');
                return false;
            }

            send('[固定职业] 已按大厅选择为玩家 ' + userId + ' 分配' + (RoleNames[roleType] || roleType));
            return true;
        } catch (e) {
            console.log('[固定职业] 自动分配异常: ' + e);
            return false;
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
                var controller = args[1];
                if (!controller.isNull()) assignFixedRole(controller);
            } catch (e) {
                console.log('[固定职业] HandleStartingNewPlayer Hook 异常: ' + e);
            }
        }
    });

    send('[固定职业] 插件已加载，等待快速进服器同步大厅职业名单');
}
