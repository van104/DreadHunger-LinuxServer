import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "[服务端]狼人无限技能_Linux.js"


NODE_HARNESS = r"""
const source = JSON.parse(process.argv[1]);
const hooks = new Map();
const memory = new Map();

class Pointer {
  constructor(value) { this.value = value; }
  add(offset) { return new Pointer(this.value + offset); }
  sub(offset) { return new Pointer(this.value - offset); }
  isNull() { return this.value === 0; }
  equals(other) { return this.value === other.value; }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  writePointer(value) { memory.set(this.value, value.value); }
  writeFloat(value) { memory.set(this.value, value); }
  readS32() { return memory.get(this.value) || 0; }
  writeS32(value) { memory.set(this.value, value); }
  readU64() { return memory.get(this.value) || 0; }
  writeU64(value) { memory.set(this.value, value); }
}

global.Process = {
  findModuleByName: () => ({ base: new Pointer(0x200000) })
};
global.Interceptor = {
  attach: (address, callbacks) => hooks.set(address.value, callbacks)
};
global.send = () => {};

eval(source);

const manager = new Pointer(0x700000);
const spell = new Pointer(0x710000);
const spellClass = new Pointer(0x720000);
const otherSpellClass = new Pointer(0x730000);
const cooldownData = new Pointer(0x740000);

memory.set(0x710010, spellClass.value);
memory.set(0x7002A8, cooldownData.value);
memory.set(0x7002B0, 2);
memory.set(0x740000, spellClass.value);
memory.set(0x740008, 1000);
memory.set(0x740010, otherSpellClass.value);
memory.set(0x740018, 2000);

for (const address of [0x29A6580, 0x29A6D00]) {
  const hook = hooks.get(address);
  if (!hook) throw new Error('missing hook at 0x' + address.toString(16));
  const context = {};
  hook.onEnter.call(context, [manager]);
  hook.onLeave.call(context);
  if (memory.get(0x700280) !== 0.0) {
    throw new Error('cooldown multiplier was not cleared after hook 0x' + address.toString(16));
  }
  if (memory.get(0x700284) !== 1.0) {
    throw new Error('charge was not restored after hook 0x' + address.toString(16));
  }
  if (memory.get(0x7002B0) !== 2 || memory.get(0x740008) !== 1000) {
    throw new Error('active spell timestamp was changed after hook 0x' + address.toString(16));
  }
  memory.set(0x700280, 1.0);
  memory.set(0x700284, 0.0);
}

const removeHook = hooks.get(0x29A73C0);
if (!removeHook) throw new Error('missing RemoveActiveSpell hook');
const removeContext = {};
removeHook.onEnter.call(removeContext, [manager, spell]);
removeHook.onLeave.call(removeContext);
if (memory.get(0x7002B0) !== 1) throw new Error('finished spell cooldown was not removed');
if (memory.get(0x740000) !== otherSpellClass.value || memory.get(0x740008) !== 2000) {
  throw new Error('remaining cooldown entry was not compacted');
}
"""


class InfiniteThrallSpellsTests(unittest.TestCase):
    def test_active_timer_is_preserved_until_spell_ends(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        result = subprocess.run(
            ["node", "-e", NODE_HARNESS, json.dumps(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
