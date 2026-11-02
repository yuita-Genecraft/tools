(function () {
  'use strict';
  const section=document.createElement('section');section.id='observationPanel';section.className='lab-observations';
  section.innerHTML=`<p class="lab-section-label">LOCAL OBSERVATIONS / CLAUDE</p><h2>起動と利用枠を、記録で照合。</h2><p>追加収集した記録専用です。上のログ集計とは独立して表示します。Codex・Antigravityの起動／利用枠の追加収集は未対応です。</p><div class="lab-foot-buttons"><button class="btn" id="obsOpen">観測ファイルを開く</button><button class="btn" id="obsDemo">観測の見本</button><button class="btn" id="obsClear">記録を閉じる</button></div><input type="file" id="obsFile" accept=".json" hidden><p id="obsStatus" aria-live="polite">未取得。収集設定の有効化以降の記録が必要です。過去のログを再起動・設定読込の証拠に変換しません。</p><div id="obsContent"></div>`;
  document.querySelector('#labPanel').appendChild(section);
  const $=s=>section.querySelector(s), esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dt=t=>new Date(t).toLocaleString('ja-JP'), value=v=>v==null?'未取得':esc(v);
  let generation=0;
  function clear(){generation++;$('#obsContent').replaceChildren();$('#obsStatus').textContent='未取得。観測ファイルを開いてください。';$('#obsFile').value='';}
  $('#obsClear').onclick=clear;$('#obsOpen').onclick=()=>$('#obsFile').click();
  function show(doc, sample=false){
    const events=LogmapObserve.read(doc);
    $('#obsStatus').textContent=`${sample?'見本・架空データ':'追加観測'} ${events.length.toLocaleString()} 件 · ローカル読込 · 内容の真正性は未検証`;
    const local=t=>new Date(t-new Date(t).getTimezoneOffset()*60000).toISOString().slice(0,19);
    const first=events[0]?.ts, last=events.at(-1)?.ts;
    $('#obsContent').innerHTML=`<div class="lab-control"><label>観測開始<input id="obsFrom" type="datetime-local" step="1" value="${first==null?'':local(first)}"></label><label>観測終了<input id="obsTo" type="datetime-local" step="1" value="${last==null?'':local(last)}"></label><button class="btn" id="obsCompare">この区間を表示</button></div><div id="obsReport"></div>`;
    function report(from=-Infinity,to=Infinity){
    const selected=events.filter(e=>e.ts>=from&&e.ts<=to);
    const cards=['five_hour','seven_day'].map((k,i)=>{const q=LogmapObserve.quota(selected,k);return `<div class="lab-cohort-row"><span>${i?'週間':'5時間'}枠の消費率差</span><b>${q.delta==null?'算出不可':q.delta.toFixed(2)+' pt'}</b><small>${esc(q.reason)}${q.first?`<br>${dt(q.first.ts)} → ${dt(q.last.ts)} · ${q.count} 点`:''}</small></div>`;}).join('');
    const recent=selected.slice(-100).reverse();
    $('#obsReport').innerHTML=`${cards}<p class="lab-caption">期間はこのパネルで指定した区間です。初期表示は読み込んだ観測全体です。上のAI・期間フィルタは適用しません。区間内の未完了・枠未取得記録があれば算出しません。観測自体が起動しなかった空白や保存先に書けなかった失敗は検出できず、連続収集を保証しません。差分は記録された両端の値だけです。別端末・並行作業も含むアカウントの率で、料金の削減額は未測定です。</p><details open><summary>観測タイムライン（最新100件まで）</summary>${recent.map(e=>`<div class="lab-check"><b>${dt(e.ts)} · ${esc(e.kind==='gap'?'収集未完了（欠測）':e.kind==='hook'?e.event+' / '+(e.source||'不明'):'実行中の報告')}</b><p>会話 ${esc(e.session.slice(0,8))} · モデル ${value(e.model)}${e.kind==='status'?` · 思考量 ${value(e.effort)}<br>文脈内の入力トークン ${value(e.inputTotal)} / 直近応答の出力 ${value(e.outputTotal)} · API換算の推定額 $${value(e.estimatedUsd)}<br>枠消費率 5時間 ${value(e.limits?.five_hour?.used)}% / 週間 ${value(e.limits?.seven_day?.used)}%`:''}</p>${e.kind==='hook'?`<p>設定ファイルの観測（採用された値の証明ではありません）<br>${(e.settings||[]).map(s=>s.state==='read'?`設定${s.slot} · SHA ${s.sha256.slice(0,12)} · model ${value(s.values.model)} / effort ${value(s.values.effortLevel)} / autoCompactWindow ${value(s.values.autoCompactWindow)}`:`設定${s.slot} 未取得`).join('<br>')||'対象未指定'}</p>`:''}</div>`).join('')}</details><p class="lab-caption">SessionStartのresumeは会話内の再開も含みます。OSプロセス再起動やautoCompactWindowの実効値は、この記録だけでは断定しません。モデル・思考量はステータス入力の報告値です。</p>`;
  }
    report();
    $('#obsCompare').onclick=()=>{const a=Date.parse($('#obsFrom').value),b=Date.parse($('#obsTo').value);if(!Number.isFinite(a)||!Number.isFinite(b)||a>b){$('#obsReport').textContent='有効な開始・終了日時を指定してください';return;}report(a,b+999);};
  }
  $('#obsDemo').onclick=()=>{clear();const schema=LogmapObserve.SCHEMA;const e=(id,kind,time,extra)=>({schema,id:`00000000-0000-0000-0000-${String(id).padStart(12,'0')}`,tool:'claude',session:'a'.repeat(24),kind,observedAt:`2026-11-02T${time}:00Z`,...extra});show({schema,events:[e(1,'hook','00:00',{event:'SessionStart',source:'startup',model:'sample-model',settings:[]}),e(2,'status','00:01',{model:'sample-model',effort:'high',inputTotal:10000,outputTotal:1000,estimatedUsd:0.01,limits:{five_hour:{used:12,resetsAt:1793584800}}}),e(3,'status','01:00',{model:'sample-model',effort:'high',inputTotal:20000,outputTotal:2000,estimatedUsd:0.02,limits:{five_hour:{used:15,resetsAt:1793584800}}})]},true);};
  $('#obsFile').onchange=async()=>{const f=$('#obsFile').files[0];if(!f)return;clear();const gen=generation;try{if(f.size>50*1024*1024)throw Error('50MB以下の観測ファイルを指定してください');const d=JSON.parse(await f.text());if(gen===generation)show(d);}catch(e){if(gen===generation){$('#obsContent').replaceChildren();$('#obsStatus').textContent=e.message;}}};
})();
