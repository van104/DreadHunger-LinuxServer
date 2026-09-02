import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
SINGLE_PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "单人山顶飞天甘油训练.js.disabled"
MULTIPLAYER_PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "多人山顶飞天甘油训练.js"


NODE_HARNESS = r"""
const source = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const multiplayer = source.includes('多人山顶飞天甘油训练');
const memory = new Map();
const hooks = new Map();
const intervals = new Map();
const timeouts = [];
const tierCalls = [];
const equippedSpellCalls = [];
const damageCalls = [];
const teleportCalls = [];
const destroyed = [];
const timeCalls = [];
const autoMoveCalls = [];
const shipOnRepCalls = [];
const spawnedPackIce = [];
const spawnedNitro = [];
const launchedNitro = [];
let nitroPickupPresent = false;
let staticClassLookups = 0;
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
  },
  copy: (target, source, size) => {
    for (let i = 0; i < size; i++) memory.set(target.value + i, memory.get(source.value + i) || 0);
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
const playerSpellManager = new Pointer(0x745000);
const playerEquippedData = new Pointer(0x746000);
const controller = new Pointer(0x750000);
const pawn = new Pointer(0x760000);
const root = new Pointer(0x770000);
const playerState2 = new Pointer(0x7A1000);
const playerSpellManager2 = new Pointer(0x7A1800);
const playerEquippedData2 = new Pointer(0x7A1900);
const controller2 = new Pointer(0x7A2000);
const pawn2 = new Pointer(0x7A3000);
const root2 = new Pointer(0x7A4000);
const nitroPickupClass = new Pointer(0x790000);
const nitroInventoryClass = new Pointer(0x782000);
const spiritWalkClass = new Pointer(0x783000);
const destructiveSpellClass = new Pointer(0x784000);
const nitroPickupData = new Pointer(0x781000);
let nitroPickupActor = new Pointer(0);
const predatorClass = new Pointer(0x7A0000);
const predatorData = new Pointer(0x7B0000);
const nearController = new Pointer(0x7C0000);
const nearPawn = new Pointer(0x7D0000);
const nearRoot = new Pointer(0x7E0000);
const farController = new Pointer(0x7F0000);
const farPawn = new Pointer(0x800000);
const farRoot = new Pointer(0x810000);
const warship = new Pointer(0x890000);
const escapeVolume = new Pointer(0x88F000);
const warshipRoot = new Pointer(0x891000);
const packIceClass = new Pointer(0x892000);
const packIceActor = new Pointer(0x893000);
const packIceRoot = new Pointer(0x894000);
const packIceActorClass = new Pointer(0x895000);
const packIceData = new Pointer(0x896000);
const hullBreachClass = new Pointer(0x897000);
const hullBreachActor = new Pointer(0x898000);
const hullBreachData = new Pointer(0x899000);

memory.set(0x5E9B6D0, world.value);
memory.set(world.value + 0x118, gameMode.value);
memory.set(gameMode.value + 0x280, gameState.value);
memory.set(gameState.value + 0x2A8, warship.value);
memory.set(gameState.value + 0x2B0, escapeVolume.value);
memory.set(gameState.value + 0x238, playerData.value);
memory.set(gameState.value + 0x240, multiplayer ? 2 : 1);
memory.set(playerData.value, playerState.value);
if (multiplayer) memory.set(playerData.value + 8, playerState2.value);
memory.set(playerState.value + 0x480, playerSpellManager.value);
memory.set(playerSpellManager.value + 0x288, playerEquippedData.value);
memory.set(playerSpellManager.value + 0x290, 2);
memory.set(playerEquippedData.value, destructiveSpellClass.value);
memory.set(playerEquippedData.value + 8, destructiveSpellClass.value);
memory.set(playerState2.value + 0x480, playerSpellManager2.value);
memory.set(playerSpellManager2.value + 0x288, playerEquippedData2.value);
memory.set(playerSpellManager2.value + 0x290, 2);
memory.set(playerEquippedData2.value, destructiveSpellClass.value);
memory.set(playerEquippedData2.value + 8, destructiveSpellClass.value);
memory.set(controller.value + 0x250, pawn.value);
memory.set(pawn.value + 0x130, root.value);
memory.set(root.value + 0x1D0, 0);
memory.set(root.value + 0x1D4, 0);
memory.set(root.value + 0x1D8, 0);
memory.set(controller2.value + 0x250, pawn2.value);
memory.set(pawn2.value + 0x130, root2.value);
memory.set(root2.value + 0x1D0, 0);
memory.set(root2.value + 0x1D4, 0);
memory.set(root2.value + 0x1D8, 0);
memory.set(warship.value + 0x130, warshipRoot.value);
memory.set(warshipRoot.value + 0x1D0, 0);
memory.set(warshipRoot.value + 0x1D4, 0);
memory.set(warshipRoot.value + 0x1D8, 0);
memory.set(warship.value + 0x2A0, 500);
memory.set(warship.value + 0x2A8, 10000);

memory.set(packIceData.value, packIceActor.value);
memory.set(packIceActor.value + 0x10, packIceActorClass.value);
memory.set(packIceActor.value + 0x130, packIceRoot.value);
memory.set(packIceActor.value + 0x350, 0);
memory.set(packIceRoot.value + 0x1C0, 1);
memory.set(packIceRoot.value + 0x1D0, 4000);
memory.set(packIceRoot.value + 0x1D4, 200);
memory.set(packIceRoot.value + 0x1D8, 100);
memory.set(hullBreachData.value, hullBreachActor.value);

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
      return ps => ps.equals(playerState) ? controller : (ps.equals(playerState2) ? controller2 : new Pointer(0));
    case 0x277FAD0:
      return (ps, tier) => tierCalls.push([ps.value, tier]);
    case 0x27A75D0:
      return (manager, spells) => {
        const data = spells.readPointer();
        const count = spells.add(8).readU32();
        equippedSpellCalls.push([manager.value, count, data.readPointer().value]);
        const equipped = manager.add(0x288);
        equipped.writePointer(data);
        equipped.add(8).writeU32(count);
        equipped.add(12).writeU32(count);
      };
    case 0x26D4120:
      return (state, time, immediate) => timeCalls.push([state.value, time, immediate]);
    case 0x279FD60:
      return (ship, enabled) => autoMoveCalls.push([ship.value, enabled]);
    case 0x279FCA0:
      return ship => shipOnRepCalls.push(ship.value);
    case 0x40A0430:
      return (actor, location) => {
        teleportCalls.push({ actor: actor.value, location: location.slice() });
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
      return () => {
        staticClassLookups++;
        if (staticClassLookups === 1) return nitroPickupClass;
        if (staticClassLookups === 2) return nitroInventoryClass;
        return spiritWalkClass;
      };
    case 0x2C97F00:
      return () => nitroInventoryClass;
    case 0x433F490:
      return (context, clazz, output) => {
        if (clazz.equals(predatorClass)) {
          output.writePointer(predatorData);
          output.add(8).writeU32(2);
          output.add(12).writeU32(2);
        } else if (clazz.equals(packIceClass)) {
          output.writePointer(packIceData);
          output.add(8).writeU32(1);
          output.add(12).writeU32(1);
        } else if (clazz.equals(hullBreachClass)) {
          output.writePointer(hullBreachData);
          output.add(8).writeU32(1);
          output.add(12).writeU32(1);
        } else if (clazz.equals(nitroPickupClass)) {
          output.writePointer(nitroPickupPresent ? nitroPickupData : new Pointer(0));
          output.add(8).writeU32(nitroPickupPresent ? 1 : 0);
          output.add(12).writeU32(nitroPickupPresent ? 1 : 0);
          if (nitroPickupPresent) memory.set(nitroPickupData.value, nitroPickupActor.value);
        } else {
          throw new Error('unexpected actor class');
        }
      };
    case 0x27D1C40:
      return () => predatorClass;
    case 0x2827C00:
      return () => packIceClass;
    case 0x2802760:
      return () => hullBreachClass;
    case 0x26EC670:
      return actor => launchedNitro.push(actor.value);
    case 0x40950A0:
      return actor => { destroyed.push(actor.value); return 1; };
    case 0x478C420:
      return () => {};
    case 0x43EDEE0:
      return (context, clazz, transform) => {
        if (clazz.equals(nitroPickupClass)) {
          const actor = new Pointer(0x8D0000 + spawnedNitro.length * 0x2000);
          const actorRoot = actor.add(0x1000);
          memory.set(actor.value + 0x10, clazz.value);
          memory.set(actor.value + 0x130, actorRoot.value);
          memory.set(actorRoot.value + 0x1D0, transform.add(0x10).readFloat());
          memory.set(actorRoot.value + 0x1D4, transform.add(0x14).readFloat());
          memory.set(actorRoot.value + 0x1D8, transform.add(0x18).readFloat());
          nitroPickupActor = actor;
          nitroPickupPresent = true;
          spawnedNitro.push([
            transform.add(0x10).readFloat(),
            transform.add(0x14).readFloat(),
            transform.add(0x18).readFloat()
          ]);
          return actor;
        }
        const actor = new Pointer(0x89A000 + spawnedPackIce.length * 0x2000);
        const actorRoot = actor.add(0x1000);
        memory.set(actor.value + 0x10, clazz.value);
        memory.set(actor.value + 0x130, actorRoot.value);
        memory.set(actor.value + 0x350, 0);
        spawnedPackIce.push([context.value, clazz.value, actor.value]);
        return actor;
      };
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

const playerTeleports = teleportCalls.filter(call => call.actor === pawn.value);
const shipTeleports = teleportCalls.filter(call => call.actor === warship.value);
if (playerTeleports.length !== 1) throw new Error('player was not teleported at match start');
if (multiplayer && teleportCalls.filter(call => call.actor === pawn2.value).length !== 1) {
  throw new Error('second player was not teleported at match start');
}
const target = playerTeleports[0].location;
if (target[0] !== 4434.21 || target[1] !== 6397.93 || target[2] !== 7297.65) {
  throw new Error('wrong training coordinates');
}
if (spawnedNitro.length !== 1 || !nitroPickupPresent) throw new Error('nitro pickup was not spawned');
if (spawnedNitro[0][0] !== 4434.21 || spawnedNitro[0][1] !== 6397.93 || spawnedNitro[0][2] !== 7347.65) {
  throw new Error('wrong nitro refresh coordinates');
}
if (memory.get(nitroPickupActor.value + 0x248) !== nitroInventoryClass.value) {
  throw new Error('nitro pickup inventory class was not initialized');
}
if (memory.get(nitroPickupActor.value + 0x2F0) !== 1 || !launchedNitro.includes(nitroPickupActor.value)) {
  throw new Error('nitro pickup physics was not launched');
}
if (!tierCalls.some(call => call[0] === playerState.value && call[1] === 2)) {
  throw new Error('spell charge was not locked to tier one');
}
if (multiplayer) {
  if (!equippedSpellCalls.some(call => call[0] === playerSpellManager.value && call[1] === 1 && call[2] === spiritWalkClass.value)) {
    throw new Error('first player was not locked to spirit walk only');
  }
  if (!equippedSpellCalls.some(call => call[0] === playerSpellManager2.value && call[1] === 1 && call[2] === spiritWalkClass.value)) {
    throw new Error('second player was not locked to spirit walk only');
  }
}
if (!damageCalls.some(call => call[0] === pawn.value && call[1] === 0)) {
  throw new Error('invincibility was not applied');
}
if (memory.get(pawn.value + 0xA30) !== 0 || memory.get(pawn.value + 0xA31) !== 0) {
  throw new Error('hunger or warmth update remained enabled');
}
if (shipTeleports.length !== 1) throw new Error('ship was not moved at match start');
const shipTarget = shipTeleports[0].location;
if (shipTarget[0] !== 3942.55 || shipTarget[1] !== 171.26 || shipTarget[2] !== 99.9) {
  throw new Error('wrong ship coordinates');
}
if (!autoMoveCalls.some(call => call[0] === warship.value && call[1] === 0)) {
  throw new Error('ship auto move was not disabled');
}
if (memory.get(warship.value + 0x2A0) !== 10000 || shipOnRepCalls.length !== 1) {
  throw new Error('ship damage was not reset at match start');
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

const equippedCallsBeforeRelock = equippedSpellCalls.length;
if (multiplayer) {
  memory.set(playerSpellManager.value + 0x288, playerEquippedData.value);
  memory.set(playerSpellManager.value + 0x290, 2);
}
intervals.get(500)();
if (spawnedNitro.length !== 1) throw new Error('an existing nitro pickup was duplicated');
if (multiplayer && equippedSpellCalls.length !== equippedCallsBeforeRelock + 1) {
  throw new Error('a changed spell loadout was not locked back to spirit walk');
}

nitroPickupPresent = false;
nitroPickupActor = new Pointer(0);
intervals.get(500)();
if (spawnedNitro.length !== 2 || !nitroPickupPresent) {
  throw new Error('taken nitro pickup was not replaced at the refresh point');
}

const movedNitroRoot = nitroPickupActor.add(0x130).readPointer();
memory.set(movedNitroRoot.value + 0x1D0, 4434.21 + 1000);
intervals.get(500)();
if (spawnedNitro.length !== 3) throw new Error('a distant nitro pickup blocked the refresh point');

intervals.get(2000)();
if (!destroyed.includes(nearPawn.value) || !destroyed.includes(nearController.value)) {
  throw new Error('nearby predator was not removed');
}
if (destroyed.includes(farPawn.value) || destroyed.includes(farController.value)) {
  throw new Error('distant predator was removed');
}

let flightResets;
memory.set(warship.value + 0x2A0, 900);
memory.set(packIceActor.value + 0x350, 3);
destroyed.length = 0;
if (multiplayer) {
  memory.set(root.value + 0x1D0, 4434.21 + 3000);
  memory.set(root.value + 0x1D8, 7297.65);
  intervals.get(500)();
  const boundaryResets = timeouts.filter(timer => timer.delay === 10000);
  if (boundaryResets.length !== 1) throw new Error('mountain activity boundary reset was not scheduled');
  boundaryResets[0].callback();
  if (teleportCalls.filter(call => call.actor === pawn.value).length !== 2) {
    throw new Error('out-of-range mountain player was not returned');
  }
  if (teleportCalls.filter(call => call.actor === warship.value).length !== 1 || memory.get(warship.value + 0x2A0) !== 900) {
    throw new Error('mountain boundary return incorrectly reset the ship');
  }
  if (destroyed.includes(packIceActor.value)) {
    throw new Error('mountain boundary return incorrectly reset pack ice');
  }

  memory.set(root.value + 0x1D0, 4434.21 + 3000);
  memory.set(root.value + 0x1D8, 7297.65 - 800);
  memory.set(root2.value + 0x1D0, 4434.21 + 3000);
  memory.set(root2.value + 0x1D8, 7297.65 - 800);
  intervals.get(500)();
  const allResets = timeouts.filter(timer => timer.delay === 10000);
  flightResets = allResets.slice(1);
  if (flightResets.length !== 2) throw new Error('true per-player flight reset was not scheduled');
} else {
  memory.set(root.value + 0x1D0, 4434.21 + 3000);
  intervals.get(500)();
  flightResets = timeouts.filter(timer => timer.delay === 10000);
  if (flightResets.length !== 1) throw new Error('single-player flight reset was not scheduled');
}

flightResets[0].callback();
if (multiplayer) {
  if (teleportCalls.filter(call => call.actor === warship.value).length !== 1) {
    throw new Error('first returning player interrupted the second player flight');
  }
  if (memory.get(warship.value + 0x2A0) !== 900 || destroyed.includes(packIceActor.value)) {
    throw new Error('shared world was reset before all truly flying players returned');
  }
  flightResets[1].callback();
}
if (teleportCalls.filter(call => call.actor === pawn.value).length !== (multiplayer ? 3 : 2)) {
  throw new Error('player was not returned after ten seconds');
}
if (multiplayer && teleportCalls.filter(call => call.actor === pawn2.value).length !== 2) {
  throw new Error('second player was not independently returned after ten seconds');
}
if (teleportCalls.filter(call => call.actor === warship.value).length !== 2) {
  throw new Error('ship was not returned after flight reset');
}
if (spawnedNitro.length !== 3) throw new Error('flight reset duplicated the nitro pickup');
if (memory.get(warship.value + 0x2A0) !== 10000 || shipOnRepCalls.length !== 2) {
  throw new Error('ship damage was not reset after flight');
}
if (!destroyed.includes(hullBreachActor.value)) throw new Error('hull breaches were not cleared');
if (!destroyed.includes(packIceActor.value)) throw new Error('damaged pack ice was not removed');
const iceRespawn = timeouts.find(timer => timer.delay === 100);
if (!iceRespawn) throw new Error('damaged pack ice was not scheduled for respawn');
iceRespawn.callback();
if (spawnedPackIce.length !== 1 || spawnedPackIce[0][1] !== packIceActorClass.value) {
  throw new Error('damaged pack ice was not restored from its original class');
}
"""


class MountainNitroTrainingTests(unittest.TestCase):
    def test_only_multiplayer_variant_is_enabled_by_default(self):
        active = sorted(path.name for path in (LINUX_SERVER_ROOT / "Linux 插件").glob("*山顶飞天甘油训练*.js"))
        self.assertEqual(active, [MULTIPLAYER_PLUGIN_PATH.name])
        self.assertTrue(SINGLE_PLUGIN_PATH.is_file())

    def test_single_and_multiplayer_training_cycles(self):
        for plugin_path in (SINGLE_PLUGIN_PATH, MULTIPLAYER_PLUGIN_PATH):
            with self.subTest(plugin=plugin_path.name):
                source = plugin_path.read_text(encoding="utf-8")
                result = subprocess.run(
                    ["node", "-e", NODE_HARNESS],
                    input=json.dumps(source),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
