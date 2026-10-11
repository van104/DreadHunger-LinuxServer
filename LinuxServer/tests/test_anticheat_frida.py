"""Optional real Frida test in an owned process; no game or cheat is executed."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "app/Linux 插件"
PLUGIN = PLUGIN_DIR / "[服务端]反作弊物资_Linux.js"
V2_PLUGIN = PLUGIN_DIR / "[服务端]反作弊物资_v2_Linux.js"
if not V2_PLUGIN.exists():
    V2_PLUGIN = V2_PLUGIN.with_suffix(".js.disabled")
FIXTURE = r"""
const allocations = [];
const ownedRanges = [];
function alloc(size) {
    const p = Memory.alloc(size);
    p.writeByteArray(new Uint8Array(size));
    allocations.push(p);
    ownedRanges.push([p, size]);
    return p;
}
function text(out, value) {
    const data = Memory.allocUtf16String(value);
    allocations.push(data);
    ownedRanges.push([data, (value.length + 1) * 2]);
    out.writePointer(data);
    out.add(8).writeU32(value.length + 1);
    out.add(12).writeU32(value.length + 1);
}
const counts = alloc(56), ammoPointer = alloc(8), spendAmmo = alloc(1);
const kickReasons = [];
let rejectKick = false;
const verifyKick = new NativeCallback((session, target, reason) => {
    const label = reason.readPointer().readUtf16String();
    if (!session.equals(gameSession) || !target.equals(controller) || label.includes('（')) throw new Error('kick ABI or identity');
    if (!label.includes('服务器黑名单') && (!messages[messages.length - 1].includes(label.replace('反作弊：', '')) ||
        !messages[messages.length - 1].includes('自动踢出游戏'))) throw new Error('kick reason or announcement order');
    kickReasons.push(label);
    return rejectKick ? 0 : 1;
}, 'uint8', ['pointer', 'pointer', 'pointer']);
spendAmmo.writeU8(1);
const native = new CModule(`
#include <stdint.h>
extern uint32_t counts[14];
extern uint8_t verify_kick(void *session, void *controller, void *reason);
extern void *ammo_actor;
extern uint8_t spend_ammo;
void spawn_flash(void *pawn, void *projectile, void *transform) { }
uint8_t ranged_use(void *weapon, void *transform, void *state) {
    counts[0]++;
    uint8_t type = *((uint8_t *)weapon + 0x290);
    if (type == 26 || type == 27 || type == 36) {
        if (spend_ammo) (*((uint8_t *)weapon + 0x8cc))--;
        spawn_flash(*(void **)((uint8_t *)weapon + 0x268), weapon, transform);
    }
    return 1;
}
void record_cheat(void *player, void *type, float multiplier) { counts[1]++; }
void tick(void *mode) { }
uint8_t kick_player(void *session, void *controller, void *reason) {
    counts[13]++;
    return verify_kick(session, controller, reason);
}
void *add_inventory(void *inventory, void *item, void *states, int *added, int *slot, int desired,
                    uint8_t only, uint8_t expand, uint8_t byproduct, uint8_t flush, void *pawn, uint8_t whole) {
    *added = desired > 0 ? desired : 3; return item;
}
void transfer(void *pawn, void *source, int slot, void *target, int targetSlot, int quantity,
              uint8_t autoSlot, uint8_t quickLoot) {
    counts[2]++;
    if (*(int *)((uint8_t *)source + 0x140) != 1) return;
    void **stored = *(void ***)((uint8_t *)source + 0x138);
    void *item = *stored;
    if (!item) return;
    int added = 0, outputSlot = 0;
    add_inventory(target, *(void **)((uint8_t *)item + 0x10), 0, &added, &outputSlot,
                  quantity, 0, 0, 0, 1, pawn, 0);
    // fixture 开关：模拟入包成功但来源未扣除的异常调用。
    if (*(int *)((uint8_t *)source + 0x244)) return;
    uint8_t *count = (uint8_t *)item + 0x8b0;
    *count -= added;
    if (!*count) *stored = 0;
}
void *pickup(void *item, void *controller, int slot) { counts[3]++; return item; }
void hit_actor(void *weapon, void *hit) { counts[4]++; }
void interact(void *component, void *target, int slot) {
    counts[5]++;
    void *controller = *(void **)((uint8_t *)component + 0xa0);
    if (controller) *(void **)((uint8_t *)component + 0x198) = *(void **)((uint8_t *)controller + 0x250);
}
uint8_t trap(void *snare, void *target) {
    if (!*((uint8_t *)snare + 0x300)) *((uint8_t *)target + 0x818) = 1;
    return 0; // 原版致死路径返回 false，并且不会给已死亡目标执行 Ensnare。
}
uint8_t call_trap(void *snare, void *target) { return trap(snare, target); }
void interact_complete(void *component, void *target, int slot) {
    pickup(*(void **)((uint8_t *)target + 0xa0), *(void **)((uint8_t *)component + 0xa0), slot);
    *(void **)((uint8_t *)component + 0x198) = 0;
}
void on_rep_buried(void *site) { }
void spawn_ground(void *component, void *project) {
    if (*(void **)project && *((uint8_t *)project + 0x54)) counts[12]++;
}
uint8_t melee_use(void *weapon, void *transform, void *state) {
    counts[6]++;
    *(uintptr_t *)((uint8_t *)weapon + 0x528) = 1;
    return 1;
}
void bone_dagger_aim(void *weapon, uint8_t aiming) {
    // 0x9F0 仅为 fixture 的拒绝开关，生产插件不读取它。
    if (*((uint8_t *)weapon + 0x9f0)) aiming = 0;
    if (aiming) *(uintptr_t *)((uint8_t *)weapon + 0x528) = 0;
    *((uint8_t *)weapon + 0x8a9) = aiming;
}
void melee_damage(void *weapon, void *hits, void *state) {
    counts[7]++;
    counts[11] += *(int *)((uint8_t *)hits + 8);
}
void reload(void *weapon) {
    counts[8]++;
    *(float *)*(void **)((uint8_t *)weapon + 0x898) = 3.0f;
}
void complete_reload(void *weapon) {
    counts[10]++;
    *((uint8_t *)weapon + 0x8cc) = *(int *)((uint8_t *)weapon + 0x51c);
}
void ranged_reload(void *weapon) {
    counts[9]++;
    if (ammo_actor && *((uint8_t *)ammo_actor + 0x8b0) > 0) {
        if (spend_ammo) (*((uint8_t *)ammo_actor + 0x8b0))--;
        complete_reload(weapon);
    }
}
void call_interact(void *component, void *target, int slot) { interact(component, target, slot); }
void call_interact_complete(void *component, void *target, int slot) { interact_complete(component, target, slot); }
void call_track_site(void *site) { on_rep_buried(site); }
void call_spawn_ground(void *component, void *project) { spawn_ground(component, project); }
uint8_t call_melee_use(void *weapon, void *transform, void *state) { return melee_use(weapon, transform, state); }
void call_melee_damage(void *weapon, void *hits, void *state) { melee_damage(weapon, hits, state); }
void call_bone_dagger_aim(void *weapon, uint8_t aiming) { bone_dagger_aim(weapon, aiming); }
void call_reload(void *weapon) { reload(weapon); }
void call_ranged_reload(void *weapon) { ranged_reload(weapon); }
void call_complete_reload(void *weapon) { complete_reload(weapon); }
uint8_t call_use(void *weapon, void *transform, void *state) { return ranged_use(weapon, transform, state); }
void call_record(void *player, void *type) { record_cheat(player, type, 1.0f); }
void call_tick(void *mode) { tick(mode); }
void call_transfer(void *pawn, void *source, void *target) { transfer(pawn, source, 0, target, 0, 1, 1, 1); }
void call_stack_transfer(void *pawn, void *source, void *target, int quantity) { transfer(pawn, source, 0, target, 0, quantity, 1, 1); }
void *call_pickup(void *item, void *controller) { return pickup(item, controller, 0); }
void call_hit(void *weapon, void *hit) { hit_actor(weapon, hit); }
void call_add_wrapper(void *inventory, void *item, void *pawn) {
    int added = 0, slot = 0;
    add_inventory(inventory, item, 0, &added, &slot, -1, 0, 0, 0, 1, pawn, 0);
}
`, {counts: counts, ammo_actor: ammoPointer, spend_ammo: spendAmmo, verify_kick: verifyKick});
const world = alloc(4096), mode = alloc(4096), state = alloc(4096), gameState = alloc(4096);
const controller = alloc(4096), pawn = alloc(4096), inventory = alloc(4096), role = alloc(128);
const players = alloc(8), gWorld = alloc(8);
const gameSession = alloc(1024);
gWorld.writePointer(world);
world.add(0x118).writePointer(mode);
mode.add(0x278).writePointer(gameSession);
mode.add(0x280).writePointer(gameState);
gameState.add(0x238).writePointer(players);
gameState.add(0x240).writeU32(1);
players.writePointer(state);
state.add(0x588).writePointer(role);
controller.add(0x250).writePointer(pawn);
pawn.add(0x808).writePointer(inventory);
pawn.add(0xC30).writePointer(state);
text(role.add(0x48), 'Captain');
const silent = alloc(16);
text(silent, 'Silent Gunshots');
const callbacks = [];
function callback(fn, ret, args) {
    const p = new NativeCallback(fn, ret, args);
    callbacks.push(p);
    return p;
}
const messages = [];
let nativeAccountId = 'EOSPlus:76561198000000000_+_|0123456789abcdef0123456789abcdef';
const uniqueAccount = alloc(64), uniqueVtable = alloc(64);
const uniqueToString = callback((output, object) => {
    if (!object.equals(uniqueAccount)) throw new Error('UniqueId this pointer incorrect');
    text(output, nativeAccountId);
}, 'void', ['pointer', 'pointer']);
state.add(0x258).writePointer(uniqueAccount);
uniqueAccount.writePointer(uniqueVtable);
uniqueVtable.add(0x38).writePointer(uniqueToString);
const digClass = alloc(64), totemClass = alloc(64), destructibleClass = alloc(64);
const climbClass = alloc(64), actorBounds = new Map(), noSimpleCollision = new Set();
const characterClass = alloc(64);
const animalClass = alloc(64);
const recipeMesh = alloc(4096), recipeBody = alloc(256), groundSurface = alloc(1024), groundActor = alloc(4096);
groundSurface.add(0xA0).writePointer(groundActor);
let groundNormal = [0, 0, 1], groundHit = true, groundPenetrating = false, placementOverlap = false;
const weakGenerations = new Map(), objectGenerations = new Map();
const digSites = [];
const functions = {
    0x32C: alloc(8), 0x27CB540: native.record_cheat, 0x2721780: native.ranged_use,
    0x270BA70: native.add_inventory, 0x4336360: native.tick, 0x5C9B6D0: gWorld, 0x5A1CF70: silent,
    0x26891D0: native.transfer, 0x2712200: native.pickup, 0x2721A70: native.hit_actor,
    0x26A0D00: native.spawn_flash,
    0x27647E0: native.interact, 0x271FE40: native.melee_use, 0x2720BF0: native.melee_damage,
    0x27650A0: native.interact_complete,
    0x26F5140: native.on_rep_buried, 0x26BBF00: native.spawn_ground,
    0x4346570: native.kick_player,
    0x459F3C0: alloc(16),
    0x27EB690: callback(() => digClass, 'pointer', []),
    0x27E1260: callback(() => climbClass, 'pointer', []),
    0x27D7D10: callback(() => characterClass, 'pointer', []),
    0x27D2100: callback(() => animalClass, 'pointer', []),
    0x2703DB0: native.trap,
    0x43E1420: callback((component, origin, extent, radius) => {
        Memory.copy(origin, component.add(0x100), 12);
        Memory.copy(extent, component.add(0x10C), 12);
        radius.writeFloat(component.add(0x118).readFloat());
    }, 'void', ['pointer', 'pointer', 'pointer', 'pointer']),
    0x283FBE0: callback(() => totemClass, 'pointer', []),
    0x27EADA0: callback(() => destructibleClass, 'pointer', []),
    0x433F490: callback((context, type, actors) => {
        const sites = type.equals(digClass) ? digSites : [];
        const data = sites.length ? alloc(sites.length * 8) : ptr(0);
        sites.forEach((site, i) => data.add(i * 8).writePointer(site));
        actors.writePointer(data); actors.add(8).writeS32(sites.length); actors.add(12).writeS32(sites.length);
    }, 'void', ['pointer', 'pointer', 'pointer']),
    0x29D7620: callback(() => {}, 'void', ['pointer']),
    0x2CA9080: callback((weak, object) => {
        weak.writePointer(object);
        weakGenerations.set(weak.toString(), objectGenerations.get(object.toString()) || 0);
    }, 'void', ['pointer', 'pointer']),
    0x2CA9210: callback(weak => {
        const object = weak.readPointer();
        return weakGenerations.has(weak.toString()) && weakGenerations.get(weak.toString()) !==
            (objectGenerations.get(object.toString()) || 0) ? ptr(0) : object;
    }, 'pointer', ['pointer']),
    0x26B8420: callback(() => recipeMesh, 'pointer', ['pointer']),
    0x427BF80: callback(() => recipeBody, 'pointer', ['pointer']),
    0x41BB160: callback(box => {
        [-20, -20, 0, 20, 20, 200].forEach((v, i) => box.add(i * 4).writeFloat(v));
        box.add(24).writeU8(1); return box;
    }, 'pointer', ['pointer', 'pointer', 'pointer']),
    0x421B6D0: callback(component => component.equals(groundSurface) ? 0 : 2, 'int', ['pointer']),
    0x41ABAB0: callback(() => {}, 'void', ['pointer', 'pointer']),
    0x41C1380: callback((context, hit, start, end, channel, query, response) => {
        require(channel === 2 && query.add(0x11).readU8() === 1 && query.add(0x1E).readU8() === 1, 'collision query ABI mismatch');
        if (!groundHit) return 0;
        hit.writeU8(groundPenetrating ? 3 : 1);
        hit.add(0x1C).writeFloat(100); hit.add(0x20).writeFloat(0); hit.add(0x24).writeFloat(0);
        groundNormal.forEach((v, i) => hit.add(0x34 + i * 4).writeFloat(v));
        hit.add(0x74).writePointer(groundSurface);
        return 1;
    }, 'uint8', ['pointer', 'pointer', 'pointer', 'pointer', 'int', 'pointer', 'pointer']),
    0x41C1A70: callback((context, origin, quat, channel, shape, query, response) => {
        require(channel === 2 && shape.readU32() === 1 && shape.add(4).readFloat() === 20 && shape.add(12).readFloat() === 50,
                'collision shape ABI mismatch or client bounds trusted');
        return Number(placementOverlap);
    }, 'uint8', ['pointer', 'pointer', 'pointer', 'int', 'pointer', 'pointer', 'pointer']),
    0x27C5940: callback(() => -10, 'float', ['pointer']),
    0x4242250: callback(() => groundActor, 'pointer', ['pointer']),
    0x4098470: callback((actor, location, rotation) => {
        Memory.copy(location, actor.add(0x130).readPointer().add(0x1D0), 12);
    }, 'void', ['pointer', 'pointer', 'pointer']),
    0x2681420: callback(() => 1, 'uint8', ['pointer']),
    0x27A5DC0: native.bone_dagger_aim,
    0x2707210: native.reload, 0x2721600: native.ranged_reload, 0x27073C0: native.complete_reload,
    0x45AB920: callback((target, origin, point, name) => {
        if (noSimpleCollision.has(target.toString())) return -1;
        Memory.copy(point, target.add(0x1D0), 12); return 1;
    },
                       'float', ['pointer', 'pointer', 'pointer', 'uint64']),
    0x4342710: callback(() => world.add(0x598).readFloat(), 'float', ['pointer']),
    0x280C210: callback((weapon, state) => weapon.add(0x290).readU8() === 24 && state.readU8() === 1 ? 2 : weapon.add(0x520).readFloat(),
                       'float', ['pointer', 'pointer']),
    0x28548F0: callback((weapon, state) => weapon.add(0x290).readU8() === 24 ? Number(state.readU8() !== 2) : Number(state.readU8() === 0),
                       'uint8', ['pointer', 'pointer']),
    0x408DAD0: callback(() => world, 'pointer', ['pointer']),
    0x470C0C0: callback((manager, handle) => handle.readPointer(), 'pointer', ['pointer', 'pointer']),
    0x470D300: callback((manager, timer) => timer.isNull() ? -1 : timer.readFloat(), 'float', ['pointer', 'pointer']),
    0x2854EE0: callback(() => 1, 'uint8', ['pointer']),
    0x270E270: callback(() => ammoPointer.readPointer(), 'pointer', ['pointer', 'pointer', 'int']),
    0x26F96E0: callback(ammo => ammo.add(0x8B0).readU8(), 'int', ['pointer', 'uint8']),
    0x26F9700: callback((manager, slot) => {
        if (slot < 0 || slot >= manager.add(0x240).readS32()) return ptr(0);
        for (let i = 0; i < manager.add(0x140).readS32(); i++) {
            const item = manager.add(0x138).readPointer().add(i * 8).readPointer();
            if (!item.isNull() && item.add(0x870).readS32() === slot) return item;
        }
        return ptr(0);
    }, 'pointer', ['pointer', 'int']),
    0x409E270: callback((actor, colliding, origin, extent, children) => {
        const bounds = actorBounds.get(actor.toString());
        const root = actor.add(0x130).readPointer();
        for (let i = 0; i < 3; i++) {
            origin.add(i * 4).writeFloat(bounds ? bounds.center[i] : root.add(0x1D0 + i * 4).readFloat());
            extent.add(i * 4).writeFloat(bounds ? bounds.extent[i] : 30);
        }
    }, 'void', ['pointer', 'uint8', 'pointer', 'pointer', 'uint8']),
    0x2B130F0: callback((out, input) => {
        const stable = Memory.allocUtf16String(input.readUtf16String());
        allocations.push(stable);
        out.writePointer(stable);
    }, 'void', ['pointer', 'pointer', 'int8']),
    0x2A13190: callback((out, input) => { out.writePointer(input.readPointer()); return out; }, 'pointer', ['pointer', 'pointer']),
    0x282B4B0: callback((pc, msg) => messages.push(msg.readPointer().readUtf16String()),
                        'void', ['pointer', 'pointer', 'pointer', 'pointer', 'pointer']),
    0x459E030: callback(out => text(out, '测试用户'), 'void', ['pointer', 'pointer']),
    0x277E4F0: callback(() => controller, 'pointer', ['pointer']),
    0x280AD20: callback(() => ptr(0), 'pointer', []),
    0x2B9C070: callback(() => ptr(0), 'pointer', []),
    0x2C95CA0: callback(() => ptr(0), 'pointer', ['pointer', 'pointer', 'pointer', 'int8'])
};
const signatures = new Map([
    [functions[0x32C].toString(), 'cd762268d82e378f'],
    [native.record_cheat.toString(), '4156534883ec28f30f114424044885ff'],
    [native.ranged_use.toString(), '554157415653504989d74989f64889fb'],
    [native.add_inventory.toString(), '554157415641554154534883ec784531'],
    [native.transfer.toString(), '554157415641554154534881ecc80000'],
    [native.pickup.toString(), '55415741564154534883ec3080bf7103'],
    [native.hit_actor.toString(), '554157415641554154534881ec880100'],
    [native.spawn_flash.toString(), '534889fb4881c7c80e0000e8b0ee0700'],
    [functions[0x409E270].toString(), '41574156534883ec204989cf4989d648'],
    [functions[0x280AD20].toString(), '50488b0578be21034885c0740259c3bf']
]);
for (const match of PLUGIN_SOURCE.matchAll(/checkBytes\((0x[0-9A-F]+), '([a-f0-9]+)'\)/g)) {
    const address = functions[Number(match[1])];
    if (!address) throw new Error('missing native fixture RVA ' + match[1]);
    if (!signatures.has(address.toString())) signatures.set(address.toString(), match[2]);
}
const originalReadBytes = NativePointer.prototype.readByteArray;
NativePointer.prototype.readByteArray = function(size) {
    const expected = signatures.get(this.toString());
    if (expected) return Uint8Array.from(expected.match(/../g).map(x => parseInt(x, 16))).buffer;
    return originalReadBytes.call(this, size);
};
const originalFindModule = Process.findModuleByName;
const originalFindRange = Process.findRangeByAddress;
// Frida 隐藏自身分配的测试内存；只给确实持有的 fixture 缓冲区补齐范围元数据。
Process.findRangeByAddress = address => address.equals(uniqueToString) ? {protection: 'r-x'} : originalFindRange(address) ||
    (ownedRanges.some(([start, size]) => address.compare(start) >= 0 && address.compare(start.add(size)) < 0)
        ? {protection: 'rw-'} : null);
Process.findModuleByName = name => name === 'DreadHungerServer-Linux-Shipping'
    ? {base: {add: offset => functions[offset]}} : originalFindModule(name);
const files = new Map();
const RealFile = File;
globalThis.File = function(path, access) {
    if (access !== 'w') throw new Error('unexpected fixture file mode');
    files.set(path, '');
    return {write: value => files.set(path, files.get(path) + String(value)), close: () => {}};
};
File.readAllText = path => {
    if (!files.has(path)) throw new Error('no event file in fixture');
    return files.get(path);
};
File.writeAllText = (path, value) => files.set(path, value);
globalThis.DH_LINUX_ROOT = '/fixture';
let now = 1000000;
Date.now = () => now;
eval(PLUGIN_SOURCE);
Interceptor.flush();
const callUse = new NativeFunction(native.call_use, 'uint8', ['pointer', 'pointer', 'pointer']);
const callRecord = new NativeFunction(native.call_record, 'void', ['pointer', 'pointer']);
const callTick = new NativeFunction(native.call_tick, 'void', ['pointer']);
const callTransfer = new NativeFunction(native.call_transfer, 'void', ['pointer', 'pointer', 'pointer']);
const callStackTransfer = new NativeFunction(native.call_stack_transfer, 'void', ['pointer', 'pointer', 'pointer', 'int']);
const callPickup = new NativeFunction(native.call_pickup, 'pointer', ['pointer', 'pointer']);
const callHit = new NativeFunction(native.call_hit, 'void', ['pointer', 'pointer']);
const callAdd = new NativeFunction(native.call_add_wrapper, 'void', ['pointer', 'pointer', 'pointer']);
const callInteract = new NativeFunction(native.call_interact, 'void', ['pointer', 'pointer', 'int']);
const callTrap = new NativeFunction(native.call_trap, 'uint8', ['pointer', 'pointer']);
const callInteractComplete = new NativeFunction(native.call_interact_complete, 'void', ['pointer', 'pointer', 'int']);
const callTrackSite = new NativeFunction(native.call_track_site, 'void', ['pointer']);
const callSpawnGround = new NativeFunction(native.call_spawn_ground, 'void', ['pointer', 'pointer']);
const callMeleeUse = new NativeFunction(native.call_melee_use, 'uint8', ['pointer', 'pointer', 'pointer']);
const callMeleeDamage = new NativeFunction(native.call_melee_damage, 'void', ['pointer', 'pointer', 'pointer']);
const callBoneDaggerAim = new NativeFunction(native.call_bone_dagger_aim, 'void', ['pointer', 'uint8']);
const callReload = new NativeFunction(native.call_reload, 'void', ['pointer']);
const callRangedReload = new NativeFunction(native.call_ranged_reload, 'void', ['pointer']);
const callCompleteReload = new NativeFunction(native.call_complete_reload, 'void', ['pointer']);
function require(value, message) { if (!value) throw new Error(message); }
rpc.exports.kickAttempts = function() { return counts.add(52).readU32(); };
rpc.exports.runRemovedTotemEvents = function() {
    const type = alloc(16);
    for (const label of ['Invalid Totem Placement', '  Invalid Totem Placement  ']) {
        text(type, label); callRecord(state, type);
    }
    const path = '/fixture/.gm_runtime/anti_cheat_events.json';
    files.set(path, JSON.stringify({events: [
        {id: 'removed-totem', player_name: '测试用户', cheat_type: 'Invalid Totem Placement'},
        {id: 'removed-totem-trimmed', player_name: '测试用户', cheat_type: '  Invalid Totem Placement  '}
    ]}));
    now += 1100; callTick(mode);
    files.delete(path);
    require(counts.add(4).readU32() === 2, 'original game event recording changed');
    require(messages.length === 0 && kickReasons.length === 0, 'removed totem event announced or kicked');
    return {nativeEvents: 2, announcements: 0, kicks: 0};
};
rpc.exports.runRemovedMeleeEvents = function() {
    const type = alloc(16), before = counts.add(4).readU32();
    const labels = ['Chainsaw Melee', ' Long Range Melee ', 'Cross Map Melee'];
    for (const label of labels) { text(type, label); callRecord(state, type); }
    const path = '/fixture/.gm_runtime/anti_cheat_events.json';
    files.set(path, JSON.stringify({events: labels.map((label, i) =>
        ({id: 'removed-melee-' + i, player_name: '测试用户', cheat_type: label}))}));
    now += 1100; callTick(mode);
    files.delete(path);
    require(counts.add(4).readU32() === before + 3, 'original melee event recording changed');
    require(messages.length === 0 && kickReasons.length === 0, 'removed melee events announced or kicked');
    return {nativeEvents: 3, announcements: 0, kicks: 0};
};
rpc.exports.runBoneDaggerRepeatedHits = function() {
    const bone = alloc(4096), transform = alloc(48), useState = alloc(1), hits = alloc(16), hit = alloc(0x8C);
    bone.add(0xF0).writeU8(3);
    bone.add(0x268).writePointer(pawn);
    bone.add(0x290).writeU8(24);
    bone.add(0x520).writeFloat(1);
    hits.writePointer(hit); hits.add(8).writeS32(1); hits.add(12).writeS32(1);
    hit.add(0x6C).writeS32(1); hit.add(0x70).writeU32(1);
    now += 31000;
    for (let i = 0; i < 5; i++) {
        require(callMeleeUse(bone, transform, useState) === 1, 'normal alternating bone dagger attack blocked');
        callMeleeDamage(bone, hits, useState);
        callMeleeDamage(bone, hits, useState);
        callBoneDaggerAim(bone, 1);
        callMeleeDamage(bone, hits, useState);
        callBoneDaggerAim(bone, 0);
        world.add(0x598).writeFloat(world.add(0x598).readFloat() + 0.05);
        now += 61000; callTick(mode);
        require(messages.length === 0 && kickReasons.length === 0, 'bone dagger repeat notifications punished');
    }
    require(counts.add(24).readU32() === 5 && counts.add(28).readU32() === 15 && counts.add(44).readU32() === 15,
            'native bone dagger attacks or damage notifications intercepted');
    return {swings: 5, damageCalls: 15, targets: 15, announcements: 0, kicks: 0};
};
rpc.exports.runTrapKilledCorpses = function() {
    const root = alloc(1024), component = alloc(512), target = alloc(1024), corpse = alloc(4096);
    const mesh = alloc(1024), source = alloc(1024), snare = alloc(1024), blueprint = alloc(64), chain = alloc(24);
    characterClass.add(0x38).writeS32(1);
    animalClass.add(0x38).writeS32(2);
    blueprint.add(0x38).writeS32(2);
    blueprint.add(0x30).writePointer(chain);
    chain.add(8).writePointer(characterClass.add(0x30));
    chain.add(16).writePointer(animalClass.add(0x30));
    pawn.add(0x130).writePointer(root);
    pawn.add(0xF0).writeU8(3);
    root.add(0x1D0).writeFloat(1680);
    controller.add(0x680).writePointer(component);
    component.add(0xA0).writePointer(controller);
    corpse.add(0x10).writePointer(blueprint);
    corpse.add(0xF0).writeU8(3);
    corpse.add(0x280).writePointer(mesh);
    mesh.add(0xA0).writePointer(corpse);
    for (let i = 0; i < 3; i++) mesh.add(0x10C + i * 4).writeFloat(30);
    actorBounds.set(corpse.toString(), {center: [0, 0, 0], extent: [30, 30, 30]});
    source.add(0xA0).writePointer(corpse);
    target.add(0xA0).writePointer(corpse);
    snare.add(0xF0).writeU8(3);
    function loot() {
        callInteract(component, target, 7);
        callTransfer(pawn, source, inventory);
        callTransfer(pawn, inventory, source);
        callPickup(corpse, controller);
    }
    require(callTrap(snare, corpse) === 0, 'fixture must keep native lethal trap return value');
    require(corpse.add(0x7A0).readPointer().isNull(), 'lethal trap must not set Ensnare');
    loot();
    corpse.add(0x818).writeU8(2); // 专服收割后没有 CarcassMesh。
    loot();
    now += 1100; callTick(mode);
    require(counts.add(20).readU32() === 2 && counts.add(8).readU32() === 4 && counts.add(12).readU32() === 2,
            'stale dedicated server corpse bounds still block interaction or looting');
    require(messages.length === 0 && kickReasons.length === 0, 'trap killed corpse movement punished');
    const other = alloc(4096), otherMesh = alloc(1024), otherManager = alloc(1024), otherTarget = alloc(1024);
    other.add(0x10).writePointer(blueprint);
    other.add(0xF0).writeU8(3);
    other.add(0x280).writePointer(otherMesh);
    otherMesh.add(0xA0).writePointer(other);
    for (let i = 0; i < 3; i++) otherMesh.add(0x10C + i * 4).writeFloat(30);
    otherManager.add(0xA0).writePointer(other);
    otherTarget.add(0xA0).writePointer(other);
    actorBounds.set(other.toString(), {center: [0, 0, 0], extent: [30, 30, 30]});
    snare.add(0x300).writeU8(1);
    callTrap(snare, other); // 活着离开夹子调用，后续武器击杀没有距离例外。
    other.add(0x818).writeU8(1);
    callInteract(component, otherTarget, 7);
    callTransfer(pawn, otherManager, inventory);
    callPickup(other, controller);
    require(counts.add(20).readU32() === 2 && counts.add(8).readU32() === 4 && counts.add(12).readU32() === 2,
            'trap survivor gained corpse distance exception');
    now += 1100; callTick(mode);
    const v2 = PLUGIN_SOURCE.includes('var AutoKick = true;');
    require(messages.length === (v2 ? 1 : 2) && kickReasons.length === Number(v2), 'unrelated remote corpse guard lost');
    return {legalInteractions: 2, legalTransfers: 4, legalPickups: 2, announcements: messages.length, kicks: kickReasons.length};
};
rpc.exports.runMovingCorpses = function() {
    const root = alloc(1024), component = alloc(512), target = alloc(1024), corpse = alloc(4096);
    const capsule = alloc(1024), mesh = alloc(1024), carcass = alloc(1024), source = alloc(1024);
    const blueprint = alloc(64), chain = alloc(16);
    characterClass.add(0x38).writeS32(1);
    blueprint.add(0x38).writeS32(1);
    blueprint.add(0x30).writePointer(chain);
    chain.add(8).writePointer(characterClass.add(0x30));
    pawn.add(0x130).writePointer(root);
    pawn.add(0xF0).writeU8(3);
    controller.add(0x680).writePointer(component);
    component.add(0xA0).writePointer(controller);
    corpse.add(0x10).writePointer(blueprint);
    corpse.add(0xF0).writeU8(3);
    corpse.add(0x130).writePointer(capsule);
    corpse.add(0x280).writePointer(mesh);
    corpse.add(0x5A8).writePointer(carcass);
    corpse.add(0x818).writeU8(1);
    source.add(0xA0).writePointer(corpse);
    target.add(0xA0).writePointer(corpse);
    mesh.add(0xA0).writePointer(corpse);
    carcass.add(0xA0).writePointer(corpse);
    function bounds(body, x) {
        body.add(0x100).writeFloat(x);
        for (let i = 0; i < 3; i++) body.add(0x10C + i * 4).writeFloat(30);
        body.add(0x118).writeFloat(52);
    }
    function loot() {
        callInteract(component, target, 7);
        callTransfer(pawn, source, inventory);
        callTransfer(pawn, inventory, source);
    }
    bounds(mesh, 1000);
    bounds(carcass, 100000);
    actorBounds.set(corpse.toString(), {center: [500, 0, 0], extent: [530, 30, 30]});
    root.add(0x1D0).writeFloat(1000);
    loot();
    bounds(mesh, 1400);
    root.add(0x1D0).writeFloat(1400);
    loot();
    corpse.add(0x818).writeU8(2);
    bounds(mesh, 100000); // 旧骨骼模型隐藏后，不能用它放行远处尸体。
    bounds(carcass, 1800);
    actorBounds.set(corpse.toString(), {center: [900, 0, 0], extent: [930, 30, 30]});
    root.add(0x1D0).writeFloat(1800);
    loot();
    root.add(0x1D0).writeFloat(2830); // 当前尸体边界最近点恰好 10.00 米。
    loot();
    now += 1100; callTick(mode);
    require(counts.add(20).readU32() === 4 && counts.add(8).readU32() === 8,
            'moving corpse interaction or inventory transfers blocked');
    require(messages.length === 0 && kickReasons.length === 0, 'moving corpse looting punished');
    root.add(0x1D0).writeFloat(2831);
    target.add(0x1D0).writeFloat(2831);
    loot();
    root.add(0x1D0).writeFloat(0); // 旧夹子位置在 Actor 整体边界内，但远离实际尸体。
    target.add(0x1D0).writeFloat(0);
    loot();
    require(counts.add(20).readU32() === 4 && counts.add(8).readU32() === 8, 'remote corpse request reached native');
    now += 1100; callTick(mode);
    const v2 = PLUGIN_SOURCE.includes('var AutoKick = true;');
    require(messages.length === (v2 ? 1 : 2) && messages[0].includes('远程交互'), 'remote corpse evidence missing');
    require(kickReasons.length === Number(v2), 'incorrect remote corpse punishment');
    return {legalInteractions: 4, legalTransfers: 8, announcements: messages.length, kicks: kickReasons.length};
};
rpc.exports.runClimbing = function() {
    const root = alloc(1024), component = alloc(512), mesh = alloc(1024), wall = alloc(4096);
    const blueprint = alloc(64), chain = alloc(16);
    climbClass.add(0x38).writeS32(1);
    blueprint.add(0x38).writeS32(1);
    blueprint.add(0x30).writePointer(chain);
    chain.add(8).writePointer(climbClass.add(0x30));
    pawn.add(0x130).writePointer(root);
    pawn.add(0xF0).writeU8(3);
    controller.add(0x680).writePointer(component);
    component.add(0xA0).writePointer(controller);
    mesh.add(0xA0).writePointer(wall);
    mesh.add(0x1D0).writeFloat(800000);
    noSimpleCollision.add(mesh.toString());
    actorBounds.set(wall.toString(), {center: [100000, 0, 1000], extent: [30, 500, 1000]});
    const legacyRange = alloc(16);
    text(legacyRange, 'Long Range Interacts');
    callRecord(state, legacyRange);
    for (let i = 0; i < 5; i++) {
        wall.add(0x10).writePointer(i === 0 ? climbClass : blueprint);
        wall.add(0x278).writeU8(i === 1 ? 1 : 2);
        root.add(0x1D0).writeFloat(i === 4 ? 101030 : 100130);
        root.add(0x1D8).writeFloat(i === 3 ? 1800 : 1000);
        pawn.add(0x640).writePointer(i === 3 ? wall : ptr(0));
        callInteract(component, mesh, 7);
        now += 61000; callTick(mode); // 退出公告冷却，确保误报不会被已有记录遮盖。
        require(counts.add(20).readU32() === i + 1 && messages.length === 0 && kickReasons.length === 0,
                'legitimate climbing blocked or punished');
    }
    root.add(0x1D0).writeFloat(101031);
    root.add(0x1D8).writeFloat(1000);
    callInteract(component, mesh, 7);
    root.add(0x1D0).writeFloat(100130);
    pawn.add(0x640).writePointer(wall);
    mesh.add(0xA0).writePointer(alloc(4096));
    mesh.add(0x1D0).writeFloat(101131);
    mesh.add(0x1D8).writeFloat(1000);
    callInteract(component, mesh, 7);
    require(counts.add(20).readU32() === 5, 'climbing bypassed distance check for remote target');
    now += 1100; callTick(mode);
    require(messages.length === 1 && messages[0].includes('远程交互'), 'real remote interaction evidence missing');
    require(kickReasons.length === Number(PLUGIN_SOURCE.includes('var AutoKick = true;')), 'incorrect punishment for remote interaction');
    return {legalInteractions: 5, announcements: messages.length, kicks: kickReasons.length};
};
rpc.exports.runStackTransfer = function() {
    const source = alloc(1024), item = alloc(4096), itemClass = alloc(64), stored = alloc(8);
    pawn.add(0xF0).writeU8(3);
    source.add(0xD8).writePointer(pawn);
    source.add(0x138).writePointer(stored); source.add(0x140).writeS32(1); source.add(0x240).writeS32(10);
    item.add(0x10).writePointer(itemClass); item.add(0xF0).writeU8(3); item.add(0x8B0).writeU8(30);
    stored.writePointer(item);
    for (let i = 0; i < 3; i++) callStackTransfer(pawn, source, inventory, 10);
    now += 1100; callTick(mode);
    require(stored.readPointer().isNull() && counts.add(8).readU32() === 3, 'source stack not fully transferred');
    require(messages.length === 0 && kickReasons.length === 0, 'native stack transfer was counted as newly generated items');
    stored.writePointer(item); item.add(0x8B0).writeU8(30);
    callStackTransfer(pawn, source, inventory, 30);
    now += 1100; callTick(mode);
    require(messages.length === 0 && kickReasons.length === 0, 'whole 30-item transfer punished');
    stored.writePointer(item); item.add(0x8B0).writeU8(30); source.add(0x244).writeS32(1);
    callStackTransfer(pawn, source, inventory, 30);
    now += 1100; callTick(mode);
    for (let i = 0; i < 4; i++) callAdd(inventory, itemClass, pawn);
    now += 1100; callTick(mode);
    require(messages.length === 0 && kickReasons.length === 0, 'removed item-addition detector still punished');
    return {transfers: counts.add(8).readU32(), announcements: messages.length, kicks: kickReasons.length};
};
rpc.exports.runV2 = function() {
    const item = alloc(64), trustedPath = '/fixture/.gm_runtime/anti_cheat_trusted_items.json';
    for (let i = 0; i < 4; i++) {
        files.set(trustedPath, JSON.stringify({grants:[{pawn:pawn.toString(),item_class:item.toString(),expires_at:now+5000,
            source:i%2 ? 'gm_give_item' : 'winning_card_reward'}]}));
        callAdd(inventory, item, pawn);
    }
    callTick(mode);
    require(kickReasons.length === 0 && messages.length === 0, 'GM/reward caused punishment');
    const type = alloc(16);
    text(type, 'Teleporting');
    for (let i = 0; i < 20; i++) callRecord(state, type);
    require(kickReasons.length === 0 && messages.length === 0, 'v2 kicked outside Tick');
    now += 1100; callTick(mode);
    require(counts.add(52).readU32() === 1 && messages.length === 1 &&
        messages[0].endsWith('理由：传送/瞬移\n处理：自动踢出游戏'), 'v2 did not announce/kick cleanly');
    now += 1100; callRecord(state, type); callTick(mode);
    require(kickReasons.length === 1 && messages.length === 1, 'same connection kicked twice');
    objectGenerations.set(state.toString(), 1); objectGenerations.set(controller.toString(), 1);
    text(type, 'Infinite Ammo');
    callRecord(state, type);
    gameState.add(0x240).writeU32(0);
    now += 1100; callTick(mode);
    require(kickReasons.length === 1, 'offline identity kicked');
    gameState.add(0x240).writeU32(1);
    rejectKick = true; now += 1100; callRecord(state, type); callTick(mode);
    require(kickReasons.length === 2 && messages.length === 2, 'native failure not attempted');
    rejectKick = false; now += 1100; callRecord(state, type); callTick(mode);
    require(kickReasons.length === 3 && messages.length === 2, 'announcement cooldown suppressed retry');
    objectGenerations.set(state.toString(), 2); objectGenerations.set(controller.toString(), 2);
    now += 1100;
    rejectKick = true;
    text(type, 'Buried Loot');
    for (let i = 0; i < 4; i++) callRecord(state, type);
    require(kickReasons.length === 3, 'event callback kicked outside Tick');
    callTick(mode);
    require(counts.add(52).readU32() === 4 && messages.length === 3 && kickReasons[3] === '反作弊：未挖掘取物',
        'new connection was not punished for buried loot');
    rejectKick = false; now += 1100; callRecord(state, type); callTick(mode);
    require(counts.add(52).readU32() === 5 && messages.length === 3, 'event cooldown suppressed native kick retry');
    return {kickAttempts: 5, announcements: 3, trustedAdds: 4};
};
rpc.exports.enforceBlacklist = function(json) {
    files.set('/fixture/gm_blacklist.json', json);
    objectGenerations.set(state.toString(), (objectGenerations.get(state.toString()) || 0) + 1);
    objectGenerations.set(controller.toString(), (objectGenerations.get(controller.toString()) || 0) + 1);
    now += 1100; callTick(mode);
    return counts.add(52).readU32();
};
rpc.exports.runWorldGuards = function() {
    now += 61000;
    const initialMessages = messages.length, root = alloc(1024), interact = alloc(512), mesh = alloc(1024);
    const site = alloc(1024), item = alloc(4096), itemRoot = alloc(1024), source = alloc(1024);
    pawn.add(0x130).writePointer(root);
    pawn.add(0xF0).writeU8(3);
    controller.add(0xF0).writeU8(3);
    controller.add(0x680).writePointer(interact);
    interact.add(0xA0).writePointer(controller);
    item.add(0xF0).writeU8(3);
    item.add(0x130).writePointer(itemRoot);
    itemRoot.add(0x1D0).writeFloat(150);
    mesh.add(0xA0).writePointer(item);
    mesh.add(0x1D0).writeFloat(120);
    source.add(0xA0).writePointer(item);
    site.add(0xF0).writeU8(3);
    site.add(0x298).writePointer(item);
    digSites.push(site);
    callTrackSite(site);
    const beforeTransfers = counts.add(8).readU32(), beforePickups = counts.add(12).readU32(), beforeInteracts = counts.add(20).readU32();
    callTransfer(pawn, source, inventory);
    require(callPickup(item, controller).isNull(), 'buried pickup escaped');
    callInteract(interact, mesh, 0);
    require(counts.add(8).readU32() === beforeTransfers && counts.add(12).readU32() === beforePickups &&
            counts.add(20).readU32() === beforeInteracts, 'unexcavated requests reached native functions');
    callTick(mode);
    require(messages.length === initialMessages + 1 && messages[messages.length - 1].includes('未挖掘'), 'buried loot announcement missing');
    site.add(0x2A0).writeU8(1);
    callTransfer(pawn, source, inventory);
    require(callPickup(item, controller).equals(item), 'dug item pickup blocked');
    callInteract(interact, mesh, 0);
    site.add(0x2A0).writeU8(0);
    callInteractComplete(interact, mesh, 0);
    require(counts.add(8).readU32() === beforeTransfers + 1 && counts.add(12).readU32() === beforePickups + 1 &&
            counts.add(20).readU32() === beforeInteracts + 1, 'digging transition or native completion bypass failed');
    const component = alloc(512), recipe = alloc(512), project = alloc(96);
    component.add(0xA0).writePointer(controller);
    component.add(0xB0).writeFloat(500);
    recipe.add(0x1F8).writePointer(totemClass);
    recipe.add(0x31).writeU8(1);
    recipe.add(0x118).writeFloat(0.5);
    project.writePointer(recipe);
    project.add(0x1C).writeFloat(1);
    project.add(0x20).writeFloat(100);
    [1, 1, 1].forEach((v, i) => project.add(0x30 + i * 4).writeFloat(v));
    project.add(0x54).writeU8(1);
    callSpawnGround(component, project);
    require(counts.add(48).readU32() === 1, 'valid totem placement blocked');
    groundNormal = [1, 0, 0];
    callSpawnGround(component, project);
    groundNormal = [0, 0, 1]; groundHit = false;
    callSpawnGround(component, project);
    groundHit = true; groundPenetrating = true;
    callSpawnGround(component, project);
    groundPenetrating = false; placementOverlap = true;
    callSpawnGround(component, project);
    placementOverlap = false;
    require(counts.add(48).readU32() === 5, 'totem placement no longer follows the original game');
    now += 1100;
    callTick(mode);
    require(messages.length === initialMessages + 1, 'removed totem detection still announces');
    return {dugTransfers: counts.add(8).readU32() - beforeTransfers, dugPickups: counts.add(12).readU32() - beforePickups,
            dugInteractions: counts.add(20).readU32() - beforeInteracts, totemPlacements: counts.add(48).readU32(), newAnnouncements: messages.length - initialMessages};
};
rpc.exports.run = function() {
    now += 31000;
    const weapon = alloc(4096), transform = alloc(48), useState = alloc(1), hit = alloc(144);
    weapon.add(0xF0).writeU8(3); weapon.add(0x268).writePointer(pawn);
    for (const value of [0, 2, 255]) {
        useState.writeU8(value);
        require(callUse(weapon, transform, useState) === 1, 'removed shooting-state guard blocked native use');
    }
    require(counts.readU32() === 3 && counts.add(4).readU32() === 0, 'removed detector still records evidence');
    const type = alloc(16); text(type, 'Infinite Ammo');
    for (let i = 0; i < 100; i++) callRecord(state, type);
    require(messages.length === 0, 'native event announced outside Tick');
    callTick(mode);
    require(messages.length === 1 && messages[0].includes('无限弹药'), 'retained native events lost or duplicated');
    useState.writeU8(0); weapon.add(0x290).writeU8(36);
    weapon.add(0x51C).writeS32(1); weapon.add(0x8CC).writeU8(1);
    callUse(weapon, transform, useState); callHit(weapon, hit); callHit(weapon, hit);
    require(counts.add(16).readU32() === 1, 'extra arrow hit reached native recovery');
    now += 1100; callTick(mode);
    require(messages.length === 2 && messages[1].includes('刷箭'), 'arrow evidence missing');
    weapon.add(0x290).writeU8(26); weapon.add(0x8CC).writeU8(1);
    callUse(weapon, transform, useState); callHit(weapon, hit); callHit(weapon, hit);
    require(counts.add(16).readU32() === 2, 'gun hit without a spent bullet reached native');
    spendAmmo.writeU8(0); weapon.add(0x8CC).writeU8(1);
    callUse(weapon, transform, useState); callHit(weapon, hit);
    require(counts.add(16).readU32() === 2, 'free shot created a valid projectile credit');
    spendAmmo.writeU8(1);
    const spare = alloc(4096), timer = alloc(32);
    ammoPointer.writePointer(spare); spare.add(0x8B0).writeU8(3);
    weapon.add(0x898).writePointer(timer); weapon.add(0x8CC).writeU8(0);
    callReload(weapon); // 原版计时器尚未到期，仍按实际弹药扣除核对。
    callRangedReload(weapon);
    require(spare.add(0x8B0).readU8() === 2 && counts.add(40).readU32() === 1 &&
            weapon.add(0x8CC).readU8() === 1, 'normal reload lost or timer check still active');
    now += 61000; spendAmmo.writeU8(0); weapon.add(0x8CC).writeU8(0);
    callRangedReload(weapon);
    require(counts.add(40).readU32() === 1 && weapon.add(0x8CC).readU8() === 0, 'free reload filled the magazine');
    callCompleteReload(weapon);
    require(counts.add(40).readU32() === 1, 'direct completion bypassed ammo debit');
    callTick(mode);
    require(messages.length === 3 && messages[2].includes('无限弹药'), 'reload ammo evidence missing');
    return {originalShots: counts.readU32(), nativeEvidence: counts.add(4).readU32(), broadcasts: messages.length,
            legalHits: counts.add(16).readU32(), legalReloads: counts.add(40).readU32()};
};
let policyGeneration = 0;
rpc.exports.runPolicy = function(label, relay, accepted) {
    const beforeMessages = messages.length, beforeKicks = kickReasons.length;
    objectGenerations.set(state.toString(), ++policyGeneration);
    objectGenerations.set(controller.toString(), policyGeneration);
    now += 61000;
    const path = '/fixture/.gm_runtime/anti_cheat_events.json';
    if (relay) files.set(path, JSON.stringify({events:[{id:'policy-' + policyGeneration,
        player_name:'测试用户',cheat_type:label}]}));
    else { const type = alloc(16); text(type, label); callRecord(state, type); }
    require(messages.length === beforeMessages && kickReasons.length === beforeKicks, 'event punished outside Tick');
    callTick(mode); files.delete(path);
    const kicks = Number(accepted && !relay && PLUGIN_SOURCE.includes('var AutoKick = true;'));
    require(messages.length === beforeMessages + Number(accepted) && kickReasons.length === beforeKicks + kicks,
            'event whitelist mismatch: ' + label);
    return {announcements: messages.length - beforeMessages, kicks: kickReasons.length - beforeKicks};
};
"""


@unittest.skipUnless(importlib.util.find_spec("frida"), "optional frida runtime is not installed")
class RealFridaAntiCheatTests(unittest.TestCase):
    def test_native_item_additions_are_ignored_and_only_five_categories_pass(self):
        import frida

        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)'],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        session = None
        try:
            session = frida.attach(child.pid)
            for plugin in (PLUGIN, V2_PLUGIN):
                with self.subTest(plugin=plugin.name):
                    errors = []
                    script = session.create_script('const PLUGIN_SOURCE = %s;\n%s' %
                                                   (json.dumps(plugin.read_text(encoding='utf-8')), FIXTURE))
                    script.on('message', lambda message, data: errors.append(message) if message['type'] == 'error' else None)
                    try:
                        script.load()
                        self.assertEqual(script.exports_sync.run_stack_transfer(),
                                         {'transfers': 5, 'announcements': 0, 'kicks': 0})
                        retained = ('Remote Interaction', 'Remote Loot', 'Cross Map Interacts', 'Buried Loot',
                                    'Arrow Duplication', 'Infinite Ammo', 'Teleporting')
                        removed = ('Long Range Interacts', 'Item Hoovering', 'Item Duplication', 'Fast Swings',
                                   'Fast Reloads', 'Silent Gunshots', 'Chainsaw Melee', 'Long Range Melee',
                                   'Cross Map Melee', 'Invalid Totem Placement', 'Speed Hacking', 'Unknown Cheat', '')
                        for relay in (False, True):
                            for label in retained + removed:
                                with self.subTest(plugin=plugin.name, relay=relay, label=label):
                                    accepted = label in retained
                                    self.assertEqual(script.exports_sync.run_policy(label, relay, accepted),
                                                     {'announcements': int(accepted),
                                                      'kicks': int(accepted and not relay and plugin == V2_PLUGIN)})
                        self.assertEqual(errors, [])
                    finally:
                        script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)

    def test_native_trap_death_skips_unsynchronized_corpse_distance_only(self):
        import frida

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        session = None
        try:
            session = frida.attach(child.pid)
            for plugin in (PLUGIN, V2_PLUGIN):
                with self.subTest(plugin=plugin.name):
                    errors = []
                    script = session.create_script("const PLUGIN_SOURCE = %s;\n%s" %
                                                   (json.dumps(plugin.read_text(encoding="utf-8")), FIXTURE))
                    script.on("message", lambda message, data: errors.append(message) if message["type"] == "error" else None)
                    try:
                        script.load()
                        kicks = int(plugin == V2_PLUGIN)
                        self.assertEqual(script.exports_sync.run_trap_killed_corpses(),
                                         {"legalInteractions": 2, "legalTransfers": 4, "legalPickups": 2,
                                          "announcements": 1 if kicks else 2, "kicks": kicks})
                        self.assertEqual(errors, [])
                    finally:
                        script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)

    def test_native_moving_corpse_interaction_and_transfer_bounds(self):
        import frida

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        session = None
        try:
            session = frida.attach(child.pid)
            for plugin in (PLUGIN, V2_PLUGIN):
                with self.subTest(plugin=plugin.name):
                    errors, requests = [], []
                    script = session.create_script("const PLUGIN_SOURCE = %s;\n%s" %
                                                   (json.dumps(plugin.read_text(encoding="utf-8")), FIXTURE))
                    def on_message(message, data):
                        if message["type"] == "error":
                            errors.append(message)
                        elif message["type"] == "send":
                            requests.append(message["payload"])
                    script.on("message", on_message)
                    try:
                        script.load()
                        kicks = int(plugin == V2_PLUGIN)
                        self.assertEqual(script.exports_sync.run_moving_corpses(),
                                         {"legalInteractions": 4, "legalTransfers": 8,
                                          "announcements": 1 if kicks else 2, "kicks": kicks})
                        self.assertEqual(errors, [])
                        self.assertEqual(len(requests), kicks)
                        self.assertTrue(all(event["reason"] == "远程交互" for event in requests))
                    finally:
                        script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)

    def test_native_removed_totem_events_bone_dagger_and_climbing_guards(self):
        import frida

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        session = None
        try:
            session = frida.attach(child.pid)
            for plugin in (PLUGIN, V2_PLUGIN):
                with self.subTest(plugin=plugin.name):
                    errors, requests = [], []
                    script = session.create_script("const PLUGIN_SOURCE = %s;\n%s" %
                                                   (json.dumps(plugin.read_text(encoding="utf-8")), FIXTURE))
                    def on_message(message, data):
                        if message["type"] == "error":
                            errors.append(message)
                        elif message["type"] == "send":
                            requests.append(message["payload"])
                    script.on("message", on_message)
                    try:
                        script.load()
                        kicks = int(plugin == V2_PLUGIN)
                        self.assertEqual(script.exports_sync.run_removed_totem_events(),
                                         {"nativeEvents": 2, "announcements": 0, "kicks": 0})
                        self.assertEqual(requests, [])
                        self.assertEqual(script.exports_sync.run_removed_melee_events(),
                                         {"nativeEvents": 3, "announcements": 0, "kicks": 0})
                        self.assertEqual(requests, [])
                        self.assertEqual(script.exports_sync.run_bone_dagger_repeated_hits(),
                                         {"swings": 5, "damageCalls": 15, "targets": 15, "announcements": 0, "kicks": 0})
                        self.assertEqual(requests, [])
                        self.assertEqual(script.exports_sync.run_climbing(),
                                         {"legalInteractions": 5, "announcements": 1, "kicks": kicks})
                        self.assertEqual(errors, [])
                        self.assertEqual(len(requests), kicks)
                        self.assertTrue(all(event["reason"] == "远程交互" for event in requests))
                    finally:
                        script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)

    def test_v2_native_kick_and_announcement_run_only_on_tick(self):
        import frida

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        session = None
        try:
            session = frida.attach(child.pid)
            errors, requests = [], []
            script = session.create_script("const PLUGIN_SOURCE = %s;\n%s" %
                                           (json.dumps(V2_PLUGIN.read_text(encoding="utf-8")), FIXTURE))
            def on_message(message, data):
                if message["type"] == "error":
                    errors.append(message)
                elif message["type"] == "send":
                    requests.append(message["payload"])
            script.on("message", on_message)
            try:
                script.load()
                self.assertEqual(errors, [])
                self.assertEqual(script.exports_sync.run_v2(), {"kickAttempts": 5, "announcements": 3, "trustedAdds": 4})
                self.assertEqual(errors, [])
                self.assertEqual(len(requests), 5)
                self.assertTrue(all(event["user_id"] == "76561198000000000_+_|0123456789abcdef0123456789abcdef"
                                    for event in requests))
                modules = []
                for name, relative in (("native_blacklist_loader", "app/frida_loader.py"),
                                       ("native_blacklist_gm", "app/GM控制台/gm_console.py")):
                    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR.parents[1] / relative)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    modules.append(module)
                loader, gm = modules
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    for event in requests:
                        loader.on_message("[服务端]反作弊物资_v2_Linux.js", {"type": "send", "payload": event}, None, root)
                    console = gm.GMConsole(root, "test")
                    stored = console.get_blacklist()
                    self.assertEqual(stored["count"], 1)
                    self.assertEqual(stored["entries"][0]["steam_id"], "76561198000000000")
                    self.assertEqual(script.exports_sync.enforce_blacklist(console.blacklist_path.read_text(encoding="utf-8")), 6)
                    console.remove_blacklist({"user_id": stored["entries"][0]["user_id"]})
                    self.assertEqual(script.exports_sync.enforce_blacklist(console.blacklist_path.read_text(encoding="utf-8")), 6)
                self.assertEqual(errors, [])
            finally:
                script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)

    def test_native_guard_forwarding_and_direct_event_hook(self):
        import frida

        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(90)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        session = None
        try:
            session = frida.attach(child.pid)
            errors = []
            script = session.create_script("const PLUGIN_SOURCE = %s;\n%s" %
                                           (json.dumps(PLUGIN.read_text(encoding="utf-8")), FIXTURE))
            script.on("message", lambda message, data: errors.append(message) if message["type"] == "error" else None)
            try:
                script.load()
                self.assertEqual(errors, [])
                self.assertEqual(script.exports_sync.kick_attempts(), 0)
                self.assertEqual(script.exports_sync.run(), {"originalShots": 6, "nativeEvidence": 100, "broadcasts": 3,
                                                            "legalHits": 2, "legalReloads": 1})
                self.assertEqual(errors, [])
                self.assertEqual(script.exports_sync.run_world_guards(), {"dugTransfers": 1, "dugPickups": 1,
                                                                          "dugInteractions": 1, "totemPlacements": 5,
                                                                          "newAnnouncements": 1})
                self.assertEqual(errors, [])
                self.assertEqual(script.exports_sync.kick_attempts(), 0)
            finally:
                script.unload()
        finally:
            if session is not None:
                session.detach()
            child.terminate()
            child.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
