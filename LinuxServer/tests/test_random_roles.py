import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RANDOM_PLUGIN = "[服务端]随机职业Plus_Linux.js"
FIXED_PLUGIN = "[服务端]固定职业_Linux.js"

NODE_CHECK = r"""
const assert = require('node:assert/strict');
const {source, handleAddress} = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const memory = new Map(), hooks = new Map(), players = [];
const moduleBase = 0x200000;
class Pointer {
  constructor(value) { this.value = Number(value); }
  add(offset) { return new Pointer(this.value + offset); }
  isNull() { return this.value === 0; }
  toString() { return String(this.value); }
  readPointer() { return new Pointer(memory.get(this.value) || 0); }
  readU8() { return memory.get(this.value) || 0; }
}
global.ptr = value => new Pointer(value);
global.DH_LINUX_ROOT = '/server';
global.Process = {
  findModuleByName: () => ({base: ptr(moduleBase)}),
  findRangeByAddress: () => ({protection: 'rw-'})
};
global.Interceptor = {attach: (address, callbacks) => hooks.set(address.value - moduleBase, callbacks)};
global.File = {readAllText: () => JSON.stringify({
  expires_at: Date.now() + 600000, roles: [{user_id: 'fixed-player', role: 8}]
})};
global.send = () => {};
Math.random = () => 0;
memory.set(moduleBase + 0x5C9B6D0, 0x900000);
for (let role = 1; role <= 8; role++) memory.set(0x500000 + role * 0x1000 + 0x58, role);
global.NativeFunction = function(address) {
  switch (address.value - moduleBase) {
    case 0x275CEE0: return role => ptr(0x500000 + role * 0x1000);
    case 0x27C8750: return (context, role, excluded) => Number(players.some(
      p => p.value !== excluded.value && p.add(0x588).readPointer().value === role.value
    ));
    case 0x2772770: return (player, role) => {
      const args = [player, role];
      hooks.get(0x2772770).onEnter(args);
      memory.set(player.value + 0x588, args[1].value);
    };
    default: throw new Error('Unexpected native address');
  }
};
eval(source);
const assigned = [];
for (let i = 0; i < 8; i++) {
  const controller = ptr(0x600000 + i * 0x1000), player = ptr(0x700000 + i * 0x1000);
  players.push(player);
  memory.set(controller.value + 0x228, player.value);
  // Each native entry checks SelectedRole before opening the selection screen.
  hooks.get(handleAddress)?.onEnter([ptr(0x800000), controller]);
  const role = player.add(0x588).readPointer();
  assert(!role.isNull(), 'Player must have a role before the native entry opens selection');
  assigned.push(role.add(0x58).readU8());
  const request = [player, ptr(0x508000)];
  hooks.get(0x2772770).onEnter(request);
  assert.equal(request[1].value, role.value, 'Client selection must keep the assigned role');
}
assert.equal(new Set(assigned).size, 8, 'Random roles must remain unique');
assert.notEqual(assigned[0], 8, 'Uploaded fixed role must not override random mode');
"""


class RandomRoleTests(unittest.TestCase):
    def test_random_assigns_and_locks_unique_roles_despite_fixed_upload(self):
        for root in (ROOT, ROOT / "Docker"):
            source = (root / "Linux 插件" / RANDOM_PLUGIN).read_text(encoding="utf-8")
            for handle_address in (0x2723F40, 0x26CB970):
                with self.subTest(root=root.name, handle_address=hex(handle_address)):
                    result = subprocess.run(
                        ["node", "-e", NODE_CHECK],
                        input=json.dumps({"source": source, "handleAddress": handle_address}),
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_loader_prefers_random_and_keeps_fixed_when_random_disabled(self):
        for root in (ROOT, ROOT / "Docker"):
            spec = importlib.util.spec_from_file_location("role_loader", root / "frida_loader.py")
            loader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(loader)
            for random_enabled in (True, False):
                with self.subTest(root=root.name, random_enabled=random_enabled), tempfile.TemporaryDirectory() as folder:
                    install = Path(folder)
                    plugins = install / "Linux 插件"
                    plugins.mkdir()
                    (plugins / FIXED_PLUGIN).write_text("send('fixed');", encoding="utf-8")
                    random_name = RANDOM_PLUGIN if random_enabled else RANDOM_PLUGIN + ".disabled"
                    (plugins / random_name).write_text("send('random');", encoding="utf-8")
                    sources = []
                    script = SimpleNamespace(on=lambda *args: None, load=lambda: None, unload=lambda: None)
                    session = SimpleNamespace(
                        create_script=lambda source: (sources.append(source), script)[1], detach=lambda: None,
                    )
                    with mock.patch.dict(sys.modules, {"frida": SimpleNamespace(attach=lambda pid: session)}), mock.patch.object(
                        loader, "find_server_pid", side_effect=[123, 123, None]
                    ), mock.patch.object(loader, "wait_for_server_ready"), mock.patch.object(
                        loader, "capture_log_offsets", return_value={}
                    ), mock.patch.object(loader, "log"):
                        loader.load_plugins(install, plugins)
                    self.assertEqual(len(sources), 1)
                    self.assertIn("send('random');" if random_enabled else "send('fixed');", sources[0])


if __name__ == "__main__":
    unittest.main()
