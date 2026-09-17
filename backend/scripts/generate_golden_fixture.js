#!/usr/bin/env node
/**
 * Regenerate a golden fixture for the deterministic engine by running the
 * ACTUAL logic from Renovation_Planner_v2.html under Node — no browser
 * needed, since computeSchedule/groupByTask/itemCost/materialLines/
 * suggestedOrder touch no DOM APIs. This is the ground truth the Python
 * port in src/renovator/engine is tested against (see tests/conftest.py,
 * tests/test_engine_golden.py, docs/agentic-renovator-design.md §4.4).
 *
 * Usage:
 *   node scripts/generate_golden_fixture.js --out tests/fixtures/seed_plan_golden.json
 *   node scripts/generate_golden_fixture.js --out tests/fixtures/seed_plan_variant_golden.json \
 *     --work-weekends --no-sequence-stages --fixed-start mb_tv=2026-10-05
 *
 * Re-run this whenever Renovation_Planner_v2.html's engine logic changes —
 * never hand-edit the generated JSON.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.join(__dirname, '..', '..');
const HTML_PATH = path.join(REPO_ROOT, 'Renovation_Planner_v2.html');
const INIT_MARKER = '/* ============================== INIT ============================== */';

function parseArgs(argv) {
  const out = { out: null, workWeekends: false, sequenceStages: true, fixedStarts: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--out') out.out = argv[++i];
    else if (a === '--work-weekends') out.workWeekends = true;
    else if (a === '--no-sequence-stages') out.sequenceStages = false;
    else if (a === '--fixed-start') out.fixedStarts.push(argv[++i]); // itemId=YYYY-MM-DD
    else throw new Error('Unknown arg: ' + a);
  }
  if (!out.out) throw new Error('--out <path> is required');
  return out;
}

function extractAppCode(html) {
  const scriptMatch = html.match(/<script>\s*\/\* ====+\s*\n\s*RENOVATION SELF-PLANNER[\s\S]*?<\/script>/);
  if (!scriptMatch) throw new Error('Could not find the inline app <script> block in ' + HTML_PATH);
  let code = scriptMatch[0].replace(/^<script>/, '').replace(/<\/script>$/, '');
  const initIdx = code.indexOf(INIT_MARKER);
  if (initIdx === -1) throw new Error('Could not find the INIT marker to cut before');
  return code.slice(0, initIdx);
}

function buildDriver(opts) {
  const overrideLines = [`state.workWeekends = ${opts.workWeekends};`, `state.sequenceStages = ${opts.sequenceStages};`];
  for (const spec of opts.fixedStarts) {
    const [itemId, date] = spec.split('=');
    overrideLines.push(
      `(function(){ const it = state.items.find(i => i.id === ${JSON.stringify(itemId)}); if (!it) throw new Error('No such item: ${itemId}'); it.startOverride = ${JSON.stringify(date)}; })();`
    );
  }

  return `
state = seedState();
${overrideLines.join('\n')}

function ser(d) { return d ? isoDate(d) : null; }

const sched = computeSchedule();
const scheduleOut = {};
for (const taskId in sched.map) {
  const s = sched.map[taskId];
  scheduleOut[taskId] = { start: ser(s.start), end: ser(s.end), dur: s.dur };
}
const projectEnd = ser(projectEndDate());

const tasks = groupByTask(state.items).map(t => ({
  taskId: t.taskId, room: t.room, name: t.name, category: t.category,
  phase: t.phase, stageId: t.stageId, mandatory: t.mandatory,
  durationDays: t.durationDays, isSplit: t.isSplit, totalCost: t.totalCost,
  lineIds: t.lines.map(l => l.id),
}));

const order = suggestedOrder().map(it => ({ id: it.id, room: it.room, name: it.name, lineType: it.lineType }));

const items = state.items;
const total = grandTotal(items);
const mandatory = grandTotal(items.filter(i => i.mandatory));
const optional = grandTotal(items.filter(i => !i.mandatory));
const materials = grandTotal(items.filter(i => i.lineType === 'Material'));
const byRoom = groupSums(items, i => i.room);
const byTradeBucketed = groupSums(items, i => tradeBucket(i.workerType || i.category).name);
const byPhase = groupSums(items, i => (getPhase(i.phase) || {}).label || 'Unassigned');
const byTradeRaw = groupSums(items, i => i.workerType || '—');

const estimate = { total, mandatory, optional, materials, byRoom, byTradeBucketed, byTradeRaw, byPhase };

const matLines = materialLines().map(r => ({
  lineId: r.line.id, needBy: ser(r.needBy), qty: r.qty, unit: r.unit, cost: r.cost, buyStatus: r.line.buyStatus,
}));
const matTotal = matLines.reduce((s, r) => s + r.cost, 0);
const toBuy = matLines.filter(r => r.buyStatus === 'To buy');
const toBuyCost = toBuy.reduce((s, r) => s + r.cost, 0);
const ordered = matLines.filter(r => r.buyStatus === 'Ordered').length;
const delivered = matLines.filter(r => r.buyStatus === 'Delivered').length;
const materialsPlan = { lines: matLines, total: matTotal, toBuyCost, toBuyCount: toBuy.length, ordered, delivered };

const planSnapshot = {
  settings: { projectStart: state.projectStart, workWeekends: state.workWeekends, sequenceStages: state.sequenceStages },
  rooms: state.rooms,
  rates: state.rates,
  phases: state.phases,
  stages: state.stages,
  items: state.items.map(it => ({
    id: it.id, taskId: it.taskId, room: it.room, name: it.name, category: it.category,
    lineType: it.lineType, workerType: it.workerType, phase: it.phase, stageId: it.stageId,
    mandatory: it.mandatory, durationDays: it.durationDays, startOverride: it.startOverride,
    dependsOn: it.dependsOn, costMethod: it.costMethod, rateKey: it.rateKey, qty: it.qty,
    customAmount: it.customAmount, buyStatus: it.buyStatus, status: it.status, notes: it.notes,
    actualCost: it.actualCost,
  })),
};

globalThis.__FIXTURE__ = JSON.stringify({
  plan: planSnapshot,
  tasks,
  schedule: { projectStart: ser(sched.projStart), projectEnd, tasks: scheduleOut },
  suggestedOrder: order,
  estimate,
  materialsPlan,
}, null, 2);
`;
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const appCode = extractAppCode(html);
  const driver = buildDriver(opts);

  // Minimal DOM stubs so the extracted app logic loads without a browser.
  global.window = { storage: undefined };
  global.document = {
    getElementById: () => null,
    addEventListener: () => {},
    removeEventListener: () => {},
    activeElement: null,
    querySelectorAll: () => [],
    documentElement: {},
  };
  global.localStorage = undefined;
  global.alert = (msg) => { throw new Error('alert() called: ' + msg); };
  global.confirm = () => true;
  global.prompt = () => null;

  // eslint-disable-next-line no-eval
  eval(appCode + '\n' + driver);

  const outPath = path.isAbsolute(opts.out) ? opts.out : path.join(process.cwd(), opts.out);
  fs.writeFileSync(outPath, globalThis.__FIXTURE__);
  console.log('Wrote ' + outPath);
}

main();
