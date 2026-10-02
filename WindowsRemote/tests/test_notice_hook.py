from pathlib import Path
import subprocess
import unittest


class NativeNoticeHookTests(unittest.TestCase):
    def test_delivers_once_on_the_current_controller_tick_and_returns_receipt(self):
        hook = Path(__file__).resolve().parents[1] / "app" / "quick_join_announce_hook.js"
        harness = r"""
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const files = {}, calls = [], messages = [];
let poll, callbacks, tickAddress;
class Pointer {
  constructor(value = 1) { this.value = value; }
  add(offset) { return new Pointer(this.value + offset); }
  isNull() { return this.value === 0; }
  readPointer() { return new Pointer(5); }
  writePointer(value) { this.source = value; }
  writeU32() {}
  writeUtf16String(text) { this.text = text; }
}
function NativeFunction(address) {
  return address.value === 0x110DC60 ? (output, input) => {output.text = input.source.text;} :
    (controller, text) => {calls.push({controller, text: text.text, object: text}); messages.unshift(text.text);};
}
class File {
  constructor(path, mode) {this.path = path; if (mode === 'w') files[path] = '';}
  readText() {if (!(this.path in files)) throw Error('missing'); return files[this.path];}
  write(text) {files[this.path] += text;}
  flush() {}
  close() {}
}
const context = {
  Process: {findModuleByName: () => ({base: new Pointer(0), path: 'C:\\Game\\client.exe'}),
    findRangeByAddress: () => ({protection: 'r-x'})},
  NativeFunction, File, ptr: value => new Pointer(value), Memory: {alloc: () => new Pointer()},
  Interceptor: {attach: (address, handler) => {tickAddress = address.value; callbacks = handler;}},
  setInterval: fn => {poll = fn;}
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
assert.equal(tickAddress, 0xECA910);
const trigger = 'C:\\Game\\quick_join_announce.json';
const receipt = 'C:\\Game\\quick_join_announce_result.json';
files[trigger] = JSON.stringify({id: 'new', text: '原生公告\n第二行', expires_at: Date.now() + 1000});
poll(); assert.equal(calls.length, 0);
const frame = {}, controller = new Pointer(100);
callbacks.onEnter.call(frame, [controller]); callbacks.onLeave.call(frame);
assert.equal(calls.length, 2); assert.equal(calls[0].controller, controller);
assert.equal(calls[1].controller, controller);
assert.deepEqual(calls.map(call => call.text), ['第二行', '原生公告']);
assert.deepEqual(messages, ['原生公告', '第二行']);
assert.notEqual(calls[0].object, calls[1].object);
assert.equal(JSON.parse(files[receipt]).id, 'new'); assert.equal(JSON.parse(files[receipt]).success, true);
callbacks.onLeave.call(frame); poll(); assert.equal(calls.length, 2);
files[trigger] = JSON.stringify({id: 'line-endings', text: '第一行\r\n\r\n  \n第二行\r第三行', expires_at: Date.now() + 1000});
poll(); callbacks.onLeave.call(frame);
assert.deepEqual(calls.slice(2).map(call => call.text), ['第三行', '第二行', '第一行']);
assert.deepEqual(messages.slice(0, 3), ['第一行', '第二行', '第三行']);
assert.equal(new Set(calls.map(call => call.object)).size, 5);
files[trigger] = JSON.stringify({id: 'system-and-max-announcement', text: '检测提示\n' + '告'.repeat(500), expires_at: Date.now() + 1000});
poll(); callbacks.onLeave.call(frame);
assert.equal(calls.length, 7);
assert.deepEqual(messages.slice(0, 2), ['检测提示', '告'.repeat(500)]);
files[trigger] = JSON.stringify({id: 'expired', text: '过期公告', expires_at: 1});
poll(); callbacks.onLeave.call(frame); assert.equal(calls.length, 7);
assert.equal(JSON.parse(files[receipt]).success, false);
"""
        subprocess.run(["node", "-e", harness, str(hook)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
