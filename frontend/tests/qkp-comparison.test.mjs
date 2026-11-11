import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {matchingQkpInputs,qkpComparisonDelta} from '../src/lib/qkpComparison.js';
const presets=JSON.parse(readFileSync(new URL('../src/lib/builtinExperiments.json',import.meta.url))).experiments;
const s=presets.find(x=>x.id==='qkp-enabled').scenario;
test('only QKP availability differs in a matched ablation',()=>{
 const off=structuredClone(s);off.config.qkp_enabled=false;
 assert.ok(matchingQkpInputs(s,off));
 const changes=[o=>o.demands[0].rate_bps++,o=>o.weather_regions[0].visibility_km*=2,
   o=>o.config.optimal_time_limit_seconds++,o=>o.balloons[0].n_tx++,
   o=>o.config.optical.source_rate_hz*=2];
 for(const change of changes){const different=structuredClone(off);change(different);assert.equal(matchingQkpInputs(s,different),false);}
});
test('delta uses measured percentage-point differences and no invented default',()=>{
 assert.equal(qkpComparisonDelta(null,null),null);
 assert.equal(qkpComparisonDelta({total_satisfaction:.7,weather_window_satisfaction:.85},null),null);
 const delta=qkpComparisonDelta({total_satisfaction:.8,weather_window_satisfaction:.9},{total_satisfaction:.58,weather_window_satisfaction:.28});
 assert.ok(Math.abs(delta.total-22)<1e-8);assert.ok(Math.abs(delta.storm-62)<1e-8);
 assert.equal(qkpComparisonDelta({total_satisfaction:.8,weather_window_satisfaction:-1},{total_satisfaction:.58,weather_window_satisfaction:.28}),null);
});
