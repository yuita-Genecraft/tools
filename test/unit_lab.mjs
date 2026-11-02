import { test } from 'node:test';
import assert from 'node:assert/strict';
import { L, parser, numericLine } from '../cc-seizon/parser-node.mjs';
const pivot = Date.UTC(2026, 9, 19), D = L.DAY;
const row = (sid, ts, cr, more = {}) => ({ sid, ts, tool: 'claude', project: 'p1', model: 'model-a', side: false, inp: 0, out: 0, cr, cw: 0, cw1h: 0, ...more });
const fixture = () => ({ parser: L.PARSER, sample: false, collectedAt: new Date(pivot + 30 * D).toISOString(),
  coverage: { files: 2, lines: 8, badLines: 0, noTime: 0, noUsage: 0 },
  sessions: [{ id: 's1', firstSeen: pivot - 20 * D }, { id: 's2', firstSeen: pivot }, { id: 's3', firstSeen: null }],
  rows: [row('s1', pivot - 7 * D, 400000), row('s1', pivot - 1, 600000), row('s1', pivot, 500000), row('s2', pivot + 1, 100000), row('s3', pivot + 2, 0), row('s2', pivot + 7 * D, 100000)], compactions: [{ sid: 's1', ts: pivot }] });
const opts = { pivot, days: 7 };
test('matched windows, strict heavy threshold, weighted denominator and cohorts by pre-window history', () => {
  const a = L.analyze(fixture(), opts);
  assert.equal(a.before.n, 2); assert.equal(a.after.n, 3); assert.equal(a.coverage.outsideWindow, 1);
  assert.equal(a.before.heavyN, 1); assert.equal(a.before.heavyShare, .6);
  assert.equal(a.after.heavyShare, .833333); assert.equal(a.deltaPoints, 23.3333);
  assert.equal(a.ongoing.n, 1); assert.equal(a.fresh.n, 1); assert.equal(a.unknown.n, 1);
  assert.equal(a.daily.reduce((s, x) => s + x.n, 0), 5); assert.equal(a.daily[7].compactions, 1);
});
test('empty group and zero-weight group are unknown, never an apparent 0% improvement', () => {
  const d = fixture(); d.rows = [row('s2', pivot, 0)]; const a = L.analyze(d, opts);
  assert.equal(a.before.heavyShare, null); assert.equal(a.after.heavyShare, null); assert.equal(a.deltaPoints, null);
  assert.equal(a.before.p50, null); assert.equal(a.after.p50, 0);
});
test('same scope on both sides and optional sidechain exclusion', () => {
  const d = fixture(); d.rows[2].side = true; d.rows[3].tool = 'codex';
  const a = L.analyze(d, { ...opts, tool: 'claude', model: 'model-a', project: 'p1' });
  assert.equal(a.after.n, 1); assert.equal(a.coverage.outsideScope, 2);
  assert.equal(L.analyze(d, { ...opts, includeSide: true }).after.n, 3);
});
test('composition shifts, unknown model/project and incomplete windows remain warnings', () => {
  const d = fixture(); d.rows[2].model = ''; d.rows[2].project = ''; d.collectedAt = new Date(pivot + D).toISOString();
  const a = L.analyze(d, opts);
  assert.equal(a.mixShift, true); assert.ok(a.warnings.some(w => w.includes('モデル不明')));
  assert.ok(a.warnings.some(w => w.includes('作業フォルダ不明'))); assert.ok(a.warnings.some(w => w.includes('まだ終わって')));
});
test('weighted quantity includes one-hour cache correctly', () => {
  assert.equal(L.weight(row('s1', pivot, 20, { inp: 10, out: 3, cw: 12, cw1h: 4 })), 45);
});
test('snapshot roundtrip preserves exact filters/results and flags demo', async () => {
  for (const d of [fixture(), L.demo()]) {
    const snap = await L.snapshot(d, opts), loaded = await L.restore(JSON.parse(JSON.stringify(snap)));
    assert.deepEqual(L.analyze(loaded.data, loaded.options), L.analyze(d, opts)); assert.equal(loaded.data.sample, d.sample);
    assert.equal(snap.sha256, (await L.snapshot(d, opts)).sha256);
    assert.notEqual(snap.sha256, (await L.snapshot(d, { ...opts, includeSide: true })).sha256);
  }
});
test('modified data and unsupported schemas fail closed', async () => {
  const doc = await L.snapshot(fixture(), opts); doc.data.rows[0].cr++;
  await assert.rejects(L.restore(doc), /一致/);
  await assert.rejects(L.restore({ ...doc, schema: 'newer' }), /版/);
});
test('bad numeric values, unsafe labels, unexpected fields and missing sessions rejected', () => {
  for (const mutate of [d => d.rows[0].cr = -1, d => d.rows[0].cr = Infinity, d => d.rows[0].cw1h = 2, d => d.rows[0].sid = 'missing', d => d.rows[0].prompt = 'secret', d => d.rows[0].model = '<img src=x>', d => d.sessions.push(d.sessions[0])]) {
    const d = fixture(); mutate(d); assert.throws(() => L.validate(d));
  }
});
test('parsing removes original paths, prompts and ids from the numeric snapshot, deduplicates response blocks', async () => {
  const acc = parser.newLogAcc(); acc.cur = parser.newFileState('private-log.jsonl');
  const base = { type: 'assistant', sessionId: 'private-session', cwd: '/Users/private/project', timestamp: new Date(pivot).toISOString(),
    message: { id: 'private-id', model: 'claude-test', content: [{ type: 'text', text: 'PRIVATE_TEXT' }], usage: { input_tokens: 2, output_tokens: 3, cache_read_input_tokens: 400000 } } };
  parser.handleLogLine(JSON.stringify({ ...base, uuid: 'u1' }), acc);
  parser.handleLogLine(JSON.stringify({ ...base, uuid: 'u2' }), acc);
  parser.handleLogLine(JSON.stringify({ type: 'system', subtype: 'compact_boundary', sessionId: 'private-session', timestamp: new Date(pivot + 1).toISOString(), uuid: 'c1' }), acc);
  const { data } = parser.labDatasetFromAcc(acc);
  assert.equal(data.rows.length, 1); assert.equal(data.rows[0].model, 'claude-test'); assert.equal(data.compactions.length, 1);
  const text = JSON.stringify(await L.snapshot(data, opts));
  for (const forbidden of ['private-session','private-id','/Users/','PRIVATE_TEXT','private-log']) assert.ok(!text.includes(forbidden));
});
test('content-stripped CLI parser agrees with original page parser for metadata and counts', () => {
  const a = parser.newLogAcc(), b = parser.newLogAcc(); a.cur = parser.newFileState('x'); b.cur = parser.newFileState('x');
  const records = [
    { type: 'session_meta', timestamp: new Date(pivot - D).toISOString(), payload: { id: 'cx', cwd: '/repo' } },
    { type: 'turn_context', timestamp: new Date(pivot).toISOString(), payload: { model: 'codex-test', cwd: '/repo' } },
    { type: 'token_usage_record', timestamp: new Date(pivot + 1).toISOString(), payload: { response_id: 'r1', usage: { input_tokens: 500, cached_input_tokens: 400, output_tokens: 20 } } },
  ];
  for (const r of records) { const s = JSON.stringify(r); parser.handleLogLine(s, a); parser.handleLogLine(numericLine(s), b); }
  const at = '2026-11-02T00:00:00Z';
  assert.equal(JSON.stringify(parser.labDatasetFromAcc(a, at).data), JSON.stringify(parser.labDatasetFromAcc(b, at).data));
  assert.equal(parser.labDatasetFromAcc(b).data.rows[0].inp, 100);
});
test('analysis does not mutate inputs', () => {
  const data = fixture(), before = L.stable(data); L.analyze(data, opts); assert.equal(L.stable(data), before);
});

test('Antigravity missing usage is excluded and disclosed, measured zero retained', () => {
 const acc=parser.newLogAcc(); acc.cur=parser.newFileState('/logs/conversations/abc/steps.jsonl');
 for (const [step_index,usage] of [[1,{}],[2,{input_tokens:0,output_tokens:0}]]) parser.handleLogLine(JSON.stringify({type:'PLANNER_RESPONSE',step_index,created_at:'2026-10-19T01:00:00Z',...usage}),acc);
 parser.finalizeGemini(acc); const {data}=parser.labDatasetFromAcc(acc);
 assert.equal(data.coverage.noUsage,1); assert.equal(data.rows.length,1); assert.equal(data.rows[0].inp,0);
});
