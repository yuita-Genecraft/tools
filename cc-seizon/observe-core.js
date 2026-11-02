(function (root) {
  'use strict';
  const SCHEMA = 'logmap-observations/1';
  const finite = (x, max=1e15) => typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= max;
  function read(doc) {
    if (!doc || doc.schema !== SCHEMA || !Array.isArray(doc.events) || doc.events.length > 100000) throw Error('観測ファイルの形式が違います');
    const ids = new Map(), result = [];
    for (const e of doc.events) {
      if (!e || e.schema !== SCHEMA || e.tool !== 'claude' || !['hook','status','gap'].includes(e.kind) || typeof e.id !== 'string' || !/^[a-f0-9-]{36}$/.test(e.id) || typeof e.session !== 'string' || !/^[a-f0-9]{24}$/.test(e.session) || typeof e.observedAt !== 'string' || !Number.isFinite(Date.parse(e.observedAt))) throw Error('観測レコードが不正です');
      if (e.kind === 'hook' && !['SessionStart','SessionEnd','ConfigChange','PostCompact'].includes(e.event)) throw Error('未対応のイベントです');
      for (const k of ['model','source','version','effort']) if (e[k] != null && (typeof e[k] !== 'string' || e[k].length > 96)) throw Error('ラベルが不正です');
      for (const k of ['inputTotal','outputTotal','contextWindow','estimatedUsd']) if (e[k] != null && !finite(e[k])) throw Error('数値が不正です');
      if (e.limits != null && (typeof e.limits !== 'object' || Array.isArray(e.limits))) throw Error('利用枠の形式が不正です');
      for (const k of ['five_hour','seven_day']) {
        const w = e.limits?.[k];
        if (w != null && (!finite(w.used,100) || !finite(w.resetsAt,4102444800))) throw Error('利用枠が不正です');
      }
      if (e.settings != null && (!Array.isArray(e.settings) || e.settings.length > 20)) throw Error('設定記録が不正です');
      for (const s of e.settings || []) {
        if (!s || !Number.isInteger(s.slot) || s.slot < 1 || s.slot > 20 || !['read','unavailable'].includes(s.state)) throw Error('設定記録が不正です');
        if (s.state === 'read' && (typeof s.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(s.sha256) || !s.values || typeof s.values !== 'object' || Array.isArray(s.values))) throw Error('設定記録が不正です');
        if (s.values) {
          for (const k of ['model','effortLevel']) if (s.values[k] != null && (typeof s.values[k] !== 'string' || s.values[k].length > 96)) throw Error('設定値が不正です');
          if (s.values.autoCompactWindow != null && !finite(s.values.autoCompactWindow)) throw Error('設定値が不正です');
        }
      }
      const raw = JSON.stringify(e);
      if (ids.has(e.id)) { if (ids.get(e.id) !== raw) throw Error('同じIDに異なる記録があります'); continue; }
      ids.set(e.id,raw); result.push({...e, ts:Date.parse(e.observedAt)});
    }
    return result.sort((a,b)=>a.ts-b.ts || a.id.localeCompare(b.id));
  }
  function quota(events, window, from=-Infinity, to=Infinity) {
    const points = events.filter(e=>e.kind==='status' && e.ts>=from && e.ts<=to && e.limits?.[window]);
    const empty={delta:null, count:points.length, first:null, last:null};
    if (points.length<2) return {...empty,reason:'利用枠の記録が2点以上必要です'};
    const first=points[0], last=points.at(-1), reset=first.limits[window].resetsAt;
    if (first.ts===last.ts) return {...empty,reason:'異なる時刻の記録が必要です'};
    if(events.some(e=>e.ts>=first.ts && e.ts<=last.ts && (e.kind==='gap' || (e.kind==='status' && !e.limits?.[window])))) return {...empty,reason:'区間内に収集未完了・利用枠未取得の記録があるため算出しません'};
    for(let i=0;i<points.length;i++) {
      const p=points[i], w=p.limits[window];
      if(w.resetsAt!==reset || p.ts>=reset*1000) return {...empty,reason:'リセットをまたぐ／期限切れの記録は差分にしません'};
      if(i && (w.used<points[i-1].limits[window].used || (p.ts===points[i-1].ts && w.used!==points[i-1].limits[window].used))) return {...empty,reason:'利用率の逆行・同時刻の不一致があるため算出しません'};
    }
    return {delta:last.limits[window].used-first.limits[window].used,count:points.length,first,last,reason:'アカウント全体の消費率差。設定の節約効果・この会話だけの消費ではありません'};
  }
  root.LogmapObserve={SCHEMA,read,quota};
})(globalThis);
