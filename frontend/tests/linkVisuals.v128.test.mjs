import assert from 'node:assert/strict';
import {demandColor,linkKeyMode,linkDisplayState,linkVisualRate,linkRateIntensity,linkFallbackColor,allocationsForLink,linkTooltip} from '../src/lib/linkVisuals.js';
const scenario={demands:[{id:'d1',source:'g1',target:'g2'},{id:'d2',source:'g1',target:'g3'},{id:'d3',source:'g2',target:'g3'}]};
const frame={demands:[
  {id:'d1',requested_bps:7000,served_bps:5000,path:['g1','h1','g2']},
  {id:'d2',requested_bps:5000,served_bps:2500,path:['g1','h1','g3']},
  {id:'d3',requested_bps:5000,served_bps:0,path:[]},
]};
const link={source:'g1',target:'h1',allocated:true,activated:true,fresh_used_bps:3000,qkp_used_bps:4500};
const lanes=allocationsForLink(link,frame,scenario);
assert.equal(lanes.length,2,'shared physical GS-HAP link must show BOTH demands');
assert.deepEqual(lanes.map(l=>l.id),['d1','d2']);
assert.notEqual(lanes[0].color,lanes[1].color);
assert.equal(linkKeyMode(link),'mixed');
assert.equal(linkKeyMode({...link,fresh_used_bps:0}),'qkp');
assert.equal(linkKeyMode({...link,qkp_used_bps:0}),'fresh');
assert.equal(linkKeyMode({allocated:true,activated:false}),'qkp');
assert.equal(allocationsForLink({...link,source:'g2',target:'h2'},frame,scenario).length,0);
assert.notEqual(demandColor(0,.1),demandColor(0,1),'luminance must respond to throughput');
assert.ok(linkTooltip(link,frame,scenario).includes('d1: 5.00 kb/s'));
const low={demands:[{id:'d1',requested_bps:7000,served_bps:500,path:['g1','h1','g2']}]};
assert.notEqual(allocationsForLink(link,low,scenario)[0].color,lanes[0].color,'single demand dims when its delivered rate falls');
console.log('PASS: unique demand lanes, shared-link attribution, rate luminance, QKP/mixed styling, legacy link flags');

// v129 regressions: link-level optical SKR/QKP draw determines darkness even
// when both physical hops carry the same end-to-end demand rate.
const rateFrame={links:[
  {id:'g1:h1',source:'g1',target:'h1',enabled:true,in_range:true,allocated:true,activated:true,
   capacity_bps:1000,used_bps:500,fresh_used_bps:500,qkp_used_bps:0},
  {id:'g2:h1',source:'g2',target:'h1',enabled:true,in_range:true,allocated:true,activated:true,
   capacity_bps:10000,used_bps:500,fresh_used_bps:500,qkp_used_bps:0},
],demands:[{id:'d1',requested_bps:1000,served_bps:500,path:['g1','h1','g2']}]};
assert.equal(linkRateIntensity(rateFrame.links[0],rateFrame),.1);
assert.equal(linkRateIntensity(rateFrame.links[1],rateFrame),1);
const dim=allocationsForLink(rateFrame.links[0],rateFrame,scenario)[0];
const bright=allocationsForLink(rateFrame.links[1],rateFrame,scenario)[0];
assert.notEqual(dim.color,bright.color,'same demand hue must have distinct link-rate luminance');
assert.equal(dim.index,bright.index,'both halves retain the same demand identity');
const qkpLow={id:'q1',enabled:true,in_range:true,allocated:true,activated:false,
  capacity_bps:9000,used_bps:200,qkp_used_bps:200,fresh_used_bps:0};
const qkpHigh={...qkpLow,id:'q2',used_bps:2000,qkp_used_bps:2000};
assert.equal(linkVisualRate(qkpLow),200,'QKP-only brightness uses *draw*, not unused optical capacity');
assert.equal(linkRateIntensity(qkpLow,{links:[qkpLow,qkpHigh]}),.1);
assert.equal(linkDisplayState(qkpLow),'qkp');
assert.equal(linkDisplayState({...qkpLow,activated:true}),'mixed',
  'generating photons AND consuming QKP is not a QKP-only link');
assert.equal(linkDisplayState({...qkpLow,activated:true,qkp_used_bps:0,fresh_used_bps:200}),'fresh');
assert.equal(linkVisualRate({...qkpLow,enabled:false}),0);
console.log('PASS: physical link rate scaling, QKP rate scaling, simultaneous optical/QKP states');

// v130: Three.js Color.setStyle parses comma-separated CSS hsl, while
// modern space-separated syntax used by MapLibre silently falls back white.
// Keep a shared, renderer-compatible value for map and 3D lanes.
for (const rate of [0, .1, .5, 1]) {
  const color=demandColor(0,rate);
  assert.match(color,/^hsl\([\d.]+, 91%, [\d.]+%\)$/,
    'MapLibre/THREE must receive a common comma-separated HSL color');
}
assert.notEqual(demandColor(0,.1),demandColor(0,1));
console.log('PASS: shared CSS3 HSL syntax for MapLibre and Three.js');

// v130: map and Three use the *same* fallback hues for non-demand links.
assert.equal(linkFallbackColor(rateFrame.links[0]),'#50cbd6');
assert.equal(linkFallbackColor(qkpLow),'#e0a35d');
assert.equal(linkFallbackColor({...qkpLow,activated:true}),'#80d4d4');
assert.equal(linkFallbackColor({...qkpLow,enabled:false}),'#a46768');
console.log('PASS: consistent fallback link colors across 2D and 3D');
