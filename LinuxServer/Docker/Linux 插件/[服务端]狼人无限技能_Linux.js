/*
  狼人无限技能 (Linux 服务端插件)

  功能:
  1. 狼人技能充能始终恢复为满值。
  2. 技能冷却倍率固定为 0，施放后可立即再次使用。
  3. 不改变已装备技能、施法目标和其他游戏规则。

  当前 Linux 服务端二进制:
  - ADH_SpellManager::UpdateSpellCharge(float) = base + 0x27A6580
  - ADH_SpellManager::CastSpell(...)            = base + 0x27A6D00
  - ADH_SpellManager::RemoveActiveSpell(...)    = base + 0x27A73C0
  - ADH_SpellManager::CooldownMultiplier        = SpellManager + 0x280
  - ADH_SpellManager::SpellChargeLevel          = SpellManager + 0x284
  - ADH_SpellManager::SpellCooldowns.Data       = SpellManager + 0x2A8
  - ADH_SpellManager::SpellCooldowns.Num        = SpellManager + 0x2B0
*/
var mod = Process.findModuleByName('DreadHungerServer-Linux-Shipping');

if (mod !== null) {
    var base = mod.base;
    var UpdateSpellCharge = base.add(0x27A6580);
    var CastSpell = base.add(0x27A6D00);
    var RemoveActiveSpell = base.add(0x27A73C0);
    var CooldownMultiplierOffset = 0x280;
    var SpellChargeLevelOffset = 0x284;
    var SpellCooldownDataOffset = 0x2A8;
    var SpellCooldownCountOffset = 0x2B0;
    var SpellCooldownEntrySize = 0x10;
    var SpellClassOffset = 0x10;
    var NoCooldownMultiplier = 0.0;
    var FullCharge = 1.0;

    function applyInfiniteSpells(spellManager) {
        try {
            if (!spellManager || spellManager.isNull()) return;
            spellManager.add(CooldownMultiplierOffset).writeFloat(NoCooldownMultiplier);
            spellManager.add(SpellChargeLevelOffset).writeFloat(FullCharge);
        } catch (e) {
            console.log('[狼人无限技能] 应用无限技能失败: ' + e);
        }
    }

    function clearFinishedSpellCooldown(spellManager, spell) {
        try {
            if (!spellManager || spellManager.isNull() || !spell || spell.isNull()) return;

            var spellClass = spell.add(SpellClassOffset).readPointer();
            var cooldownData = spellManager.add(SpellCooldownDataOffset).readPointer();
            var cooldownCountAddress = spellManager.add(SpellCooldownCountOffset);
            var cooldownCount = cooldownCountAddress.readS32();
            if (spellClass.isNull() || cooldownData.isNull() || cooldownCount <= 0 || cooldownCount > 64) return;

            for (var i = 0; i < cooldownCount; i++) {
                var entry = cooldownData.add(i * SpellCooldownEntrySize);
                if (!entry.readPointer().equals(spellClass)) continue;

                for (var j = i + 1; j < cooldownCount; j++) {
                    var source = cooldownData.add(j * SpellCooldownEntrySize);
                    var target = source.sub(SpellCooldownEntrySize);
                    target.writePointer(source.readPointer());
                    target.add(8).writeU64(source.add(8).readU64());
                }
                cooldownCountAddress.writeS32(cooldownCount - 1);
                return;
            }
        } catch (e) {
            console.log('[狼人无限技能] 清除已结束法术冷却失败: ' + e);
        }
    }

    Interceptor.attach(UpdateSpellCharge, {
        onEnter: function (args) {
            this.spellManager = args[0];
        },
        onLeave: function () {
            applyInfiniteSpells(this.spellManager);
        }
    });

    Interceptor.attach(CastSpell, {
        onEnter: function (args) {
            this.spellManager = args[0];
        },
        onLeave: function () {
            applyInfiniteSpells(this.spellManager);
        }
    });

    Interceptor.attach(RemoveActiveSpell, {
        onEnter: function (args) {
            this.spellManager = args[0];
            this.spell = args[1];
        },
        onLeave: function () {
            clearFinishedSpellCooldown(this.spellManager, this.spell);
            applyInfiniteSpells(this.spellManager);
        }
    });

    send('狼人无限技能: 已加载');
}
