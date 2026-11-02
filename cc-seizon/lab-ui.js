(function () {
  'use strict';
  const L = globalThis.LogmapLab, app = window.__seizon, panel = document.querySelector('#labPanel');
  const $ = s => panel.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = v => v === null ? '—' : Math.round(v).toLocaleString('ja-JP');
  const pc = v => v === null ? '—' : (v * 100).toFixed(1) + '%';
  const shortDate = t => new Date(t).toISOString().slice(5, 10).replace('-', '/');
  const dateTime = t => new Date(t).toISOString().slice(0, 16).replace('T', ' ');
  const names = { claude: 'Claude', codex: 'Codex', gemini: 'Antigravity' };
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const inputTime = t => new Date(t - new Date(t).getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  let data = null, state = null, result = null, restoredOptions = null, savedHash = '';
  panel.innerHTML = `<form id="labForm"><div class="lab-control">
    <label class="lab-field"><span>確かめたい変更</span><input id="labName" maxlength="120" placeholder="例：圧縮設定を変えた"></label>
    <label class="lab-field"><span>変更日時 <small>${esc(zone)}</small></span><input id="labPivot" type="datetime-local" required></label>
    <label class="lab-field"><span>比較する期間</span><select id="labDays"><option value="7">前後 7 日ずつ</option><option value="14" selected>前後 14 日ずつ</option><option value="30">前後 30 日ずつ</option></select></label>
    <button class="btn primary lab-apply" type="submit">この条件で比べる <span aria-hidden="true">↗</span></button>
  </div><div class="lab-filters">
    <label>AI <select id="labTool" aria-label="AI を絞る"></select></label>
    <label>作業 <select id="labProject" aria-label="作業フォルダを絞る"></select></label>
    <label>モデル <select id="labModel" aria-label="モデルを絞る"></select></label>
    <label><input type="checkbox" id="labSide">サブエージェントを含める</label>
    <span class="lab-utc">SAME WINDOW · UTC</span>
  </div></form><div id="labResult" class="lab-result"></div>
  <div class="lab-foot"><div><p>数字と条件を、ひとつのファイルに。会話本文・コード・元のパスは保存しません。日時と使用量は含まれるため、共有前に確認してください。</p><span id="labHash" class="lab-saved"></span></div>
    <div class="lab-foot-buttons"><button class="btn" id="labLoad">保存データを開く</button><button class="btn" id="labCopy">結果をコピー</button><button class="btn" id="labImage">カード画像</button><button class="btn primary" id="labSave">条件ごと保存 ↓</button></div>
  </div><input type="file" id="labFile" accept=".json,application/json" hidden><p id="labMessage" class="lab-message" aria-live="polite"></p>`;

  const message = (text, error = false) => { $('#labMessage').textContent = text; $('#labMessage').classList.toggle('error', error); };
  function selectValues(selector, values, label) {
    $(selector).innerHTML = '<option value="">すべて</option>' + [...new Set(values)].sort().map(v => `<option value="${esc(v)}">${esc(label(v))}</option>`).join('');
  }
  function setControls(o) {
    $('#labName').value = o.change;
    $('#labPivot').value = inputTime(o.pivot);
    $('#labDays').value = String(o.days);
    $('#labTool').value = o.tool; $('#labProject').value = o.project; $('#labModel').value = o.model;
    $('#labSide').checked = o.includeSide;
  }
  function readControls() {
    return L.options({ change: $('#labName').value, pivot: state && $('#labPivot').value === inputTime(state.pivot) ? state.pivot : Date.parse($('#labPivot').value), days: Number($('#labDays').value),
      tool: $('#labTool').value, project: $('#labProject').value, model: $('#labModel').value, includeSide: $('#labSide').checked });
  }
  function onData() {
    if (data !== app.labData) {
      data = app.labData; savedHash = ''; message('');
      const latest = data.rows.reduce((m, r) => Math.max(m, r.ts), 0) || Date.parse(data.collectedAt);
      const p = data.sample ? Date.UTC(2026, 9, 19) : Math.floor(latest / L.DAY) * L.DAY - 7 * L.DAY;
      state = restoredOptions || L.options({ pivot: p, days: 14, change: data.sample ? '圧縮設定を見直した' : '' }); restoredOptions = null;
      selectValues('#labTool', data.rows.map(r => r.tool), v => names[v]);
      selectValues('#labProject', data.rows.map(r => r.project).filter(Boolean), v => app.labLabels[v] || '作業 ' + v.slice(1));
      selectValues('#labModel', data.rows.map(r => r.model).filter(Boolean), v => v);
      setControls(state); render();
      if (!data.sample && !state.change) message('日時は仮置きです。実際に変えた日時と内容を指定してください。');
    }
  }
  function render() {
    result = L.analyze(data, state); savedHash = ''; $('#labHash').textContent = '';
    const R = result, B = R.before, A = R.after, D = R.deltaPoints;
    const delta = D === null ? '—' : (D > 0 ? '+' : '') + D.toFixed(1);
    const valid = D !== null, subtitle = state.change || '変更の前後を確かめる';
    const bar = (label, x, cls) => `<div class="compare-row ${cls}"><label>${label}</label><span class="lab-bar"><i style="width:${(x.heavyShare || 0) * 100}%"></i></span><b>${pc(x.heavyShare)}</b></div>`;
    const metric = (label, a, b, detail) => `<div class="lab-metric"><span>${label}</span><strong>${a}<i>→</i>${b}</strong><small>${detail}</small></div>`;
    const cohort = (title, c) => `<div class="lab-cohort-row"><span>${title}</span><b>${pc(c.heavyShare)}</b><small>${n(c.sessions)} 会話 · ${n(c.n)} 応答 · 40万超 ${n(c.heavyN)} 応答</small><span class="lab-mini"><i style="width:${(c.heavyShare || 0) * 100}%"></i></span></div>`;
    const warnings = [...R.warnings];
    if (!state.change) warnings.unshift('変更内容と日時を指定してから、結果を判断してください。');
    const chartBars = R.daily.map((d, i) => `<div class="lab-day${i >= state.days ? ' after' : ''}${!d.n ? ' empty' : ''}" tabindex="0" role="img" aria-label="${dateTime(d.start)} UTC から24時間。${n(d.n)}応答、40万超の重み付き割合 ${pc(d.heavyShare)}、圧縮境界 ${d.compactions}件"><i style="height:${(d.heavyShare || 0) * 100}%"></i><span class="lab-tooltip">${shortDate(d.start)} · ${pc(d.heavyShare)}<br>${n(d.n)} responses<br>圧縮境界 ${d.compactions}</span></div>`).join('');
    $('#labResult').innerHTML = `<div class="lab-topline"><p class="lab-section-label">01 / CHANGE REPORT</p><span class="lab-status">${data.sample ? '見本・架空データ' : valid ? '比較を表示 · 効果は未判定' : '比較する記録が不足'}</span></div>
      <section class="lab-score" aria-label="変更前後の観測差"><div><p class="lab-section-label">${esc(subtitle)}</p><h2>長い文脈が占める割合の変化</h2><div class="lab-n${D > 0 ? ' rise' : ''}">${delta}<small>pt</small></div><p class="lab-caption">文脈 <b>40万トークン超</b>の応答が、重み付き使用量に占める割合。<br>この差は、料金や利用枠の削減率ではありません。</p></div>
      <div class="lab-compare">${bar('BEFORE', B, '')}${bar('AFTER', A, 'after')}<div class="lab-comparison-note"><span>${shortDate(R.start)} — ${shortDate(state.pivot)} — ${shortDate(R.end)}</span><span>各 ${state.days} 日 / UTC</span></div><p class="lab-caption">${valid ? '前後の差を観測しています。作業内容・モデル・会話の構成が変わるため、設定の効果とはまだ断定できません。' : '片側に記録がない場合は 0% として比べません。日時や条件を見直してください。'}</p></div></section>
      <div class="lab-metrics">${metric('応答数', n(B.n), n(A.n), '対象の量も合わせて確認')}${metric('1 応答あたりの重み付き量', n(B.perResponse), n(A.perResponse), '共通の重み · 金額ではありません')}${metric('文脈の中央値', n(B.p50), n(A.p50), '入力＋キャッシュ読み・書き / tokens')}${metric('記録のある会話', n(B.sessions), n(A.sessions), '会話数は完了した仕事の数ではありません')}</div>
      <section class="lab-chart-section"><div class="lab-chart-title"><div><p class="lab-section-label">OVER TIME</p><h3>変化は、続いているか。</h3></div><div class="lab-chart-legend"><span>変更前</span><span>変更後</span></div></div><div class="lab-chart"><span class="lab-axis top">100%</span><span class="lab-axis mid">50%</span><span class="lab-axis">0%</span><div class="lab-chart-bars">${chartBars}</div><div class="lab-change-line"><span>変更 ${shortDate(state.pivot)}</span></div></div><div class="lab-xaxis"><span>${shortDate(R.start)}</span><span>${shortDate(R.end)}</span></div><p class="lab-caption">変更日時を境に 24 時間ずつ集計。縦軸は文脈 40万超の重み付き割合。記録のない区間は空欄です。棒に触れると件数・圧縮境界の記録数を確認できます。</p></section>
      <div class="lab-bottom"><section class="lab-cohorts"><p class="lab-section-label">SESSION COHORTS</p><h3>続けた会話に、差が残っていないか。</h3>${cohort('変更前から記録がある会話', R.ongoing)}${cohort('変更後に初めて記録された会話', R.fresh)}${R.unknown.n ? cohort('開始時期が分からない会話', R.unknown) : ''}<p class="lab-caption">どちらも<b>変更後の応答だけ</b>を比較。開始時期は手元のログで最初に観測した時刻です。ログの欠落や再開のため、実際の新規作成日時とは限りません。設定が読み込まれたかどうかは、この数字だけでは分かりません。</p></section>
      <section class="lab-evidence"><p class="lab-section-label">EVIDENCE & LIMITS</p><h3>この数字から、言えること。</h3>${warnings.slice(0, 4).map(w => `<div class="lab-check">${esc(w)}</div>`).join('')}${warnings.length > 4 ? `<details><summary>ほか ${warnings.length - 4} 件の確認点</summary>${warnings.slice(4).map(w => `<p>${esc(w)}</p>`).join('')}</details>` : ''}<div class="lab-check limit">完了時間・受入件数・本人の手間は、このログだけでは未測定。小さい数字をそのまま「改善」とは扱いません。</div><details id="labProvenance"><summary>集計条件と取り込みの内訳</summary><dl><dt>期間の開始（含む）</dt><dd>${dateTime(R.start)} UTC</dd><dt>期間の終了（含まない）</dt><dd>${dateTime(R.end)} UTC</dd><dt>収集日時</dt><dd>${dateTime(Date.parse(data.collectedAt))} UTC</dd><dt>入力ファイル</dt><dd>${n(data.coverage.files)}</dd><dt>入力の全応答</dt><dd>${n(data.rows.length)}</dd><dt>今回の対象</dt><dd>${n(R.coverage.included)}</dd><dt>AI・作業・モデル等で除外</dt><dd>${n(R.coverage.outsideScope)}</dd><dt>期間外</dt><dd>${n(R.coverage.outsideWindow)}</dd><dt>日時不明 / 使用量なし</dt><dd>${n(data.coverage.noTime)} / ${n(data.coverage.noUsage)}</dd><dt>読めなかった対象行</dt><dd>${n(data.coverage.badLines)}</dd></dl><p>入力 1・出力 5・キャッシュ読み 0.1・書き込み 5分 1.25 / 1時間 2。モデルの単価差は含みません。</p><p>作業フォルダは会話の最初の cwd です。複数 repo にまたがる作業を厳密に分離するものではありません。保存時は匿名番号になります。</p><code>${esc(data.parser)} · ${esc(L.VERSION)}</code></details></section></div>`;
  }
  function reportText() {
    const R = result;
    return [data.sample ? '【見本・架空データ】AI 開発ログマップ' : 'AI 開発ログマップ · 変更前後の観測',
      state.change || '変更内容は未指定', `変更日時：${dateTime(state.pivot)} UTC、前後 ${state.days} 日ずつ`,
      `対象：${state.tool ? names[state.tool] : '全AI'} / ${state.project || '全作業'} / ${state.model || '全モデル'} / サブエージェント${state.includeSide ? '含む' : '除外'}`,
      `40万超の重み付き割合：${pc(R.before.heavyShare)} → ${pc(R.after.heavyShare)}（差 ${R.deltaPoints === null ? '未算出' : R.deltaPoints.toFixed(1) + ' ポイント'}）`,
      `応答数：${n(R.before.n)} → ${n(R.after.n)}、1応答あたり重み付き量：${n(R.before.perResponse)} → ${n(R.after.perResponse)}`,
      `変更後のうち、前から記録のある会話：${pc(R.ongoing.heavyShare)} / 後に初記録の会話：${pc(R.fresh.heavyShare)}`,
      '共通の料金比で重み付けした観測値。設定の効果・料金や利用枠の削減率・仕事の品質は未判定。',
      ...R.warnings.map(w => '確認点：' + w), savedHash ? '保存データ SHA-256: ' + savedHash : '',
      '解析版：' + data.parser].filter(Boolean).join('\n');
  }
  function download(blob, name) {
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('#labForm').addEventListener('submit', e => { e.preventDefault(); try { state = readControls(); render(); message(''); } catch (err) { message(err.message, true); } });
  for (const id of ['#labDays', '#labTool', '#labProject', '#labModel', '#labSide']) $(id).addEventListener('change', () => $('#labForm').requestSubmit());
  // Editing the conditions invalidates export until the displayed result is updated.
  for (const id of ['#labName', '#labPivot']) $(id).addEventListener('change', () => $('#labForm').requestSubmit());
  $('#labSave').addEventListener('click', async () => {
    const button = $('#labSave'); button.disabled = true;
    try {
      state = readControls(); render(); const source = data, options = state;
      const doc = await L.snapshot(source, options);
      download(new Blob([JSON.stringify(doc)], { type: 'application/json' }), `logmap-${source.sample ? 'sample-' : ''}${doc.sha256.slice(0, 12)}.json`);
      if (data === source && state === options) { savedHash = doc.sha256; $('#labHash').textContent = 'SHA-256 ' + savedHash.slice(0, 16) + '…'; message('集計条件と数値を保存しました。識別子は内容の照合用で、記録の真正性を保証するものではありません。'); }
    } catch (err) { message(err.message, true); } finally { button.disabled = false; }
  });
  $('#labLoad').addEventListener('click', () => $('#labFile').click());
  async function restoreDocument(doc) {
    const restored = await L.restore(doc);
    restoredOptions = restored.options; app.importLab(restored.data); savedHash = restored.sha256;
    $('#labHash').textContent = 'SHA-256 ' + savedHash.slice(0, 16) + '…'; message('内容の一致を確認しました。同じ条件で再表示しています。使用量の詳細・手直しには元のログを読み込んでください。');
    return restored;
  }
  $('#labFile').addEventListener('change', async e => {
    const file = e.target.files[0]; e.target.value = ''; if (!file) return;
    try {
      if (file.size > 80 * 1024 * 1024) throw Error('保存データは 80 MB 以下にしてください。');
      await restoreDocument(JSON.parse(await file.text()));
    } catch (err) { message('読み込めませんでした：' + err.message, true); }
  });
  $('#labCopy').addEventListener('click', async () => {
    try { state = readControls(); render(); await navigator.clipboard.writeText(reportText()); message('表示中の条件と結果をコピーしました。'); }
    catch (err) { message('コピーできませんでした。保存データまたはカード画像をご利用ください。', true); }
  });
  $('#labImage').addEventListener('click', () => {
    try {
      state = readControls(); render();
      const c = document.createElement('canvas'); c.width = 1200; c.height = 900; const x = c.getContext('2d');
      const text = (s, y, size, color = '#eff1e7') => { x.fillStyle = color; x.font = `${size >= 60 ? 500 : 400} ${size}px ${size >= 60 ? 'PlexMonoSub, monospace' : 'sans-serif'}`; x.fillText(s, 64, y, 1072); };
      x.fillStyle = '#11130f'; x.fillRect(0, 0, 1200, 900); x.fillStyle = '#d4f77d'; x.fillRect(64, 52, 8, 27);
      text('    LOGMAP / CHANGE REPORT', 75, 22, '#d4f77d');
      text(data.sample ? '見本・架空データ' : '手元のログから集計した観測値', 130, 20, '#b7bdab');
      text(state.change || '変更前後の比較', 200, 34);
      text('文脈40万超の応答が、重み付き使用量に占める割合', 252, 24, '#b7bdab');
      text(`${pc(result.before.heavyShare)}  →  ${pc(result.after.heavyShare)}`, 382, 76, '#d4f77d');
      text(`差 ${result.deltaPoints === null ? '未算出' : result.deltaPoints.toFixed(1) + ' ポイント'} / 前 ${n(result.before.n)} 応答・後 ${n(result.after.n)} 応答`, 446, 26);
      text(`変更 ${dateTime(state.pivot)} UTC · 前後 ${state.days} 日ずつ`, 515, 24, '#b7bdab');
      text(`${state.tool ? names[state.tool] : '全 AI'} / ${state.project || '全作業'} / ${state.model || '全モデル'}`, 558, 22, '#b7bdab');
      text(`変更前から記録あり ${pc(result.ongoing.heavyShare)} / 変更後に初記録 ${pc(result.fresh.heavyShare)}`, 625, 24);
      text('設定の効果、料金・利用枠の削減率、仕事の品質は未判定。', 726, 24, '#d4f77d');
      text('同じ AI・モデル・作業でも、内容やログ欠落の影響が残ります。', 767, 20, '#b7bdab');
      text(`${data.parser} · 入力1 / 出力5 / cache読0.1 / 書1.25–2`, 839, 17, '#939c86');
      c.toBlob(blob => download(blob, 'logmap-change-report.png'), 'image/png');
    } catch (err) { message(err.message, true); }
  });
  document.querySelector('.brand').addEventListener('click', e => { e.preventDefault(); document.querySelector('[data-tab="lab"]').click(); });
  window.addEventListener('logmap:render', onData);
  window.__logmapLab = { get result() { return result; }, get state() { return state; }, reportText, restore: restoreDocument };
  onData();
})();
