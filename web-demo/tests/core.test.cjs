// 日期：2026-10-24；状态：网页示例计算与边界回归。
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const match = html.match(/<script id="el-core">([\s\S]*?)<\/script>/);
assert.ok(match, 'HTML 应包含共享计算内核');
const context = vm.createContext({});
vm.runInContext(match[1], context);
const core = context.ELDemo;
const plain = value => JSON.parse(JSON.stringify(value));
const opts = { powers:{ lamp:5, sign:1 }, threshold:172 };

test('办公示例：按实际连接得到四回路、19 设备、63 W', () => {
  const result = core.analyze(core.makeScene('office'), opts);
  assert.equal(result.circuits.length, 4);
  assert.equal(result.deviceCount, 19);
  assert.equal(result.totalKnownWatts, 63);
  assert.deepEqual(plain(result.circuits.map(c => c.watts)), [21, 12, 17, 13]);
  assert.equal(result.warningCount, 0);
});
test('教学示例：三回路、17 设备、61 W', () => {
  const result = core.analyze(core.makeScene('school'), opts);
  assert.equal(result.circuits.length, 3);
  assert.equal(result.deviceCount, 17);
  assert.equal(result.totalKnownWatts, 61);
  assert.deepEqual(plain(result.circuits.map(c => c.watts)), [26, 13, 22]);
});
test('功率修改按数量重算，空功率保持未知', () => {
  const scene = core.makeScene('office');
  assert.equal(core.analyze(scene, { powers:{ lamp:8, sign:1 } }).totalKnownWatts, 96);
  const result = core.analyze(scene, { powers:{ lamp:null, sign:1 } });
  assert.equal(result.totalKnownWatts, 8);
  assert.equal(result.unknownCount, 11);
  assert.ok(result.circuits.every(c => c.watts === null));
  assert.equal(result.warningCount, 4);
  assert.ok(core.diagramSvg(scene, result).includes('功率待核对'));
});
test('断线只排除不可达末端，恢复连接还原结果，原始数据不变', () => {
  const scene = core.makeScene('office'), before = JSON.stringify(scene);
  const result = core.analyze(scene, { ...opts, brokenRoutes:['route-1'] });
  assert.equal(result.deviceCount, 18);
  assert.equal(result.totalKnownWatts, 62);
  assert.equal(result.circuits[0].watts, 20);
  assert.equal(result.circuits[0].count, 4);
  assert.equal(JSON.stringify(scene), before);
  assert.equal(core.analyze(scene, opts).deviceCount, 19);
});
test('导线中段交叉不合并，真实 T 接点可连通', () => {
  const scene = { seeds:[{ id:'a', label:'ZE1', point:[0,0] }], breakLinks:{},
    wires:[{ id:'a', a:[0,0], b:[100,0] },{ id:'b', a:[50,-50], b:[50,50] }],
    devices:[{ id:'remote', type:'lamp', bounds:[48,38,52,42] }] };
  assert.equal(core.analyze(scene, opts).deviceCount, 0);
  scene.wires[1].a = [50,0];
  assert.equal(core.analyze(scene, opts).deviceCount, 1);
});
test('设备按真实矩形接触判定，不纳入只是靠近的设备', () => {
  const wire = { a:[0,0], b:[100,0] };
  assert.equal(core.wireTouchesDevice(wire, { bounds:[40,-2,44,2] }), true);
  assert.equal(core.wireTouchesDevice(wire, { bounds:[40,1,44,3] }), false);
  assert.equal(core.wireTouchesDevice({ a:[41,0], b:[42,0] }, { bounds:[40,-2,44,2] }), true);
});
test('多回路共享设备保留冲突，汇总去重', () => {
  const scene = { seeds:[{ id:'a', label:'A', point:[0,0] },{ id:'b', label:'B', point:[100,0] }], breakLinks:{},
    wires:[{ id:'w', a:[0,0], b:[100,0] }], devices:[{ id:'d', type:'lamp', bounds:[45,-2,55,2] }] };
  const result = core.analyze(scene, opts);
  assert.equal(result.deviceCount, 1);
  assert.equal(result.totalKnownWatts, 5);
  assert.ok(result.circuits.every(c => c.issues.includes('SHARED_DEVICE') && c.issues.includes('SHARED_WIRE')));
});
test('提醒阈值和缺失、重复编号保留核对状态', () => {
  const scene = core.makeScene('office');
  const threshold = core.analyze(scene, { ...opts, threshold:20 });
  assert.ok(threshold.circuits[0].issues.includes('OVER_LIMIT'));
  assert.ok(!threshold.circuits[2].issues.includes('OVER_LIMIT'));
  const labels = core.analyze(scene, { ...opts, labels:{ 'route-1':'X', 'route-2':'X', 'route-3':'' } });
  assert.ok(labels.circuits[0].issues.includes('LABEL_CONFLICT'));
  assert.ok(labels.circuits[1].issues.includes('LABEL_CONFLICT'));
  assert.ok(labels.circuits[2].issues.includes('LABEL_MISSING'));
});
test('导出保留用户编号并转义 SVG 与 CSV 公式', () => {
  const scene = core.makeScene('office');
  const result = core.analyze(scene, { ...opts, labels:{ 'route-1':'<照明&1>', 'route-2':'=1+1' } });
  const svg = core.diagramSvg(scene, result);
  assert.ok(svg.includes('&lt;照明&amp;1&gt;'));
  assert.ok(!svg.includes('<照明&1>'));
  assert.ok(svg.includes('63 W'));
  const csv = core.resultCsv(scene, result);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes("\"'=1+1\""));
});
test('全部断线保持可达设备，边界功率不被悄悄转为 0', () => {
  const result = core.analyze(core.makeScene('office'), { ...opts, brokenRoutes:['route-1','route-2','route-3','route-4'] });
  assert.equal(result.deviceCount, 15);
  assert.equal(result.totalKnownWatts, 59);
  assert.equal(core.validPower(''), null);
  assert.equal(core.validPower(-1), null);
  assert.equal(core.validPower(1.2), null);
  assert.equal(core.validPower(0), 0);
});
