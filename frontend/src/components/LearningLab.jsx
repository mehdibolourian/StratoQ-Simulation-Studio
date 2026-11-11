import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, BrainCircuit, Cpu, Database, RefreshCcw, Play, Pause, StopCircle, Plus, Trash2, MousePointer2, Map as MapIcon, Rotate3D, Copy, SlidersHorizontal, ChevronDown } from 'lucide-react';
import Network3D from './Network3D.jsx';
import GeoMap from './GeoMap.jsx';
import { potentialLinks } from '../lib/topology.js';
import { CENTER } from '../lib/geo.js';

const DRAFT_KEY='stratoq.learning.network.v122';
// Exact defaults from the published piecewise reward expression.
const PAPER_REWARD={reward_success_threshold:.95,reward_success:1,
  reward_at_or_above_hi:.6,reward_above_hi_slope:.4,
  reward_between_base:.1,reward_between_gain:.1,reward_below_slope:1,
  reward_zero_service_guard:false};
// Compact illustrative preview; backend evaluates the same branch ordering.
function rewardPreview(rho, p, hi=.7, lo=.5) {
  if(p.reward_zero_service_guard && rho===0 && hi===0)return 0;
  if(rho>=p.reward_success_threshold)return p.reward_success;
  if(rho>=hi)return p.reward_at_or_above_hi+p.reward_above_hi_slope*(rho-hi);
  if(rho>=lo)return p.reward_between_base+p.reward_between_gain*(rho-lo)/(hi-lo+1e-8);
  return -p.reward_below_slope*(lo-rho);
}

const percentage = value => Number.isFinite(value) ? `${(value*100).toFixed(1)}%` : '—';
const bits = value => !Number.isFinite(value) ? '—' : value>=1e6 ? `${(value/1e6).toFixed(2)} Mbit` : `${(value/1e3).toFixed(1)} kbit`;
const clone = value => JSON.parse(JSON.stringify(value));
const clamp = (v,min,max) => Math.max(min,Math.min(max,Number(v)));
function readDraft() { try{return JSON.parse(localStorage.getItem(DRAFT_KEY)||'null');}catch{return null;} }
function shapeOf(sc) {
  if(!sc) return null;
  const ng=sc.ground_stations.length, nh=sc.balloons.length, nd=sc.demands.length;
  const obs=7*2*ng*nh+6*nd;
  return {n_gs:ng,n_haps:nh,n_demands:nd,observation_dim:obs,logits_dim:nh*(nd+1),hidden_dim:Math.max(64,Math.min(256,32*Math.ceil(obs/128)))};
}
// Bound chart DOM work even for a multi-thousand-episode training run.
// Min/max sampling keeps local spikes and the first/last measurement visible.
export function compactMetricHistory(rows, limit=2400) {
  if(rows.length<=limit)return rows;
  const bucketCount=Math.max(1,Math.floor((limit-2)/6));
  const picks=new Map([[0,rows[0]],[rows.length-1,rows[rows.length-1]]]);
  for(let k=0;k<bucketCount;k++) {
    const left=1+Math.floor(k*(rows.length-2)/bucketCount);
    const right=1+Math.floor((k+1)*(rows.length-2)/bucketCount);
    if(right<=left)continue;
    picks.set(left,rows[left]);picks.set(right-1,rows[right-1]);
    for(const key of ['train_reward','train_satisfaction']) {
      let low=Infinity,high=-Infinity,lo=-1,hi=-1;
      for(let i=left;i<right;i++) {
        const v=rows[i][key];
        if(!Number.isFinite(v))continue;
        if(v<low){low=v;lo=i;}if(v>high){high=v;hi=i;}
      }
      if(lo>=0)picks.set(lo,rows[lo]);
      if(hi>=0)picks.set(hi,rows[hi]);
    }
  }
  return [...picks.entries()].sort((a,b)=>a[0]-b[0]).map(([,v])=>v);
}
function compactPlotSeries(points,limit=1600) {
  if(points.length<=limit)return points;
  const n=Math.max(1,Math.floor((limit-2)/4));
  const picks=new Map([[0,points[0]],[points.length-1,points.at(-1)]]);
  for(let b=0;b<n;b++) {
    const lo=1+Math.floor((points.length-2)*b/n);
    const hi=1+Math.floor((points.length-2)*(b+1)/n);
    if(hi<=lo)continue;
    picks.set(lo,points[lo]);picks.set(hi-1,points[hi-1]);
    let min=lo,max=lo;
    for(let i=lo+1;i<hi;i++) {
      if(points[i].y<points[min].y)min=i;
      if(points[i].y>points[max].y)max=i;
    }
    picks.set(min,points[min]);picks.set(max,points[max]);
  }
  return [...picks.entries()].sort((a,b)=>a[0]-b[0]).map(([,v])=>v);
}
function policyParameters(shape) {
  if(!shape)return 0;
  const w=shape.hidden_dim, n=shape.observation_dim, a=shape.logits_dim;
  // Encoder Linear(n,w), two Residual(w,w,w), Actor(w,a), Critic(w,1).
  return (n+1)*w + 2*(2*w*w+2*w) + (w+1)*a + (w+1);
}
function PolicyArchitecture({shape,stats,episodes,slotCount}) {
  if(!shape)return null;
  const n=shape.n_gs, h=shape.n_haps, d=shape.n_demands, width=shape.hidden_dim;
  return <section className="ll-card ll-policy-card">
    <div className="ll-card-head"><div><strong>Actual PPO network & training diagnostics</strong><small>Fresh actor–critic sized to the current fixed network · parameters derived from the implementation</small></div></div>
    <div className="ll-network-graph" role="img" aria-label={`Neural architecture: ${shape.observation_dim} observation inputs to ${width} hidden units, two residual blocks, actor output ${shape.logits_dim} logits and critic output one value`}>
      <div className="ll-net-node"><span>Observation</span><b>{shape.observation_dim}</b><small>7 × {2*n*h} directed links + 6 × {d} demands</small></div>
      <div className="ll-net-arrow">→</div>
      <div className="ll-net-node"><span>Encoder</span><b>{width}</b><small>Linear + tanh</small></div>
      <div className="ll-net-arrow">→</div>
      <div className="ll-net-node ll-net-residual"><span>Residual × 2</span><b>{width}</b><small>Linear → tanh skip</small></div>
      <div className="ll-net-arrow">→</div>
      <div className="ll-net-heads"><div className="ll-net-node"><span>Actor</span><b>{shape.logits_dim}</b><small>{h} HAP × {d+1} choices</small></div><div className="ll-net-node"><span>Critic</span><b>1</b><small>State value</small></div></div>
    </div>
    <div className="ll-policy-facts"><span>Trainable weights <b>{policyParameters(shape).toLocaleString()}</b></span><span>Rollout <b>{slotCount??'—'} slots/episode</b></span><span>Completed <b>{episodes??0} episodes</b></span></div>
    <div className="ll-stats ll-diagnostics">
      <Summary label="Policy loss" value={Number.isFinite(stats?.policy_loss)?stats.policy_loss.toFixed(4):'—'} detail="PPO clipped surrogate"/>
      <Summary label="Value loss" value={Number.isFinite(stats?.value_loss)?stats.value_loss.toFixed(4):'—'} detail="Critic prediction error"/>
      <Summary label="Policy entropy" value={Number.isFinite(stats?.entropy)?stats.entropy.toFixed(4):'—'} detail="Mean action uncertainty"/>
      <Summary label="Entropy coefficient" value={Number.isFinite(stats?.entropy_coef)?stats.entropy_coef.toExponential(2):'—'} detail="Exploration regularization"/>
      <Summary label="Approx. PPO KL" value={Number.isFinite(stats?.approx_kl)?stats.approx_kl.toFixed(5):'—'} detail="Mean update divergence (not policy quality)"/>
      <Summary label="Clipped updates" value={Number.isFinite(stats?.clip_fraction)?percentage(stats.clip_fraction):'—'} detail="Fraction exceeding PPO clip range"/>
      <Summary label="Policy weight change" value={Number.isFinite(stats?.relative_weight_change)?percentage(stats.relative_weight_change):'—'} detail="Relative L2 parameter change this episode"/>
    </div>
    <p className="ll-caption">These are actual PPO update diagnostics, not throughput measurements. Training loss alone does not establish better network decisions; use frozen-checkpoint keys served for that comparison.</p>
  </section>;
}
function readableApiError(data, status) {
  if(typeof data?.detail==='string')return data.detail;
  if(Array.isArray(data?.detail))return data.detail.map(issue=>{
    const where=(issue.loc||[]).filter(x=>x!=='body').join('.');
    return `${where||'Request'}: ${issue.msg||'invalid value'}`;
  }).join(' · ');
  return data?.message||`HTTP ${status}`;
}
async function request(url,init) {
  const response=await fetch(url, {cache:'no-store',...init});
  const data=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(readableApiError(data,response.status));
  return data;
}
function Summary({label,value,detail}) { return <div className="ll-summary"><small>{label}</small><strong>{value}</strong>{detail&&<span>{detail}</span>}</div>; }
function PerformanceChart({metrics,checkpoints,selectedEpisode,view,live,totalEpisodes,finished}) {
  const isSat=view==='satisfaction';
  const train=metrics.filter(m=>Number.isFinite(isSat?m.train_satisfaction:m.train_reward))
    .map(m=>({x:m.episode,y:isSat?m.train_satisfaction:m.train_reward}));
  // Frozen evaluations use keys-served satisfaction rather than the
  // heuristic-relative training reward. Never overlay these as if comparable.
  const evalPoints=isSat?checkpoints.filter(c=>Number.isFinite(c.evaluation_satisfaction))
    .map(c=>({x:c.episode,y:c.evaluation_satisfaction})):[];
  // A 25-episode trailing average exposes the long-run trend behind noisy PPO rollouts.
  const smoothed=[];
  if(!isSat && train.length>=5) {
    const window=25;
    let sum=0;
    for(let i=0;i<train.length;i++) {
      sum+=train[i].y;
      if(i>=window)sum-=train[i-window].y;
      smoothed.push({x:train[i].x,y:sum/Math.min(i+1,window)});
    }
  }
  const isLive=live && !live.episode_complete && live.slots_done>0 &&
    (live.stage==='training'||live.stage==='initial-evaluation'||live.stage==='checkpoint-evaluation');
  const partial=isLive && (isSat || live.stage==='training') ? {
    x:live.stage==='training' ? Math.max(0,live.episode-1)+live.slots_done/Math.max(1,live.slots_total) : live.episode,
    y:isSat?live.partial_satisfaction:live.partial_reward,
    series:live.stage==='training'?'training':'evaluation',
  }:null;
  const series=[{name:isSat?'Training · keys served':'Training · heuristic-relative reward',values:compactPlotSeries(train),color:'#78cfc1'},
                {name:isSat?'Frozen evaluation · keys served':'Reward · trailing 25-episode average',values:compactPlotSeries(isSat?evalPoints:smoothed),color:'#e6bc76'}];
  const validPartial=partial&&Number.isFinite(partial.y)?partial:null;
  const points=[...series[0].values,...series[1].values,...(validPartial?[validPartial]:[])];
  if(!points.length) return <div className="ll-chart-empty">Waiting for first measured optical/LP result. Live slot progress appears above during setup and evaluation.</div>;
  const lastSeen=points.reduce((max,p)=>Math.max(max,p.x),0);
  const end=finished ? Math.max(1,totalEpisodes||1) : Math.max(2,Math.ceil(lastSeen));
  const low=isSat ? 0 : points.reduce((lo,p)=>Math.min(lo,p.y),-.2);
  const high=isSat ? 1 : points.reduce((hi,p)=>Math.max(hi,p.y),1);
  const X=x=>58+730*x/end, Y=y=>234-191*(y-low)/Math.max(.0001,high-low);
  // Never render thousands of overlapping SVG circles. Thin the visual marks
  // as more episodes arrive; line segments still represent the history.
  const count=train.length+evalPoints.length;
  const dotRadius=count<30?3:count<100?2.1:count<350?1.25:.75;
  const showAllDots=count<=900;
  return <div className="ll-chart">
    <svg viewBox="0 0 825 275" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Continuously updated PPO performance measurements">
      {[0,.25,.5,.75,1].map((f,i)=><g key={i}><line x1="58" x2="788" y1={Y(low+(high-low)*f)} y2={Y(low+(high-low)*f)} stroke="rgba(137,170,181,.15)" strokeDasharray="4 5" />
        <text x="49" y={Y(low+(high-low)*f)+4} fill="#9bb1c3" fontSize="12" textAnchor="end">{isSat?`${Math.round(f*100)}%`:(low+(high-low)*f).toFixed(2)}</text></g>)}
      {series.map(s=><g key={s.name}>
        {s.values.length>1&&<polyline fill="none" stroke={s.color} strokeWidth={count>400?1.5:2.3} strokeLinejoin="round" points={s.values.map(p=>`${X(p.x)},${Y(p.y)}`).join(' ')}/>}
        {showAllDots?s.values.map(p=><circle key={p.x} cx={X(p.x)} cy={Y(p.y)} r={dotRadius} fill={s.color}/>):s.values.length>0&&<circle cx={X(s.values.at(-1).x)} cy={Y(s.values.at(-1).y)} r="2.2" fill={s.color}/>}
      </g>)}
      {validPartial&&<g>
        {validPartial.series==='training'&&train.length>0&&<line x1={X(train[train.length-1].x)} y1={Y(train[train.length-1].y)} x2={X(validPartial.x)} y2={Y(validPartial.y)} stroke="#78cfc1" strokeDasharray="4 5" strokeWidth="1.5" />}
        <circle className="ll-live-dot" cx={X(validPartial.x)} cy={Y(validPartial.y)} r="4" fill={validPartial.series==='training'?'#8af4d5':'#e6bc76'} stroke="#122935" strokeWidth="1.5" /></g>}
      {selectedEpisode!==null&&selectedEpisode<=end&&<line x1={X(selectedEpisode)} x2={X(selectedEpisode)} y1="34" y2="235" stroke="#f0d2aa" strokeWidth="1" strokeDasharray="5 5"/>}
      <text x="58" y="263" fill="#9bb1c3" fontSize="12">Episode 0</text><text x="788" y="263" fill="#9bb1c3" fontSize="12" textAnchor="end">Episode {end}{!finished?' · live scale':''}</text>
    </svg>
    <div className="ll-legend">{series.filter(s=>s.values.length).map(s=><span key={s.name}><i style={{background:s.color}} />{s.name}</span>)}{validPartial&&<span>● Live slot-level measurement</span>}</div>
  </div>;
}
function NumberSetting({title,value,onChange,min,max,step='any',disabled=false,hint}) {
  return <label>{title}<input disabled={disabled} type="number" step={step} min={min} max={max} value={value} onChange={e=>{if(e.target.value!=='') onChange(Number(e.target.value));}} />{hint&&<small className="ll-hint">{hint}</small>}</label>;
}

export default function LearningLab({studioScenario}) {
  const [preset,setPreset]=useState(null);
  const [draft,setDraft]=useState(readDraft);
  const [selectedNode,setSelectedNode]=useState(null);
  const [dragMode,setDragMode]=useState(true);
  const [mapMode,setMapMode]=useState(false);
  const [sceneMode,setSceneMode]=useState('edit');
  const [sceneKey,setSceneKey]=useState(0);
  const [slotSeconds,setSlotSeconds]=useState(300);
  const [horizonMinutes,setHorizonMinutes]=useState(120);
  const computedSlots=horizonMinutes*60/slotSeconds;
  const validTimeGrid=Number.isInteger(computedSlots)&&computedSlots>=1&&computedSlots<=288&&
    Number.isInteger(slotSeconds)&&slotSeconds>=1&&slotSeconds<=3600&&
    Number.isInteger(horizonMinutes)&&horizonMinutes>=1&&horizonMinutes<=1440;
  const [episodes,setEpisodes]=useState(48);
  const [interval,setInterval]=useState(6);
  const [checkpointPage,setCheckpointPage]=useState(null);
  const [seed,setSeed]=useState(42);
  const [params,setParams]=useState({learning_rate:.0002,gamma:.99,gae_lambda:.95,clip:.2,ppo_epochs:8,batch_size:16,entropy_start:.008,entropy_end:.0003,
    compare_baselines:false,curriculum_enabled:true,curriculum_first_demands:1,curriculum_second_demands:2,curriculum_first_end_pct:12,curriculum_second_end_pct:30});
  const [rewardParams,setRewardParams]=useState(()=>({...PAPER_REWARD}));
  const [job,setJob]=useState(null);
  const [metrics,setMetrics]=useState([]);
  const [live,setLive]=useState({});
  const [evaluation,setEvaluation]=useState(null);
  const [selected,setSelected]=useState(null);
  const [slot,setSlot]=useState(0);
  const [playing,setPlaying]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [working,setWorking]=useState(false);
  const [chartView,setChartView]=useState('satisfaction');
  const canTrain=!job || ['failed','complete','stopped'].includes(job.status);
  const draftShape=useMemo(()=>shapeOf(draft),[draft]);
  const progressRef=useRef(0);
  const metricCursorRef=useRef(0);

  useEffect(()=>{request('/api/learning/preset?slots=24').then(p=>{setPreset(p);setDraft(old=>old||p.scenario);}).catch(e=>setError(e.message));},[]);
  useEffect(()=>{if(draft) localStorage.setItem(DRAFT_KEY,JSON.stringify(draft));},[draft]);
  useEffect(()=>{request('/api/learning/latest').then(x=>{if(x)setJob(x);}).catch(()=>{});},[]);
  useEffect(()=>{
    if(!job?.id)return;
    let mounted=true,seq=0, timer=null, terminal=false;
    metricCursorRef.current=0;setMetrics([]);
    const poll=async()=>{
      if(!mounted)return;
      const current=++seq;
      const since=metricCursorRef.current;
      try{
        const [status,series,currentLive]=await Promise.all([
          request(`/api/learning/runs/${job.id}`),request(`/api/learning/runs/${job.id}/metrics?since=${since}&max_points=${since===0?1800:0}`),request(`/api/learning/runs/${job.id}/live`)]);
        if(mounted && current>=progressRef.current){progressRef.current=current;setJob(status);metricCursorRef.current=Math.max(since,series.at(-1)?.episode||0);setMetrics(old=>compactMetricHistory(since===0?series:[...old,...series]));setLive(currentLive||{});terminal=['complete','failed','stopped'].includes(status.status);}
      }catch(e){if(mounted)setError(e.message);}
      finally {if(mounted&&!terminal)timer=setTimeout(poll,750);}
    };
    progressRef.current=0;
    poll();
    return()=>{mounted=false;clearTimeout(timer);};
  },[job?.id]);
  const checkpoints=job?.checkpoints||[];
  const checkpointPages=Math.max(1,Math.ceil(checkpoints.length/200));
  const shownCheckpointPage=checkpointPage===null?checkpointPages-1:Math.min(checkpointPage,checkpointPages-1);
  const visibleCheckpoints=checkpoints.slice(shownCheckpointPage*200,(shownCheckpointPage+1)*200);
  useEffect(()=>{
    if(!checkpoints.length)return;
    if(selected===null || !checkpoints.some(c=>c.episode===selected))setSelected(checkpoints[checkpoints.length-1].episode);
  },[checkpoints.length,job?.id]);
  useEffect(()=>{
    if(!job?.id||selected===null)return;
    let mounted=true;
    setEvaluation(null);setSlot(0);setPlaying(false);
    request(`/api/learning/runs/${job.id}/evaluation/${selected}`).then(v=>{if(mounted)setEvaluation(v);})
      .catch(e=>{if(mounted)setError(e.message);});
    return()=>{mounted=false;};
  },[job?.id,selected]);
  const frames=evaluation?.frames||[];
  useEffect(()=>{if(!playing||!frames.length)return;const timer=setInterval(()=>setSlot(i=>(i+1)%frames.length),750);return()=>clearInterval(timer);},[playing,frames.length]);
  const frame=frames[Math.min(slot,Math.max(0,frames.length-1))]||null;
  const sceneScenario=sceneMode==='edit' ? draft : evaluation?.scenario||draft;
  const visualLinks=useMemo(()=>sceneScenario?potentialLinks(sceneScenario,sceneMode==='replay'?frame:null,true):[],[sceneScenario,sceneMode,frame]);
  const currentCheckpoint=checkpoints.find(c=>c.episode===selected);
  const finalMetric=metrics.at(-1);
  const baseline=evaluation?.baselines?.scar_q_bits!==undefined?evaluation.baselines:job?.baselines;
  const requested=evaluation?.summary?.requested_bits;
  const editLock=!canTrain;
  const isTraining=job?.status==='running'||job?.status==='queued';
  const stageText={queued:'Starting learning worker', 'physical-rates':'Computing Balloon-QNet optical rates', 'initial-evaluation':'Evaluating untrained policy', 'baseline-evaluation':'Evaluating SCAR-Q / MCR-Q', 'checkpoint-evaluation':'Evaluating frozen checkpoint',training:'Training PPO · Gurobi per-slot allocation','ppo-update':'Updating PPO policy weights',complete:'Training complete',failed:'Training failed',stopped:'Stopped'};
  const stage=job?.stage||'queued';

  function edit(mutator){if(editLock)return;setDraft(old=>{const next=clone(old);mutator(next);return next;});}
  function updateItem(id,key,value){edit(sc=>{for(const group of ['ground_stations','balloons','demands','weather_regions']) {const item=sc[group].find(x=>x.id===id);if(item){item[key]=value;break;}}});}
  function moveNode(id,lat,lon){edit(sc=>{const node=[...sc.ground_stations,...sc.balloons,...sc.weather_regions].find(x=>x.id===id);if(node){node.lat=clamp(lat,-90,90);node.lon=clamp(lon,-180,180);}});}
  function add(kind){
    if(editLock)return;
    if(kind==='demand'&&draft.ground_stations.length<2){setError('Add at least two ground stations first.');return;}
    const id=`ll-${kind}-${Date.now().toString(36)}`,n=(draft[kind==='gs'?'ground_stations':kind==='hap'?'balloons':kind==='demand'?'demands':'weather_regions']||[]).length;
    const midLat=draft.ground_stations.reduce((s,g)=>s+g.lat,0)/Math.max(1,draft.ground_stations.length)||CENTER.lat;
    const midLon=draft.ground_stations.reduce((s,g)=>s+g.lon,0)/Math.max(1,draft.ground_stations.length)||CENTER.lon;
    edit(sc=>{
      if(kind==='gs')sc.ground_stations.push({id,name:`GS ${n+1}`,lat:midLat+.08*(n%3),lon:midLon+.10*(n%4),capacity_bits:8e6,n_rx:1,n_tx:1,yaw_deg:0});
      if(kind==='hap')sc.balloons.push({id,name:`HAP ${n+1}`,lat:midLat+.06*(n%3),lon:midLon+.06*(n%4),altitude_km:15,coverage_km:210,capacity_bits:12e6,n_rx:1,n_tx:1,yaw_deg:0});
      if(kind==='demand')sc.demands.push({id,source:sc.ground_stations[0].id,target:sc.ground_stations[1].id,rate_bps:3000,pattern:'constant'});
      if(kind==='weather')sc.weather_regions.push({id,name:`Fog ${n+1}`,lat:midLat,lon:midLon,radius_km:18,attenuation_db:0,effect:'fog',visibility_km:.5});
    });setSelectedNode(id);
  }
  function removeNode(){if(!selectedNode||editLock)return;
    edit(sc=>{for(const group of ['ground_stations','balloons','demands','weather_regions'])sc[group]=sc[group].filter(x=>x.id!==selectedNode);
      sc.demands=sc.demands.filter(d=>d.source!==selectedNode&&d.target!==selectedNode);
      sc.link_overrides=(sc.link_overrides||[]).filter(o=>o.source!==selectedNode&&o.target!==selectedNode);});setSelectedNode(null);
  }
  function copyStudio(){
    if(editLock||!studioScenario)return;
    const snap=clone(studioScenario);
    const moving=snap.balloons.filter(h=>h.trajectory_id);
    // Explicit snapshot semantics: the Learning Lab trains fixed node locations,
    // never silently reuses moving trajectories during its episodes.
    for(const h of moving){delete h.trajectory_id;delete h.trajectory_name;delete h.trajectory_duration_seconds;}
    setNotice(moving.length?`Imported ${moving.length} trajectory-bearing HAP(s) as static snapshots at their currently configured coordinates. Original Studio trajectories were not modified.`:'Copied current Network Studio experiment for independent editing.');
    setDraft(snap);setSelectedNode(null);setSceneMode('edit');
  }
  function resetPreset(){if(editLock)return;if(!preset)return;setDraft(clone(preset.scenario));setSelectedNode(null);setSceneMode('edit');setNotice('Ontario example restored in the Learning Lab only.');}
  const selectedData=draft && ['ground_stations','balloons','demands','weather_regions'].map(g=>({group:g,item:draft[g].find(x=>x.id===selectedNode)})).find(x=>x.item);
  const item=selectedData?.item;
  const setParam=(key,v)=>setParams(old=>({...old,[key]:v}));
  const setRewardParam=(key,v)=>setRewardParams(old=>({...old,[key]:v}));
  const updateLink=(id,enabled)=>edit(sc=>{const [source,target]=id.split(':');const old=(sc.link_overrides||[]).find(x=>x.source===source&&x.target===target);sc.link_overrides=(sc.link_overrides||[]).filter(x=>!(x.source===source&&x.target===target));sc.link_overrides.push({...old,source,target,enabled});});
  async function start(){
    setError('');setWorking(true);
    try{
      if(!draft)throw new Error('Prepare a learning topology first.');
      if(draft.ground_stations.length<2||!draft.balloons.length||!draft.demands.length)throw new Error('Learning needs at least two GSs, one HAP and one demand.');
      if(!Number.isSafeInteger(episodes)||episodes<1||!Number.isSafeInteger(interval)||interval<1)throw new Error('Episodes and checkpoint interval must be positive, safe integers.');
      if(!validTimeGrid)throw new Error('Time horizon must be a whole number of slots (1–288), lasting at most 24 hours. Adjust slot length or horizon.');
      for(const [key,value] of Object.entries(rewardParams)) {
        if(key==='reward_zero_service_guard')continue;
        const upper=key==='reward_success_threshold'?1:['reward_below_slope','reward_above_hi_slope'].includes(key)?5:2;
        if(!Number.isFinite(value)||value<0||value>upper)
          throw new Error(`Reward constant ${key} must be between 0 and ${upper}.`);
      }
      const {curriculum_enabled,compare_baselines,...otherParams}=params;
      const curriculumParams=curriculum_enabled?otherParams:Object.fromEntries(Object.entries(otherParams).filter(([key])=>!key.startsWith('curriculum_')));
      const run=await request('/api/learning/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preset:'ontario-compact-v1',scenario:draft,slots:computedSlots,slot_seconds:slotSeconds,episodes,checkpoint_every:interval,seed,curriculum_enabled,compare_baselines,...curriculumParams,...rewardParams})});
      setJob(run);metricCursorRef.current=0;setMetrics([]);setLive({});setEvaluation(null);setSelected(null);setCheckpointPage(null);setSlot(0);
    }catch(e){setError(e.message);}finally{setWorking(false);}
  }
  async function stop(){if(!job?.id)return;setWorking(true);try{setJob(await request(`/api/learning/runs/${job.id}/stop`,{method:'POST'}));}catch(e){setError(e.message);}finally{setWorking(false);}}
  const stageProgress=job?.slot_progress;
  const nowSlot=live?.slots_done&&live.stage==='training'?live.slots_done:stageProgress?.completed;
  const prog=job?.status==='complete'?100:(job?.episodes ?Math.min(99,100*((job.episode||0)+(isTraining&&live?.stage==='training'&&!live.episode_complete?(live.slots_done||0)/Math.max(1,live.slots_total):0))/job.episodes):0);
  return <main className="ll-body">
    <section className="ll-intro"><div className="ll-kicker"><BrainCircuit size={15}/> REINFORCEMENT LEARNING WORKSPACE</div>
      <h1>StratoQ <span>Learning Lab</span></h1>
      <p>Arrange a network, train a fresh topology-sized PPO agent, and watch measured performance arrive slot by slot. Fixed geometry for each training run, with real optical rates and Gurobi allocation.</p>
      <div className="ll-caveat"><AlertCircle size={16}/><span>Studio-specific learning experiment, not the paper's held-out flight evaluation. Editing the network creates a new experiment; existing checkpoints do not transfer across topologies.</span></div>
    </section>
    {error&&<div className="ll-error"><AlertCircle size={16}/>{error}<button onClick={()=>setError('')}>Dismiss</button></div>}
    {notice&&<div className="ll-info">{notice}<button onClick={()=>setNotice('')}>Dismiss</button></div>}
    <div className="ll-columns">
      <aside className="ll-config">
        <div className="ll-panel-title"><MousePointer2 size={17}/> Fixed network editor</div>
        <div className="ll-edit-actions"><button onClick={copyStudio} disabled={editLock} title="Copy the active Network Studio experiment"><Copy size={14}/> Use Studio network</button><button onClick={resetPreset} disabled={editLock}><RefreshCcw size={13}/> Ontario preset</button></div>
        <p className="ll-caption">Arrange nodes in the 3D scene (Move mode), or drag markers on the map. Configure demands and links below. Editing is locked during training.</p>
        <div className="ll-edit-actions ll-add-actions"><button disabled={editLock} onClick={()=>add('gs')}><Plus size={13}/> GS</button><button disabled={editLock} onClick={()=>add('hap')}><Plus size={13}/> HAP</button><button disabled={editLock} onClick={()=>add('demand')}><Plus size={13}/> Demand</button><button disabled={editLock} onClick={()=>add('weather')}><Plus size={13}/> Weather</button></div>
        <label>Selected object<select value={selectedNode||''} onChange={e=>setSelectedNode(e.target.value||null)}><option value="">Select a node or demand</option>{draft?.ground_stations.map(x=><option key={x.id} value={x.id}>GS · {x.name}</option>)}{draft?.balloons.map(x=><option key={x.id} value={x.id}>HAP · {x.name}</option>)}{draft?.demands.map(x=><option key={x.id} value={x.id}>Demand · {x.id}</option>)}{draft?.weather_regions.map(x=><option key={x.id} value={x.id}>Weather · {x.name}</option>)}</select></label>
        {item&&<div className="ll-entity-editor">
          {selectedData.group==='demands'?<div className="ll-caption">Demand ID: <code>{item.id}</code></div>:<label>Name<input disabled={editLock} value={item.name??''} onChange={e=>updateItem(item.id,'name',e.target.value)}/></label>}
          {item.trajectory_id&&<button className="ll-remove" onClick={()=>edit(sc=>{const h=sc.balloons.find(h=>h.id===item.id);if(h){delete h.trajectory_id;delete h.trajectory_name;delete h.trajectory_duration_seconds;}})}>Use fixed position (remove trajectory)</button>}
          {item.lat!==undefined&&<div className="ll-pair"><NumberSetting title="Latitude" disabled={editLock} min={-90} max={90} value={item.lat} onChange={v=>updateItem(item.id,'lat',v)}/><NumberSetting title="Longitude" disabled={editLock} min={-180} max={180} value={item.lon} onChange={v=>updateItem(item.id,'lon',v)}/></div>}
          {selectedData.group==='balloons'&&<div className="ll-pair"><NumberSetting title="Altitude · km" disabled={editLock} min={1} max={50} value={item.altitude_km} onChange={v=>updateItem(item.id,'altitude_km',v)}/><NumberSetting title="Coverage · km" disabled={editLock} min={1} max={500} value={item.coverage_km} onChange={v=>updateItem(item.id,'coverage_km',v)}/></div>}
          {['ground_stations','balloons'].includes(selectedData.group)&&<><NumberSetting title="QKP capacity · bits" disabled={editLock} min={1} value={item.capacity_bits} onChange={v=>updateItem(item.id,'capacity_bits',v)}/><div className="ll-pair"><NumberSetting title="N_TX" disabled={editLock} min={0} max={10000} step={1} value={item.n_tx??1} onChange={v=>updateItem(item.id,'n_tx',v)}/><NumberSetting title="N_RX" disabled={editLock} min={0} max={10000} step={1} value={item.n_rx??1} onChange={v=>updateItem(item.id,'n_rx',v)}/></div></>}
          {selectedData.group==='demands'&&<><label>Source GS<select disabled={editLock} value={item.source} onChange={e=>updateItem(item.id,'source',e.target.value)}>{draft.ground_stations.filter(g=>g.id!==item.target).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label><label>Destination GS<select disabled={editLock} value={item.target} onChange={e=>updateItem(item.id,'target',e.target.value)}>{draft.ground_stations.filter(g=>g.id!==item.source).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label><NumberSetting title="Mean key demand · bps" disabled={editLock} min={.01} max={1e9} value={item.rate_bps} onChange={v=>updateItem(item.id,'rate_bps',v)}/><label>Demand pattern<select disabled={editLock} value={item.pattern||'constant'} onChange={e=>updateItem(item.id,'pattern',e.target.value)}><option value="constant">Constant</option><option value="diurnal">Diurnal</option><option value="dual_peak">Dual peak</option><option value="bursty">Bursty</option></select></label></>}
          {selectedData.group==='weather_regions'&&<><label>Type<select disabled={editLock} value={item.effect||'fog'} onChange={e=>updateItem(item.id,'effect',e.target.value)}><option value="fog">Fog</option><option value="rain">Rain</option><option value="snow">Snow</option></select></label><NumberSetting title="Region radius · km" disabled={editLock} min={.1} value={item.radius_km} onChange={v=>updateItem(item.id,'radius_km',v)}/>{item.effect==='fog'?<NumberSetting title="Visibility · km" disabled={editLock} min={.01} value={item.visibility_km??.5} onChange={v=>updateItem(item.id,'visibility_km',v)}/>:<NumberSetting title="Precipitation · mm/h" disabled={editLock} min={0} value={item.precipitation_rate_mm_h??5} onChange={v=>updateItem(item.id,'precipitation_rate_mm_h',v)}/>}</>}
          <button className="ll-remove" disabled={editLock} onClick={removeNode}><Trash2 size={13}/> Remove selected</button>
        </div>}
        <details className="ll-section"><summary>Optical link enable/disable <ChevronDown size={13}/></summary><div className="ll-link-grid">{draft?.ground_stations.flatMap(g=>draft.balloons.map(h=>{const id=`${g.id}:${h.id}`;const enabled=draft.link_overrides?.find(o=>o.source===g.id&&o.target===h.id)?.enabled!==false;return <label key={id} className="ll-link-toggle"><input type="checkbox" disabled={editLock} checked={enabled} onChange={e=>updateLink(id,e.target.checked)}/><span>{g.name} ↔ {h.name}</span></label>;}))}</div></details>
        <div className="ll-panel-title"><Cpu size={17}/> Training configuration</div>
        <div className="ll-architecture"><strong>Fresh PPO network · topology-scaled</strong><div><span>GS / HAP / demands</span><b>{draftShape?`${draftShape.n_gs} / ${draftShape.n_haps} / ${draftShape.n_demands}`:'—'}</b></div><div><span>Observation inputs</span><b>{draftShape?.observation_dim??'—'}</b></div><div><span>Action logits</span><b>{draftShape?.logits_dim??'—'}</b></div><div><span>Hidden units</span><b>{draftShape?.hidden_dim??'—'}</b></div><small>Each run begins from newly initialized weights sized to this topology.</small></div>
        <div className="ll-pair"><NumberSetting title={<span className="ll-two-line">Slot length<span>seconds</span></span>} min={1} max={3600} step={1} disabled={editLock} value={slotSeconds} onChange={setSlotSeconds}/><NumberSetting title={<span className="ll-two-line">Episode horizon<span>minutes</span></span>} min={1} max={1440} step={1} disabled={editLock} value={horizonMinutes} onChange={setHorizonMinutes}/></div>
        <p className={`ll-caption ${validTimeGrid?'':'ll-time-invalid'}`}>{validTimeGrid?`${computedSlots} time slots × ${slotSeconds} s = ${horizonMinutes} min per episode. The PPO architecture depends on GS/HAP/demand counts; this time grid sets rollout steps and temporal physics samples.`:'Select an integer number of slots (1–288), with a horizon up to 24 hours.'}</p>
        <div className="ll-pair"><NumberSetting title="Episodes" min={1} step={1} disabled={editLock} value={episodes} onChange={v=>setEpisodes(Math.max(1,Math.trunc(v)))}/><NumberSetting title="Checkpoint every" min={1} step={1} disabled={editLock} value={interval} onChange={v=>setInterval(Math.max(1,Math.trunc(v)))}/></div>
        <NumberSetting title="Random seed" min={0} max={2147483647} step={1} disabled={editLock} value={seed} onChange={v=>setSeed(clamp(v,0,2147483647))}/>
        <details className="ll-section" open><summary><SlidersHorizontal size={14}/> PPO hyperparameters <ChevronDown size={13}/></summary>
          <div className="ll-pair"><NumberSetting title="Learning rate" disabled={editLock} min={1e-7} max={.01} value={params.learning_rate} onChange={v=>setParam('learning_rate',v)}/><NumberSetting title="Discount γ" disabled={editLock} min={0} max={1} step={.01} value={params.gamma} onChange={v=>setParam('gamma',v)}/></div>
          <div className="ll-pair"><NumberSetting title="GAE λ" disabled={editLock} min={0} max={1} step={.01} value={params.gae_lambda} onChange={v=>setParam('gae_lambda',v)}/><NumberSetting title="PPO clip ε" disabled={editLock} min={.01} max={.5} step={.01} value={params.clip} onChange={v=>setParam('clip',v)}/></div>
          <div className="ll-pair"><NumberSetting title="Update epochs" disabled={editLock} min={1} max={30} step={1} value={params.ppo_epochs} onChange={v=>setParam('ppo_epochs',v)}/><NumberSetting title="Mini-batch size" disabled={editLock} min={1} max={1024} step={1} value={params.batch_size} onChange={v=>setParam('batch_size',v)}/></div>
          <div className="ll-pair"><NumberSetting title="Entropy start" disabled={editLock} min={0} max={1} value={params.entropy_start} onChange={v=>setParam('entropy_start',v)}/><NumberSetting title="Entropy end" disabled={editLock} min={0} max={1} value={params.entropy_end} onChange={v=>setParam('entropy_end',v)}/></div>
          <p className="ll-caption">Entropy coefficient decreases linearly from start to end. The demo defaults favor more updates and less late-stage exploration. Checkpoints are evaluated with all demands and no exploration. Only the fixed evaluation curve compares identical workloads when curriculum is active.</p>
        </details>
        <details className="ll-section"><summary><SlidersHorizontal size={14}/> Reward function · advanced <ChevronDown size={13}/></summary>
          <p className="ll-caption">Edit the constants in the paper's four-branch heuristic-relative reward. Each new run saves these exact values; existing runs/checkpoints are unaffected. The numerical stability ε = 10⁻⁸ is fixed.</p>
          <div className="ll-pair"><NumberSetting title="Success threshold ρ ≥" disabled={editLock} min={0} max={1} step={.01} value={rewardParams.reward_success_threshold} onChange={v=>setRewardParam('reward_success_threshold',v)}/><NumberSetting title="Success reward · 1" disabled={editLock} min={0} max={2} step={.05} value={rewardParams.reward_success} onChange={v=>setRewardParam('reward_success',v)}/></div>
          <div className="ll-pair"><NumberSetting title="Match-best bonus · 0.6" disabled={editLock} min={0} max={2} step={.05} value={rewardParams.reward_at_or_above_hi} onChange={v=>setRewardParam('reward_at_or_above_hi',v)}/><NumberSetting title="Above-best slope · 0.4" disabled={editLock} min={0} max={5} step={.05} value={rewardParams.reward_above_hi_slope} onChange={v=>setRewardParam('reward_above_hi_slope',v)}/></div>
          <div className="ll-pair"><NumberSetting title="Between-baselines base · 0.1" disabled={editLock} min={0} max={2} step={.05} value={rewardParams.reward_between_base} onChange={v=>setRewardParam('reward_between_base',v)}/><NumberSetting title="Between-baselines gain · 0.1" disabled={editLock} min={0} max={2} step={.05} value={rewardParams.reward_between_gain} onChange={v=>setRewardParam('reward_between_gain',v)}/></div>
          <NumberSetting title="Below-worst penalty factor · 1" disabled={editLock} min={0} max={5} step={.1} value={rewardParams.reward_below_slope} onChange={v=>setRewardParam('reward_below_slope',v)}/>
          <label className="ll-checkbox"><input type="checkbox" disabled={editLock} checked={rewardParams.reward_zero_service_guard} onChange={e=>setRewardParam('reward_zero_service_guard',e.target.checked)}/> Do not reward zero service when both heuristics also serve zero (experimental safeguard)</label>
          <p className="ll-caption">Preview with best heuristic 70% and weaker heuristic 50%: agent satisfaction 69% → {rewardPreview(.69,rewardParams).toFixed(3)} · 70% → {rewardPreview(.7,rewardParams).toFixed(3)} · 80% → {rewardPreview(.8,rewardParams).toFixed(3)} · 95% → {rewardPreview(.95,rewardParams).toFixed(3)}. When all three serve 0: {rewardPreview(0,rewardParams,0,0).toFixed(3)}.</p>
          <p className="ll-caption">Lower the match-best bonus and/or increase the above-best slope to reward actual improvements over merely matching a heuristic. A separate jump remains at the success threshold; these controls do not guarantee learning.</p>
          <button className="ll-refresh" disabled={editLock} onClick={()=>setRewardParams({...PAPER_REWARD})}><RefreshCcw size={13}/> Restore paper defaults</button>
        </details>
        <details className="ll-section" open><summary>Curriculum learning <ChevronDown size={13}/></summary>
          <label className="ll-checkbox"><input disabled={editLock} type="checkbox" checked={params.curriculum_enabled} onChange={e=>setParam('curriculum_enabled',e.target.checked)}/> Increase the number of active demands in three stages</label>
          {params.curriculum_enabled&&<><div className="ll-pair"><NumberSetting title="Stage 1 · demands" disabled={editLock} min={1} max={20} step={1} value={params.curriculum_first_demands} onChange={v=>setParam('curriculum_first_demands',v)}/><NumberSetting title="Stage 2 · demands" disabled={editLock} min={1} max={20} step={1} value={params.curriculum_second_demands} onChange={v=>setParam('curriculum_second_demands',v)}/></div>
          <div className="ll-pair"><NumberSetting title="Stage 1 ends · %" disabled={editLock} min={1} max={98} step={1} value={params.curriculum_first_end_pct} onChange={v=>setParam('curriculum_first_end_pct',v)}/><NumberSetting title="Stage 2 ends · %" disabled={editLock} min={2} max={99} step={1} value={params.curriculum_second_end_pct} onChange={v=>setParam('curriculum_second_end_pct',v)}/></div></>}
          <p className="ll-caption">Stages use {params.curriculum_first_demands} → {params.curriculum_second_demands} → all {draft?.demands.length||0} demands (clamped to network size). With these settings, stage 3 has {Math.max(0,episodes-Math.max(1,Math.round(episodes*params.curriculum_second_end_pct/100)))} of {episodes} episodes. Frozen checkpoint evaluations always include all demands.</p>
        </details>
        <label className="ll-checkbox"><input disabled={editLock} type="checkbox" checked={params.compare_baselines} onChange={e=>setParam('compare_baselines',e.target.checked)}/> Compute SCAR-Q / MCR-Q reference comparisons after training (slower)</label>
        {canTrain?<button className="ll-primary" onClick={start} disabled={working||!draft||!validTimeGrid}><Play size={16}/>{working?'Starting…':'Start new PPO training'}</button>:<button className="ll-stop" onClick={stop} disabled={working}><StopCircle size={16}/>Stop training</button>}
        <p className="ll-caption">For the first smoke test use 2 episodes, a 5-minute slot, a 60-minute horizon, and checkpoint interval 1. Training automatically completes after all requested episodes and checkpoint evaluations; reference comparisons are optional.</p>
        <div className="ll-panel-title"><Database size={16}/> Reproducibility</div>
        <p className="ll-caption">Each run stores its complete topology, PPO settings, progress samples, real measurements and checkpoints in <code>backend/data/learning/</code>.</p>
      </aside>
      <div className="ll-main">
        <section className="ll-card">
          <div className="ll-card-head"><div><strong>Network workspace</strong><small>{sceneMode==='edit'?'Arrange this fixed network before training.':'Frozen-checkpoint decisions on the saved topology.'}</small></div><button className="ll-refresh" onClick={()=>setSceneKey(v=>v+1)} title="Reset camera"><RefreshCcw size={16}/></button></div>
          <div className="ll-view-tools"><button className={sceneMode==='edit'?'active':''} onClick={()=>{setSceneMode('edit');setPlaying(false);}}>Arrange network</button><button className={sceneMode==='replay'?'active':''} disabled={!evaluation} onClick={()=>setSceneMode('replay')}>Checkpoint replay</button><span className="ll-toolbar-separator"/><button className={mapMode?'active':''} onClick={()=>setMapMode(true)}><MapIcon size={14}/> Map</button><button className={!mapMode?'active':''} onClick={()=>setMapMode(false)}><Rotate3D size={14}/> 3D</button>{!mapMode&&sceneMode==='edit'&&<label className="ll-checkbox"><input type="checkbox" checked={dragMode} disabled={editLock} onChange={e=>setDragMode(e.target.checked)}/> Move nodes</label>}</div>
          <div className="ll-stage">{sceneScenario?(mapMode?<GeoMap key={`geo-${sceneMode}-${sceneKey}`} scenario={sceneScenario} frame={sceneMode==='replay'?frame:null} topologyLinks={visualLinks} selectedId={sceneMode==='edit'?selectedNode:null} onSelect={sceneMode==='edit'?setSelectedNode:()=>{}} onPositionChange={sceneMode==='edit'?moveNode:()=>{}} />
            :<Network3D key={`${sceneMode}-${sceneKey}`} scenario={sceneScenario} frame={sceneMode==='replay'?frame:null} topologyLinks={visualLinks} selectedId={sceneMode==='edit'?selectedNode:null} onSelect={sceneMode==='edit'?setSelectedNode:()=>{}} dragMode={sceneMode==='edit'&&dragMode&&!editLock} onPositionChange={sceneMode==='edit'?moveNode:()=>{}} autoRotate={false}/>):<div className="ll-stage-empty">Loading network…</div>}
            {sceneMode==='replay'&&!frame&&<div className="ll-stage-overlay">Waiting for checkpoint evaluation…</div>}
          </div>
          {sceneMode==='edit'?<p className="ll-caption">The next training run captures this fixed network. Detailed optical settings are inherited when you copy a Studio experiment; the original is not modified.</p>
          :<><div className="ll-time-controls"><button disabled={!frames.length} onClick={()=>setPlaying(v=>!v)}>{playing?<Pause size={16}/>:<Play size={16}/>}</button><input aria-label="Evaluation slot" type="range" min="0" max={Math.max(0,frames.length-1)} value={Math.min(slot,Math.max(0,frames.length-1))} disabled={!frames.length} onChange={e=>{setSlot(Number(e.target.value));setPlaying(false);}}/><span>{frame?`${frame.slot+1} / ${frames.length} · T+${Math.round(frame.time_seconds/60)}m`:'No evaluation yet'}</span></div>{frame&&<div className="ll-frame-stats"><span>Served <b>{(frame.served_bps_total/1000).toFixed(2)} kb/s</b></span><span>QKP <b>{bits(frame.stored_bits_total)}</b></span><span>Active links <b>{frame.links.filter(l=>l.activated).length}</b></span><span>Paths <b>{frame.demands.filter(d=>d.path?.length).length}</b></span></div>}</>}
        </section>
        <section className="ll-card">
          <div className="ll-card-head"><div><strong>Live training progress</strong><small>{job?`Run ${job.id.slice(0,8)} · ${stageText[stage]||stage}`:'No training run yet'}</small></div><span className={`ll-status ${job?.status||'idle'}`}>{job?.status||'Not started'}</span></div>
          <div className="ll-progress"><div style={{width:`${clamp(prog,0,100)}%`}}/></div>
          <div className="ll-progress-label"><span>{job?`Episode ${job.episode||0} / ${job.episodes}`:'Ready to train'}</span><span>{stage==='physical-rates'?`Real optical rates: ${job.physical_progress?.completed??0}/${job.physical_progress?.total??'…'} · ${job.physical_progress?.cached??0} cached`: stage==='baseline-evaluation'?(job.baseline_progress ? `${job.baseline_progress.algorithm==='mcr_q'?'MCR-Q':'SCAR-Q'} · ${job.baseline_progress.completed}/${job.baseline_progress.total} slots` : 'Computing independent references'):stageProgress&&isTraining?`Slot ${nowSlot||0}/${stageProgress.total} · ${job.curriculum_active_demands||job.shape?.n_demands||'—'} active demands`:stageText[stage]||''}</span></div>
          {job?.status==='complete'&&<div className="ll-done">Training finished automatically · {job.episodes} / {job.episodes} episodes · {checkpoints.length} evaluated checkpoints.</div>}
          {isTraining&&<div className="ll-working"><span className="ll-working-spinner"/>{stageText[stage]||'Working'}{stageProgress?.total?` · ${stageProgress.completed}/${stageProgress.total} slots`:''}</div>}
          {job?.error&&<div className="ll-error"><AlertCircle size={14}/>{job.error} · See backend/data/learning/{job.id}/run.log</div>}
          <div className="ll-chart-head"><strong>Measured performance · live</strong><div className="ll-mini-toggle"><button className={chartView==='satisfaction'?'active':''} onClick={()=>setChartView('satisfaction')}>Keys served</button><button className={chartView==='reward'?'active':''} onClick={()=>setChartView('reward')}>Reward</button></div></div>
          <PerformanceChart metrics={metrics} checkpoints={checkpoints} selectedEpisode={selected} view={chartView} live={live} totalEpisodes={job?.episodes||episodes} finished={job?.status==='complete'}/>
          <p className="ll-caption">{chartView==='reward'?'Training-only heuristic-relative reward, plus its 25-episode trailing average. Frozen evaluations use a different metric, so they are not mixed into this plot.':'Training keys served vary with curriculum and sampled demands. The frozen evaluation curve uses the same fixed full-demand scenario at every checkpoint and is the fair learning-performance comparison.'}</p>
          {job?.reward_shape&&<p className="ll-caption">This run used: match-best bonus {job.reward_shape.reward_at_or_above_hi}, above-best slope {job.reward_shape.reward_above_hi_slope}, success reward {job.reward_shape.reward_success}, zero-service safeguard {job.reward_shape.reward_zero_service_guard?'on':'off'}. See the saved job configuration for all seven constants.</p>}
          <div className="ll-stats"><Summary label="Live episode reward" value={(live?.stage==='training'||live?.stage==='complete')&&Number.isFinite(live?.partial_reward)?live.partial_reward.toFixed(3):'—'} detail={live?.stage==='training'?`Episode ${live.episode} · ${live.slots_done}/${live.slots_total} slots`:'Awaiting training slots'}/><Summary label="Latest completed keys served" value={percentage(finalMetric?.train_satisfaction)} detail={finalMetric?`Episode ${finalMetric.episode}`:'No completed episode yet'}/><Summary label="Frozen checkpoint keys" value={percentage(currentCheckpoint?.evaluation_satisfaction)} detail={`Episode ${selected??'—'} · fixed evaluation`}/></div>
        </section>
        <PolicyArchitecture shape={job?.shape||draftShape} stats={finalMetric} episodes={job?.episode||0} slotCount={job?.slots||computedSlots}/>
        <section className="ll-card"><div className="ll-card-head"><div><strong>Measured checkpoint comparison</strong><small>Select a frozen policy and replay its per-slot allocation decisions.</small></div></div>
          {checkpoints.length>200&&<div className="ll-checkpoint-nav">
            <button disabled={shownCheckpointPage===0} onClick={()=>setCheckpointPage(0)}>First</button>
            <button disabled={shownCheckpointPage===0} onClick={()=>setCheckpointPage(shownCheckpointPage-1)}>Previous</button>
            <span>Checkpoints {shownCheckpointPage*200+1}–{Math.min((shownCheckpointPage+1)*200,checkpoints.length)} of {checkpoints.length}</span>
            <button disabled={shownCheckpointPage>=checkpointPages-1} onClick={()=>setCheckpointPage(shownCheckpointPage+1)}>Next</button>
            <button disabled={shownCheckpointPage>=checkpointPages-1} onClick={()=>setCheckpointPage(null)}>Latest</button>
          </div>}
          <div className="ll-checkpoints" role="region" aria-label="Scrollable evaluated checkpoints" tabIndex={0}>{checkpoints.length?visibleCheckpoints.map(c=><button key={c.episode} onClick={()=>{setSelected(c.episode);setSceneMode('replay');}} className={selected===c.episode?'selected':''}>Episode {c.episode}<small>{percentage(c.evaluation_satisfaction)}</small></button>):<span>Episode 0 appears after the first genuine optical-rate calculation and frozen evaluation.</span>}</div>
          <div className="ll-comparison"><Summary label="PPO checkpoint" value={bits(currentCheckpoint?.evaluation_served_bits)} detail={percentage(currentCheckpoint?.evaluation_satisfaction)}/><Summary label="SCAR-Q reference" value={bits(baseline?.scar_q_bits)} detail={requested&&baseline?percentage(baseline.scar_q_bits/requested):'Independent history'}/><Summary label="MCR-Q reference" value={bits(baseline?.mcr_q_bits)} detail={requested&&baseline?percentage(baseline.mcr_q_bits/requested):'1 Monte Carlo sample'}/></div>
          <p className="ll-caption">All methods use the same fixed evaluation network, with independent key pools. The PPO evaluation curve reports per-demand satisfaction reward; training reward is heuristic-relative. Improvement is not guaranteed.</p>
        </section>
      </div>
    </div>
  </main>;
}
