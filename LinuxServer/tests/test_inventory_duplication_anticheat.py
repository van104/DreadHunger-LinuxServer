import json
import subprocess
import tempfile
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "app" / "Linux 插件" / "[服务端]反作弊物资_Linux.js"
V2_PLUGIN_PATH = PLUGIN_PATH.with_name("[服务端]反作弊物资_v2_Linux.js")
if not V2_PLUGIN_PATH.exists():
    V2_PLUGIN_PATH = V2_PLUGIN_PATH.with_suffix(".js.disabled")


NODE_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const source = typeof input === 'string' ? input : input.anticheat;
const mode = process.argv[2];
const memory = new Map();
const strings = new Map();
const textValues = new Map();
const files = new Map();
const hooks = new Map();
let nextAllocation = 0x900000;

class Pointer {
  constructor(value) { this.value = Number(value); }
  add(offset) { return new Pointer(this.value + Number(offset)); }
  isNull() { return this.value === 0; }
  equals(other) { return this.value === other.value; }
  toInt32() { return this.value | 0; }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  writePointer(value) { memory.set(this.value, value.value); }
  readU32() { return memory.get(this.value) || 0; }
  writeU32(value) { memory.set(this.value, Number(value) >>> 0); }
  readS32() { return memory.get(this.value) || 0; }
  writeS32(value) { memory.set(this.value, Number(value)); }
  readU8() { return memory.get(this.value) || 0; }
  readFloat() { return memory.has(this.value) ? memory.get(this.value) : 0; }
  writeFloat(value) { memory.set(this.value, Number(value)); }
  writeByteArray(value) { Array.from(value).forEach((v, i) => memory.set(this.value + i, v)); }
  readByteArray(size) {
    const signatures = {
      [moduleBase + 0x32C]: 'cd762268d82e378f',
      [moduleBase + 0x27CB540]: '4156534883ec28f30f114424044885ff',
      [moduleBase + 0x2721780]: '554157415653504989d74989f64889fb',
      [moduleBase + 0x270BA70]: '554157415641554154534883ec784531',
      [moduleBase + 0x26891D0]: '554157415641554154534881ecc80000',
      [moduleBase + 0x2712200]: '55415741564154534883ec3080bf7103',
      [moduleBase + 0x2721A70]: '554157415641554154534881ec880100',
      [moduleBase + 0x26A0D00]: '534889fb4881c7c80e0000e8b0ee0700',
      [moduleBase + 0x409E270]: '41574156534883ec204989cf4989d648',
      [moduleBase + 0x280AD20]: '50488b0578be21034885c0740259c3bf'
    };
    for (const match of source.matchAll(/checkBytes\((0x[0-9A-F]+), '([a-f0-9]+)'\)/g)) {
      if (!(moduleBase + Number(match[1]) in signatures)) signatures[moduleBase + Number(match[1])] = match[2];
    }
    let bytes = Buffer.from(signatures[this.value] || '', 'hex');
    if (mode === 'wrong_build') bytes.fill(0);
    return Uint8Array.from(bytes.subarray(0, size)).buffer;
  }
  writeU8(value) { memory.set(this.value, Number(value)); }
  writeUtf16String(value) { strings.set(this.value, String(value)); }
  readUtf16String() { return strings.get(this.value) || ''; }
  toString() { return '0x' + this.value.toString(16); }
}

function writeFString(output, value) {
  const data = Memory.alloc((value.length + 1) * 2);
  data.writeUtf16String(value);
  output.writePointer(data);
  output.add(8).writeU32(value.length);
}

global.ptr = value => new Pointer(typeof value === 'string' ? Number(value) : value);
global.Memory = {
  copy: (target, origin, size) => {
    const values = [...memory.entries()].filter(([at]) => at >= origin.value && at < origin.value + size);
    for (const at of memory.keys()) if (at >= target.value && at < target.value + size) memory.delete(at);
    for (const [at, value] of values) memory.set(target.value + at - origin.value, value);
  },
  alloc: size => {
    const result = new Pointer(nextAllocation);
    nextAllocation += Math.max(16, Number(size)) + 16;
    return result;
  }
};

const moduleBase = 0x200000;
const world = new Pointer(0x700000);
const gameMode = new Pointer(0x710000);
const gameState = new Pointer(0x720000);
const playerArrayData = new Pointer(0x730000);
const playerState = new Pointer(0x740000);
const controller = new Pointer(0x750000);
const pawn = new Pointer(0x760000);
const inventory = new Pointer(0x770000);
const roleInfo = new Pointer(0x780000);
const coalClass = new Pointer(0x790000);
const inventoryBaseClass = Memory.alloc(64);
const coalPath = '/Game/Blueprints/Inventory/Coal/BP_Coal_Inventory.BP_Coal_Inventory_C';
const trustedPath = '/srv/dh/.gm_runtime/anti_cheat_trusted_items.json';
const nativeEventsPath = '/srv/dh/.gm_runtime/anti_cheat_events.json';
const messages = [];
const logMessages = [];
console.log = value => logMessages.push(String(value));
const kickCalls = [], banRequests = [];
const accountValues = new Map();
function setAccount(state, value) {
  const unique = Memory.alloc(64), vtable = Memory.alloc(64);
  state.add(0x258).writePointer(unique); unique.writePointer(vtable);
  vtable.add(0x38).writePointer(ptr(moduleBase + 0x1000));
  accountValues.set(unique.value, value);
}
setAccount(playerState, 'EOSPlus:76561198000000000_+_|0123456789abcdef0123456789abcdef');
const owningControllers = new Map();
const weakSerials = new Map(), objectSerials = new Map();
const gameSession = Memory.alloc(1024);
gameMode.add(0x278).writePointer(gameSession);
const replacements = new Map();
let originalRangedCalls = 0;
let recordedCheats = 0;
let originalTransfers = 0, originalPickups = 0, originalHits = 0;
let originalInteractions = 0, originalMeleeUses = 0, originalMeleeHits = 0;
let originalRangedReloads = 0, originalReloadCompletions = 0;
const meleeTargets = [];
function completePickup(component, target, slot) {
  const hook = hooks.get(moduleBase + 0x27650A0), context = {threadId: mode === 'pickup_other_thread' ? 2 : 1};
  if (hook) hook.onEnter.call(context, [component, target, ptr(slot)]);
  replacements.get(moduleBase + 0x2712200)(target.add(0xA0).readPointer(), controller, slot);
  if (mode === 'pickup_repeat_completion') {
    replacements.get(moduleBase + 0x2712200)(target.add(0xA0).readPointer(), controller, slot);
  }
  component.add(0x198).writePointer(ptr(0));
  if (hook) hook.onLeave.call(context, ptr(0));
}
let ammoForReload = ptr(0), reloadConsumes = true;
let fakeGameTime = 1000;
let fakeNow = 1000000;
Date.now = () => fakeNow;
const digSiteClass = Memory.alloc(64), totemClass = Memory.alloc(64), destructibleClass = Memory.alloc(64);
const climbableClass = Memory.alloc(64), climbableBlueprintClass = Memory.alloc(64), climbableSuperChain = Memory.alloc(16);
climbableClass.add(0x38).writeS32(1);
climbableBlueprintClass.add(0x38).writeS32(1);
climbableBlueprintClass.add(0x30).writePointer(climbableSuperChain);
climbableSuperChain.add(8).writePointer(climbableClass.add(0x30));
const characterClass = Memory.alloc(64), characterBlueprintClass = Memory.alloc(64), characterSuperChain = Memory.alloc(16);
characterClass.add(0x38).writeS32(1);
characterBlueprintClass.add(0x38).writeS32(1);
characterBlueprintClass.add(0x30).writePointer(characterSuperChain);
characterSuperChain.add(8).writePointer(characterClass.add(0x30));
const animalClass = Memory.alloc(64), animalBlueprintClass = Memory.alloc(64), animalSuperChain = Memory.alloc(24);
animalClass.add(0x38).writeS32(2);
animalBlueprintClass.add(0x38).writeS32(2);
animalBlueprintClass.add(0x30).writePointer(animalSuperChain);
animalSuperChain.add(8).writePointer(characterClass.add(0x30));
animalSuperChain.add(16).writePointer(animalClass.add(0x30));
const actorBounds = new Map();
const recipeMesh = Memory.alloc(4096), recipeBody = Memory.alloc(256), ground = Memory.alloc(1024);
const groundActor = Memory.alloc(4096), attachmentActor = Memory.alloc(4096);
ground.add(0xA0).writePointer(groundActor);
let digSites = [], actorScans = 0, nativeFrees = 0, groundProjects = 0;
const staleWeakObjects = new Set();
let placementPosition = [100, 0, 0], placementNormal = [0, 0, 1];
let surfaceType = 0, seaLevel = -10;
const totemBlueprintClass = Memory.alloc(64), totemSuperChain = Memory.alloc(8);
totemClass.add(0x38).writeS32(0);
totemBlueprintClass.add(0x30).writePointer(totemSuperChain);
totemBlueprintClass.add(0x38).writeS32(0);
totemSuperChain.writePointer(totemClass.add(0x30));

memory.set(moduleBase + 0x5C9B6D0, world.value);
memory.set(world.value + 0x118, gameMode.value);
memory.set(gameMode.value + 0x280, gameState.value);
memory.set(gameState.value + 0x238, playerArrayData.value);
memory.set(gameState.value + 0x240, 1);
memory.set(playerArrayData.value, playerState.value);
memory.set(playerState.value + 0x588, roleInfo.value);
memory.set(controller.value + 0x250, pawn.value);
memory.set(pawn.value + 0x808, inventory.value);
writeFString(roleInfo.add(0x48), 'Captain');

global.Process = {
  pointerSize: 8,
  getCurrentThreadId: () => 1,
  findModuleByName: () => ({ base: new Pointer(moduleBase) }),
  findRangeByAddress: () => ({ protection: mode === 'ban_non_executable' ? 'r--' : 'r-x' })
};
global.Interceptor = {
  attach: (address, callbacks) => hooks.set(address.value, callbacks),
  replace: (address, callback) => replacements.set(address.value, callback)
};
global.NativeCallback = function(callback) { return callback; };
global.File = function(path, access) {
  if (mode === 'gm_write_failure' && path === trustedPath) throw new Error('permission denied');
  if (access !== 'w') throw new Error('unexpected file mode');
  files.set(path, '');
  this.write = value => files.set(path, files.get(path) + String(value));
  this.close = () => {};
};
File.readAllText = path => {
    if (!files.has(path)) throw new Error('file missing');
    return files.get(path);
};
File.writeAllText = (path, value) => {
  if (mode === 'gm_write_failure' && path === trustedPath) throw new Error('permission denied');
  value = String(value);
  // 实跑 Frida 17.16.1：静态覆盖写入不会截掉较长的旧尾部。
  files.set(path, value + (files.get(path) || '').slice(value.length));
};
global.DH_LINUX_ROOT = '/srv/dh';
global.send = payload => {
  if (mode === 'ban_send_failure') throw new Error('delivery failed');
  banRequests.push(payload);
};

global.NativeFunction = function(address) {
  const offset = address.value - moduleBase;
  switch (offset) {
    case 0x1000:
      return (output, unique) => writeFString(output, accountValues.get(unique.value) || '');
    case 0x2B130F0:
      return (output, input) => textValues.set(output.value, strings.get(input.value) || '');
    case 0x2A13190:
      return (output, input) => textValues.set(output.value, textValues.get(input.value) || '');
    case 0x282B4B0:
      return (_controller, message) => messages.push(textValues.get(message.value) || '');
    case 0x459E030:
      return output => writeFString(output, '测试用户');
    case 0x277E4F0:
      return state => owningControllers.get(state.value) || controller;
    case 0x4346570:
      return (session, target, reason) => {
        if (!session.equals(gameSession)) throw new Error('kick ABI mismatch');
        const label = textValues.get(reason.value) || '';
        if (!label.startsWith('反作弊：') || label.includes('（')) throw new Error('kick reason contains technical details');
        if (!label.includes('服务器黑名单') && messages.length < 1) throw new Error('kick before announcement');
        if (mode === 'ban_detect' && banRequests.length !== 1) throw new Error('kick before blacklist identity delivery');
        kickCalls.push({controller: target.value, reason: label});
        return mode === 'v2_retry' && kickCalls.length === 1 ? 0 : 1;
      };
    case 0x2B9C070:
      return () => new Pointer(0x7A0000);
    case 0x280AD20:
      return () => inventoryBaseClass;
    case 0x2C95CA0:
      return (_uclass, _outer, path) => strings.get(path.value) === coalPath ? coalClass : new Pointer(0);
    case 0x2721780:
      return weapon => {
        originalRangedCalls++;
        if (mode.startsWith('arrow_') || mode.startsWith('gun_')) {
          if (mode !== 'arrow_no_consumption' && mode !== 'gun_no_consumption') {
            weapon.add(0x8CC).writeU8(weapon.add(0x8CC).readU8() - 1);
          }
          hooks.get(moduleBase + 0x26A0D00).onEnter.call({}, [pawn, new Pointer(0x800000)]);
        }
        return 1;
      };
    case 0x26891D0:
      return (_pawn, source, sourceSlot, target, _targetSlot, quantity) => {
        originalTransfers++;
        if (!mode.startsWith('stack_transfer_')) return;
        const item = source.add(0x138).readPointer().readPointer();
        const added = mode === 'stack_transfer_excess' ? quantity + 30 : quantity;
        const destination = mode === 'stack_transfer_wrong_target' ? inventory : target;
        addCoal(added, false, destination, mode === 'stack_transfer_wrong_class' ? ptr(0x123456) : coalClass);
        if (mode === 'stack_transfer_multi_add') addCoal(30, false, target);
        if (mode !== 'stack_transfer_no_debit') {
          const left = item.add(0x8B0).readU8() - quantity;
          item.add(0x8B0).writeU8(Math.max(0, left));
          if (left <= 0) source.add(0x138).readPointer().writePointer(ptr(0));
          let received = target.add(0x138).readPointer().readPointer();
          if (received.isNull()) {
            received = Memory.alloc(4096);
            received.add(0x10).writePointer(coalClass); received.add(0xF0).writeU8(3);
            target.add(0x138).readPointer().writePointer(received);
          }
          received.add(0x8B0).writeU8(received.add(0x8B0).readU8() + added);
        }
      };
    case 0x2712200:
      return () => { originalPickups++; return new Pointer(0x800000); };
    case 0x2721A70:
      return () => { originalHits++; };
    case 0x27647E0:
      return (component, target, slot) => {
        originalInteractions++;
        if (mode === 'interact_legacy_range') {
          const type = Memory.alloc(16); writeFString(type, 'Long Range Interacts');
          hooks.get(moduleBase + 0x27CB540).onEnter.call({}, [playerState, type, ptr(0)]);
        }
        if ((mode.startsWith('pickup_') || mode.startsWith('snow_') || mode === 'climb_complete_pickup') && mode !== 'pickup_rejected_interact') {
          component.add(0x198).writePointer(pawn);
          if (mode === 'pickup_immediate') completePickup(component, target, slot);
        }
      };
    case 0x45AB920:
      return (target, origin, point) => {
        if (mode === 'interact_no_collision' || mode.startsWith('climb_')) return -1;
        for (let i = 0; i < 3; i++) memory.set(point.value + i * 4, target.add(0x1D0 + i * 4).readFloat());
        return mode === 'interact_inside_collision' ? (Memory.copy(point, origin, 12), 0) : 1;
      };
    case 0x4342710:
      return () => fakeGameTime;
    case 0x280C210:
      return (weapon, state) => weapon.add(0x290).readU8() === 24 && state.readU8() === 1 ? 2 : weapon.add(0x520).readFloat();
    case 0x28548F0:
      return (weapon, state) => weapon.add(0x290).readU8() === 24 ? Number(state.readU8() !== 2) : Number(state.readU8() === 0);
    case 0x271FE40:
      return weapon => {
        originalMeleeUses++;
        if (['melee_failed_use', 'bone_dagger_failed_use'].includes(mode) ||
            (mode === 'bone_dagger_next_failed_use' && originalMeleeUses === 2)) return 0;
        weapon.add(0x528).writePointer(ptr(1));
        return 1;
      };
    case 0x2720BF0:
      return (_weapon, hits) => {
        originalMeleeHits++;
        for (let i = 0; i < hits.add(8).readS32(); i++) {
          meleeTargets.push(hits.readPointer().add(i * 0x8C + 0x6C).readS32());
        }
      };
    case 0x408DAD0:
      return () => ptr(0x880000);
    case 0x470C0C0:
      return (_manager, handle) => handle.readPointer();
    case 0x470D300:
      return (_manager, timer) => timer.isNull() ? -1 : timer.readFloat();
    case 0x2854EE0:
      return () => reloadConsumes ? 1 : 0;
    case 0x270E270:
      return () => ammoForReload;
    case 0x26F96E0:
      return ammo => ammo.add(0x8B0).readU8();
    case 0x26F9700:
      return (manager, slot) => {
        if (slot < 0 || slot >= manager.add(0x240).readS32()) return ptr(0);
        for (let i = 0; i < manager.add(0x140).readS32(); i++) {
          const item = manager.add(0x138).readPointer().add(i * 8).readPointer();
          if (!item.isNull() && item.add(0x870).readS32() === slot) return item;
        }
        return ptr(0);
      };
    case 0x2721600:
      return weapon => {
        originalRangedReloads++;
        if (mode === 'reload_no_ammo') return;
        if (reloadConsumes && !ammoForReload.isNull() && mode !== 'reload_free_ammo') {
          ammoForReload.add(0x8B0).writeU8(ammoForReload.add(0x8B0).readU8() - 1);
        }
        replacements.get(moduleBase + 0x27073C0)(weapon);
      };
    case 0x27073C0:
      return weapon => { originalReloadCompletions++; weapon.add(0x8CC).writeU8(weapon.add(0x51C).readS32()); };
    case 0x409E270:
      return (actor, _colliding, origin, extent) => {
        const bounds = actorBounds.get(actor.value);
        const root = actor.add(0x130).readPointer();
        for (let i = 0; i < 3; i++) {
          memory.set(origin.value + i * 4, bounds ? bounds.center[i] : root.add(0x1D0 + i * 4).readFloat());
          memory.set(extent.value + i * 4, bounds ? bounds.extent[i] : 30);
        }
      };
    case 0x27E1260: return () => climbableClass;
    case 0x27D7D10: return () => characterClass;
    case 0x27D2100: return () => animalClass;
    case 0x43E1420:
      return (component, origin, extent, radius) => {
        Memory.copy(origin, component.add(0x100), 12);
        Memory.copy(extent, component.add(0x10C), 12);
        radius.writeFloat(component.add(0x118).readFloat());
      };
    case 0x27EB690: return () => digSiteClass;
    case 0x283FBE0: return () => totemClass;
    case 0x27EADA0: return () => destructibleClass;
    case 0x433F490:
      return (_world, _class, array) => {
        actorScans++;
        const data = digSites.length ? Memory.alloc(digSites.length * 8) : ptr(0);
        digSites.forEach((actor, i) => data.add(i * 8).writePointer(actor));
        array.writePointer(data);
        array.add(8).writeS32(digSites.length);
        array.add(12).writeS32(digSites.length);
      };
    case 0x29D7620: return () => { nativeFrees++; };
    case 0x2CA9080: return (weak, object) => {
      weak.writePointer(object);
      weakSerials.set(weak.value, objectSerials.get(object.value) || 0);
    };
    case 0x2CA9210: return weak => {
      const object = weak.readPointer();
      return staleWeakObjects.has(object.value) || (weakSerials.has(weak.value) &&
        weakSerials.get(weak.value) !== (objectSerials.get(object.value) || 0)) ? ptr(0) : object;
    };
    case 0x26BBF00: return () => { groundProjects++; };
    case 0x26B8420: return () => mode === 'totem_no_mesh' ? ptr(0) : recipeMesh;
    case 0x427BF80: return () => recipeBody;
    case 0x41BB160:
      return box => {
        [-20, -20, 0, 20, 20, 200].forEach((v, i) => box.add(i * 4).writeFloat(v));
        box.add(24).writeU8(1);
        return box;
      };
    case 0x421B6D0: return component => component.equals(ground) ? surfaceType : 2;
    case 0x41ABAB0: return () => {};
    case 0x41C1380:
      return (_world, hit, start, end, channel, query) => {
        if (channel !== 2 || query.add(0x11).readU8() !== 1 || query.add(0x1E).readU8() !== 1) throw new Error('wrong collision query ABI');
        const terrainHeight = mode === 'totem_ground_mismatch' ? 1.5 : 0;
        const t = (terrainHeight - start.add(8).readFloat()) / (end.add(8).readFloat() - start.add(8).readFloat());
        if (!(t >= 0 && t <= 1)) return 0;
        hit.writeU8(mode === 'totem_penetrating' ? 3 : 1);
        for (let i = 0; i < 3; i++) hit.add(0x1C + i * 4).writeFloat(start.add(i * 4).readFloat() + t * (end.add(i * 4).readFloat() - start.add(i * 4).readFloat()));
        placementNormal.forEach((v, i) => hit.add(0x34 + i * 4).writeFloat(v));
        hit.add(0x74).writePointer(ground);
        return 1;
      };
    case 0x41C1A70:
      return (_world, _center, _quat, channel, shape) => {
        if (channel !== 2 || shape.readU32() !== 1 || shape.add(4).readFloat() !== 20 || shape.add(12).readFloat() !== 50) throw new Error('client bounds used or wrong box ABI');
        return Number(mode === 'totem_overlap');
      };
    case 0x27C5940: return () => seaLevel;
    case 0x4242250: return () => attachmentActor;
    case 0x4098470:
      return (_pawn, out) => { out.writeFloat(0); out.add(4).writeFloat(0); out.add(8).writeFloat(64); };
    case 0x2681420: return () => Number(mode !== 'totem_explorer');
    case 0x27CB540:
      return (state, type) => {
        recordedCheats++;
        if (mode === 'record_failure') throw new Error('record failed');
        hooks.get(moduleBase + 0x27CB540).onEnter.call({}, [state, type]);
      };
    default:
      throw new Error('unexpected native offset 0x' + offset.toString(16));
  }
};

if (mode === 'wrong_build') {
  let failed = false;
  try { eval(source); } catch(e) { failed = /版本不匹配/.test(e.message); }
  if (!failed || hooks.size || replacements.size) throw new Error('unsupported binary was hooked');
  process.exit(0);
}
eval(source);

const inventoryHook = hooks.get(moduleBase + 0x270BA70);
if (inventoryHook) throw new Error('removed item-addition detector is still attached');
for (const address of [0x271FE40, 0x27A5DC0, 0x2707210]) {
  if (hooks.has(moduleBase + address) || replacements.has(moduleBase + address)) throw new Error('removed combat detector is still attached');
}
const gameTickHook = hooks.get(moduleBase + 0x4336360);
if (!gameTickHook) throw new Error('missing AGameMode::Tick hook');

function addCoal(quantity, trusted, destination = inventory, itemClass = coalClass) {
  if (trusted) {
    files.set(trustedPath, JSON.stringify({
      grants: [{
        pawn: pawn.toString(),
        item_class: coalClass.toString(),
        expires_at: Date.now() + 5000,
        source: 'winning_card_reward'
      }]
    }));
  }
  const states = Memory.alloc(64);
  states.add(8).writeU32(quantity);
  const output = Memory.alloc(8);
  output.writeS32(quantity);
  const context = {};
  if (inventoryHook) inventoryHook.onEnter.call(context, [destination, itemClass, states, output, new Pointer(0), new Pointer(0),
    new Pointer(0), new Pointer(0), new Pointer(0), new Pointer(0), pawn]);
  if (inventoryHook) inventoryHook.onLeave.call(context, new Pointer(0));
}

if (mode === 'policy_direct' || mode === 'policy_log') {
  const type = input.cheatType;
  if (mode === 'policy_direct') {
    const label = Memory.alloc(16); writeFString(label, type);
    hooks.get(moduleBase + 0x27CB540).onEnter.call({}, [playerState, label]);
  } else files.set(nativeEventsPath, JSON.stringify({events:[{id:'policy',player_name:'测试用户',cheat_type:type}]}));
  if (messages.length || kickCalls.length || banRequests.length) throw new Error('policy event punished outside Tick');
  gameTickHook.onEnter.call({}, [gameMode]);
  const accepted = Number(input.accepted), directKick = Number(input.accepted && mode === 'policy_direct' && source.includes('var AutoKick = true;'));
  if (messages.length !== accepted || kickCalls.length !== directKick || banRequests.length !== directKick) {
    throw new Error('event policy mismatch: ' + JSON.stringify({type,messages,kickCalls,banRequests}));
  }
} else if (mode.startsWith('stack_transfer_')) {
  const chest = Memory.alloc(1024), rock = Memory.alloc(4096);
  pawn.add(0xF0).writeU8(3);
  inventory.add(0xD8).writePointer(pawn); chest.add(0xD8).writePointer(pawn);
  for (const manager of [inventory, chest]) {
    manager.add(0x138).writePointer(Memory.alloc(8));
    manager.add(0x140).writeS32(1); manager.add(0x240).writeS32(10);
  }
  rock.add(0xF0).writeU8(3); rock.add(0x10).writePointer(coalClass); rock.add(0x8B0).writeU8(30);
  inventory.add(0x138).readPointer().writePointer(rock);
  const transfer = replacements.get(moduleBase + 0x26891D0);
  if (mode === 'stack_transfer_roundtrip' || mode === 'stack_transfer_after') {
    for (let i = 0; i < 3; i++) {
      transfer(pawn, inventory, 0, chest, 0, 30, 1, 0);
      transfer(pawn, chest, 0, inventory, 0, 30, 1, 1);
    }
  } else if (mode === 'stack_transfer_burst') {
    for (let i = 0; i < 4; i++) transfer(pawn, inventory, 0, chest, 0, 5, 1, 0);
  } else transfer(pawn, inventory, 0, chest, 0, 30, 1, 0);
  gameTickHook.onEnter.call({}, [gameMode]);
  if (mode === 'stack_transfer_after') addCoal(30, false);
  fakeNow += 1100; gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length || kickCalls.length || banRequests.length) throw new Error('item additions or stack transfers triggered punishment');
} else if (mode.startsWith('ban_')) {
  const blacklistPath = '/srv/dh/gm_blacklist.json';
  const firstId = '76561198000000000_+_|0123456789abcdef0123456789abcdef';
  const blacklist = value => files.set(blacklistPath, JSON.stringify({version:1,entries:value}));
  if (['ban_existing','ban_steam','ban_eos','ban_same_name','ban_rejoin'].includes(mode)) {
    let expectedController = controller;
    const entry = mode === 'ban_steam' ? {steam_id:'76561198000000000'} :
      mode === 'ban_eos' ? {eos_id:'0123456789ABCDEF0123456789ABCDEF'} : {user_id:firstId};
    if (mode === 'ban_same_name') {
      const other = Memory.alloc(4096), otherController = Memory.alloc(4096), otherPawn = Memory.alloc(4096);
      otherController.add(0x250).writePointer(otherPawn); owningControllers.set(other.value, otherController);
      memory.set(playerArrayData.value+8, other.value); gameState.add(0x240).writeU32(2);
      setAccount(other, '76561198000000001'); entry.user_id = '76561198000000001';
      expectedController = otherController;
    }
    blacklist([entry]); gameTickHook.onEnter.call({}, [gameMode]);
    if (kickCalls.length !== 1 || kickCalls[0].controller !== expectedController.value || banRequests.length) {
      throw new Error('server blacklist did not use exact account or wrongly generated new ban');
    }
    fakeNow += 1100; gameTickHook.onEnter.call({}, [gameMode]);
    if (kickCalls.length !== 1) throw new Error('same connection repeatedly kicked');
    if (mode === 'ban_rejoin') {
      objectSerials.set(playerState.value,1); objectSerials.set(controller.value,1);
      fakeNow += 1100; gameTickHook.onEnter.call({}, [gameMode]);
      if (kickCalls.length !== 2) throw new Error('blacklisted reconnect accepted');
    }
  } else if (mode === 'ban_removed') {
    blacklist([{user_id:firstId}]); gameTickHook.onEnter.call({}, [gameMode]);
    if (kickCalls.length !== 1) throw new Error('initial blacklist not enforced');
    blacklist([]); objectSerials.set(playerState.value,1); objectSerials.set(controller.value,1);
    fakeNow += 1100; gameTickHook.onEnter.call({}, [gameMode]);
    if (kickCalls.length !== 1 || banRequests.length) throw new Error('removed account still banned');
  } else {
    if (mode === 'ban_no_id') playerState.add(0x258).writePointer(ptr(0));
    if (mode === 'ban_invalid') setAccount(playerState, '测试用户');
    const type=Memory.alloc(16); writeFString(type, 'Infinite Ammo');
    hooks.get(moduleBase+0x27CB540).onEnter.call({}, [playerState,type]);
    if (banRequests.length || kickCalls.length) throw new Error('blacklist written outside Tick');
    gameTickHook.onEnter.call({}, [gameMode]);
    const isV1 = !source.includes('var AutoKick = true;');
    const invalid = ['ban_no_id','ban_invalid','ban_non_executable','ban_send_failure'].includes(mode);
    if (kickCalls.length !== (isV1 ? 0 : 1) || banRequests.length !== (isV1 || invalid ? 0 : 1)) {
      throw new Error('ban eligibility or fallback kick incorrect');
    }
    if (banRequests.length && (banRequests[0].user_id !== firstId ||
        banRequests[0].reason !== '无限弹药' || banRequests[0].type !== 'anti_cheat_blacklist')) {
      throw new Error('ban identity or clean Chinese reason lost');
    }
  }
} else if (mode.startsWith('v2_') || mode === 'v1_monitor') {
  const native = hooks.get(moduleBase + 0x27CB540), type = Memory.alloc(16);
  writeFString(type, 'Infinite Ammo');
  let target = controller, targetState = playerState;
  if (mode === 'v2_same_name') {
    const other = Memory.alloc(4096), otherController = Memory.alloc(4096), otherPawn = Memory.alloc(4096), otherRole = Memory.alloc(128);
    memory.set(playerArrayData.value + 8, other.value);
    gameState.add(0x240).writeU32(2);
    other.add(0x588).writePointer(otherRole);
    writeFString(otherRole.add(0x48), 'Hunter');
    otherController.add(0x250).writePointer(otherPawn);
    owningControllers.set(other.value, otherController);
    target = otherController; targetState = other;
  }
  if (mode === 'v2_log_only') {
    files.set(nativeEventsPath, JSON.stringify({events:[{id:'old-log',player_name:'测试用户',
      cheat_type:'Infinite Ammo',detail:'未匹配服务端消耗弹药的发射'}]}));
  } else {
    for (let i = 0; i < (mode === 'v2_repeat' ? 10000 : 1); i++) native.onEnter.call({}, [targetState, type]);
    if (mode === 'v2_multi') {
      writeFString(type, 'Teleporting'); native.onEnter.call({}, [targetState, type]);
    }
  }
  if (messages.length || kickCalls.length) throw new Error('punishment happened before game-thread Tick');
  if (mode === 'v2_offline') gameState.add(0x240).writeU32(0);
  if (mode === 'v2_stale_state') staleWeakObjects.add(targetState.value);
  if (mode === 'v2_stale_controller') staleWeakObjects.add(target.value);
  if (mode === 'v2_reused_state') objectSerials.set(targetState.value, 1);
  if (mode === 'v2_reused_controller') objectSerials.set(target.value, 1);
  if (mode === 'v2_world_changed') {
    const nextWorld = Memory.alloc(4096);
    nextWorld.add(0x118).writePointer(gameMode);
    new Pointer(moduleBase + 0x5C9B6D0).writePointer(nextWorld);
  }
  if (mode === 'v2_session_retry') gameMode.add(0x278).writePointer(ptr(0));
  gameTickHook.onEnter.call({}, [gameMode]);
  const skipped = ['v2_offline','v2_stale_state','v2_stale_controller','v2_reused_state','v2_reused_controller','v2_world_changed'].includes(mode);
  const expected = skipped || ['v1_monitor','v2_log_only','v2_session_retry'].includes(mode) ? 0 : 1;
  if (kickCalls.length !== expected || messages.length !== (skipped ? 0 : mode === 'v2_same_name' ? 2 : 1)) throw new Error('incorrect kick/announcement count');
  if (expected && kickCalls[0].controller !== target.value) throw new Error('wrong same-name connection kicked');
  if (mode === 'v1_monitor' && messages[0].includes('踢出')) throw new Error('v1 displayed punishment');
  if (mode === 'v2_same_name' && !messages.every(value => value.includes('猎人'))) throw new Error('same-name role mistaken');
  if (['v2_repeat','v2_retry','v2_session_retry','v2_rejoin'].includes(mode)) {
    fakeNow += 1100;
    if (mode === 'v2_rejoin') {
      objectSerials.set(targetState.value, 1); objectSerials.set(target.value, 1);
    }
    gameMode.add(0x278).writePointer(gameSession);
    native.onEnter.call({}, [targetState, type]);
    gameTickHook.onEnter.call({}, [gameMode]);
    const expectedTotal = ['v2_retry','v2_rejoin'].includes(mode) ? 2 : 1;
    if (kickCalls.length !== expectedTotal) throw new Error('kick retried incorrectly or new connection was exempted');
    if (messages.length !== (mode === 'v2_rejoin' ? 2 : 1)) throw new Error('announcement cooldown lost or old session suppressed new connection');
  }
} else if (mode === 'trusted') {
  for (let i = 0; i < 4; i++) addCoal(3, true);
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length || kickCalls.length) throw new Error('trusted winning rewards triggered announcement/kick');
} else if (mode === 'normal') {
  for (let i = 0; i < 3; i++) addCoal(1, false);
  if (messages.length !== 0) throw new Error('ordinary pickup-sized additions triggered an anti-cheat broadcast');
} else if (mode === 'duplication' || mode === 'large_grant') {
  for (let i = 0; i < 4; i++) addCoal(mode === 'large_grant' ? 30 : 3, false);
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length || kickCalls.length || banRequests.length) throw new Error('removed quantity detector still punished');
} else if (mode === 'native_teleport') {
  files.set(nativeEventsPath, JSON.stringify({
    events: [{
      id: 'DreadHunger.log:1024:0',
      player_name: '测试用户',
      cheat_type: 'Teleporting',
      detail: 'with a multiplier of [319.835815]'
    }]
  }));
  gameTickHook.onEnter.call({}, [gameMode]);
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length !== 1) throw new Error('native anti-cheat event was not broadcast exactly once');
  const expected = '发现 测试用户 船长 作弊\n理由：传送/瞬移';
  if (messages[0] !== expected) throw new Error('unexpected native anti-cheat broadcast: ' + JSON.stringify(messages[0]));
} else if (mode === 'native_cross_map_repeat') {
  files.set(nativeEventsPath, JSON.stringify({
    events: [
      { id: 'DreadHunger.log:2048:0', player_name: '测试用户', cheat_type: 'Cross Map Interacts', detail: 'with a multiplier of [1.000000]' },
      { id: 'DreadHunger.log:2112:0', player_name: '测试用户', cheat_type: 'Cross Map Interacts', detail: 'with a multiplier of [1.000000]' }
    ]
  }));
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length !== 1) throw new Error('repeated cross-map interactions produced announcement spam');
  const expected = '发现 测试用户 船长 作弊\n理由：跨地图交互/远程摸尸';
  if (messages[0] !== expected) throw new Error('unexpected cross-map anti-cheat broadcast: ' + JSON.stringify(messages[0]));
} else if (mode === 'direct_events' || mode === 'offline_event' || mode === 'duplicate_name') {
  const native = hooks.get(moduleBase + 0x27CB540);
  const type = Memory.alloc(16);
  writeFString(type, 'Infinite Ammo');
  if (mode === 'duplicate_name') {
    const other = new Pointer(0x7B0000);
    const otherRole = new Pointer(0x7C0000);
    memory.set(playerArrayData.value + 8, other.value);
    memory.set(gameState.value + 0x240, 2);
    memory.set(other.value + 0x588, otherRole.value);
    writeFString(otherRole.add(0x48), 'Hunter');
    native.onEnter.call({}, [other, type]);
  } else {
    for (let i = 0; i < 10000; i++) native.onEnter.call({}, [playerState, type]);
  }
  if (messages.length) throw new Error('broadcast happened outside Tick');
  if (mode === 'offline_event') memory.set(gameState.value + 0x240, 0);
  gameTickHook.onEnter.call({}, [gameMode]);
  const expectedCount = mode === 'offline_event' ? 0 : (mode === 'duplicate_name' ? 2 : 1);
  if (messages.length !== expectedCount) throw new Error('native event aggregation/offline handling failed');
  if (mode === 'duplicate_name' && !messages.every(m => m.includes('猎人'))) throw new Error('same-name player misidentified');
  if (mode === 'direct_events') {
    files.set(nativeEventsPath, JSON.stringify({events: [{id:'fallback',player_name:'测试用户',cheat_type:'Infinite Ammo'}]}));
    fakeNow += 1100;
    gameTickHook.onEnter.call({}, [gameMode]);
    if (messages.length !== 1) throw new Error('direct and log relay announced twice');
  }
} else if (mode.startsWith('snow_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), target = Memory.alloc(1024);
  const site = Memory.alloc(1024), item = Memory.alloc(4096), itemRoot = Memory.alloc(1024), manager = Memory.alloc(1024);
  pawn.add(0xF0).writeU8(3);
  pawn.add(0x130).writePointer(root);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  target.add(0xA0).writePointer(item);
  target.add(0x1D0).writeFloat(120);
  item.add(0xF0).writeU8(3);
  item.add(0x130).writePointer(itemRoot);
  itemRoot.add(0x1D0).writeFloat(150);
  site.add(0xF0).writeU8(3);
  site.add(0x298).writePointer(item);
  site.add(0x224).writeFloat(mode === 'snow_partial' ? 0 : 50);
  site.add(0x2A0).writeU8(['snow_dug', 'snow_reburied'].includes(mode) ? 1 : 0);
  manager.add(0xA0).writePointer(item);
  digSites = [site];
  const transfer = replacements.get(moduleBase + 0x26891D0), pickup = replacements.get(moduleBase + 0x2712200);
  const interact = replacements.get(moduleBase + 0x27647E0);
  const track = () => {
    const hook = hooks.get(moduleBase + 0x26F5140), context = {};
    if (!hook) throw new Error('missing streamed digsite tracking');
    hook.onEnter.call(context, [site]);
    hook.onLeave.call(context, ptr(0));
  };
  if (mode === 'snow_stale') staleWeakObjects.add(site.value);
  if (mode === 'snow_unrelated') site.add(0x298).writePointer(Memory.alloc(4096));
  if (mode === 'snow_streamed') {
    digSites = [];
    pickup(item, controller, 0);
    track();
  }
  if (['snow_transition', 'snow_reassigned', 'snow_world_change'].includes(mode)) {
    pickup(item, controller, 0); // 热加载时已存在的埋藏物，必须被首次枚举发现。
    if (mode === 'snow_transition') site.add(0x2A0).writeU8(1);
    if (mode === 'snow_reassigned') { site.add(0x298).writePointer(Memory.alloc(4096)); track(); }
    if (mode === 'snow_world_change') {
      const nextWorld = Memory.alloc(4096);
      nextWorld.add(0x118).writePointer(gameMode);
      memory.set(moduleBase + 0x5C9B6D0, nextWorld.value);
      digSites = [];
    }
  }
  const before = [originalTransfers, originalPickups, originalInteractions];
  const legal = ['snow_dug', 'snow_unrelated', 'snow_transition', 'snow_stale', 'snow_reassigned', 'snow_world_change'].includes(mode);
  if (mode === 'snow_reburied') {
    interact(component, target, 0);
    site.add(0x2A0).writeU8(0);
    completePickup(component, target, 0); // 已授权的近距离 E 也不能绕过再次埋藏状态。
    if (originalPickups !== before[1]) throw new Error('native completion bypassed buried state');
  } else {
    transfer(pawn, manager, 0, inventory, 0, 1, 1, 1);
    pickup(item, controller, 0);
    interact(component, target, 0);
    if ([originalTransfers, originalPickups, originalInteractions].some((v, i) => v - before[i] !== Number(legal))) {
      throw new Error('buried loot escaped or dug/unrelated loot was blocked');
    }
  }
  if (actorScans !== (mode === 'snow_world_change' ? 2 : 1)) throw new Error('digsite index rescanned per request or failed to refresh');
  if (nativeFrees !== (mode === 'snow_streamed' ? 0 : 1)) throw new Error('engine actor array was not freed');
  gameTickHook.onEnter.call({}, [gameMode]);
  const expectedAlert = !legal || ['snow_transition', 'snow_reassigned', 'snow_world_change'].includes(mode);
  if (messages.length !== Number(expectedAlert) || (expectedAlert && !messages[0].includes('未挖掘'))) throw new Error('wrong buried loot announcement');
} else if (mode.startsWith('totem_events_')) {
  const record = new NativeFunction(ptr(moduleBase + 0x27CB540)), type = Memory.alloc(16);
  if (mode !== 'totem_events_log') {
    for (const label of ['Invalid Totem Placement', '  Invalid Totem Placement  ']) {
      writeFString(type, label); record(playerState, type);
    }
    if (recordedCheats !== 2) throw new Error('original game event recording changed');
  }
  if (mode !== 'totem_events_direct') {
    files.set(nativeEventsPath, JSON.stringify({events: [
      {id: 'removed-totem', player_name: '测试用户', cheat_type: 'Invalid Totem Placement'},
      {id: 'removed-totem-trimmed', player_name: '测试用户', cheat_type: '  Invalid Totem Placement  '}
    ]}));
  }
  const mixed = mode === 'totem_events_mixed';
  if (mixed) { writeFString(type, 'Infinite Ammo'); record(playerState, type); }
  gameTickHook.onEnter.call({}, [gameMode]);
  const punish = mixed && source.includes('var AutoKick = true;');
  if (messages.length !== Number(mixed) || kickCalls.length !== Number(punish) || banRequests.length !== Number(punish)) {
    throw new Error('removed totem event caused punishment or suppressed other detection');
  }
  if (mixed && !messages[0].includes('无限弹药')) throw new Error('wrong surviving detection reason');
} else if (mode.startsWith('totem_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), project = Memory.alloc(96), recipe = Memory.alloc(512);
  pawn.add(0xF0).writeU8(3);
  pawn.add(0x130).writePointer(root);
  controller.add(0xF0).writeU8(3);
  component.add(0xA0).writePointer(controller);
  component.add(0xB0).writeFloat(500);
  recipe.add(0x1F8).writePointer(mode === 'totem_other_recipe' ? coalClass : totemBlueprintClass);
  recipe.add(0x31).writeU8(1);
  recipe.add(0x118).writeFloat(0.5);
  project.writePointer(recipe);
  project.add(0x54).writeU8(mode === 'totem_client_invalid' ? 0 : 1);
  project.add(0x1C).writeFloat(1);
  [1, 1, 1].forEach((v, i) => project.add(0x30 + i * 4).writeFloat(v));
  [99999, 99999, 99999].forEach((v, i) => project.add(0x48 + i * 4).writeFloat(v)); // 客户端碰撞尺寸不可采信。
  if (mode === 'totem_slope') {
    placementNormal = [0, 0.6, 0.8];
    project.add(0x10).writeFloat(-Math.sqrt(0.1));
    project.add(0x1C).writeFloat(Math.sqrt(0.9));
  }
  if (mode === 'totem_wall') placementNormal = [1, 0, 0];
  if (mode === 'totem_near_flat') placementNormal = [Math.sqrt(1 - 0.995 * 0.995), 0, 0.995]; // 原版 FindSlopeRotation 吸附成水平姿态。
  if (mode === 'totem_max_slope') placementNormal = [0, Math.sqrt(1 - 0.75 * 0.75), 0.75];
  if (mode === 'totem_air') placementPosition[2] = 50;
  if (mode === 'totem_underground') placementPosition[2] = -50;
  if (mode === 'totem_shallow_underground') placementPosition[2] = -1.5;
  if (mode === 'totem_quantized') placementPosition[2] = 0.5;
  if (mode === 'totem_wrong_alignment') {
    project.add(0x10).writeFloat(-Math.sqrt(0.1));
    project.add(0x1C).writeFloat(Math.sqrt(0.9));
  }
  if (mode === 'totem_yaw') { project.add(0x18).writeFloat(1); project.add(0x1C).writeFloat(0); }
  if (mode === 'totem_surface_type') surfaceType = 2;
  if (mode === 'totem_far') placementPosition = [1200, 0, 0];
  if (mode === 'totem_water') seaLevel = 10;
  if (mode === 'totem_destructible') groundActor.add(0x10).writePointer(destructibleClass);
  if (mode === 'totem_disallowed' || mode === 'totem_attachment') {
    const disallowed = Memory.alloc(64), classes = Memory.alloc(8);
    classes.writePointer(disallowed);
    recipe.add(0x38).writePointer(classes);
    recipe.add(0x40).writeS32(1);
    (mode === 'totem_disallowed' ? groundActor : attachmentActor).add(0x10).writePointer(disallowed);
  }
  placementPosition.forEach((v, i) => project.add(0x20 + i * 4).writeFloat(v));
  if (mode === 'totem_nan') project.add(0x20).writeFloat(NaN);
  if (mode === 'totem_bad_rotation') project.add(0x1C).writeFloat(0);
  if (mode === 'totem_bad_scale') project.add(0x30).writeFloat(0);
  const spawn = replacements.get(moduleBase + 0x26BBF00) || new NativeFunction(ptr(moduleBase + 0x26BBF00));
  spawn(component, project);
  if (groundProjects !== 1) throw new Error('totem placement no longer follows the original game');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length || kickCalls.length || banRequests.length) throw new Error('removed totem detection still punishes players');
} else if (mode.startsWith('pickup_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), target = Memory.alloc(1024);
  const item = Memory.alloc(4096), itemRoot = Memory.alloc(1024);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  target.add(0xA0).writePointer(item);
  target.add(0x1D0).writeU32(1000);
  item.add(0xF0).writeU8(3);
  item.add(0x130).writePointer(itemRoot);
  itemRoot.add(0x1D0).writeU32(1039); // Actor 包围盒最近点 10.09 米，E 起始碰撞点 10.00 米。
  if (mode === 'pickup_ship_retake') {
    root.add(0x1D0).writeU32(100000);
    target.add(0x1D0).writeU32(101000);
    itemRoot.add(0x1D0).writeU32(101039);
  }
  if (mode === 'pickup_outside_start') target.add(0x1D0).writeU32(1001);
  if (mode === 'pickup_malformed_start') memory.set(target.value + 0x1D0, NaN);
  const interact = replacements.get(moduleBase + 0x27647E0);
  const pickup = replacements.get(moduleBase + 0x2712200);
  if (mode !== 'pickup_no_start') interact(component, target, 7);
  if (mode === 'pickup_no_start' || mode === 'pickup_rejected_interact') component.add(0x198).writePointer(pawn);
  if (mode === 'pickup_cancelled') component.add(0x198).writePointer(ptr(0));
  if (mode === 'pickup_changed_controller') component.add(0xA0).writePointer(ptr(0x123000));
  if (mode === 'pickup_changed_item') {
    const otherItem = Memory.alloc(4096);
    otherItem.add(0xF0).writeU8(3);
    otherItem.add(0x130).writePointer(itemRoot);
    target.add(0xA0).writePointer(otherItem);
  }
  if (mode === 'pickup_direct_during_wait') pickup(item, controller, 7);
  if (mode === 'pickup_followup_far') {
    const farTarget = Memory.alloc(1024);
    farTarget.add(0x1D0).writeU32(1001);
    interact(component, farTarget, 7);
  }
  let completionTarget = target;
  if (mode === 'pickup_changed_target') {
    completionTarget = Memory.alloc(1024);
    completionTarget.add(0xA0).writePointer(item);
  }
  if (mode !== 'pickup_immediate') completePickup(component, completionTarget, mode === 'pickup_wrong_slot' ? 6 : 7);
  if (mode === 'pickup_replay') {
    component.add(0x198).writePointer(pawn);
    completePickup(component, target, 7);
  }
  const legal = ['pickup_drop_retake', 'pickup_ship_retake', 'pickup_immediate'].includes(mode);
  const allowed = legal || ['pickup_replay', 'pickup_repeat_completion', 'pickup_direct_during_wait'].includes(mode);
  if (originalPickups !== Number(allowed)) throw new Error('normal F/E completion blocked or unrelated/repeated pickup authorized');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (legal && messages.length) throw new Error('normal F/E pickup was announced as cheating');
  if (!legal && !messages.some(m => m.includes('远程摸物资'))) throw new Error('remote pickup guard was bypassed');
} else if (mode.startsWith('remote_')) {
  const root = Memory.alloc(1024), corpse = Memory.alloc(4096), corpseRoot = Memory.alloc(1024);
  const sourceManager = Memory.alloc(1024), interact = Memory.alloc(512);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  corpse.add(0x130).writePointer(corpseRoot);
  corpse.add(0xF0).writeU8(3);
  sourceManager.add(0xA0).writePointer(corpse);
  controller.add(0x680).writePointer(interact);
  memory.set(interact.value + 0xB0, 160);
  memory.set(corpseRoot.value + 0x1D0, mode === 'remote_near' ? 120 : 5000);
  if (mode === 'remote_fixed_edge' || mode === 'remote_pickup_edge') memory.set(corpseRoot.value + 0x1D0, 1030); // 包围盒最近点 1000 cm。
  if (mode === 'remote_old_tolerance') memory.set(corpseRoot.value + 0x1D0, 700); // 旧阈值会误报，新阈值允许 6.7 米。
  if (mode === 'remote_outside_limit' || mode === 'remote_pickup_outside') memory.set(corpseRoot.value + 0x1D0, 1031);
  if (mode === 'remote_custom_server') {
    memory.set(interact.value + 0xB0, 120);
    memory.set(corpseRoot.value + 0x1D0, 1030);
  }
  if (mode === 'remote_custom_over_limit') {
    memory.set(interact.value + 0xB0, 500);
    memory.set(corpseRoot.value + 0x1D0, 1031);
  }
  if (mode === 'remote_ship') {
    memory.set(root.value + 0x1D0, 100000);
    memory.set(corpseRoot.value + 0x1D0, 100120);
  }
  const transfer = replacements.get(moduleBase + 0x26891D0);
  const pickup = replacements.get(moduleBase + 0x2712200);
  if (!transfer || !pickup) throw new Error('missing corpse loot guards');
  if (mode === 'remote_owned') sourceManager.add(0xD8).writePointer(pawn);
  if (mode === 'remote_backpack') {
    const chain = Memory.alloc(8);
    inventoryBaseClass.add(0x38).writeS32(0);
    inventoryBaseClass.add(0x30).writePointer(chain);
    chain.writePointer(inventoryBaseClass.add(0x30));
    corpse.add(0x10).writePointer(inventoryBaseClass);
    corpse.add(0x268).writePointer(pawn); // 隐藏的背包 Actor 在远处，持有者在当前角色。
  }
  transfer(pawn, sourceManager, 0, inventory, 0, 1, 1, 1);
  transfer(pawn, inventory, 0, sourceManager, 0, 1, 1, 0); // 丢入远处容器同样检查。
  if (mode === 'remote_near') pickup(corpse, controller, 0);
  else if (mode.startsWith('remote_pickup')) pickup(corpse, controller, 0);
  const legal = ['remote_near', 'remote_owned', 'remote_backpack', 'remote_ship', 'remote_fixed_edge', 'remote_pickup_edge', 'remote_custom_server', 'remote_old_tolerance'].includes(mode);
  if (originalTransfers !== (legal ? 2 : 0)) throw new Error('remote transfer escaped or normal loot was blocked');
  if (originalPickups !== (['remote_near', 'remote_pickup_edge'].includes(mode) ? 1 : 0)) throw new Error('remote pickup escaped or normal pickup was blocked');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length !== (legal ? 0 : 1)) throw new Error('remote loot announcement missing/duplicated');
  if (!legal && !messages[0].includes('远程摸物资')) throw new Error('wrong remote loot reason');
  if (!legal && !logMessages.some(value => value.includes('允许 10.00 米'))) throw new Error('missing remote loot limit in diagnostic log');
} else if (mode.startsWith('melee_event_')) {
  const labels = ['Chainsaw Melee', ' Long Range Melee ', 'Cross Map Melee'];
  if (mode === 'melee_event_fast') labels.push('Fast Swings');
  if (mode === 'melee_event_log') {
    files.set('/srv/dh/.gm_runtime/anti_cheat_events.json', JSON.stringify({events: labels.map((label, i) =>
      ({id: 'removed-melee-' + i, player_name: '测试用户', cheat_type: label}))}));
  } else {
    for (const label of labels) {
      const type = Memory.alloc(16);
      writeFString(type, label);
      hooks.get(moduleBase + 0x27CB540).onEnter.call({}, [playerState, type]);
    }
  }
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length || kickCalls.length || banRequests.length) throw new Error('removed melee events still punished');
} else if (mode.startsWith('trap_corpse_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), target = Memory.alloc(1024);
  const corpse = Memory.alloc(4096), mesh = Memory.alloc(1024), manager = Memory.alloc(1024), trap = Memory.alloc(1024);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  root.add(0x1D0).writeFloat(1680); // 客户端尸体在玩家旁边；专服边界仍在夹子处，旧检测误报 16.50 米。
  corpse.add(0x10).writePointer(mode === 'trap_corpse_human' ? characterBlueprintClass :
    mode === 'trap_corpse_native_animal' ? animalClass : animalBlueprintClass);
  corpse.add(0xF0).writeU8(3);
  corpse.add(0x280).writePointer(mesh);
  mesh.add(0xA0).writePointer(corpse);
  for (let i = 0; i < 3; i++) mesh.add(0x10C + i * 4).writeFloat(30);
  actorBounds.set(corpse.value, {center: [0, 0, 0], extent: [30, 30, 30]});
  manager.add(0xA0).writePointer(corpse);
  target.add(0xA0).writePointer(corpse);
  trap.add(0xF0).writeU8(mode === 'trap_corpse_non_authority' ? 2 : 3);
  corpse.add(0x818).writeU8(mode === 'trap_corpse_already_dead' ? 1 : 0);
  const trapHook = hooks.get(moduleBase + 0x2703DB0);
  if (!trapHook) throw new Error('missing native trap death observer');
  function changeWorld() {
    const nextWorld = Memory.alloc(4096);
    nextWorld.add(0x118).writePointer(gameMode);
    memory.set(moduleBase + 0x5C9B6D0, nextWorld.value);
  }
  if (mode !== 'trap_corpse_no_hook') {
    const context = {};
    trapHook.onEnter.call(context, [trap, corpse]);
    if (mode === 'trap_corpse_world_during_trap') changeWorld();
    if (!['trap_corpse_survived', 'trap_corpse_live'].includes(mode)) corpse.add(0x818).writeU8(1);
    trapHook.onLeave.call(context, ptr(0)); // 原版捕兽夹致死路径返回 false，不能用返回值判断是否击杀。
  }
  if (mode === 'trap_corpse_no_hook' || mode === 'trap_corpse_survived') corpse.add(0x818).writeU8(1);
  if (mode === 'trap_corpse_carcass') corpse.add(0x818).writeU8(2); // 专服不创建 CarcassMesh。
  if (mode === 'trap_corpse_obliterated') corpse.add(0x818).writeU8(3);
  if (mode === 'trap_corpse_revived') corpse.add(0x818).writeU8(0);
  if (mode === 'trap_corpse_no_mesh') corpse.add(0x280).writePointer(ptr(0));
  if (mode === 'trap_corpse_stale') staleWeakObjects.add(corpse.value);
  if (mode === 'trap_corpse_world_change') changeWorld();
  const legal = ['trap_corpse_wolf', 'trap_corpse_bear', 'trap_corpse_native_animal',
    'trap_corpse_carcass', 'trap_corpse_no_mesh', 'trap_corpse_other_container'].includes(mode);
  replacements.get(moduleBase + 0x27647E0)(component, target, 7);
  replacements.get(moduleBase + 0x26891D0)(pawn, manager, 0, inventory, 0, 1, 1, 1);
  replacements.get(moduleBase + 0x26891D0)(pawn, inventory, 0, manager, 0, 1, 1, 1);
  replacements.get(moduleBase + 0x2712200)(corpse, controller, 0);
  if (originalInteractions !== Number(legal) || originalTransfers !== (legal ? 2 : 0) || originalPickups !== Number(legal))
    throw new Error('trap death exception missing or applied to unrelated targets');
  if (legal && (Object.keys(PendingNativeEvents).length || messages.length || kickCalls.length || banRequests.length))
    throw new Error('legitimate client-only corpse movement queued punishment');
  if (!legal && !logMessages.some(value => value.includes('Remote Interaction')))
    throw new Error('unrelated remote interaction no longer guarded');
  if (mode === 'trap_corpse_other_container') {
    const otherManager = Memory.alloc(1024), container = Memory.alloc(4096);
    otherManager.add(0xA0).writePointer(container);
    actorBounds.set(container.value, {center: [100000, 0, 0], extent: [30, 30, 30]});
    replacements.get(moduleBase + 0x26891D0)(pawn, manager, 0, otherManager, 0, 1, 1, 1);
    replacements.get(moduleBase + 0x26891D0)(pawn, otherManager, 0, manager, 0, 1, 1, 1);
    if (originalTransfers !== 2 || !logMessages.some(value => value.includes('Remote Loot')))
      throw new Error('trap corpse authorized transfer with unrelated remote container');
  }
} else if (mode.startsWith('corpse_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), target = Memory.alloc(1024);
  const corpse = Memory.alloc(4096), capsule = Memory.alloc(1024), mesh = Memory.alloc(1024);
  const carcass = Memory.alloc(1024), sourceManager = Memory.alloc(1024);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  corpse.add(0x10).writePointer(mode === 'corpse_native_class' ? characterClass : characterBlueprintClass);
  corpse.add(0xF0).writeU8(3);
  corpse.add(0x130).writePointer(capsule);
  corpse.add(0x280).writePointer(mesh);
  corpse.add(0x5A8).writePointer(carcass);
  corpse.add(0x818).writeU8(mode === 'corpse_carcass' ? 2 : 1);
  sourceManager.add(0xA0).writePointer(corpse);
  target.add(0xA0).writePointer(corpse);
  mesh.add(0xA0).writePointer(corpse);
  carcass.add(0xA0).writePointer(corpse);
  function bodyBounds(body, x) {
    body.add(0x100).writeFloat(x);
    for (let i = 0; i < 3; i++) body.add(0x10C + i * 4).writeFloat(30);
    body.add(0x118).writeFloat(52);
  }
  bodyBounds(mesh, 1000);
  bodyBounds(carcass, mode === 'corpse_carcass' ? 1000 : 100000);
  if (mode === 'corpse_carcass') bodyBounds(mesh, 100000); // 已隐藏的旧骨骼不能参与测距。
  root.add(0x1D0).writeFloat(1000);
  // Actor 整体包围盒包含停在夹子处的胶囊，不能作为尸体当前位置。
  actorBounds.set(corpse.value, {center: [500, 0, 0], extent: [530, 30, 30]});
  if (mode === 'corpse_edge' || mode === 'corpse_far') root.add(0x1D0).writeFloat(mode === 'corpse_edge' ? 2030 : 2031);
  if (mode === 'corpse_far') target.add(0x1D0).writeFloat(2031); // 陈旧组件刚好在玩家旁边也不能授权远处尸体。
  if (mode === 'corpse_old_position') root.add(0x1D0).writeFloat(-100);
  const guarded = ['corpse_alive', 'corpse_obliterated', 'corpse_fake_class', 'corpse_foreign_mesh', 'corpse_no_mesh'];
  if (guarded.includes(mode)) root.add(0x1D0).writeFloat(1100);
  if (guarded.includes(mode)) actorBounds.set(corpse.value, {center: [0, 0, 0], extent: [30, 30, 30]});
  if (mode === 'corpse_alive') corpse.add(0x818).writeU8(0);
  if (mode === 'corpse_obliterated') corpse.add(0x818).writeU8(3);
  if (mode === 'corpse_fake_class') corpse.add(0x10).writePointer(totemBlueprintClass);
  if (mode === 'corpse_foreign_mesh') mesh.add(0xA0).writePointer(pawn);
  if (mode === 'corpse_no_mesh') corpse.add(0x280).writePointer(ptr(0));
  const interact = replacements.get(moduleBase + 0x27647E0), transfer = replacements.get(moduleBase + 0x26891D0);
  const legal = !guarded.includes(mode) && !['corpse_far', 'corpse_old_position'].includes(mode);
  function loot() {
    interact(component, target, 7);
    transfer(pawn, sourceManager, 0, inventory, 0, 1, 1, 1);
    transfer(pawn, inventory, 0, sourceManager, 0, 1, 1, 1);
  }
  loot();
  if (mode === 'corpse_moving') {
    bodyBounds(mesh, 1400);
    root.add(0x1D0).writeFloat(1400);
    loot();
  }
  const passes = legal ? (mode === 'corpse_moving' ? 2 : 1) : 0;
  if (originalInteractions !== passes || originalTransfers !== passes * 2) throw new Error('corpse movement measured from stale component/capsule or remote corpse allowed');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (legal && (messages.length || kickCalls.length || banRequests.length)) throw new Error('legitimate corpse looting punished');
  if (!legal && (messages.length !== (source.includes('var AutoKick = true;') ? 1 : 2) ||
      !messages.some(value => value.includes('远程交互')))) throw new Error('remote corpse evidence missing');
  if (!legal && source.includes('var AutoKick = true;') && (kickCalls.length !== 1 || banRequests.length !== 1)) throw new Error('remote corpse not punished');
} else if (mode.startsWith('climb_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), mesh = Memory.alloc(1024), wall = Memory.alloc(4096);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  wall.add(0x10).writePointer(mode === 'climb_native_class' ? climbableClass : climbableBlueprintClass);
  wall.add(0xF0).writeU8(3);
  wall.add(0x278).writeU8(mode === 'climb_ladder' ? 1 : 2);
  mesh.add(0xA0).writePointer(wall);
  actorBounds.set(wall.value, {center: [100000, 0, 1000], extent: [30, 500, 1000]});
  root.add(0x1D0).writeFloat(100130);
  root.add(0x1D8).writeFloat(mode === 'climb_exit' ? 1800 : 1000);
  mesh.add(0x1D0).writeFloat(800000); // 大型攀爬组件的原点远离玩家，不代表交互点。
  if (mode === 'climb_exit') pawn.add(0x640).writePointer(wall);
  if (mode === 'climb_edge') root.add(0x1D0).writeFloat(101030);
  if (mode === 'climb_far') root.add(0x1D0).writeFloat(101031);
  const legal = !['climb_far', 'climb_fake_type', 'climb_remote_item'].includes(mode);
  if (mode === 'climb_fake_type') wall.add(0x10).writePointer(totemBlueprintClass);
  if (mode === 'climb_remote_item') {
    pawn.add(0x640).writePointer(wall);
    const item = Memory.alloc(4096);
    mesh.add(0xA0).writePointer(item);
    mesh.add(0x1D0).writeFloat(101131);
    mesh.add(0x1D8).writeFloat(1000);
  }
  replacements.get(moduleBase + 0x27647E0)(component, mesh, 7);
  if (originalInteractions !== Number(legal)) throw new Error('climb bounds or ordinary interaction guard wrong');
  if (mode === 'climb_complete_pickup') {
    actorBounds.set(wall.value, {center: [900000, 0, 1000], extent: [30, 500, 1000]});
    completePickup(component, mesh, 7);
    if (originalPickups) throw new Error('climbing granted inventory pickup permission');
  }
  gameTickHook.onEnter.call({}, [gameMode]);
  const alert = !legal || mode === 'climb_complete_pickup';
  if (messages.length !== Number(alert) || (alert && !messages[0].includes(mode === 'climb_complete_pickup' ? '远程摸物资' : '远程交互'))) throw new Error('climb evidence wrong');
  if (!alert && (kickCalls.length || banRequests.length)) throw new Error('legitimate climbing punished');
  if (alert && source.includes('var AutoKick = true;') && (kickCalls.length !== 1 || banRequests.length !== 1)) {
    throw new Error('real remote interaction was not punished');
  }
} else if (mode.startsWith('interact_')) {
  const root = Memory.alloc(1024), component = Memory.alloc(512), target = Memory.alloc(1024);
  pawn.add(0x130).writePointer(root);
  pawn.add(0xF0).writeU8(3);
  controller.add(0x680).writePointer(component);
  component.add(0xA0).writePointer(controller);
  memory.set(component.value + 0xB0, 160);
  memory.set(target.value + 0x1D0, ['interact_edge', 'interact_custom'].includes(mode) ? 1000 : 1001);
  if (mode === 'interact_custom') memory.set(component.value + 0xB0, 120);
  if (mode === 'interact_custom_over_limit') memory.set(component.value + 0xB0, 500);
  if (mode === 'interact_ship') {
    memory.set(root.value + 0x1D0, 100000);
    memory.set(target.value + 0x1D0, 100120);
  }
  if (mode === 'interact_legacy_range') {
    target.add(0x1D0).writeFloat(800);
    files.set(nativeEventsPath, JSON.stringify({events: [{player_name: '测试用户', cheat_type: 'Long Range Interacts'}]}));
  }
  const legal = ['interact_edge', 'interact_custom', 'interact_ship', 'interact_inside_collision', 'interact_legacy_range'].includes(mode);
  replacements.get(moduleBase + 0x27647E0)(component, target, 7);
  if (originalInteractions !== Number(legal)) throw new Error('interaction fixed range/collision/world position wrong');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length !== Number(!legal) || (!legal && !messages[0].includes('远程交互'))) throw new Error('interaction evidence wrong');
  if (!legal && !logMessages.some(value => value.includes('允许 10.00 米'))) throw new Error('missing interaction limit in diagnostic log');
} else if (mode.startsWith('reload_')) {
  const weapon = Memory.alloc(4096), timer = Memory.alloc(32), ammo = Memory.alloc(4096);
  weapon.add(0xF0).writeU8(3);
  weapon.add(0x268).writePointer(pawn);
  weapon.add(0x290).writeU8(26);
  weapon.add(0x51C).writeS32(1);
  weapon.add(0x898).writePointer(timer);
  ammo.add(0x8B0).writeU8(mode === 'reload_last_ammo' ? 1 : 3);
  ammoForReload = mode === 'reload_no_ammo' ? ptr(0) : ammo;
  if (mode === 'reload_no_consumption_server') reloadConsumes = false;
  if (mode === 'reload_infinite_server') inventory.add(0x200).writeU8(1);
  if (mode !== 'reload_warmup') fakeNow += 31000;
  memory.set(timer.value, mode === 'reload_early' ? 0.1 : 0);
  if (mode === 'reload_pause') { memory.set(timer.value, 2); fakeNow += 100000; }
  const finish = replacements.get(moduleBase + 0x2721600);
  if (mode === 'reload_direct' || mode === 'reload_infinite_server') replacements.get(moduleBase + 0x27073C0)(weapon);
  else finish(weapon);
  if (mode === 'reload_repeat') finish(weapon);
  const legal = ['reload_normal', 'reload_last_ammo', 'reload_early', 'reload_pause', 'reload_no_start', 'reload_no_consumption_server', 'reload_warmup', 'reload_infinite_server', 'reload_repeat'].includes(mode);
  if (originalReloadCompletions !== (mode === 'reload_repeat' ? 2 : Number(legal)) || weapon.add(0x8CC).readU8() !== Number(legal)) throw new Error('reload filled ammo incorrectly');
  if (mode === 'reload_normal' && ammo.add(0x8B0).readU8() !== 2) throw new Error('normal reload did not spend ammo');
  if (mode === 'reload_last_ammo' && ammo.add(0x8B0).readU8() !== 0) throw new Error('last spare bullet was not consumed');
  if (mode === 'reload_direct' && originalRangedReloads) throw new Error('direct completion reached reload side effects');
  gameTickHook.onEnter.call({}, [gameMode]);
  const alert = ['reload_free_ammo', 'reload_direct'].includes(mode);
  if (messages.length !== Number(alert)) throw new Error('reload evidence missing/false positive');
  if (mode === 'reload_free_ammo' && !messages[0].includes('无限弹药')) throw new Error('wrong ammo conservation reason');
} else if (mode.startsWith('arrow_') || mode.startsWith('gun_')) {
  const weapon = Memory.alloc(4096), state = Memory.alloc(1), hit = Memory.alloc(144);
  weapon.add(0xF0).writeU8(3);
  weapon.add(0x268).writePointer(pawn);
  pawn.add(0xC30).writePointer(playerState);
  weapon.add(0x290).writeU8(36);
  if (mode.startsWith('gun_')) weapon.add(0x290).writeU8(mode === 'gun_musket' ? 27 : 26);
  weapon.add(0x51C).writeS32(1);
  weapon.add(0x8CC).writeU8(1);
  if (mode === 'arrow_infinite_weapon') weapon.add(0x51C).writeS32(0);
  if (mode === 'arrow_nonbow') weapon.add(0x290).writeU8(26);
  const use = replacements.get(moduleBase + 0x2721780), hitActor = replacements.get(moduleBase + 0x2721A70);
  if (!hitActor) throw new Error('missing bow hit guard');
  if (mode !== 'arrow_inflight') fakeNow += 31000; // 热加载时容许已在飞行的箭。
  if (mode === 'arrow_infinite_server') inventory.add(0x200).writeU8(1);
  if (!['arrow_forged', 'arrow_inflight', 'arrow_infinite_server', 'gun_forged'].includes(mode)) {
    use(weapon, Memory.alloc(48), state);
    if (mode === 'arrow_expired') fakeNow += 31000;
  }
  hitActor(weapon, hit); // 不提供活体，验证尸体也必须检查。
  if (mode === 'arrow_repeat' || mode === 'gun_repeat') hitActor(weapon, hit);
  const legal = ['arrow_normal', 'arrow_inflight', 'arrow_infinite_server', 'arrow_infinite_weapon', 'arrow_nonbow', 'gun_normal', 'gun_musket'].includes(mode);
  const expectedHits = legal || mode === 'arrow_repeat' || mode === 'gun_repeat' ? 1 : 0;
  if (originalHits !== expectedHits) throw new Error('forged corpse hit escaped or last legal arrow was rejected');
  gameTickHook.onEnter.call({}, [gameMode]);
  if (messages.length !== (legal ? 0 : 1)) throw new Error('arrow announcement missing/unexpected');
  if (!legal && !messages[0].includes(mode.startsWith('gun_') ? '无限弹药' : '刷箭')) throw new Error('wrong projectile reason');
} else {
  throw new Error('unknown mode');
}
if (input.assertNoKick) {
  fakeNow += 1100;
  gameTickHook.onEnter.call({}, [gameMode]);
  if (kickCalls.length || messages.length || banRequests.length) throw new Error('normal gameplay queued v2 punishment');
}
if (messages.some(value => value.includes('（'))) throw new Error('technical parentheses remain in announcement');
if (!source.includes('var AutoKick = true;') && (kickCalls.length || banRequests.length)) throw new Error('v1 punished a player');
"""


class InventoryDuplicationAntiCheatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Windows 的命令行上限不足以容纳增长后的 fixture。
        directory = tempfile.TemporaryDirectory(prefix="dh-anticheat-")
        cls.addClassCleanup(directory.cleanup)
        cls.harness_path = Path(directory.name) / "fixture.cjs"
        cls.harness_path.write_text(NODE_HARNESS, encoding="utf-8")

    def test_only_five_categories_pass_native_and_log_event_policy(self):
        retained = ('Remote Interaction', 'Remote Loot', 'Cross Map Interacts', 'Buried Loot',
                    'Arrow Duplication', 'Infinite Ammo', 'Teleporting')
        removed = ('Long Range Interacts', 'Item Hoovering', 'Item Duplication', 'Fast Swings', 'Fast Reloads',
                   'Silent Gunshots', 'Chainsaw Melee', 'Long Range Melee', 'Cross Map Melee',
                   'Invalid Totem Placement', 'Speed Hacking', 'Unknown Cheat', '')
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for mode in ('policy_direct', 'policy_log'):
                for cheat_type in retained + removed:
                    with self.subTest(plugin=variant.name, mode=mode, cheat_type=cheat_type):
                        source = {'anticheat': variant.read_text(encoding='utf-8'), 'cheatType': cheat_type,
                                  'accepted': cheat_type in retained}
                        result = subprocess.run(['node', str(self.harness_path), mode],
                                                input=json.dumps(source, ensure_ascii=False),
                                                capture_output=True, text=True, encoding='utf-8', check=False)
                        self.assertEqual(result.returncode, 0, result.stderr)

    def test_item_quantity_and_stack_transfers_no_longer_punish(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for suffix in ('roundtrip', 'burst', 'after', 'no_debit', 'excess', 'multi_add', 'wrong_target', 'wrong_class'):
                with self.subTest(plugin=variant.name, case=suffix):
                    result = subprocess.run(['node', str(self.harness_path), 'stack_transfer_' + suffix],
                                            input=json.dumps(variant.read_text(encoding='utf-8'), ensure_ascii=False),
                                            capture_output=True, text=True, encoding='utf-8', check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_ten_meter_distance_replaces_legacy_native_distance_events(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for mode in ('interact_legacy_range', 'interact_edge', 'interact_far'):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(['node', str(self.harness_path), mode],
                                            input=json.dumps(variant.read_text(encoding='utf-8'), ensure_ascii=False),
                                            capture_output=True, text=True, encoding='utf-8', check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_melee_events_are_ignored(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for mode in ("melee_event_direct", "melee_event_log", "melee_event_fast"):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(["node", str(self.harness_path), mode],
                                            input=json.dumps(variant.read_text(encoding="utf-8"), ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_totem_events_do_not_punish_players(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for mode in ("totem_events_direct", "totem_events_log", "totem_events_mixed"):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(["node", str(self.harness_path), mode],
                                            input=json.dumps(variant.read_text(encoding="utf-8"), ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_moving_corpses_use_current_body_bounds_and_keep_remote_guards(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            source = variant.read_text(encoding="utf-8")
            for mode in ("corpse_wolf", "corpse_bear", "corpse_native_class", "corpse_carcass", "corpse_moving",
                         "corpse_edge", "corpse_far", "corpse_old_position", "corpse_alive", "corpse_obliterated",
                         "corpse_fake_class", "corpse_foreign_mesh", "corpse_no_mesh"):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_only_observed_trap_killed_animals_skip_stale_corpse_distances(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            for suffix in ("wolf", "bear", "native_animal", "carcass", "no_mesh", "other_container",
                           "survived", "live", "human", "already_dead", "no_hook", "non_authority",
                           "obliterated", "revived", "stale", "world_change", "world_during_trap"):
                with self.subTest(plugin=variant.name, case=suffix):
                    result = subprocess.run(["node", str(self.harness_path), "trap_corpse_" + suffix],
                                            input=json.dumps(variant.read_text(encoding="utf-8"), ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_climbing_uses_surface_bounds_without_exempting_other_targets(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            source = variant.read_text(encoding="utf-8")
            for mode in ("climb_icewall", "climb_ladder", "climb_native_class", "climb_exit", "climb_edge",
                         "climb_far", "climb_fake_type", "climb_remote_item", "climb_complete_pickup"):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_v2_kicks_only_live_identified_players_on_game_thread(self):
        source = V2_PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("v2_direct", "v2_repeat", "v2_multi", "v2_retry", "v2_offline",
                     "v2_stale_state", "v2_stale_controller", "v2_reused_state", "v2_reused_controller",
                     "v2_world_changed", "v2_session_retry", "v2_same_name", "v2_log_only", "v2_rejoin"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["node", str(self.harness_path), "trusted"], input=json.dumps(source, ensure_ascii=False),
                                capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_v2_account_blacklist_delivery_and_reconnect_enforcement(self):
        for mode in ("ban_detect", "ban_no_id", "ban_invalid", "ban_non_executable", "ban_send_failure",
                     "ban_existing", "ban_steam", "ban_eos", "ban_same_name", "ban_rejoin", "ban_removed", "ban_v1"):
            with self.subTest(mode=mode):
                variant = PLUGIN_PATH if mode == "ban_v1" else V2_PLUGIN_PATH
                result = subprocess.run(["node", str(self.harness_path), mode],
                                        input=json.dumps(variant.read_text(encoding="utf-8"), ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_v2_preserves_normal_gameplay(self):
        sources = {"anticheat": V2_PLUGIN_PATH.read_text(encoding="utf-8"), "assertNoKick": True}
        for mode in ("pickup_drop_retake", "snow_dug", "totem_flat",
                     "reload_normal", "gun_normal", "arrow_normal", "interact_edge", "remote_near", "wrong_build"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(sources, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["node", str(self.harness_path), "v1_monitor"],
                                input=json.dumps(PLUGIN_PATH.read_text(encoding="utf-8"), ensure_ascii=False),
                                capture_output=True, text=True, encoding="utf-8", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_buried_loot_requires_server_digging_completion(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("snow_buried", "snow_partial", "snow_dug", "snow_unrelated", "snow_transition",
                     "snow_streamed", "snow_stale", "snow_reassigned", "snow_world_change", "snow_reburied"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_totem_placement_follows_original_game_without_extra_detection(self):
        for variant in (PLUGIN_PATH, V2_PLUGIN_PATH):
            source = variant.read_text(encoding="utf-8")
            for mode in ("totem_flat", "totem_near_flat", "totem_slope", "totem_yaw", "totem_quantized", "totem_air", "totem_underground",
                         "totem_shallow_underground", "totem_wall", "totem_max_slope", "totem_wrong_alignment", "totem_penetrating",
                         "totem_ground_mismatch", "totem_overlap", "totem_water", "totem_disallowed", "totem_attachment",
                         "totem_destructible", "totem_surface_type", "totem_far", "totem_explorer", "totem_nan",
                         "totem_bad_rotation", "totem_bad_scale", "totem_no_mesh", "totem_other_recipe", "totem_client_invalid"):
                with self.subTest(plugin=variant.name, mode=mode):
                    result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                            capture_output=True, text=True, encoding="utf-8", check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_dropped_item_uses_one_validated_native_interaction(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("pickup_drop_retake", "pickup_ship_retake", "pickup_immediate", "pickup_no_start",
                     "pickup_outside_start", "pickup_malformed_start", "pickup_rejected_interact", "pickup_cancelled",
                     "pickup_changed_target", "pickup_changed_controller", "pickup_changed_item", "pickup_other_thread",
                     "pickup_wrong_slot", "pickup_replay",
                     "pickup_repeat_completion", "pickup_direct_during_wait", "pickup_followup_far"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_ammo_and_direct_interaction_guards(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("interact_edge", "interact_far", "interact_custom", "interact_custom_over_limit", "interact_ship", "interact_no_collision",
                     "interact_inside_collision", "reload_normal", "reload_last_ammo", "reload_early",
                     "reload_pause", "reload_free_ammo", "reload_no_start", "reload_direct", "reload_repeat",
                     "reload_no_ammo", "reload_no_consumption_server", "reload_warmup", "reload_infinite_server",
                     "gun_normal", "gun_musket", "gun_forged", "gun_no_consumption", "gun_repeat"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_removed_item_detection_and_retained_native_events(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("normal", "trusted", "duplication", "large_grant", "native_teleport", "native_cross_map_repeat",
                     "wrong_build", "direct_events", "offline_event", "duplicate_name"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["node", str(self.harness_path), mode],
                    input=json.dumps(source, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missed_corpse_loot_and_arrow_paths(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("remote_far", "remote_near", "remote_owned", "remote_backpack", "remote_ship", "remote_pickup",
                     "remote_fixed_edge", "remote_old_tolerance", "remote_outside_limit", "remote_custom_server",
                     "remote_custom_over_limit", "remote_pickup_edge", "remote_pickup_outside",
                     "arrow_normal", "arrow_repeat", "arrow_forged", "arrow_no_consumption", "arrow_inflight",
                     "arrow_infinite_server", "arrow_infinite_weapon", "arrow_nonbow", "arrow_expired"):
            with self.subTest(mode=mode):
                result = subprocess.run(["node", str(self.harness_path), mode], input=json.dumps(source, ensure_ascii=False),
                                        capture_output=True, text=True, encoding="utf-8", check=False)
                self.assertEqual(result.returncode, 0, result.stderr)



if __name__ == "__main__":
    unittest.main()
