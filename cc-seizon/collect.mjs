#!/usr/bin/env node
// One-shot, explicit inputs only. No credentials, network, watchers or AI calls.
import { parseArgs } from 'node:util';
import { readdir, lstat, writeFile, readFile, mkdtemp, rm } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { resolve, basename, join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { L, parser, numericLine } from './parser-node.mjs';
const help = `Usage: node cc-seizon/collect.mjs --logs DIR [--logs DIR] --out FILE
  --pivot ISO_TIME_WITH_ZONE   Actual change time (e.g. 2026-10-21T07:00:00+09:00)
  --days 7|14|30              Matched windows, default 14
  --change TEXT              Optional change label
  --tool claude|codex|gemini  Optional scope (all tools still saved)
  --html FILE                Also create an offline report (requires Python 3)
The output contains numeric events with anonymous session/project IDs, no source
paths, prompts or code. It can be opened with '保存データを開く'. Existing output
files are never overwritten. Logs are read to the size observed at file-open time.`;
try {
  const { values: a } = parseArgs({ options: { logs: { type: 'string', multiple: true }, out: { type: 'string' }, html: { type: 'string' }, pivot: { type: 'string' }, days: { type: 'string' }, change: { type: 'string' }, tool: { type: 'string' }, help: { type: 'boolean' } } });
  if (a.help) { console.log(help); process.exit(0); }
  if (!a.logs?.length || !a.out || !a.pivot || !/(Z|[+-]\d{2}:\d{2})$/.test(a.pivot)) throw Error(help);
  if (a.tool && !['claude', 'codex', 'gemini'].includes(a.tool)) throw Error('Unknown --tool');
  const opts = L.options({ pivot: Date.parse(a.pivot), days: Number(a.days || 14), change: a.change, tool: a.tool });
  const files = new Set();
  const skip = parser.LOG_SKIP_DIRS;
  async function walk(path) {
    const st = await lstat(path);
    if (st.isSymbolicLink()) throw Error('Symbolic links are not read: ' + path);
    if (st.isFile()) { if (path.endsWith('.jsonl')) files.add(path); return; }
    if (!st.isDirectory() || skip.has(basename(path))) return;
    for (const entry of (await readdir(path, { withFileTypes: true })).sort((x, y) => x.name.localeCompare(y.name))) {
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory() || entry.isFile() && entry.name.endsWith('.jsonl')) await walk(join(path, entry.name));
    }
  }
  for (const path of a.logs) await walk(resolve(path));
  if (!files.size) throw Error('No JSONL files found.');
  const acc = parser.newLogAcc();
  for (const path of [...files].sort()) {
    const st = await lstat(path); acc.cur = parser.newFileState(path);
    if (st.size) {
      const lines = createInterface({ input: createReadStream(path, { encoding: 'utf8', start: 0, end: st.size - 1 }), crlfDelay: Infinity });
      for await (const line of lines) parser.handleLogLine(numericLine(line), acc);
    }
    acc.files++;
  }
  parser.finalizeGemini(acc);
  const { data } = parser.labDatasetFromAcc(acc);
  if (!data.rows.length) throw Error('No supported response usage records found.');
  const doc = await L.snapshot(data, opts), report = L.analyze(data, opts);
  await writeFile(resolve(a.out), JSON.stringify(doc), { flag: 'wx', mode: 0o600 });
  if (a.html) {
    const temp = await mkdtemp(join(tmpdir(), 'logmap-report-'));
    try {
      const built = join(temp, 'report.html');
      execFileSync('python3', [fileURLToPath(new URL('../build_standalone.py', import.meta.url)), fileURLToPath(new URL('./app.html', import.meta.url)), built], { stdio: 'pipe' });
      const html = await readFile(built, 'utf8');
      const json = JSON.stringify(doc).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
      const reportHTML = html.replace('</body>', () => '<script>window.__logmapLab.restore(' + json + ').catch(e => { document.getElementById("labMessage").textContent = "読込失敗: " + e.message; });</script>\n</body>');
      await writeFile(resolve(a.html), reportHTML, { flag: 'wx', mode: 0o600 });
    } finally { await rm(temp, { recursive: true, force: true }); }
  }
  console.log(JSON.stringify({ output: resolve(a.out), sha256: doc.sha256, responses: data.rows.length, before: report.before.n, after: report.after.n, deltaPoints: report.deltaPoints, coverage: data.coverage }));
} catch (err) { console.error(err.message); process.exitCode = 1; }
