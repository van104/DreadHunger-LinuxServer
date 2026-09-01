import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "山顶飞天甘油训练_Linux.js"


NODE_HARNESS = r"""
const source = JSON.parse(process.argv[1]);
const memory = new Map();
const hooks = new Map();
const intervals = new Map();
const timeouts = [];
const tierCalls = [];
const damageCalls = [];
const teleportCalls = [];
const destroyed = [];
const timeCalls = [];
let nitroAdds = 0;
let inventoryHasNitro = false;
let nextAllocation = 0x900000;

class Pointer {
  constructor(value) { this.value = Number(value); }
  add(offset) { return new Pointer(this.value + offset); }
  sub(offset) { return new Pointer(this.value - offset); }
  isNull() { return this.value === 0; }
  equals(other) { return this.value === other.value; }
  toString() { return '0x' + this.value.toString(16); }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  writePointer(value) { memory.set(this.value, value.value); }
  readU32() { return memory.get(this.value) || 0; }
  writeU32(value) { memory.set(this.value, value >>> 0); }
  readS32() { return memory.get(this.value) || 0; }
  writeS32(value) { memory.set(this.value, value); }
  readFloat() { return memory.get(this.value) || 0; }
  writeFloat(value) { memory.set(this.value, value); }
  readU64() { return memory.get(this.value) || 0; }
  writeU64(value) { memory.set(this.value, value); }
  writeU8(value) { memory.set(this.value, value); }
  writeUtf16String() {}
}

global.ptr = value => {
  if (typeof value === 'string') return new Pointer(Number(BigInt(value)));
  return new Pointer(value);
};
global.Memory = {
  alloc: size => {
    const result = new Pointer(nextAllocation);
    nextAllocation += Math.max(size, 16) + 16;
    return result;
  }
};
global.Process = {
  pointerSize: 8,
  findModuleByName: () => ({ base: new Pointer(0x200000) }),
  findRangeByAddress: address => address && !address.isNull() ? { protection: 'rw-' } : null
};
global.Interceptor = {
  attach: (address, callbacks) => hooks.set(address.value, callbacks)
};
global.setInterval = (callback, delay) => intervals.set(delay, callback);
global.setTimeout = (callback, delay) => {
  timeouts.push({ callback, delay });
  return timeouts.length;
};
global.send = () => {};

const world = new Pointer(0x700000);
const gameMode = new Pointer(0x710000);
const gameState = new Pointer(0x720000);
const playerData = new Pointer(0x730000);
const playerState = new Pointer(0x740000);
const controller = new Pointer(0x750000);
const pawn = new Pointer(0x760000);
const root = new Pointer(0x770000);
const inventory = new Pointer(0x780000);
const nitroClass = new Pointer(0x790000);
const predatorClass = new Pointer(0x7A0000);
const predatorData = new Pointer(0x7B0000);
const nearController = new Pointer(0x7C0000);
const nearPawn = new Pointer(0x7D0000);
const nearRoot = new Pointer(0x7E0000);
const farController = new Pointer(0x7F0000);
const farPawn = new Pointer(0x800000);
const farRoot = new Pointer(0x810000);

memory.set(0x5E9B6D0, world.value);
memory.set(world.value + 0x118, gameMode.value);
memory.set(gameMode.value + 0x280, gameState.value);
memory.set(gameState.value + 0x238, playerData.value);
memory.set(gameState.value + 0x240, 1);
memory.set(playerData.value, playerState.value);
memory.set(controller.value + 0x250, pawn.value);
memory.set(pawn.value + 0x130, root.value);
memory.set(pawn.value + 0x808, inventory.value);
memory.set(root.value + 0x1D0, 0);
memory.set(root.value + 0x1D4, 0);
memory.set(root.value + 0x1D8, 0);

memory.set(predatorData.value, nearController.value);
memory.set(predatorData.value + 8, farController.value);
memory.set(nearController.value + 0x250, nearPawn.value);
memory.set(nearPawn.value + 0x130, nearRoot.value);
memory.set(nearRoot.value + 0x1D0, 4434.21 + 100);
memory.set(nearRoot.value + 0x1D4, 6397.93);
memory.set(nearRoot.value + 0x1D8, 7297.65);
memory.set(farController.value + 0x250, farPawn.value);
memory.set(farPawn.value + 0x130, farRoot.value);
memory.set(farRoot.value + 0x1D0, 4434.21 + 7000);
memory.set(farRoot.value + 0x1D4, 6397.93);
memory.set(farRoot.value + 0x1D8, 7297.65);

global.NativeFunction = function (address, returnType, argumentTypes) {
  const offset = address.value - 0x200000;
  switch (offset) {
    case 0x26C6160:
      return () => 1;
    case 0x277E4F0:
      return ps => ps.equals(playerState) ? controller : new Pointer(0);
    case 0x277FAD0:
      return (ps, tier) => tierCalls.push([ps.value, tier]);
    case 0x26D4120:
      return (state, time, immediate) => timeCalls.push([state.value, time, immediate]);
    case 0x40A0430:
      return (actor, location) => {
        teleportCalls.push(location.slice());
        const actorRoot = actor.add(0x130).readPointer();
        memory.set(actorRoot.value + 0x1D0, location[0]);
        memory.set(actorRoot.value + 0x1D4, location[1]);
        memory.set(actorRoot.value + 0x1D8, location[2]);
        return 1;
      };
    case 0x408CCF0:
      return (actor, value) => {
        if (!Number.isInteger(value)) throw new Error('expected an integer');
        damageCalls.push([actor.value, value]);
      };
    case 0x2B9C070:
      return () => new Pointer(0x820000);
    case 0x2C95CA0:
      return () => nitroClass;
    case 0x2C97F00:
      return () => nitroClass;
    case 0x270E270:
      return () => inventoryHasNitro ? new Pointer(0x830000) : new Pointer(0);
    case 0x270CA50:
      return (manager, clazz, states, added) => {
        inventoryHasNitro = true;
        nitroAdds++;
        added.writeS32(1);
      };
    case 0x433F490:
      return (context, clazz, output) => {
        output.writePointer(predatorData);
        output.add(8).writeU32(2);
        output.add(12).writeU32(2);
      };
    case 0x27D1C40:
      return () => predatorClass;
    case 0x40950A0:
      return actor => { destroyed.push(actor.value); return 1; };
    case 0x2B130F0:
    case 0x2A13190:
    case 0x282B610:
      return () => {};
    default:
      throw new Error('unexpected native offset 0x' + offset.toString(16));
  }
};

eval(source);

const startup = timeouts.find(timer => timer.delay === 500);
if (!startup) throw new Error('missing startup monitor');
startup.callback();

if (teleportCalls.length !== 1) throw new Error('player was not teleported at match start');
const target = teleportCalls[0];
if (target[0] !== 4434.21 || target[1] !== 6397.93 || target[2] !== 7297.65) {
  throw new Error('wrong training coordinates');
}
if (nitroAdds !== 1 || !inventoryHasNitro) throw new Error('nitro was not added');
if (!tierCalls.some(call => call[0] === playerState.value && call[1] === 2)) {
  throw new Error('spell charge was not locked to tier one');
}
if (!damageCalls.some(call => call[0] === pawn.value && call[1] === 0)) {
  throw new Error('invincibility was not applied');
}
if (memory.get(pawn.value + 0xA30) !== 0 || memory.get(pawn.value + 0xA31) !== 0) {
  throw new Error('hunger or warmth update remained enabled');
}

const spellManager = new Pointer(0x840000);
const spell = new Pointer(0x850000);
const spellClass = new Pointer(0x860000);
const otherSpellClass = new Pointer(0x870000);
const cooldownData = new Pointer(0x880000);
memory.set(spell.value + 0x10, spellClass.value);
memory.set(spellManager.value + 0x2A8, cooldownData.value);
memory.set(spellManager.value + 0x2B0, 2);
memory.set(cooldownData.value, spellClass.value);
memory.set(cooldownData.value + 8, 1000);
memory.set(cooldownData.value + 0x10, otherSpellClass.value);
memory.set(cooldownData.value + 0x18, 2000);

const castHook = hooks.get(0x29A6D00);
if (!castHook) throw new Error('missing CastSpell hook');
memory.set(spellManager.value + 0x280, 1);
const castContext = {};
castHook.onEnter.call(castContext, [spellManager]);
if (memory.get(spellManager.value + 0x280) !== 0) throw new Error('cooldown was not disabled before cast');
castHook.onLeave.call(castContext);
if (memory.get(spellManager.value + 0x280) !== 0) throw new Error('cooldown multiplier was not cleared');
if (memory.get(spellManager.value + 0x2B0) !== 2) throw new Error('active spell timer was cleared too early');

const removeHook = hooks.get(0x29A73C0);
if (!removeHook) throw new Error('missing RemoveActiveSpell hook');
const removeContext = {};
removeHook.onEnter.call(removeContext, [spellManager, spell]);
removeHook.onLeave.call(removeContext);
if (memory.get(spellManager.value + 0x2B0) !== 1) throw new Error('finished spell cooldown was not removed');
if (memory.get(cooldownData.value) !== otherSpellClass.value || memory.get(cooldownData.value + 8) !== 2000) {
  throw new Error('remaining cooldown entry was not compacted');
}

intervals.get(5000)();
if (!timeCalls.some(call => call[0] === gameState.value && call[1] === 12 && call[2] === 1)) {
  throw new Error('time of day was not fixed at noon');
}

intervals.get(500)();
if (nitroAdds !== 1) throw new Error('an existing nitro was duplicated');

intervals.get(2000)();
if (!destroyed.includes(nearPawn.value) || !destroyed.includes(nearController.value)) {
  throw new Error('nearby predator was not removed');
}
if (destroyed.includes(farPawn.value) || destroyed.includes(farController.value)) {
  throw new Error('distant predator was removed');
}

memory.set(root.value + 0x1D0, 4434.21 + 3000);
intervals.get(500)();
const reset = timeouts.find(timer => timer.delay === 10000);
if (!reset) throw new Error('flight reset was not scheduled');

inventoryHasNitro = false;
reset.callback();
if (teleportCalls.length !== 2) throw new Error('player was not returned after ten seconds');
if (nitroAdds !== 2 || !inventoryHasNitro) throw new Error('nitro was not replenished after reset');
"""


class MountainNitroTrainingTests(unittest.TestCase):
    def test_training_cycle_and_predator_cleanup(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        result = subprocess.run(
            ["node", "-e", NODE_HARNESS, json.dumps(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
