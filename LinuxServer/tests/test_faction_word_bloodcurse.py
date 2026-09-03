import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "阵营词语血咒玩法_Linux.js"


NODE_HARNESS = r'''
const source = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const memory = new Map();
const hooks = new Map();
const messages = [];
const thrallCalls = [];
const equippedCalls = [];
const hushCalls = [];
const deadCalls = [];
const reviveCalls = [];
const spiritCalls = [];
const ignoreCalls = [];
const coalCalls = [];
let matchStarted = false;
let now = 100000;
let nextAllocation = 0x1000000;
let classIndex = 0;

class Pointer {
  constructor(value) { this.value = Number(value); }
  add(offset) { return new Pointer(this.value + Number(offset)); }
  isNull() { return this.value === 0; }
  equals(other) { return !!other && this.value === other.value; }
  toString() { return '0x' + this.value.toString(16); }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  writePointer(value) { memory.set(this.value, value.value); }
  readU8() { return memory.get(this.value) || 0; }
  writeU8(value) { memory.set(this.value, value); }
  readU32() { return memory.get(this.value) || 0; }
  writeU32(value) { memory.set(this.value, value >>> 0); }
  readS32() { return memory.get(this.value) || 0; }
  writeS32(value) { memory.set(this.value, value); }
  readU64() { return memory.get(this.value) || 0; }
  writeU64(value) { memory.set(this.value, value); }
  readFloat() { return memory.get(this.value) || 0; }
  writeFloat(value) { memory.set(this.value, value); }
  writeUtf16String() {}
}

global.ptr = value => new Pointer(typeof value === 'string' ? Number(BigInt(value)) : value);
global.Memory = { alloc: size => { const p = new Pointer(nextAllocation); nextAllocation += Math.max(size, 16) + 16; return p; } };
global.Process = {
  pointerSize: 8,
  findModuleByName: () => ({ base: new Pointer(0x200000) }),
  findRangeByAddress: p => p && !p.isNull() ? { protection: 'rw-' } : null
};
global.Interceptor = { attach: (address, callbacks) => hooks.set(address.value, callbacks) };
global.send = value => messages.push(String(value));
global.setTimeout = () => 0;
global.setInterval = () => 0;
global.Date = { now: () => now };
Math.random = () => 0.9;

const world = new Pointer(0x700000);
const gameMode = new Pointer(0x710000);
const gameState = new Pointer(0x720000);
const playerArray = new Pointer(0x730000);
const warship = new Pointer(0x740000);
const warshipRoot = new Pointer(0x741000);
const playerStates = [];
const controllers = [];
const pawns = [];
for (let i = 0; i < 7; i++) {
  playerStates.push(new Pointer(0x750000 + i * 0x1000));
  controllers.push(new Pointer(0x800000 + i * 0x1000));
  pawns.push(new Pointer(0x900000 + i * 0x1000));
  memory.set(controllers[i].value + 0x228, playerStates[i].value);
  memory.set(controllers[i].value + 0x250, pawns[i].value);
  memory.set(playerStates[i].value + 0x480, 0xA50000 + i * 0x1000);
  memory.set(pawns[i].value + 0x130, 0xA00000 + i * 0x1000);
  memory.set(0xA00000 + i * 0x1000 + 0x1D0, i * 10);
  memory.set(0xA00000 + i * 0x1000 + 0x1D4, 0);
  memory.set(0xA00000 + i * 0x1000 + 0x1D8, 0);
}
const psData = new Pointer(0x780000);
for (let i = 0; i < 7; i++) memory.set(psData.value + i * 8, playerStates[i].value);
memory.set(0x5E9B6D0, world.value);
memory.set(world.value + 0x118, gameMode.value);
memory.set(gameMode.value + 0x280, gameState.value);
memory.set(gameMode.value + 0x2C0, 0x5C1B978);
memory.set(gameMode.value + 0x3A8, 0x7F0000);
memory.set(gameState.value + 0x238, psData.value);
memory.set(gameState.value + 0x240, 2);
memory.set(gameState.value + 0x2A8, warship.value);
memory.set(gameState.value + 0x348, 5);
memory.set(warship.value + 0x130, warshipRoot.value);
memory.set(warshipRoot.value + 0x1D0, 100);
memory.set(warshipRoot.value + 0x1D4, 100);
memory.set(warshipRoot.value + 0x1D8, 100);
memory.set(0x5C1B978, 0x5C1B978);

global.NativeFunction = function(address) {
  const offset = address.value - 0x200000;
  switch (offset) {
    case 0x26C6160: return () => matchStarted ? 1 : 0;
    case 0x277E4F0: return ps => { const i = playerStates.findIndex(p => p.equals(ps)); return i >= 0 ? controllers[i] : new Pointer(0); };
    case 0x277F060: return (ps, value) => thrallCalls.push([ps.value, value]);
    case 0x277EE70: return (ps, value) => memory.set(ps.value + 0x568, value);
    case 0x27807E0: return (ps, value) => hushCalls.push([ps.value, value]);
    case 0x26D62A0: return (gs, value) => hushCalls.push([gs.value, value]);
    case 0x27A75D0: return (manager, array) => equippedCalls.push([manager.value, array.add(8).readU32()]);
    case 0x269E8A0: return (pawn, killer) => deadCalls.push([pawn.value, killer.value]);
    case 0x2693900: return pawn => reviveCalls.push(pawn.value);
    case 0x2693DD0: return () => {};
    case 0x2691610: return (pawn, enabled, duration) => spiritCalls.push([pawn.value, enabled, duration]);
    case 0x446CD10: return (controller, value) => ignoreCalls.push(['move', controller.value, value]);
    case 0x446CD50: return (controller, value) => ignoreCalls.push(['look', controller.value, value]);
    case 0x408CCF0: return () => {};
    case 0x26C8920: return () => {};
    case 0x26CACE0: return (gm, actor) => coalCalls.push([gm.value, actor.value]);
    case 0x26EC670: return () => {};
    case 0x478C420: return () => {};
    case 0x43EDEE0: return () => new Pointer(0xB00000 + coalCalls.length * 0x1000);
    case 0x2B9C070: return () => new Pointer(0xC00000);
    case 0x2C95CA0: return () => new Pointer(0xD00000 + classIndex++ * 0x1000);
    case 0x2C97F00: return () => new Pointer(0xD10000);
    case 0x2B130F0: return () => {};
    case 0x2A13190: return () => {};
    case 0x282B610: return (controller, text) => messages.push(['message', controller.value, text.value]);
    case 0x43360E0: return () => {};
    case 0x2730050: return () => {};
    case 0x26CB250: return () => {};
    case 0x4335A40: return () => { matchStarted = true; };
    case 0x4336360: return () => {};
    default: return () => {};
  }
};

eval(source);
const tick = hooks.get(0x4536360);
if (!tick) throw new Error('GameMode Tick hook missing');
function runTick() { tick.onEnter.call({}, [gameMode]); }
runTick();
runTick();
now += 11000;
runTick();
if (thrallCalls.filter(call => call[1] === 1).length === 0) throw new Error('wolf was not assigned');
if (equippedCalls.length === 0 || equippedCalls[equippedCalls.length - 1][1] !== 2) throw new Error('wolf does not have two spell slots');
if (coalCalls.length !== 1) throw new Error('one coal was not added during countdown');
if (!ignoreCalls.some(call => call[2] === 1) || !ignoreCalls.some(call => call[2] === 0)) throw new Error('countdown movement lock did not toggle');

const wolfIndex = thrallCalls.find(call => call[1] === 1)[0];
const wolfPosition = playerStates.findIndex(ps => ps.value === wolfIndex);
const wolfController = controllers[wolfPosition];
const targetPosition = wolfPosition === 0 ? 1 : 0;
const hushClass = new Pointer(0xD02000);
const cannibalsClass = new Pointer(0xD03000);
memory.set(pawns[targetPosition].value + 0xE10, 1);
const cast = hooks.get(0x2971FD0);
if (!cast) throw new Error('CastTotemSpell hook missing');
const hushArgs = [wolfController, hushClass, pawns[targetPosition]];
cast.onEnter(hushArgs);
runTick();
if (reviveCalls.length !== 1 || spiritCalls.length !== 1) throw new Error('antidote did not revive and spirit-walk target');
const poisonArgs = [wolfController, cannibalsClass, pawns[targetPosition]];
cast.onEnter(poisonArgs);
runTick();
if (deadCalls.length !== 1) throw new Error('poison did not directly kill target');

memory.set(gameState.value + 0x348, 18);
runTick();
now += 30000;
runTick();
if (!hushCalls.some(call => call[0] === gameState.value && call[1] === 1)) throw new Error('evening silence did not start');
now += 60000;
runTick();
if (!hushCalls.some(call => call[0] === gameState.value && call[1] === 0)) throw new Error('silence did not end');
'''


class FactionWordBloodCurseTests(unittest.TestCase):
    def test_plugin_loads_and_covers_core_flow(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        result = subprocess.run(
            ["node", "-e", NODE_HARNESS],
            input=json.dumps(source, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deployment_conflicts_are_documented(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for name in ("开局沉默", "狼人无限技能", "修复充能", "表情不当狼", "山顶训练"):
            self.assertIn(name, source)
        self.assertIn("mode: 'two_player_test'", source)
        self.assertIn("requiredPlayers: 2", source)
        self.assertIn("requiredPlayers: 7", source)
        self.assertIn("spiritWalkTier: 4", source)
        self.assertIn("ADH_GameState_SetWinningTeam", source)


if __name__ == "__main__":
    unittest.main()
