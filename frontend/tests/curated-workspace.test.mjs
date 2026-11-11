import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {upgradeLegacyShowcase} from '../src/lib/curatedWorkspace.js';
const presets=JSON.parse(readFileSync(new URL('../src/lib/builtinExperiments.json',import.meta.url))).experiments;
const clone=x=>structuredClone(x);
const isScenario=s=>!!s?.config&&Array.isArray(s.ground_stations);
const normalize=s=>clone(s);
let i=0;
const makeBuiltin=p=>({id:`new-${++i}`,name:p.title,builtin:{id:p.id},scenario:clone(p.scenario),baselineScenario:clone(p.scenario)});
const old=p=>({id:`old-${++i}`,name:'Storm bridge',builtin:{id:p.id},scenario:clone(p.scenario),baselineScenario:clone(p.scenario)});

test('old showcase tabs and duplicates consolidate to four shared 24h presets',()=>{
 const saved=[old(presets[0]),old(presets[1]),old(presets[2]),old(presets[2]),old(presets[3])];
 saved[0].scenario.config.slots=24; saved[0].baselineScenario.config.slots=24;
 const result=upgradeLegacyShowcase(saved,saved[2].id,presets,makeBuiltin,normalize,isScenario);
 assert.ok(result); assert.equal(result.experiments.length,4);
 assert.deepEqual(result.experiments.map(e=>e.builtin.id),presets.map(p=>p.id));
 assert.equal(result.experiments.find(e=>e.id===result.activeId).builtin.id,'qkp-enabled');
});
test('edits and custom experiments survive migration',()=>{
 const a=old(presets[0]);a.scenario.config.slots=24;a.baselineScenario.config.slots=24;
 const edited=old(presets[1]);edited.scenario.demands[0].rate_bps++;
 const custom={id:'my-own-experiment',scenario:clone(presets[0].scenario)};
 const result=upgradeLegacyShowcase([a,edited,custom],edited.id,presets,makeBuiltin,normalize,isScenario);
 assert.ok(result);assert.equal(result.experiments.length,6);
 assert.equal(result.activeId,edited.id);
 assert.ok(result.experiments.includes(edited)); assert.ok(result.experiments.includes(custom));
});
test('already-curated or intentionally closed presets do not regenerate',()=>{
 const curated=[old(presets[0]),old(presets[2]),old(presets[3])];
 assert.equal(upgradeLegacyShowcase(curated,curated[0].id,presets,makeBuiltin,normalize,isScenario),null);
});
