import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "[服务端]人物无敌_Linux.js"


NODE_HARNESS = r"""
const source = JSON.parse(process.argv[1]);
const hooks = new Map();
const memory = new Map();
const nativeCalls = [];

class Pointer {
  constructor(value) { this.value = value; }
  add(offset) { return new Pointer(this.value + offset); }
  isNull() { return this.value === 0; }
  writeU8(value) { memory.set(this.value, value); }
}

global.Process = {
  findModuleByName: () => ({ base: new Pointer(0x200000) })
};
global.NativeFunction = function (address, returnType, argumentTypes) {
  if (address.value !== 0x428CCF0) throw new Error('wrong SetCanBeDamaged address');
  if (returnType !== 'void' || argumentTypes.join(',') !== 'pointer,bool') {
    throw new Error('wrong SetCanBeDamaged signature');
  }
  return (character, canBeDamaged) => {
    if (!Number.isInteger(canBeDamaged)) throw new Error('expected an integer');
    nativeCalls.push([character.value, canBeDamaged]);
  };
};
global.Interceptor = {
  attach: (address, callbacks) => hooks.set(address.value, callbacks)
};
global.send = () => {};

eval(source);

const tickHook = hooks.get(0x2895160);
if (!tickHook) throw new Error('missing HumanCharacter::Tick hook');

const character = new Pointer(0x700000);
memory.set(0x700A30, 1);
memory.set(0x700A31, 1);
tickHook.onEnter([character]);

if (memory.get(0x700A30) !== 0) throw new Error('hunger update was not disabled');
if (memory.get(0x700A31) !== 0) throw new Error('warmth update was not disabled');
if (nativeCalls.length !== 1 || nativeCalls[0][0] !== character.value || nativeCalls[0][1] !== 0) {
  throw new Error('damage was not disabled');
}
"""


class InvincibleHumansTests(unittest.TestCase):
    def test_damage_hunger_and_warmth_are_disabled_on_tick(self):
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
