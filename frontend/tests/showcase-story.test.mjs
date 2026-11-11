import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {SHOWCASE_STORIES,buildStoryMoments,getSlotMeasurement,measuredCaption} from '../src/lib/showcaseStory.js';
const presets=JSON.parse(readFileSync(new URL('../src/lib/builtinExperiments.json',import.meta.url))).experiments;
const byId = Object.fromEntries(presets.map(p=>[p.id,p]));
function resultWithFrames(p, overrides={}){
 const slots=p.scenario.config.slots,secs=p.scenario.config.slot_seconds;
 const frames=Array.from({length:slots},(_,i)=>({slot:i,time_seconds:i*secs,stored_bits_total:0,qkp_drawn_link_bits:0,
 demands:p.scenario.demands.map(d=>({id:d.id,source:d.source,target:d.target,requested_bps:d.rate_bps,served_bps:0,path:[]})),
 links:[],optimizer:{candidate_solves:1}}));
 for(let [idx,change] of Object.entries(overrides))Object.assign(frames[Number(idx)],change);
 return {frames, summary:{}};
}
test('four matched 24-hour experiments and simple guided stories',()=>{
 assert.equal(presets.length,4);
 assert.equal(Object.keys(SHOWCASE_STORIES).length,4);
 assert.deepEqual(presets.map(p=>p.id),['corridor-scar','corridor-mcr','qkp-enabled','qkp-disabled']);
 const ref=presets[0].scenario;
 const withoutAlgorithm=s=>{const c=structuredClone(s);delete c.config.allocation_mode;delete c.config.qkp_enabled;return c;};
 for(const p of presets){
  assert.deepEqual(withoutAlgorithm(p.scenario), withoutAlgorithm(ref));
  const s=SHOWCASE_STORIES[p.id]; assert.ok(s,`missing story for ${p.id}`);
  assert.ok(s.question.length>25&&s.mechanism.length>40&&s.contrast.length>40);
  assert.ok(s.takeaways.length>=2&&s.steps.length>=3);
 }
});
test('annotated moments are visible before any run, with no fabricated outputs',()=>{
 for(const p of presets){
  const moments=buildStoryMoments(p.id,p.scenario);
  assert.equal(moments.length,SHOWCASE_STORIES[p.id].steps.length);
  for(const m of moments){assert.ok(m.index>=0&&m.index<p.scenario.config.slots);assert.equal(m.observed,false);assert.equal(m.metrics,null);}
 }
});
test('older saved horizon displays only in-window story markers',()=>{
 const p=byId['qkp-enabled'];const old=structuredClone(p.scenario);
 old.config.horizon_seconds=18000;old.config.slots=30;
 const a=buildStoryMoments(p.id,old,null);
 assert.ok(a.length>=1);assert.ok(a.every(x=>x.index<30));
});
test('a measured buffer draw moves the annotated cue to the real observed slot',()=>{
 const p=byId['qkp-enabled'];
 const out=resultWithFrames(p,{50:{qkp_drawn_link_bits:1800,stored_bits_total:10000},70:{qkp_drawn_link_bits:8200,stored_bits_total:7000},71:{qkp_drawn_link_bits:0,stored_bits_total:4000}});
 const moments=buildStoryMoments(p.id,p.scenario,out);
 const rain=moments.find(x=>x.id==='qkp-rain');
 assert.equal(rain.index,70);assert.equal(rain.observed,true);
 assert.equal(rain.metrics.draw,8200);assert.match(measuredCaption(rain.metrics),/QKP draw/);
 const depletion=moments.find(x=>x.id==='qkp-fog');
 assert.equal(depletion.index,50); assert.equal(depletion.observed,true);
});
test('no key draw or depletion does not become an observed event',()=>{
 const p=byId['qkp-enabled'];const res=resultWithFrames(p);
 const moments=buildStoryMoments(p.id,p.scenario,res);
 assert.equal(moments.find(x=>x.id==='qkp-rain').observed,false);
 assert.equal(moments.find(x=>x.id==='qkp-fog').observed,false);
});
test('actual route switch and candidate solves highlight real allocation changes',()=>{
 const p=byId['corridor-mcr'];const res=resultWithFrames(p);
 res.frames[2].optimizer.candidate_solves=12;
 res.frames[2].demands[0].path=[p.scenario.demands[0].source,'hap-west',p.scenario.demands[0].target];
 res.frames[2].demands[0].served_bps=900;
 const ev=buildStoryMoments(p.id,p.scenario,res).find(x=>x.id==='mcr-candidates');
 assert.equal(ev.index,2);assert.equal(ev.observed,true);assert.equal(ev.metrics.candidates,12);
 const m=getSlotMeasurement(res.frames[2],res.frames[1]); assert.equal(m.routesChanged,true);
});
test('old missing runtime data cannot cause a fake observation',()=>{
 const p=byId['qkp-enabled'];const res={frames:[],summary:{}};
 assert.ok(buildStoryMoments(p.id,p.scenario,res).every(x=>x.observed===false));
});
