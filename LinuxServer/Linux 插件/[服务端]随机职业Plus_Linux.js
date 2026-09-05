/*
   在 HandleStartingNewPlayer 检查 SelectedRole 前分配职业，跳过选人界面。
   同局职业不重复；锁定首次分配结果，覆盖客户端后续提交。

   当前 Linux 服务端二进制:
   - ADH_GameMode::HandleStartingNewPlayer_Implementation = base + 0x26CB970
   - ADH_PlayerState::SetPlayerRole                    = base + 0x2772770
   - UDH_PlayerRoleData::FindByType                    = base + 0x275CEE0
   - UDH_GameplayStatics::IsRoleTaken                  = base + 0x27C8750
   - AController::PlayerState                          = Controller + 0x228
   - ADH_PlayerState::SelectedRole                     = PlayerState + 0x588
 */

var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;

    var HandleStartingNewPlayerAddress = base.add(0x26CB970);
    var SetPlayerRoleAddress = base.add(0x2772770);
    var GWorld = base.add(0x5C9B6D0);

    var FindByType = new NativeFunction(
        base.add(0x275CEE0),
        'pointer',
        ['int8', 'pointer']
    );
    var IsRoleTaken = new NativeFunction(
        base.add(0x27C8750),
        'uint8',
        ['pointer', 'pointer', 'pointer']
    );
    var SetPlayerRole = new NativeFunction(
        SetPlayerRoleAddress,
        'void',
        ['pointer', 'pointer', 'uint8']
    );

    var PlayerStateOffset = 0x228;
    var SelectedRoleOffset = 0x588;
    var RoleTypeOffset = 0x58;
    var AllRoleTypes = [1, 2, 3, 4, 5, 6, 7, 8];

    var CurrentWorldKey = '';
    var AvailableRoleTypes = AllRoleTypes.slice();
    var AssignedRole = Object.create(null);
    var AssignedRoleType = Object.create(null);

    function isReadable(address) {
        try {
            if (!address || address.isNull()) return false;
            var range = Process.findRangeByAddress(address);
            return range !== null && range.protection.indexOf('r') !== -1;
        } catch (e) {
            return false;
        }
    }

    function resetForCurrentWorld() {
        try {
            if (!isReadable(GWorld)) return;
            var world = GWorld.readPointer();
            if (world.isNull()) return;

            var worldKey = world.toString();
            if (worldKey !== CurrentWorldKey) {
                CurrentWorldKey = worldKey;
                AvailableRoleTypes = AllRoleTypes.slice();
                AssignedRole = Object.create(null);
                AssignedRoleType = Object.create(null);
            }
        } catch (e) {
            console.log('[随机职业Plus] 重置职业池异常: ' + e);
        }
    }

    function removeAvailableRole(roleType) {
        var index = AvailableRoleTypes.indexOf(roleType);
        if (index >= 0) AvailableRoleTypes.splice(index, 1);
    }

    function readRoleType(roleObject) {
        try {
            if (!isReadable(roleObject.add(RoleTypeOffset))) return 0;
            return roleObject.add(RoleTypeOffset).readU8();
        } catch (e) {
            return 0;
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

    function readSelectedRole(playerState) {
        try {
            var address = playerState.add(SelectedRoleOffset);
            if (!isReadable(address)) return ptr(0);
            return address.readPointer();
        } catch (e) {
            return ptr(0);
        }
    }

    function shuffle(values) {
        for (var i = values.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var temp = values[i];
            values[i] = values[j];
            values[j] = temp;
        }
        return values;
    }

    function rememberExistingRole(playerState, roleObject) {
        var key = playerState.toString();
        AssignedRole[key] = roleObject;

        var roleType = readRoleType(roleObject);
        if (roleType >= 1 && roleType <= 8) {
            AssignedRoleType[key] = roleType;
            removeAvailableRole(roleType);
        }
    }

    function chooseRandomRole(playerState) {
        resetForCurrentWorld();

        var key = playerState.toString();
        if (AssignedRole[key] && !AssignedRole[key].isNull()) {
            return {
                object: AssignedRole[key],
                type: AssignedRoleType[key] || readRoleType(AssignedRole[key])
            };
        }

        var candidates = shuffle(AvailableRoleTypes.slice());
        for (var i = 0; i < candidates.length; i++) {
            var roleType = candidates[i];
            var roleObject = ptr(0);

            try {
                roleObject = FindByType(roleType, playerState);
                if (roleObject.isNull()) continue;

                /* 游戏自身也检查角色是否已被占用，避免与晚注入或其他插件发生重复。 */
                if (IsRoleTaken(playerState, roleObject, playerState) !== 0) {
                    removeAvailableRole(roleType);
                    continue;
                }
            } catch (e) {
                console.log('[随机职业Plus] 检查职业 ' + roleType + ' 异常: ' + e);
                continue;
            }

            AssignedRole[key] = roleObject;
            AssignedRoleType[key] = roleType;
            removeAvailableRole(roleType);
            return { object: roleObject, type: roleType };
        }

        return null;
    }

    function releaseFailedAssignment(playerState) {
        var key = playerState.toString();
        var roleType = AssignedRoleType[key] || 0;
        delete AssignedRole[key];
        delete AssignedRoleType[key];
        if (roleType >= 1 && roleType <= 8 && AvailableRoleTypes.indexOf(roleType) < 0) {
            AvailableRoleTypes.push(roleType);
        }
    }

    function assignRoleBeforeSelection(controller) {
        var playerState = readPlayerState(controller);
        if (playerState.isNull()) {
            console.log('[随机职业Plus] 玩家进入时 PlayerState 尚未就绪，保留原选人流程');
            return false;
        }

        resetForCurrentWorld();

        var selectedRole = readSelectedRole(playerState);
        if (!selectedRole.isNull()) {
            rememberExistingRole(playerState, selectedRole);
            return true;
        }

        var choice = chooseRandomRole(playerState);
        if (choice === null) {
            console.log('[随机职业Plus] 没有可分配的空闲职业，保留原选人流程');
            return false;
        }

        try {
            /* 同步调用；返回后原函数会立即检查 SelectedRole，并据此跳过选人界面。 */
            SetPlayerRole(playerState, choice.object, 1);

            selectedRole = readSelectedRole(playerState);
            if (selectedRole.isNull()) {
                releaseFailedAssignment(playerState);
                console.log('[随机职业Plus] 自动分配职业失败，保留原选人流程');
                return false;
            }

            send(
                '[随机职业Plus] 已自动分配职业编号 ' + choice.type +
                '，玩家将直接进入服务器，无需手动选人'
            );
            return true;
        } catch (e) {
            releaseFailedAssignment(playerState);
            console.log('[随机职业Plus] 自动分配异常: ' + e);
            return false;
        }
    }

    /*
       保留服务端锁定：若客户端仍通过旧界面或异常请求提交职业，
       统一替换为服务端首次随机分配的职业。
    */
    Interceptor.attach(SetPlayerRoleAddress, {
        onEnter: function (args) {
            try {
                var playerState = args[0];
                var requestedRole = args[1];
                if (playerState.isNull() || requestedRole.isNull()) return;

                resetForCurrentWorld();

                var key = playerState.toString();
                if (AssignedRole[key] && !AssignedRole[key].isNull()) {
                    args[1] = AssignedRole[key];
                    return;
                }

                var choice = chooseRandomRole(playerState);
                if (choice !== null) args[1] = choice.object;
            } catch (e) {
                console.log('[随机职业Plus] SetPlayerRole Hook 异常: ' + e);
            }
        }
    });

    /*
       关键 Hook：原函数在入口后检查 Controller.PlayerState.SelectedRole。
       此处先同步分配，使原函数直接走“已有职业”的进入游戏分支。
    */
    Interceptor.attach(HandleStartingNewPlayerAddress, {
        onEnter: function (args) {
            try {
                var controller = args[1];
                if (controller.isNull()) return;
                assignRoleBeforeSelection(controller);
            } catch (e) {
                console.log('[随机职业Plus] HandleStartingNewPlayer Hook 异常: ' + e);
            }
        }
    });
}
