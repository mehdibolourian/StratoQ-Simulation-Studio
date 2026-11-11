/** A single four-case, 24-hour demonstration. Cues are observations of computed
 * frames, not fabricated solver decisions or promised outcomes. */
const periods = {
  clear: {start:0,end:25200,kind:'storage'},
  fog: {start:25200,end:37800,kind:'weather'},
  rain: {start:37800,end:61200,kind:'weather'},
  recovery: {start:61200,end:86400,kind:'recovery'},
};
export const SHOWCASE_STORIES = {
  'corridor-scar': {
    title:'1 · SCAR-Q: decide one slot at a time',
    question:'Which optical routes can the scarcity-first heuristic serve as conditions change?',
    mechanism:'SCAR-Q greedily prioritizes scarce routes. It uses the same 24-hour flight, ground stations, demands and weather as the other algorithms.',
    contrast:'Compare its actual served keys with MCR-Q and Optimal + QKP on; the online heuristics do not have the future information of the whole-horizon solver.',
    takeaways:['Track which demand is served and which route is selected.','Compare delivered/requested keys over the full day, not just one slot.'],
    steps:[
      {id:'scar-clear',...periods.clear,label:'Clear skies',signal:'routes',why:'Inspect demand colors and which optical paths SCAR-Q selects.'},
      {id:'scar-fog',...periods.fog,label:'Fog begins',signal:'service-drop',why:'Check delivered versus requested keys as optical conditions worsen.'},
      {id:'scar-rain',...periods.rain,label:'Rain overlaps',signal:'route-change',why:'Look for actual route changes; no change is assumed.'},
      {id:'scar-recovery',...periods.recovery,label:'Recovery',signal:'recovery',why:'See whether throughput improves after visibility returns.'},
    ],
  },
  'corridor-mcr': {
    title:'2 · MCR-Q: search candidate allocations',
    question:'Does evaluating alternative assignments help more demands get served?',
    mechanism:'MCR-Q samples several feasible assignments before solving each slot. All physical inputs match the other three scenarios.',
    contrast:'Compare full-day served keys and solver effort with SCAR-Q, and identify the full-horizon Optimal benchmark.',
    takeaways:['Observe candidate assignments and demand paths.','An improvement is not guaranteed and candidate evaluation costs computation.'],
    steps:[
      {id:'mcr-candidates',...periods.clear,label:'Try candidates',signal:'candidates',why:'Inspect how many candidate allocations were evaluated.'},
      {id:'mcr-fog',...periods.fog,label:'Fog begins',signal:'service-drop',why:'Watch whether more difficult optical conditions change served rates.'},
      {id:'mcr-rain',...periods.rain,label:'Weather overlap',signal:'route-change',why:'Watch for actual rerouting between candidate allocations.'},
      {id:'mcr-recovery',...periods.recovery,label:'Recovery',signal:'recovery',why:'Compare end-to-end served keys across the same horizon.'},
    ],
  },
  'qkp-enabled': {
    title:'3 · Optimal: QKP enabled',
    question:'Can storing keys before bad weather improve end-to-end service during bad weather?',
    mechanism:'The whole-horizon optimizer may generate spare link keys in clear slots, keep them in QKPs, and spend them when fresh link rates fall.',
    contrast:'Run Optimal · QKP off. Both share identical physical inputs and solver settings; only storage availability differs.',
    takeaways:['Look for actual inventory growth before fog and QKP draw while optical rates fall.','Compare the whole-day and storm-window served/requested key percentages; do not assume a particular gap.'],
    steps:[
      {id:'qkp-fill',...periods.clear,label:'Build reserves?',signal:'storage-build',why:'See whether stored key inventory increases during seven clear hours.'},
      {id:'qkp-fog',...periods.fog,label:'Fog begins',signal:'qkp-draw',why:'Inspect QKP consumption when the shared optical path is attenuated.'},
      {id:'qkp-rain',...periods.rain,label:'Use stored keys?',signal:'qkp-draw',why:'Follow actual QKP draw and demand delivery during overlapping fog and rain.'},
      {id:'qkp-recovery',...periods.recovery,label:'Recovery',signal:'recovery',why:'Compare all-day and storm-period service with QKP disabled.'},
    ],
  },
  'qkp-disabled': {
    title:'4 · Optimal: QKP disabled',
    question:'How much service can the same network deliver without carrying keys across slots?',
    mechanism:'Same whole-horizon optimizer, trajectory, weather, terminals and demands as Optimal · QKP on, but link-key storage is disabled.',
    contrast:'Switch to Optimal · QKP on to isolate the effect of QKP on measured end-to-end service.',
    takeaways:['QKP storage and draws should remain zero.','Compare the measured effect during the 10-hour fog interval and the full day.'],
    steps:[
      {id:'off-clear',...periods.clear,label:'Fresh keys only',signal:'routes',why:'The optimizer cannot preserve link keys for future slots.'},
      {id:'off-fog',...periods.fog,label:'Fog begins',signal:'service-drop',why:'Check delivered keys when fresh optical capacity falls.'},
      {id:'off-rain',...periods.rain,label:'Weather overlap',signal:'blocked',why:'Inspect reduced or blocked end-to-end demands while weather persists.'},
      {id:'off-recovery',...periods.recovery,label:'Recovery',signal:'recovery',why:'Compare total served keys with the QKP-enabled case.'},
    ],
  },
};

const nonneg = value => Math.max(0, Number(value)||0);
export const clockLabel = seconds => {
  const s=Math.max(0,Math.round(seconds));
  return `${String(Math.floor(s/3600)).padStart(2,'0')}:${String(Math.floor(s%3600/60)).padStart(2,'0')}`;
};
export function getSlotMeasurement(frame,previous=null) {
  if(!frame)return null;
  const demand=frame.demands||[];
  const requested=demand.reduce((v,d)=>v+nonneg(d.requested_bps),0);
  const served=demand.reduce((v,d)=>v+nonneg(d.served_bps),0);
  const links=frame.links||[];
  const blocked=demand.filter(d=>nonneg(d.requested_bps)>0 && nonneg(d.served_bps)<1e-6).length;
  const paths=demand.filter(d=>Array.isArray(d.path)&&d.path.length>0).map(d=>`${d.id}:${d.path.join('>')}`).sort().join('|');
  const previousPaths=(previous?.demands||[]).filter(d=>Array.isArray(d.path)&&d.path.length>0).map(d=>`${d.id}:${d.path.join('>')}`).sort().join('|');
  const stored=nonneg(frame.stored_bits_total);
  const deltaStored=previous ? stored-nonneg(previous.stored_bits_total):0;
  const prevRequested=(previous?.demands||[]).reduce((v,d)=>v+nonneg(d.requested_bps),0);
  const prevServed=(previous?.demands||[]).reduce((v,d)=>v+nonneg(d.served_bps),0);
  const satisfaction=requested ? served/requested : 1;
  const prevSatisfaction=prevRequested ? prevServed/prevRequested : 1;
  return {
    requested,served,satisfaction,blocked,stored,deltaStored,
    draw:nonneg(frame.qkp_drawn_link_bits),
    optical:links.filter(l=>l.activated).length,
    deltaOptical:previous ? links.filter(l=>l.activated).length-(previous.links||[]).filter(l=>l.activated).length:0,
    qkpOnly:links.filter(l=>l.allocated&&!l.activated).length,
    paths:demand.filter(d=>d.path?.length).length,
    routesChanged:!!previous && paths!==previousPaths,
    serviceChange:satisfaction-prevSatisfaction,
    candidates:nonneg(frame.optimizer?.candidate_solves),
  };
}
export function signalStrength(name, metrics) {
  if(!metrics)return 0;
  switch(name){
    case 'routes': return metrics.paths;
    case 'activation': return metrics.optical;
    case 'activation-change': return Math.abs(metrics.deltaOptical);
    case 'route-change': return metrics.routesChanged ? 1 : 0;
    case 'candidates': return Math.max(0,metrics.candidates-1);
    case 'blocked': return metrics.blocked;
    case 'storage-build': return Math.max(0,metrics.deltaStored);
    case 'storage-deplete': return Math.max(0,-metrics.deltaStored);
    case 'qkp-draw': return metrics.draw;
    case 'service-drop': return Math.max(0,-metrics.serviceChange);
    case 'recovery': return Math.max(0,metrics.serviceChange);
    case 'service': return metrics.served;
    default: return 0;
  }
}
/** Data-driven highlight chosen only within a curated story beat's time window. */
export function buildStoryMoments(presetId,scenario,result=null) {
  const story=SHOWCASE_STORIES[presetId];
  if(!story||!scenario?.config)return [];
  const seconds=nonneg(scenario.config.slot_seconds)||300;
  const horizon=nonneg(scenario.config.horizon_seconds)||seconds*nonneg(scenario.config.slots);
  const slots=Math.max(1,Math.ceil(horizon/seconds));
  const frames=Array.isArray(result?.frames)?result.frames:[];
  return story.steps.filter(step=>step.start<horizon).map(step=>{
    const from=Math.max(0,Math.min(slots-1,Math.ceil(step.start/seconds)));
    const until=Math.max(from,Math.min(slots-1,Math.floor((Math.min(step.end,horizon)-1e-7)/seconds)));
    let index=from, strength=0;
    if(frames.length){
      // The first matching slot is the default when the expected behavior
      // does not occur. Never invent an observed occurrence.
      for(let i=from;i<=Math.min(until,frames.length-1);i++){
        const s=signalStrength(step.signal,getSlotMeasurement(frames[i],frames[i-1]));
        if(s>strength){strength=s;index=i;}
      }
    }
    return {...step,index,fromIndex:from,toIndex:until,
      observed:frames.length>0&&strength>1e-8,
      hasResults:frames.length>0,
      timeSeconds:index*seconds,
      fromSeconds:step.start,
      toSeconds:Math.min(horizon,step.end),
      horizonSeconds:horizon,
      metrics:getSlotMeasurement(frames[index],frames[index-1]),
    };
  });
}
export const readableBits = bits => {
  const val=nonneg(bits);
  if(val>=1e9)return `${(val/1e9).toFixed(2)} Gbit`;
  if(val>=1e6)return `${(val/1e6).toFixed(2)} Mbit`;
  if(val>=1e3)return `${(val/1e3).toFixed(1)} kbit`;
  return `${val.toFixed(0)} bit`;
};
export function measuredCaption(m) {
  if(!m)return 'Run the simulation to inspect measured routes, service and QKP movement.';
  return `${(m.satisfaction*100).toFixed(1)}% served · ${m.paths} paths · ${m.optical} activated optical links · ${readableBits(m.draw)} QKP draw · ${readableBits(m.stored)} stored`;
}
