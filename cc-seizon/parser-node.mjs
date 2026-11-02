// Reuse the page's parsing functions, without mounting its UI or retaining text.
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import './lab-core.js';
export const L = globalThis.LogmapLab;
const source = await readFile(new URL('./app.html', import.meta.url), 'utf8');
const start = source.indexOf("'use strict';", source.indexOf('<script>'));
const end = source.indexOf('/* ---------- 画面 ---------- */', start);
if (start < 0 || end < start) throw Error('The shared parser boundary was not found.');
const context = vm.createContext({ LogmapLab: L, window: {}, document: {}, crypto: webcrypto });
new vm.Script(source.slice(start, end) + '\nglobalThis.parser = {newLogAcc,newFileState,handleLogLine,finalizeGemini,labDatasetFromAcc,tokenStats,LOG_SKIP_DIRS};', { filename: 'cc-seizon-shared-parser' }).runInContext(context);
export const parser = context.parser;
// Drop conversation/code content before the existing parser stores anything.
// Keep timestamps, identities, usage, model and Cwd needed for the same totals.
export function numericLine(line) {
  let o;
  try { o = JSON.parse(line); } catch { return line; }
  if (!o || typeof o !== 'object') return '';
  if (o.message && typeof o.message === 'object') {
    return JSON.stringify({ type: o.type, sessionId: o.sessionId, timestamp: o.timestamp, uuid: o.uuid, cwd: o.cwd, isSidechain: o.isSidechain, isMeta: o.isMeta,
      message: { id: o.message.id, role: o.message.role, model: o.message.model, usage: o.message.usage, content: [] } });
  }
  if (o.type === 'system' && o.subtype === 'compact_boundary') return JSON.stringify({ type: o.type, subtype: o.subtype, sessionId: o.sessionId, timestamp: o.timestamp, uuid: o.uuid, cwd: o.cwd });
  if (o.payload && typeof o.payload === 'object') {
    const p = o.payload;
    return JSON.stringify({ type: o.type, timestamp: o.timestamp, payload: { type: p.type, id: p.id, cwd: p.cwd, model: p.model, response_id: p.response_id, usage: p.usage } });
  }
  if (typeof o.step_index === 'number') {
    const tool_calls = (Array.isArray(o.tool_calls) ? o.tool_calls : []).filter(t => t?.name === 'run_command').map(t => {
      let args = t.args;
      if (typeof args === 'string') { try { args = JSON.parse(args); } catch { args = {}; } }
      return { name: 'run_command', args: { Cwd: args?.Cwd } };
    });
    return JSON.stringify({ step_index: o.step_index, type: o.type, created_at: o.created_at, model: o.model, input_tokens: o.input_tokens, output_tokens: o.output_tokens, cache_read_tokens: o.cache_read_tokens, truncated_fields: o.truncated_fields, tool_calls });
  }
  return '';
}
