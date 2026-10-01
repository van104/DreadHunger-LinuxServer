/* 初始背包: 按职业设置背包上限 (Linux 偏移: AddStartingInventory 0x26931D0, SetStorageLimit 0x270CC90) */
var mod = Process.findModuleByName("DreadHungerServer-Linux-Shipping");

if (mod !== null) {
    var base = mod.base;
    var ADH_HumanCharacter_AddStartingInventory_addr = base.add(0x26931D0);
    var UDH_InventoryManager_SetStorageLimit = new NativeFunction(base.add(0x270CC90), 'void', ['pointer', 'int32']);
    var StorageLimit = new Map([
        ['Captain', 10],
        ['Chaplain', 10],
        ['Cook', 10],
        ['Doctor', 10],
        ['Engineer', 10],
        ['Hunter', 10],
        ['Marine', 10],
        ['Navigator', 10]
    ]);
    /* 角色名对照: Captain船长 Chaplain牧师 Cook厨子 Doctor医生 Engineer工程 Hunter猎人 Marine枪手 Navigator导航 */

    function getArraySize(TArray) {
        return TArray.add(8).readU32();
    }

    function getString(FString) {
        var Size = getArraySize(FString);
        return FString.readPointer().readUtf16String(Size);
    }

    Interceptor.attach(ADH_HumanCharacter_AddStartingInventory_addr, {
        onEnter: function (args) {
            try {
                var HumanCharacter = args[0];
                var PlayerState = HumanCharacter.add(0x240).readPointer();
                var InventoryComponent = HumanCharacter.add(0x808).readPointer();
                var SelectedRole = PlayerState.add(0x588).readPointer();
                var Name = getString(SelectedRole.add(0x48));
                if (StorageLimit.has(Name)) {
                    UDH_InventoryManager_SetStorageLimit(InventoryComponent, StorageLimit.get(Name));
                }
            } catch (e) {}
        }
    });
}
