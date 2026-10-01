/*
 * 服务端可观测作弊检测（Linux Finale 1.2.4）。
 *
 * 只监听服务端实际成功加入背包的物品；达到短时间异常数量时公告，不修改玩家背包也不自动处罚。
 * GM 发物品和赢牌奖励会在调用前写入短时可信凭据，由本插件消费后跳过检测。
 * 游戏原生 LogDHAntiCheat 事件由 frida_loader.py 转发到本插件，并在游戏线程内公告。
 */
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;
    var TrustedItemsFile = DH_LINUX_ROOT + '/.gm_runtime/anti_cheat_trusted_items.json';
    var AntiCheatEventsFile = DH_LINUX_ROOT + '/.gm_runtime/anti_cheat_events.json';
    var BurstWindowMs = 3000;
    var BurstItemCount = 10;
    var BurstCallCount = 4;
    var LargeSingleGrantCount = 20;
    var AlertCooldownMs = 10000;
    var NativeAlertCooldownMs = 60000;

    var FName_FName = new NativeFunction(base.add(0x2B130F0), 'void', ['pointer', 'pointer', 'int8']);
    var FText_FromName = new NativeFunction(base.add(0x2A13190), 'pointer', ['pointer', 'pointer']);
    var ReceiveGameplayMsg = new NativeFunction(base.add(0x282B4B0), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']);
    var APlayerState_GetPlayerName = new NativeFunction(base.add(0x459E030), 'void', ['pointer', 'pointer']);
    var ADH_PlayerState_GetOwningController = new NativeFunction(base.add(0x277E4F0), 'pointer', ['pointer']);
    var UClass_GetPrivateStaticClass = new NativeFunction(base.add(0x2B9C070), 'pointer', []);
    var StaticFindObject = new NativeFunction(base.add(0x2C95CA0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8']);
    var AddInventory = base.add(0x270CA50);
    var AGameMode_Tick = base.add(0x4336360);
    var GWorld = base.add(0x5C9B6D0);

    var RoleNames = {
        'Captain': '船长', 'Chaplain': '牧师', 'Cook': '厨子', 'Doctor': '医生',
        'Engineer': '工程师', 'Hunter': '猎人', 'Marine': '枪手', 'Navigator': '导航员'
    };

    var ItemDefinitions = [
        ['拳头', '/Game/Blueprints/Inventory/Fists/BP_Fists_Inventory.BP_Fists_Inventory_C'],
        ['燧发手枪', '/Game/Blueprints/Inventory/Flintlock/BP_Flintlock_Inventory.BP_Flintlock_Inventory_C'],
        ['步枪', '/Game/Blueprints/Inventory/Musket/BP_Musket_Inventory.BP_Musket_Inventory_C'],
        ['弓', '/Game/Blueprints/Inventory/Bow/BP_Bow_Inventory.BP_Bow_Inventory_C'],
        ['枪械零件', '/Game/Blueprints/Inventory/Flint/BP_GunParts_Inventory.BP_GunParts_Inventory_C'],
        ['子弹', '/Game/Blueprints/Inventory/Flintlock/BP_Flintlock_Ammo_Inventory.BP_Flintlock_Ammo_Inventory_C'],
        ['箭', '/Game/Blueprints/Inventory/Bow/BP_Arrows_Inventory.BP_Arrows_Inventory_C'],
        ['军刀', '/Game/Blueprints/Inventory/Sword/BP_Sword_Inventory.BP_Sword_Inventory_C'],
        ['斧头', '/Game/Blueprints/Inventory/WoodAxe/BP_WoodAxe_Inventory.BP_WoodAxe_Inventory_C'],
        ['冰镐', '/Game/Blueprints/Inventory/IceAxe/BP_IceAxe_Inventory.BP_IceAxe_Inventory_C'],
        ['菜刀', '/Game/Blueprints/Inventory/Cleaver/BP_Cleaver_Inventory.BP_Cleaver_Inventory_C'],
        ['铲子', '/Game/Blueprints/Inventory/Shovel/BP_Shovel_Inventory.BP_Shovel_Inventory_C'],
        ['木板', '/Game/Blueprints/Inventory/Stick/BP_Stick_Inventory.BP_Stick_Inventory_C'],
        ['石头', '/Game/Blueprints/Inventory/Rock/BP_Rock_Inventory.BP_Rock_Inventory_C'],
        ['废铁', '/Game/Blueprints/Inventory/Metals/BP_IronIngot_Inventory.BP_IronIngot_Inventory_C'],
        ['钉子', '/Game/Blueprints/Inventory/Metals/BP_Nails_Inventory.BP_Nails_Inventory_C'],
        ['铅锭', '/Game/Blueprints/Inventory/Metals/BP_LeadIngot_Inventory.BP_LeadIngot_Inventory_C'],
        ['煤炭', '/Game/Blueprints/Inventory/Coal/BP_Coal_Inventory.BP_Coal_Inventory_C'],
        ['火药', '/Game/Blueprints/Inventory/Flintlock/BP_Gunpowder_Inventory.BP_Gunpowder_Inventory_C'],
        ['肌腱', '/Game/Blueprints/Inventory/AnimalParts/BP_Sinew_Inventory.BP_Sinew_Inventory_C'],
        ['动物皮毛', '/Game/Blueprints/Inventory/AnimalParts/BP_WolfPelt_Inventory.BP_WolfPelt_Inventory_C'],
        ['草药', '/Game/Blueprints/Inventory/Tea/BP_Herbs_Inventory.BP_Herbs_Inventory_C'],
        ['针筒', '/Game/Blueprints/Inventory/Syringe/BP_Syringe_Inventory.BP_Syringe_Inventory_C'],
        ['解毒剂', '/Game/Blueprints/Inventory/Poison/BP_Antidote_Inventory.BP_Antidote_Inventory_C'],
        ['鸦片酊', '/Game/Blueprints/Inventory/Syringe/BP_Inventory_Laudanum.BP_Inventory_Laudanum_C'],
        ['兽肉', '/Game/Blueprints/Inventory/Meat/BP_AnimalMeat_Inventory.BP_AnimalMeat_Inventory_C'],
        ['熟兽肉', '/Game/Blueprints/Inventory/Meat/BP_CookedMeat_Inventory.BP_CookedMeat_Inventory_C'],
        ['人肉', '/Game/Blueprints/Inventory/Meat/BP_HumanMeat_Inventory.BP_HumanMeat_Inventory_C'],
        ['骨棒', '/Game/Blueprints/Inventory/Meat/BP_BoneClub_Inventory.BP_BoneClub_Inventory_C'],
        ['脂肪', '/Game/Blueprints/Inventory/AnimalParts/BP_Blubber_Inventory.BP_Blubber_Inventory_C'],
        ['炖肉', '/Game/Blueprints/Inventory/Meat/BP_Stew_Inventory.BP_Stew_Inventory_C'],
        ['茶', '/Game/Blueprints/Inventory/Tea/BP_Tea_Inventory.BP_Tea_Inventory_C'],
        ['磨刀石', '/Game/Blueprints/Inventory/Metals/BP_Whetstone_Inventory.BP_Whetstone_Inventory_C'],
        ['捕兽夹', '/Game/Blueprints/Inventory/BearTrap/BP_BearTrap_Inventory.BP_BearTrap_Inventory_C'],
        ['望远镜', '/Game/Blueprints/Inventory/Spyglass/BP_Spyglass_Inventory.BP_Spyglass_Inventory_C'],
        ['灯笼', '/Game/Blueprints/Inventory/Lantern/BP_Lantern_Inventory.BP_Lantern_Inventory_C'],
        ['煤炭桶', '/Game/Blueprints/Inventory/Powderkeg/BP_CoalBarrel_Inventory.BP_CoalBarrel_Inventory_C'],
        ['炸药桶', '/Game/Blueprints/Inventory/Powderkeg/BP_Powderkeg_Inventory.BP_Powderkeg_Inventory_C'],
        ['毒药', '/Game/Blueprints/Inventory/Poison/BP_Poison_Inventory.BP_Poison_Inventory_C'],
        ['硝化甘油', '/Game/Blueprints/Environment/Nitro/BP_Nitro_Inventory.BP_Nitro_Inventory_C'],
        ['万能钥匙', '/Game/Blueprints/Inventory/LockPick/BP_SkeletonKey_Inventory.BP_SkeletonKey_Inventory_C'],
        ['船长钥匙', '/Game/Blueprints/Inventory/LockPick/BP_CaptainsKey_Inventory.BP_CaptainsKey_Inventory_C'],
        ['军械库密码', '/Game/Blueprints/Inventory/Armory/BP_Code_Inventory.BP_Code_Inventory_C'],
        ['骸骨匕首', '/Game/Blueprints/Inventory/Totem/BP_BoneDagger_Inventory.BP_BoneDagger_Inventory_C'],
        ['任务卷轴', '/Game/Blueprints/Inventory/Quest/BP_Quest_Inventory.BP_Quest_Inventory_C'],
        ['背包', '/Game/Blueprints/Inventory/Backpack/BP_Backpack_Inventory.BP_Backpack_Inventory_C'],
        ['人类尸体', '/Game/Blueprints/Player/BP_HumanBody_Inventory.BP_HumanBody_Inventory_C'],
        ['人类手臂', '/Game/Blueprints/Player/Gore/BP_Human_Arm_Inventory.BP_Human_Arm_Inventory_C'],
        ['人类头颅', '/Game/Blueprints/Player/Gore/BP_Human_Head_Inventory.BP_Human_Head_Inventory_C'],
        ['人类腿', '/Game/Blueprints/Player/Gore/BP_Human_Leg_Inventory.BP_Human_Leg_Inventory_C'],
        ['熊头', '/Game/Blueprints/AI/Predators/Gore/BP_Bear_Head_Inventory.BP_Bear_Head_Inventory_C'],
        ['狼头', '/Game/Blueprints/AI/Predators/Gore/BP_Wolf_Head_Inventory.BP_Wolf_Head_Inventory_C'],
        ['狼腿', '/Game/Blueprints/AI/Predators/Gore/BP_Wolf_Leg_Inventory.BP_Wolf_Leg_Inventory_C'],
        ['兔头', '/Game/Blueprints/AI/Prey/Gore/BP_Rabbit_Head_Inventory.BP_Rabbit_Head_Inventory_C'],
        ['骨符', '/Game/Blueprints/Inventory/Totem/BP_BoneCharm_Inventory.BP_BoneCharm_Inventory_C'],
        ['纯净水晶', '/Game/Mods/Maps/Archipelago/Blueprints/Mission/Explorer/PureCrystal/BP_PureCrystal_Inventory.BP_PureCrystal_Inventory_C']
    ];

    var KnownItemNames = {};
    var RecentAdds = {};
    var LastAlerts = {};
    var HandledServerEventIds = {};
    var HandledServerEventOrder = [];
    var LastNativeAlerts = {};
    var NextServerEventPollAt = 0;

    function newFName(text) {
        var out = Memory.alloc(8);
        var buffer = Memory.alloc((text.length + 4) * 2);
        buffer.writeUtf16String(text);
        FName_FName(out, buffer, 1);
        return out;
    }

    function makeFText(text) {
        var out = Memory.alloc(24);
        FText_FromName(out, newFName(text));
        return out;
    }

    function readFString(fstring) {
        try {
            var data = fstring.readPointer();
            var length = fstring.add(8).readU32();
            if (length < 1 || length > 256 || data.isNull()) return '';
            var range = Process.findRangeByAddress(data);
            if (range === null || range.protection.indexOf('r') < 0) return '';
            return data.readUtf16String(length) || '';
        } catch (e) { return ''; }
    }

    function getGameState() {
        try {
            var world = GWorld.readPointer();
            if (world.isNull()) return null;
            var gameMode = world.add(0x118).readPointer();
            if (gameMode.isNull()) return null;
            var gameState = gameMode.add(0x280).readPointer();
            return gameState.isNull() ? null : gameState;
        } catch (e) { return null; }
    }

    function getPlayerName(playerState) {
        try {
            var out = Memory.alloc(16);
            APlayerState_GetPlayerName(out, playerState);
            return readFString(out);
        } catch (e) { return ''; }
    }

    function getRoleName(playerState) {
        try {
            var role = playerState.add(0x588).readPointer();
            if (role.isNull()) return '';
            var roleId = readFString(role.add(0x48));
            return RoleNames[roleId] || roleId || '';
        } catch (e) { return ''; }
    }

    function getOnlinePlayers() {
        var players = [];
        try {
            var gameState = getGameState();
            if (!gameState) return players;
            var playerArray = gameState.add(0x238);
            var count = playerArray.add(8).readU32();
            var data = playerArray.readPointer();
            if (count < 1 || count > 64 || data.isNull()) return players;
            for (var i = 0; i < count; i++) {
                var playerState = data.add(i * 8).readPointer();
                if (playerState.isNull()) continue;
                var controller = ADH_PlayerState_GetOwningController(playerState);
                if (controller.isNull()) continue;
                var pawn = controller.add(0x250).readPointer();
                if (pawn.isNull()) continue;
                var inventory = pawn.add(0x808).readPointer();
                players.push({
                    playerState: playerState,
                    controller: controller,
                    pawn: pawn,
                    inventory: inventory,
                    name: getPlayerName(playerState),
                    role: getRoleName(playerState)
                });
            }
        } catch (e) {}
        return players;
    }

    function findPlayer(pawn, inventory) {
        var players = getOnlinePlayers();
        for (var i = 0; i < players.length; i++) {
            if (players[i].pawn.equals(pawn) || (!inventory.isNull() && players[i].inventory.equals(inventory))) {
                return players[i];
            }
        }
        return null;
    }

    function findPlayerByName(name) {
        var players = getOnlinePlayers();
        for (var i = 0; i < players.length; i++) {
            if (players[i].name === name) return players[i];
        }
        return null;
    }

    function broadcast(text) {
        var players = getOnlinePlayers();
        if (players.length < 1) return;
        var message = makeFText(text);
        var title = makeFText('反作弊');
        for (var i = 0; i < players.length; i++) {
            try {
                ReceiveGameplayMsg(players[i].controller, message, ptr(0), ptr(0), title);
            } catch (e) {}
        }
    }

    function refreshKnownItemNames() {
        try {
            var uclass = UClass_GetPrivateStaticClass();
            for (var i = 0; i < ItemDefinitions.length; i++) {
                var buffer = Memory.alloc((ItemDefinitions[i][1].length + 1) * 2);
                buffer.writeUtf16String(ItemDefinitions[i][1]);
                var itemClass = StaticFindObject(uclass, ptr('0xffffffffffffffff'), buffer, 0);
                if (!itemClass.isNull()) KnownItemNames[itemClass.toString()] = ItemDefinitions[i][0];
            }
        } catch (e) {}
    }

    function getItemName(itemClass) {
        var key = itemClass.toString();
        if (!KnownItemNames[key]) refreshKnownItemNames();
        return KnownItemNames[key] || '未知物品';
    }

    function rememberServerEvent(id) {
        HandledServerEventIds[id] = true;
        HandledServerEventOrder.push(id);
        if (HandledServerEventOrder.length > 400) {
            delete HandledServerEventIds[HandledServerEventOrder.shift()];
        }
    }

    function formatNativeAntiCheatReason(event) {
        var type = String(event.cheat_type || '').replace(/[\r\n]/g, ' ').trim();
        var labels = {
            'Teleporting': '瞬移/飞天',
            'Speed Hacking': '加速',
            'Long Range Interacts': '超距离交互',
            'Cross Map Interacts': '跨地图交互/远程摸尸',
            'Chainsaw Melee': '异常近战'
        };
        var reason = labels[type] || '游戏原生反作弊拦截';
        var detail = String(event.detail || '').replace(/[\r\n]/g, ' ').trim();
        var multiplier = /^with a multiplier of \[([^\]]+)\]$/.exec(detail);
        if (multiplier) detail = '倍率 ' + multiplier[1];
        if (!type) return detail ? reason + '（' + detail + '）' : reason;
        return detail ? reason + '（' + type + '，' + detail + '）' : reason + '（' + type + '）';
    }

    function processNativeAntiCheatEvents() {
        var now = Date.now();
        if (now < NextServerEventPollAt) return;
        NextServerEventPollAt = now + 1000;

        var data;
        try { data = JSON.parse(File.readAllText(AntiCheatEventsFile)); }
        catch (e) { return; }
        if (!data || !Array.isArray(data.events)) return;

        for (var i = 0; i < data.events.length; i++) {
            var event = data.events[i];
            if (!event || typeof event.id !== 'string' || HandledServerEventIds[event.id]) continue;
            rememberServerEvent(event.id);

            var name = String(event.player_name || '未知用户').replace(/[\r\n]/g, ' ').trim() || '未知用户';
            var player = findPlayerByName(name);
            var role = player && player.role ? player.role : '未知职业';
            var alertKey = name + ':' + String(event.cheat_type || '');
            if (LastNativeAlerts[alertKey] && now - LastNativeAlerts[alertKey] < NativeAlertCooldownMs) {
                console.log('[反作弊][原生] 已抑制重复公告: ' + alertKey);
                continue;
            }
            LastNativeAlerts[alertKey] = now;
            var reason = formatNativeAntiCheatReason(event);
            console.log('[反作弊][原生] ' + name + ' / ' + role + ' / ' + reason);
            broadcast('发现 ' + name + ' ' + role + ' 作弊\n理由：' + reason);
        }
    }

    function readTrustedGrants() {
        try {
            var data = JSON.parse(File.readAllText(TrustedItemsFile));
            return data && Array.isArray(data.grants) ? data.grants : [];
        } catch (e) { return []; }
    }

    function consumeTrustedGrant(pawn, itemClass) {
        var grants = readTrustedGrants();
        if (grants.length < 1) return false;
        var now = Date.now();
        var pawnKey = pawn.toString();
        var itemKey = itemClass.toString();
        var trusted = false;
        var remaining = [];
        for (var i = 0; i < grants.length; i++) {
            var grant = grants[i];
            if (!grant || Number(grant.expires_at) <= now) continue;
            if (!trusted && grant.pawn === pawnKey && grant.item_class === itemKey) {
                trusted = true;
                continue;
            }
            remaining.push(grant);
        }
        try { File.writeAllText(TrustedItemsFile, JSON.stringify({ grants: remaining })); } catch (e) {}
        return trusted;
    }

    function recordUntrustedAdd(player, itemClass, quantity) {
        var now = Date.now();
        var itemName = getItemName(itemClass);
        var key = player.playerState.toString() + ':' + itemClass.toString();
        var entries = RecentAdds[key] || [];
        var recent = [];
        var total = quantity;
        for (var i = 0; i < entries.length; i++) {
            if (now - entries[i].at <= BurstWindowMs) {
                recent.push(entries[i]);
                total += entries[i].quantity;
            }
        }
        recent.push({ at: now, quantity: quantity });
        RecentAdds[key] = recent;

        var isBurst = total >= BurstItemCount && recent.length >= BurstCallCount;
        var isLargeSingleGrant = quantity >= LargeSingleGrantCount;
        if (!isBurst && !isLargeSingleGrant) return;
        if (LastAlerts[key] && now - LastAlerts[key] < AlertCooldownMs) return;
        LastAlerts[key] = now;

        var name = player.name || '未知用户';
        var role = player.role || '未知职业';
        var message = '发现 ' + name + ' ' + role + ' 作弊\n理由：刷' + itemName;
        console.log('[反作弊][刷物资] ' + name + ' / ' + role + ' / ' + itemName + ' / ' + total);
        broadcast(message);
    }

    Interceptor.attach(AddInventory, {
        onEnter: function (args) {
            this.inventory = args[0];
            this.itemClass = args[1];
            this.output = args[3];
            this.pawn = args[6];
        },
        onLeave: function () {
            try {
                var quantity = this.output.readS32();
                if (quantity <= 0) {
                    consumeTrustedGrant(this.pawn, this.itemClass);
                    return;
                }
                if (consumeTrustedGrant(this.pawn, this.itemClass)) return;
                var player = findPlayer(this.pawn, this.inventory);
                if (!player) return;
                recordUntrustedAdd(player, this.itemClass, quantity);
            } catch (e) {
                console.log('[反作弊][刷物资] 读取背包增加事件失败: ' + e);
            }
        }
    });

    /* 文件轮询只做读取；公告的 Unreal 调用固定在游戏线程执行。 */
    Interceptor.attach(AGameMode_Tick, {
        onEnter: function () { processNativeAntiCheatEvents(); }
    });

    console.log('[反作弊] 已启动：物资异常和游戏原生反作弊事件公告已启用');
}
