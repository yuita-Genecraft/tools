/* Shared, deterministic analytics. No DOM, network, storage, or model calls. */
(function (root) {
  'use strict';
  const VERSION = 'logmap-change-lab/2';
  const PARSER = 'cc-seizon/2026-11-02.1';
  const DAY = 86400000;
  const WEIGHTS = Object.freeze({ input: 1, output: 5, read: 0.1, write5m: 1.25, write1h: 2 });
  const context = r => r.inp + r.cr + r.cw;
  const weight = r => r.inp + r.out * 5 + r.cr * 0.1 + (r.cw - r.cw1h) * 1.25 + r.cw1h * 2;
  const sorted = xs => [...xs].sort();
  const mean = (a, n) => n ? a / n : null;
  const quantile = (xs, q) => xs.length ? xs[Math.max(0, Math.ceil(xs.length * q) - 1)] : null;
  const round = x => x === null ? null : Math.round(x * 1e6) / 1e6;
  function summarize(rows) {
    const cs = rows.map(context).sort((a, b) => a - b);
    let w = 0, heavyW = 0, heavyN = 0, tokens = 0;
    const sessions = new Set(), strata = new Map();
    for (const r of rows) {
      const v = weight(r); w += v; tokens += context(r) + r.out; sessions.add(r.sid);
      if (context(r) > 400000) { heavyW += v; heavyN++; }
      const key = JSON.stringify([r.tool, r.project, r.model]);
      strata.set(key, (strata.get(key) || 0) + 1);
    }
    return { n: rows.length, sessions: sessions.size, weight: round(w), tokens,
      heavyN, heavyShare: round(mean(heavyW, w)), heavyRate: round(mean(heavyN, rows.length)),
      perResponse: round(mean(w, rows.length)), p50: quantile(cs, .5), p95: quantile(cs, .95),
      strata: [...strata].sort((a, b) => a[0].localeCompare(b[0])) };
  }
  function options(o = {}) {
    const pivot = Number(o.pivot), days = Number(o.days || 14);
    if (!Number.isFinite(pivot) || pivot < 946684800000 || pivot > 4102444800000) throw Error('変更日時を指定してください。');
    if (![7, 14, 30].includes(days)) throw Error('比較期間は 7・14・30 日から選んでください。');
    return { pivot, days, tool: String(o.tool || ''), project: String(o.project || ''), model: String(o.model || ''),
      includeSide: o.includeSide === true, change: String(o.change || '').slice(0, 120) };
  }
  function analyze(data, rawOptions) {
    const o = options(rawOptions), start = o.pivot - o.days * DAY, end = o.pivot + o.days * DAY;
    const sessions = new Map(data.sessions.map(s => [s.id, { ...s }]));
    // Explicit boundaries are observation evidence, including in older saved datasets.
    for (const c of data.compactions) { const session = sessions.get(c.sid); if (session && (session.firstSeen === null || c.ts < session.firstSeen)) session.firstSeen = c.ts; }
    const scoped = data.rows.filter(r => (!o.tool || r.tool === o.tool) && (!o.project || r.project === o.project) &&
      (!o.model || r.model === o.model) && (o.includeSide || !r.side));
    const rows = scoped.filter(r => r.ts >= start && r.ts < end);
    const before = rows.filter(r => r.ts < o.pivot), after = rows.filter(r => r.ts >= o.pivot);
    const ongoing = [], fresh = [], unknown = [];
    for (const r of after) {
      const s = sessions.get(r.sid);
      if (!s || s.firstSeen === null) unknown.push(r);
      else (s.firstSeen < o.pivot ? ongoing : fresh).push(r);
    }
    const B = summarize(before), A = summarize(after);
    const warnings = [];
    if (!B.n || !A.n) warnings.push('変更の前と後、両方の記録が必要です。片側だけでは差を出しません。');
    if (B.sessions < 5 || A.sessions < 5) warnings.push('片側の会話が 5 件未満です。少数の会話に左右される比較です。');
    if (rows.some(r => !r.model)) warnings.push('モデル不明の記録を含みます。同じモデルの比較とは確認できません。');
    if (rows.some(r => !r.project)) warnings.push('作業フォルダ不明の記録を含みます。同じプロジェクトとは確認できません。');
    const beforeMix = new Map(B.strata), afterMix = new Map(A.strata);
    const keys = new Set([...beforeMix.keys(), ...afterMix.keys()]);
    const mixShift = B.n && A.n ? [...keys].some(k => Math.abs((beforeMix.get(k) || 0) / B.n - (afterMix.get(k) || 0) / A.n) > .1) : false;
    if (mixShift) warnings.push('AI・モデル・作業フォルダの構成比が前後で 10 ポイント超異なります。条件を絞って再確認してください。');
    if (end > Date.parse(data.collectedAt)) warnings.push('変更後の比較期間はまだ終わっていません。総量の単純比較はできません。');
    if (data.coverage.noTime || data.coverage.noUsage || data.coverage.badLines) warnings.push('日時・使用量の欠落や読めない行があります。取り込みの内訳を確認してください。');
    const bins = Array.from({ length: o.days * 2 }, (_, i) => ({ start: start + i * DAY, rows: [], compactions: 0 }));
    for (const r of rows) bins[Math.floor((r.ts - start) / DAY)].rows.push(r);
    const allowedSids = new Set(scoped.map(r => r.sid));
    for (const c of data.compactions) if (c.ts >= start && c.ts < end && allowedSids.has(c.sid)) bins[Math.floor((c.ts - start) / DAY)].compactions++;
    return { options: o, start, end, before: B, after: A, ongoing: summarize(ongoing), fresh: summarize(fresh), unknown: summarize(unknown),
      deltaPoints: B.heavyShare !== null && A.heavyShare !== null ? round((A.heavyShare - B.heavyShare) * 100) : null,
      warnings, mixShift, daily: bins.map(b => ({ start: b.start, ...summarize(b.rows), compactions: b.compactions })),
      coverage: { included: rows.length, outsideWindow: scoped.length - rows.length, outsideScope: data.rows.length - scoped.length },
      total: summarize(data.rows), source: data.sample ? 'sample' : 'logs' };
  }
  function discover(data, rawOptions) {
    const o = options(rawOptions);
    const scoped = data.rows.filter(r => (!o.tool || r.tool === o.tool) && (!o.project || r.project === o.project) && (!o.model || r.model === o.model) && (o.includeSide || !r.side));
    const end = scoped.reduce((m, r) => Math.max(m, r.ts + 1), 0);
    const start = end ? end - 7 * DAY : null;
    const rows = scoped.filter(r => r.ts >= start && r.ts < end), total = summarize(rows);
    const grouped = new Map();
    for (const r of rows) { if (!grouped.has(r.sid)) grouped.set(r.sid, []); grouped.get(r.sid).push(r); }
    const candidates = [...grouped].map(([sid, rs]) => {
      const heavy = rs.filter(r => context(r) > 400000), heavyWeight = heavy.reduce((v, r) => v + weight(r), 0);
      return { sid, n: rs.length, heavyN: heavy.length, heavyWeight, share: total.weight ? heavyWeight / total.weight : null,
        tool: rs[0].tool, projects: sorted(new Set(rs.map(r => r.project))), models: sorted(new Set(rs.map(r => r.model))),
        compactions: [...new Set(data.compactions.filter(c => c.sid === sid && c.ts >= start && c.ts < end).map(c => c.ts))].sort((a, b) => a - b),
        first: rs.reduce((m, r) => Math.min(m, r.ts), Infinity), last: rs.reduce((m, r) => Math.max(m, r.ts), -Infinity),
        examples: heavy.sort((a, b) => weight(b) - weight(a) || a.ts - b.ts).slice(0, 5).map(r => ({ ts: r.ts, context: context(r), weight: round(weight(r)), model: r.model })) };
    }).filter(c => c.heavyN && c.heavyWeight > 0).sort((a, b) => b.heavyWeight - a.heavyWeight || a.sid.localeCompare(b.sid)).slice(0, 3);
    return { start, end: end || null, total, candidates, byTool: sorted(new Set(rows.map(r => r.tool))).map(tool => ({ tool, ...summarize(rows.filter(r => r.tool === tool)) })) };
  }
  function stable(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}';
  }
  async function digest(value) {
    const bytes = new TextEncoder().encode(stable(value));
    const hash = await root.crypto.subtle.digest('SHA-256', bytes);
    return [...new Uint8Array(hash)].map(b => b.toString(16).padStart(2, '0')).join('');
  }
  function validate(data) {
    const fail = () => { throw Error('対応するログマップの保存データではないか、数値・対応関係が壊れています。'); };
    const exact = (o, keys) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join('|') === keys.sort().join('|');
    const num = n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1e12;
    const ts = n => typeof n === 'number' && Number.isFinite(n) && n >= 946684800000 && n <= 4102444800000;
    if (!exact(data, ['parser', 'sample', 'collectedAt', 'coverage', 'sessions', 'rows', 'compactions']) || data.parser !== PARSER || typeof data.sample !== 'boolean' || !ts(Date.parse(data.collectedAt))) fail();
    if (!exact(data.coverage, ['files', 'lines', 'badLines', 'noTime', 'noUsage']) || !Object.values(data.coverage).every(n => num(n) && Number.isInteger(n))) fail();
    if (!Array.isArray(data.sessions) || data.sessions.length > 100000 || !Array.isArray(data.rows) || data.rows.length > 1000000 || !Array.isArray(data.compactions) || data.compactions.length > 100000) fail();
    const ids = new Set();
    for (const s of data.sessions) {
      if (!exact(s, ['id', 'firstSeen']) || !/^s\d{1,6}$/.test(s.id) || ids.has(s.id) || (s.firstSeen !== null && !ts(s.firstSeen))) fail();
      ids.add(s.id);
    }
    for (const r of data.rows) {
      if (!exact(r, ['sid', 'ts', 'tool', 'project', 'model', 'side', 'inp', 'out', 'cr', 'cw', 'cw1h']) || !ids.has(r.sid) || !ts(r.ts) || !['claude', 'codex', 'gemini'].includes(r.tool) || typeof r.project !== 'string' || !/^(p\d{1,6})?$/.test(r.project) || typeof r.model !== 'string' || r.model.length > 96 || !/^[\w .:/-]*$/.test(r.model) || typeof r.side !== 'boolean' || !['inp', 'out', 'cr', 'cw', 'cw1h'].every(k => num(r[k])) || r.cw1h > r.cw) fail();
    }
    for (const c of data.compactions) if (!exact(c, ['sid', 'ts']) || !ids.has(c.sid) || !ts(c.ts)) fail();
    return data;
  }
  async function snapshot(data, rawOptions) {
    validate(data);
    const payload = { schema: VERSION, weights: WEIGHTS, data, options: options(rawOptions) };
    return { ...payload, sha256: await digest(payload) };
  }
  async function restore(doc) {
    if (!doc || ![VERSION, 'logmap-change-lab/1'].includes(doc.schema) || stable(doc.weights) !== stable(WEIGHTS) || typeof doc.sha256 !== 'string') throw Error('保存データの版または重みが対応していません。');
    validate(doc.data);
    const opts = options(doc.options);
    const payload = { schema: doc.schema, weights: WEIGHTS, data: doc.data, options: opts };
    if (await digest(payload) !== doc.sha256) throw Error('保存データの識別子と内容が一致しません。元の JSON を読み直してください。');
    return { data: doc.data, options: opts, sha256: doc.sha256, legacy: doc.schema !== VERSION };
  }
  function demo() {
    const pivot = Date.UTC(2026, 9, 19), rows = [], sessions = [], compactions = [];
    for (let d = -14; d < 14; d++) for (let j = 0; j < 8; j++) {
      const id = 's' + sessions.length, firstSeen = pivot + d * DAY + (j + 1) * 3600000;
      sessions.push({ id, firstSeen });
      for (let k = 0; k < 15; k++) {
        const ts = firstSeen + k * 180000, big = d < 0 ? (j + k) % 4 === 0 : (j + k) % 19 === 0;
        rows.push({ sid: id, ts, tool: j < 6 ? 'claude' : j === 6 ? 'codex' : 'gemini', project: 'p1', model: j < 6 ? 'Claude demo' : j === 6 ? 'Codex demo' : 'Antigravity demo', side: false, inp: 800, out: 900 + k * 30, cr: big ? 510000 : 120000 + k * 7500, cw: k === 0 ? 20000 : 0, cw1h: 0 });
      }
      if (j === 0) compactions.push({ sid: id, ts: firstSeen + 2000000 });
    }
    // Sessions observed before the change that continue afterwards.
    for (let j = 0; j < 6; j++) for (let k = 0; k < 22; k++) rows.push({ sid: 's' + j, ts: pivot + (j + 8) * DAY + k * 180000, tool: 'claude', project: 'p1', model: 'Claude demo', side: false, inp: 800, out: 700, cr: k % 3 === 0 ? 530000 : 180000, cw: 0, cw1h: 0 });
    rows.sort((a, b) => a.ts - b.ts || a.sid.localeCompare(b.sid));
    return { parser: PARSER, sample: true, collectedAt: new Date(pivot + 14 * DAY).toISOString(), coverage: { files: 224, lines: 0, badLines: 0, noTime: 0, noUsage: 0 }, sessions, rows, compactions };
  }
  root.LogmapLab = Object.freeze({ VERSION, PARSER, WEIGHTS, DAY, context, weight, summarize, analyze, discover, options, stable, digest, validate, snapshot, restore, demo });
})(globalThis);
