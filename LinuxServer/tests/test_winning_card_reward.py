import json
import subprocess
import unittest
from pathlib import Path


LINUX_SERVER_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = LINUX_SERVER_ROOT / "Linux 插件" / "[服务端]赢牌对家开船_Linux.js"


NODE_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const source = input.source;
const config = input.config;
const memory = new Map();
const strings = new Map();
const textValues = new Map();
const hooks = new Map();
const intervals = new Map();
const timeouts = [];
const storageLimits = [];
const inventoryAdds = [];
const messages = [];
let nextAllocation = 0x900000;
let matchStarted = false;

class Pointer {
  constructor(value) { this.value = Number(value); }
  add(offset) { return new Pointer(this.value + offset); }
  isNull() { return this.value === 0; }
  equals(other) { return this.value === other.value; }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  writePointer(value) { memory.set(this.value, value.value); }
  readU32() { return memory.get(this.value) || 0; }
  writeU32(value) { memory.set(this.value, value >>> 0); }
  readS32() { return memory.get(this.value) || 0; }
  writeS32(value) { memory.set(this.value, value); }
  readU8() { return memory.get(this.value) || 0; }
  writeU8(value) { memory.set(this.value, value); }
  readFloat() { return memory.get(this.value) || 0; }
  writeFloat(value) { memory.set(this.value, value); }
  writeUtf16String(value) { strings.set(this.value, value); }
  readUtf16String() { return strings.get(this.value) || ''; }
}

global.ptr = value => new Pointer(typeof value === 'string' ? Number(BigInt(value)) : value);
global.Memory = {
  alloc: size => {
    const result = new Pointer(nextAllocation);
    nextAllocation += Math.max(size, 16) + 16;
    return result;
  }
};
global.Process = {
  pointerSize: 8,
  findModuleByName: () => ({ base: new Pointer(0x200000) })
};
global.Interceptor = { attach: (address, callbacks) => hooks.set(address.value, callbacks) };
global.setInterval = (callback, delay) => intervals.set(delay, callback);
global.setTimeout = (callback, delay) => { timeouts.push({ callback, delay }); return timeouts.length; };
global.File = { readAllText: () => JSON.stringify(config) };
global.DH_LINUX_ROOT = '/srv/dh';
global.send = () => {};
Math.random = () => 0.9;

const world = new Pointer(0x700000);
const gameMode = new Pointer(0x710000);
const gameState = new Pointer(0x720000);
const playerData = new Pointer(0x730000);
const playerState1 = new Pointer(0x740000);
const playerState2 = new Pointer(0x741000);
const roleInfo1 = new Pointer(0x742000);
const gameplayController1 = new Pointer(0x750000);
const gameplayController2 = new Pointer(0x751000);
const gameplayPawn1 = new Pointer(0x760000);
const gameplayPawn2 = new Pointer(0x761000);
const inventory1 = new Pointer(0x770000);
const inventory2 = new Pointer(0x771000);
const lobbyController1 = new Pointer(0x780000);
const lobbyController2 = new Pointer(0x781000);
const lobbyPawn1 = new Pointer(0x790000);
const lobbyPawn2 = new Pointer(0x791000);
const lobbyRoot1 = new Pointer(0x7A0000);
const lobbyRoot2 = new Pointer(0x7A1000);
const dealer = new Pointer(0x7B0000);
const dealerPlayers = new Pointer(0x7B1000);
const itemClass = new Pointer(0x7C0000);

memory.set(0x5E9B6D0, world.value);
memory.set(world.value + 0x118, gameMode.value);
memory.set(gameMode.value + 0x280, gameState.value);
memory.set(gameState.value + 0x238, playerData.value);
memory.set(gameState.value + 0x240, 2);
memory.set(playerData.value, playerState1.value);
memory.set(playerData.value + 8, playerState2.value);
memory.set(gameplayController1.value + 0x250, gameplayPawn1.value);
memory.set(gameplayController2.value + 0x250, gameplayPawn2.value);
memory.set(gameplayPawn1.value + 0x808, inventory1.value);
memory.set(gameplayPawn2.value + 0x808, inventory2.value);

memory.set(lobbyPawn1.value + 0x258, lobbyController1.value);
memory.set(lobbyPawn2.value + 0x258, lobbyController2.value);
memory.set(lobbyController1.value + 0x228, playerState1.value);
memory.set(lobbyController2.value + 0x228, playerState2.value);
memory.set(lobbyPawn1.value + 0x130, lobbyRoot1.value);
memory.set(lobbyPawn2.value + 0x130, lobbyRoot2.value);
memory.set(lobbyRoot1.value + 0x1D0, -100);
memory.set(lobbyRoot1.value + 0x1D4, 0);
memory.set(lobbyRoot2.value + 0x1D0, 100);
memory.set(lobbyRoot2.value + 0x1D4, 0);
memory.set(dealer.value + 0x330, dealerPlayers.value);
memory.set(dealer.value + 0x338, 2);
memory.set(dealerPlayers.value, lobbyPawn1.value);
memory.set(dealerPlayers.value + 8, lobbyPawn2.value);
memory.set(dealer.value + 0x468, lobbyPawn1.value);

function writeFString(output, value) {
  const data = Memory.alloc((value.length + 1) * 2);
  data.writeUtf16String(value);
  output.writePointer(data);
  output.add(8).writeU32(value.length);
}

memory.set(playerState1.value + 0x588, roleInfo1.value);
writeFString(roleInfo1.add(0x48), 'Captain');

global.NativeFunction = function(address) {
  const offset = address.value - 0x200000;
  switch (offset) {
    case 0x2B130F0:
      return (output, buffer) => textValues.set(output.value, strings.get(buffer.value) || '');
    case 0x2A13190:
      return (output, fname) => textValues.set(output.value, textValues.get(fname.value) || '');
    case 0x433C920:
      return ps => ps.equals(playerState1) ? gameplayController1 : gameplayController2;
    case 0x433F490:
      return () => {};
    case 0x282B4B0:
    case 0x282B610:
      return (controller, message) => messages.push([controller.value, textValues.get(message.value) || '']);
    case 0x2C95CA0:
    case 0x2C97F00:
      return () => itemClass;
    case 0x2B9C070:
      return () => new Pointer(0x7D0000);
    case 0x459E030:
      return (output, ps) => writeFString(output, ps.equals(playerState1) ? '赢家甲' : '玩家乙');
    case 0x277E4F0:
      return ps => ps.equals(playerState1) ? gameplayController1 : gameplayController2;
    case 0x26C6160:
      return () => matchStarted ? 1 : 0;
    case 0x270CC90:
      return (inventory, limit) => storageLimits.push([inventory.value, limit]);
    case 0x270CA50:
      return (inventory, clazz, states, output) => {
        const quantity = states.add(8).readU32();
        inventoryAdds.push([inventory.value, clazz.value, quantity]);
        output.writeS32(quantity);
      };
    default:
      throw new Error('unexpected native offset 0x' + offset.toString(16));
  }
};

eval(source);
const showdown = hooks.get(0x292E980);
if (!showdown) throw new Error('showdown hook missing');
showdown.onEnter([dealer]);
showdown.onLeave(new Pointer(0));
if (!dealer.add(0x468).readPointer().equals(lobbyPawn2)) throw new Error('opponent did not receive ship control');

matchStarted = true;
const poll = intervals.get(1000);
if (!poll) throw new Error('reward match poll missing');
poll();
const rewardTimer = timeouts.find(timer => timer.delay === 5000);
if (!rewardTimer) throw new Error('configured reward delay was not scheduled');
rewardTimer.callback();

const expectedInventory = inventory1.value;
if (storageLimits.length !== 1 || storageLimits[0][0] !== expectedInventory || storageLimits[0][1] !== 12) {
  throw new Error('backpack reward target or size is wrong');
}
if (!inventoryAdds.every(entry => entry[0] === expectedInventory)) {
  throw new Error('a non-winning player received the reward');
}
if (config.mode === 'fixed' && (inventoryAdds.length !== 2 || inventoryAdds[0][2] !== 3 || inventoryAdds[1][2] !== 1)) {
  throw new Error('fixed reward did not grant every configured item');
}
if (config.mode === 'random' && (inventoryAdds.length !== 1 || inventoryAdds[0][2] !== 1)) {
  throw new Error('random reward did not grant exactly one configured item');
}
const expectedReward = config.mode === 'fixed' ? '煤炭 x3' : '燧发手枪 x1';
if (!messages.some(entry => entry[1].includes('船长') && entry[1].includes(expectedReward))) {
  throw new Error('editable announcement did not use the winning profession');
}
if (messages.some(entry => entry[1].includes('赢家甲') && entry[1].includes(expectedReward))) {
  throw new Error('editable announcement still used the winning username');
}
"""


class WinningCardRewardTests(unittest.TestCase):
    def test_winner_receives_fixed_or_random_configured_reward(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        for mode in ("fixed", "random"):
            config = {
                "enabled": True,
                "mode": mode,
                "delay_seconds": 5,
                "backpack_slots": 12,
                "items": [
                    {
                        "item": "coal",
                        "item_name": "煤炭",
                        "item_class": "/Game/Blueprints/Inventory/Coal/BP_Coal_Inventory.BP_Coal_Inventory_C",
                        "quantity": 3,
                    },
                    {
                        "item": "flintlock",
                        "item_name": "燧发手枪",
                        "item_class": "/Game/Blueprints/Inventory/Flintlock/BP_Flintlock_Inventory.BP_Flintlock_Inventory_C",
                        "quantity": 1,
                    },
                ],
                "announcement": "[牌局奖励] {player} 获得：{rewards}",
            }
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["node", "-e", NODE_HARNESS],
                    input=json.dumps({"source": source, "config": config}, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
