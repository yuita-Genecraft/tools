import test from 'node:test';import assert from 'node:assert/strict';import '../cc-seizon/observe-core.js';
const O=globalThis.LogmapObserve, base={schema:O.SCHEMA,id:'00000000-0000-0000-0000-000000000001',session:'a'.repeat(24),tool:'claude',kind:'status',observedAt:'2026-11-02T00:00:00Z',limits:{five_hour:{used:10,resetsAt:1793584800}}};
const next=(extra={})=>({...base,id:'00000000-0000-0000-0000-000000000002',observedAt:'2026-11-02T01:00:00Z',limits:{five_hour:{used:15,resetsAt:1793584800}},...extra});
const read=(events)=>O.read({schema:O.SCHEMA,events});
test('quota actual points 5pt, not savings',()=>assert.equal(O.quota(read([next(),base]),'five_hour').delta,5));
test('missing quota not zero',()=>assert.equal(O.quota(read([base,next()]),'seven_day').delta,null));
test('reset mismatch refuses difference',()=>assert.equal(O.quota(read([base,next({limits:{five_hour:{used:20,resetsAt:1793584801}}})]),'five_hour').delta,null));
test('counter regression refuses',()=>assert.equal(O.quota(read([base,next({limits:{five_hour:{used:5,resetsAt:1793584800}}})]),'five_hour').delta,null));
test('expired quota refuses',()=>assert.equal(O.quota(read([base,next({observedAt:'2026-11-03T00:00:00Z'})]),'five_hour').delta,null));
test('same timestamp conflict refuses',()=>assert.equal(O.quota(read([base,next({observedAt:base.observedAt})]),'five_hour').delta,null));
test('duplicate exact IDs dedup and conflicts refuse',()=>{assert.equal(read([base,base]).length,1);assert.throws(()=>read([base,{...base,model:'other'}]));});
test('invalid numbers / settings / schema rejected',()=>{for(const row of [{...base,inputTotal:-1},{...base,settings:[{slot:1,state:'read',sha256:'bad',values:{}}]},{...base,observedAt:'bad'}]) assert.throws(()=>read([row]));assert.throws(()=>O.read({schema:'wrong',events:[]}));});

test('durable failure gap or missing quota inside interval refuses delta',()=>{for(const event of [next({kind:'gap',limits:undefined}),next({limits:{}})]){event.observedAt='2026-11-02T00:30:00Z';event.id='00000000-0000-0000-0000-000000000003';assert.equal(O.quota(read([base,event,next()]),'five_hour').delta,null);}});
