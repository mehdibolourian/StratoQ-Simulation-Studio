import assert from 'node:assert/strict';
import { potentialLinks, resolveVisualLinks } from '../src/lib/topology.js';

const scenario = {
  ground_stations: [{id:'gs-1',lat:48.6,lon:-81.0},{id:'gs-2',lat:48.7,lon:-81.1}],
  balloons: [{id:'hap-1',lat:48.62,lon:-81.01,coverage_km:85,altitude_km:15}],
  link_overrides: [],
};
const base = [{id:'gs-1:hap-1',source:'gs-1',target:'hap-1',enabled:true,in_range:true},
  {id:'gs-2:hap-1',source:'gs-2',target:'hap-1',enabled:true,in_range:true}];
const fresh = {links:base.map((l,i)=>({...l,capacity_bps:5000,used_bps:4000,activated:i===0,allocated:true}))};
let states = resolveVisualLinks(potentialLinks(scenario,fresh),fresh);
assert.equal(states[0].activated,true,'live optical generation is shown on the physical GS–HAP link');
assert.equal(states[1].allocated,true);
assert.equal(states[1].activated,false,'second hop is QKP-only, not optical generation');
const qkp = {links:base.map(l=>({...l,capacity_bps:5000,used_bps:4000,activated:false,allocated:true}))};
states = resolveVisualLinks(potentialLinks(scenario,qkp),qkp);
assert(states.every(l=>l.allocated && !l.activated),'QKP-only links must not look idle or fresh');
assert(states.every(l=>l.id.includes(':hap-1')),'only physical GS–HAP links are rendered');
const noResults = resolveVisualLinks(potentialLinks(scenario));
assert(noResults.every(l=>!l.activated&&!l.allocated),'unsimulated links stay idle');
// Regression: small frontend/backend range disagreements must not hide solver states.
const nearEdge = structuredClone(scenario);
nearEdge.balloons[0].coverage_km=0.01;
states = resolveVisualLinks(potentialLinks(nearEdge,fresh),fresh);
assert.equal(states[0].activated,true,'backend solver status must override frontend approximation');
assert.equal(states[0].in_range,true,'backend geometry is authoritative after simulation');
console.log('PASS: frontend GS–HAP optical/QKP/idle state tests');
