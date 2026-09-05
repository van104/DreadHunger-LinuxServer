/*
  关闭人物受伤及饥饿、寒冷的自然消耗。

  当前 Linux 服务端二进制:
  - ADH_HumanCharacter::Tick(float) = base + 0x2695160
  - AActor::SetCanBeDamaged(bool)    = base + 0x408CCF0
  - ADH_HumanCharacter::bUpdateHunger = HumanCharacter + 0xA30
  - ADH_HumanCharacter::bUpdateWarmth = HumanCharacter + 0xA31
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;
    var HumanCharacterTick = base.add(0x2695160);
    var SetCanBeDamaged = new NativeFunction(base.add(0x408CCF0), 'void', ['pointer', 'bool']);
    var UpdateHungerOffset = 0xA30;
    var UpdateWarmthOffset = 0xA31;

    Interceptor.attach(HumanCharacterTick, {
        onEnter: function (args) {
            var humanCharacter = args[0];
            try {
                if (!humanCharacter || humanCharacter.isNull()) return;
                humanCharacter.add(UpdateHungerOffset).writeU8(0);
                humanCharacter.add(UpdateWarmthOffset).writeU8(0);
                SetCanBeDamaged(humanCharacter, 0);
            } catch (e) {
                console.log('[人物无敌] 应用无敌状态失败: ' + e);
            }
        }
    });

    send('人物无敌: 已加载');
}
