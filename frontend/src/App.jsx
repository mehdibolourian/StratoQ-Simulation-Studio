import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownToLine, ArrowRight, Box, Check, ChevronDown, CircleHelp,
  Cloud, Crosshair, Gauge, Layers3, Map, Maximize2, MousePointer2,
  Pause, Play, Plus, RadioTower, RefreshCcw, Rotate3D, SatelliteDish,
  Settings2, SlidersHorizontal, Sparkles, Trash2, Wifi, WifiOff, X,
} from 'lucide-react';
import Network3D from './components/Network3D.jsx';
import GeoMap from './components/GeoMap.jsx';
import { INITIAL_SCENARIO } from './lib/sample.js';
import { CENTER, flatDistance } from './lib/geo.js';
import { potentialLinks } from './lib/topology.js';

const STUDIO_VERSION = '0.9.0';
const clone = (obj) => structuredClone(obj);
const fmtRate = (n) => !Number.isFinite(n) ? '—' : `${(n / 1000).toFixed(1)} kb/s`;
const fmtBits = (n) => !Number.isFinite(n) ? '—' : n >= 1e6 ? `${(n/1e6).toFixed(2)} Mb` : `${(n/1000).toFixed(0)} kb`;
const toClock = (secs) => `${String(Math.floor(secs/3600)).padStart(2,'0')}:${String(Math.floor(secs%3600/60)).padStart(2,'0')}`;

function IconButton({ icon: Icon, label, onClick, active=false, disabled=false }) {
  return <button className={`icon-button ${active ? 'active' : ''}`} title={label} aria-label={label}
    onClick={onClick} disabled={disabled}><Icon size={17} /></button>;
}
function Numeric({ label, value, onChange, unit, min, max, step='any', small=false }) {
  return <label className={`field-label ${small ? 'compact' : ''}`}>
    <span>{label}</span>
    <div className="number-shell"><input type="number" value={value} min={min} max={max} step={step}
      onChange={e => {if (e.target.value !== '') onChange(Number(e.target.value));}} />{unit && <i>{unit}</i>}</div>
  </label>;
}
function TextField({ label, value, onChange }) {
  return <label className="field-label"><span>{label}</span><input className="text-input" value={value} onChange={e=>onChange(e.target.value)} /></label>;
}
function Chip({ children, accent }) { return <span className={`chip ${accent || ''}`}>{children}</span>; }
function GroupTitle({ children, extra }) { return <div className="group-title"><span>{children}</span>{extra}</div>; }
function ButtonRow({ icon: Icon, text, count, onClick, accent }) {
  return <button className="add-row" onClick={onClick}><span className={`add-row-icon ${accent}`}><Icon size={17} /></span>
    <span>{text}</span><span className="count">{count}</span><Plus size={14} className="add-small" /></button>;
}
function EntityItem({ item, icon: Icon, subtitle, selected, onClick }) {
  return <button className={`entity-item ${selected?'selected':''}`} onClick={onClick}>
    <span className="entity-icon"><Icon size={16}/></span><span className="entity-copy"><b>{item.name}</b><small>{subtitle}</small></span>
    <span className="entity-indicator" /></button>;
}
function downloadJSON(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href=url; a.download=filename; a.click(); setTimeout(()=>URL.revokeObjectURL(url), 200);
}

export default function App() {
  const [scenario, setScenario] = useState(() => clone(INITIAL_SCENARIO));
  const [selectedId, setSelectedId] = useState('hap-1');
  const [mode, setMode] = useState('3d');
  const [dragMode, setDragMode] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const [sceneKey, setSceneKey] = useState(0);
  const [result, setResult] = useState(null);
  const [dirty, setDirty] = useState(true);
  const [running, setRunning] = useState(false);
  const [backend, setBackend] = useState('checking');
  const [apiVersion, setApiVersion] = useState(null);
  const [error, setError] = useState('');
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [uploadingTrajectory, setUploadingTrajectory] = useState(false);
  const [physicsProgress, setPhysicsProgress] = useState(null);
  const [physicsStatus, setPhysicsStatus] = useState(null);
  const requestId = useRef(0);

  const currentFrame = !dirty ? result?.frames[frameIndex] : null;
  const visualScenario = useMemo(() => {
    if (!currentFrame?.positions) return scenario;
    const copy = clone(scenario);
    copy.balloons.forEach(h => { const p = currentFrame.positions[h.id]; if (p) Object.assign(h, p); });
    return copy;
  }, [scenario, currentFrame]);
  const nodes = useMemo(() => [...scenario.ground_stations, ...scenario.balloons, ...scenario.weather_regions], [scenario]);
  const topologyLinks = useMemo(() => potentialLinks(visualScenario, currentFrame, !dirty), [visualScenario, currentFrame, dirty]);
  const selectedLink = topologyLinks.find(l => l.id === selectedId);
  const selected = nodes.find(n => n.id === selectedId) || scenario.demands.find(n => n.id === selectedId) || selectedLink;
  const selectedType = selectedLink ? 'link' : selectedId?.startsWith('gs-') ? 'gs'
    : selectedId?.startsWith('hap-') ? 'hap' : selectedId?.startsWith('weather-') ? 'weather' : 'demand';
  const activeLinks = currentFrame?.links.filter(l => l.active).length || 0;
  const served = currentFrame?.served_bps_total;
  const requested = scenario.demands.reduce((n,d)=>n+d.rate_bps, 0);
  const satisfaction = currentFrame && requested > 0 ? Math.round(100*served/requested) : null;
  const firstLink = currentFrame?.links.find(l=>l.target===selectedId || l.source===selectedId) || currentFrame?.links[0];

  function patchScenario(mutator) {
    setScenario(old => { const next = clone(old); mutator(next); return next; });
    requestId.current += 1; // Discard responses computed for older scenarios.
    setRunning(false); setDirty(true); setPlaying(false); setPhysicsProgress(null);
  }
  function modifyItem(id, field, value) {
    patchScenario(s=>{for(const group of ['ground_stations','balloons','weather_regions','demands']) {
      const obj=s[group].find(o=>o.id===id); if(obj) {obj[field]=value; break;}
    }});
  }
  function onPositionChange(id, lat, lon) {
    patchScenario(s=>{const n=[...s.ground_stations,...s.balloons,...s.weather_regions].find(x=>x.id===id);
      if (n) { n.lat=Math.max(-90,Math.min(90,lat)); n.lon=Math.max(-180,Math.min(180,lon)); }});
  }
  function add(kind) {
    const base = Date.now().toString(36).slice(-6);
    const offset = 0.09 + Math.random()*0.12;
    if (kind==='gs') {
      const id = `gs-${base}`;
      patchScenario(s=>s.ground_stations.push({id,name:`Ground station ${s.ground_stations.length+1}`,
        lat: CENTER.lat-offset,lon:CENTER.lon+offset,capacity_bits:8000000,n_rx:1,n_tx:1,yaw_deg:0}));
      setSelectedId(id);
    } else if (kind==='hap') {
      const id=`hap-${base}`;
      patchScenario(s=>s.balloons.push({id,name:`Strato-${String(s.balloons.length+1).padStart(2,'0')}`,
        lat:CENTER.lat+offset/2,lon:CENTER.lon-offset/2,altitude_km:15,coverage_km:85,capacity_bits:12000000,n_rx:1,n_tx:1,yaw_deg:0}));
      setSelectedId(id);
    } else if(kind==='weather') {
      const id=`weather-${base}`;
      patchScenario(s=>s.weather_regions.push({id,name:`Fog region ${s.weather_regions.length+1}`,
        lat:CENTER.lat,lon:CENTER.lon,radius_km:16,attenuation_db:0,effect:"fog",visibility_km:0.5,precipitation_rate_mm_h:5}));
      setSelectedId(id);
    } else if (kind==='demand') {
      if(scenario.ground_stations.length < 2) {setError('Add two ground stations before creating a demand.');return;}
      const id=`d-${base}`;
      patchScenario(s=>s.demands.push({id,source:s.ground_stations[0].id,target:s.ground_stations[1].id,rate_bps:6000}));
      setSelectedId(id);
    }
  }
  function removeSelected() {
    if (!selected || selectedType === 'link') return;
    patchScenario(s=>{
      for(const group of ['ground_stations','balloons','weather_regions','demands']) s[group]=s[group].filter(o=>o.id!==selectedId);
      s.demands=s.demands.filter(d=>d.source!==selectedId && d.target!==selectedId);
      s.link_overrides=(s.link_overrides||[]).filter(o=>o.source!==selectedId && o.target!==selectedId);
    });
    setSelectedId(null);
  }
  function setLinkEnabled(link, enabled) {
    patchScenario(s => {
      const existing=(s.link_overrides||[]).find(o=>o.source===link.source&&o.target===link.target);
      s.link_overrides=(s.link_overrides||[]).filter(o=>!(o.source===link.source&&o.target===link.target));
      s.link_overrides.push({...existing,source:link.source,target:link.target,enabled});
    });
  }
  function changeLinkProperty(link, field, value) {
    patchScenario(s => {
      const old=(s.link_overrides||[]).find(o=>o.source===link.source&&o.target===link.target);
      s.link_overrides=(s.link_overrides||[]).filter(o=>!(o.source===link.source&&o.target===link.target));
      s.link_overrides.push({...old,source:link.source,target:link.target,enabled:old?.enabled??true,[field]:value});
    });
  }
  async function uploadTrajectory(hapId, file) {
    if (!file) return;
    setUploadingTrajectory(true); setError('');
    const form = new FormData(); form.append('file', file);
    try {
      const response = await fetch('/api/trajectories/upload', {method:'POST', body:form});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Invalid trajectory');
      patchScenario(s=>{
        const hap=s.balloons.find(h=>h.id===hapId);
        if (hap) Object.assign(hap, {trajectory_id:payload.trajectory_id,trajectory_name:payload.filename, ...payload.first});
        s.config.slots = Math.min(1500, Math.floor(payload.duration_seconds/s.config.slot_seconds)+1);
      });
    } catch(e) { setError(`Trajectory import: ${e.message}`); }
    finally {setUploadingTrajectory(false);}
  }
  async function runSim(caseInput=scenario, {silent=false, autoPlay=false}={}) {
    const id=++requestId.current;
    setRunning(true);setError('');setPlaying(false);
    setPhysicsProgress({stage:'queued',completed:0,total:0,cached:0,computed:0});
    try {
      // The real upstream LOWTRAN + turbulence/AO channel can take minutes on
      // larger topologies; start a monitored backend job instead of blocking UI.
      const response=await fetch('/api/simulations', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(caseInput)});
      const body=await response.json().catch(()=>null);
      if(!response.ok)throw new Error(body?.detail ? JSON.stringify(body.detail).slice(0,300):`HTTP ${response.status}`);
      const jid=body.id;
      while (id===requestId.current) {
        const statusResponse=await fetch(`/api/simulations/${jid}`,{cache:'no-store'});
        if(!statusResponse.ok)throw new Error(`Cannot read simulation progress: HTTP ${statusResponse.status}. Check backend restart.`);
        const status=await statusResponse.json();
        if(id!==requestId.current)return;
        setPhysicsProgress(status);
        if(status.status==='failed')throw new Error(status.error||'Physical-layer evaluation failed');
        if(status.status==='complete')break;
        await new Promise(resolve=>setTimeout(resolve,550));
      }
      if(id!==requestId.current)return;
      const resultResponse=await fetch(`/api/simulations/${jid}/result`);
      if(!resultResponse.ok){const errorBody=await resultResponse.json().catch(()=>null);throw new Error(errorBody?.detail||`HTTP ${resultResponse.status}`);}
      const data=await resultResponse.json();
      if(id!==requestId.current)return;
      setResult(data);setFrameIndex(0);setDirty(false);setBackend('online');
      if(autoPlay && data.frames?.length)setPlaying(true);
    }catch(e){
      if(id!==requestId.current)return;
      setError(`Physical simulation failed: ${e.message}. See FastAPI terminal. No approximate rates were substituted.`);
    }finally{if(id===requestId.current)setRunning(false);}
  }
  useEffect(() => {
    fetch('/api/health',{cache:'no-store'})
      .then(r=>{if(!r.ok)throw new Error('unavailable');return r.json();})
      .then(body=>{setApiVersion(body.version||'legacy');setBackend('online');})
      .catch(()=>{setApiVersion('unavailable');setBackend('offline');});
    fetch('/api/physics/status',{cache:'no-store'})
      .then(r=>r.ok?r.json():null).then(setPhysicsStatus).catch(()=>{});
    // Do not automatically launch the expensive physical calculations on page load.
  },[]);
  useEffect(() => {
    if(!playing || !result) return;
    const interval=setInterval(()=>setFrameIndex(i=>i >= result.frames.length-1 ? 0 : i+1), 650);
    return ()=>clearInterval(interval);
  }, [playing, result]);
  function togglePlayback() {
    if (running) return;
    if (playing) {setPlaying(false);return;}
    if (dirty || !result) {runSim(scenario, {autoPlay:true});return;}
    setPlaying(true);
  }
  function reset() {
    const resetCase=clone(INITIAL_SCENARIO);
    setScenario(resetCase); setSelectedId('hap-1'); setFrameIndex(0); setSceneKey(k=>k+1);
    setPlaying(false); setDirty(true); runSim(resetCase);
  }
  const totalFrames=result?.frames.length||scenario.config.slots;
  const selectedDemand=result?.frames[frameIndex]?.demands.find(d=>d.id===selectedId);

  return <div className="app-shell">
    <aside className="left-panel">
      <div className="brand-wrap">
        <div className="brand-symbol"><Layers3 size={23} strokeWidth={2.1}/></div>
        <div><div className="brand-title">strato<span>Q</span><sup>STUDIO</sup></div><div className="brand-sub">QUANTUM NETWORK LAB</div></div>
      </div>
      <div className="side-scroll">
        <div className="section-pad">
          <div className="eyebrow">WORKSPACE <span className="eyebrow-hint">01 / EXPERIMENT</span></div>
          <div className="project-card">
            <div className="project-name"><span className="project-status" /> Northern Ontario <ChevronDown size={15}/></div>
            <p>HAP-assisted QKD sandbox</p>
            <span className="project-id">LOCAL SCENARIO <span>·</span> DEMO 001</span>
          </div>
        </div>
        <div className="side-divider"/>
        <section className="section-pad">
          <GroupTitle extra={<span className="section-mini">EDIT</span>}>NETWORK ELEMENTS</GroupTitle>
          <div className="add-list">
            <ButtonRow icon={SatelliteDish} text="Ground stations" count={scenario.ground_stations.length} onClick={()=>add('gs')} accent="aqua"/>
            <ButtonRow icon={RadioTower} text="HAP balloons" count={scenario.balloons.length} onClick={()=>add('hap')} accent="amber"/>
            <ButtonRow icon={Cloud} text="Weather regions" count={scenario.weather_regions.length} onClick={()=>add('weather')} accent="violet"/>
            <ButtonRow icon={Activity} text="Traffic demands" count={scenario.demands.length} onClick={()=>add('demand')} accent="lime"/>
          </div>
        </section>
        <div className="side-divider"/>
        <section className="section-pad">
          <GroupTitle>SCENE OBJECTS</GroupTitle>
          <div className="object-list">
            {scenario.balloons.map(h=><EntityItem key={h.id} item={h} icon={RadioTower} subtitle={`${h.altitude_km} km · ${h.coverage_km} km range`}
              selected={selectedId===h.id} onClick={()=>setSelectedId(h.id)} />)}
            {scenario.ground_stations.map(g=><EntityItem key={g.id} item={g} icon={SatelliteDish} subtitle={`${g.lat.toFixed(3)}° N  ${Math.abs(g.lon).toFixed(3)}° W`}
              selected={selectedId===g.id} onClick={()=>setSelectedId(g.id)} />)}
            {scenario.weather_regions.map(w=><EntityItem key={w.id} item={w} icon={Cloud} subtitle={`${w.effect || 'fog'} · ${w.radius_km} km · ${w.effect==='fog' ? `${w.visibility_km??0.5} km vis.` : `${w.precipitation_rate_mm_h??5} mm/h`}`} selected={selectedId===w.id} onClick={()=>setSelectedId(w.id)}/>)}
            {scenario.demands.map(d=><EntityItem key={d.id} item={{name:`Demand ${d.id.slice(2,7)}`}} icon={Activity}
              subtitle={`${fmtRate(d.rate_bps)} requested`} selected={selectedId===d.id} onClick={()=>setSelectedId(d.id)} />)}
          </div>
        </section>
      </div>
      <div className="left-bottom">
        <button className="primary-button" onClick={()=>runSim()} disabled={running}>
          {running ? <RefreshCcw size={17} className="spin"/> : <Play size={17} fill="currentColor" />}
          {running?'Computing physical rates…':'Run simulation'} <ArrowRight size={16}/>
        </button>
        {running && physicsProgress && <div className="physics-progress" role="status" aria-live="polite">
          <div className="physics-progress-meta"><b>{physicsProgress.stage==='channel'?'Calculating upstream channel':'Preparing physical setup…'}</b>
          <span>{physicsProgress.total?`${physicsProgress.completed}/${physicsProgress.total}`:'Initializing'}</span></div>
          <div className="physics-progress-track"><div style={{width:`${physicsProgress.total?Math.min(100,100*physicsProgress.completed/physicsProgress.total):3}%`}} /></div>
          <small>{physicsProgress.cached||0} reused · {physicsProgress.computed||0} computed · {physicsProgress.workers||0} workers</small>
        </div>}
        {!running && !dirty && physicsProgress?.stage==='complete' && <div className="physics-last-run">
          <Check size={12}/> Upstream physics · {physicsProgress.computed||0} calculated · {physicsProgress.cached||0} cached
        </div>}
        <div className="run-hint"><span className={`status-pin ${backend}`} />
          {backend==='online'?'Upstream balloon_qnet backend connected':backend==='checking'?'Connecting to local API…':'Backend offline — see README'}
        </div>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div className="breadcrumb"><span>Projects</span><span className="chevron">/</span><strong>Northern Ontario</strong><span className="chevron">/</span><span>Network editor</span></div>
        <div className="topbar-right">
          <Chip accent="demo">BALLOON_QNET THEORY · UI {STUDIO_VERSION}</Chip>
          <span className="top-separator"/>
          <button className="header-text-button" onClick={()=>downloadJSON('stratoq-scenario.json',scenario)}><ArrowDownToLine size={16}/> Export scenario</button>
          <button className="avatar" title="Local user">SQ</button>
        </div>
      </header>
      <div className="stage-shell">
        <div className="stage-top">
          <div>
            <div className="stage-overline"><span className="live-light" /> INTERACTIVE NETWORK ENVIRONMENT</div>
            <h1>Network topology <span className="h1-mark">/ {mode==='3d'?'3D space':'geographic map'}</span></h1>
            <p>Explore optical links and key-buffer dynamics in a balloon-assisted QKD network.</p>
          </div>
          <div className="view-toggle"><button className={mode==='3d'?'active':''} onClick={()=>setMode('3d')}><Box size={16}/> 3D scene</button>
            <button className={mode==='map'?'active':''} onClick={()=>setMode('map')}><Map size={16}/> Map view</button></div>
        </div>
        <div className="scene-wrapper">
          <div className="scene-view">
            {mode==='3d' ? <Network3D key={sceneKey} scenario={visualScenario} frame={currentFrame} topologyLinks={topologyLinks} selectedId={selectedId}
              onSelect={setSelectedId} dragMode={dragMode} onPositionChange={onPositionChange} autoRotate={autoRotate} />
              : <GeoMap scenario={visualScenario} frame={currentFrame} topologyLinks={topologyLinks} selectedId={selectedId} onSelect={setSelectedId} onPositionChange={onPositionChange} />}
          </div>
          <div className="scene-corner top-left">
            <div className="floating-label"><span className="floating-dot"/> NETWORK LIVE VIEW <span className="light-divider">/</span> {mode==='3d'?'LOCAL XYZ':'WGS84'}</div>
          </div>
          <div className="scene-corner top-right">
            <div className="toolbox">
              {mode==='3d' && <><IconButton icon={MousePointer2} label={dragMode?'Turn off moving objects':'Move selected objects by dragging'}
                active={dragMode} onClick={()=>setDragMode(v=>!v)} />
              <IconButton icon={Rotate3D} label="Auto-orbit camera" active={autoRotate} onClick={()=>setAutoRotate(v=>!v)} />
              <span className="tool-divider" />
              <IconButton icon={Crosshair} label="Reset 3D camera" onClick={()=>setSceneKey(v=>v+1)} /></>}
              {mode==='map'&&<IconButton icon={Crosshair} label="Switch to the resettable 3D scene" onClick={()=>setMode('3d')} />}
              <IconButton icon={RefreshCcw} label="Reset scenario" onClick={reset} />
            </div>
          </div>
          {mode==='3d' && <div className="scene-corner bottom-left">
            <div className="visual-legend"><span><i className="legend-mark link"/> Optical link</span><span><i className="legend-mark demand"/> Demand route</span><span><i className="legend-mark cloud"/> Weather region</span></div>
            <div className="scene-instructions">Drag to orbit <span>·</span> Scroll to zoom <span>·</span> {dragMode?'Drag any object to move':'Drag weather directly · Move tool for GS/HAP'}</div>
          </div>}
          {running&&physicsProgress&&<div className="scene-corner bottom-right"><div className="pending-indicator">Physical model · {physicsProgress.total?`${physicsProgress.completed}/${physicsProgress.total}`:'preparing'} · {physicsProgress.cached||0} cached</div></div>}
          {dirty&&!running&&<div className="scene-corner bottom-right"><div className="pending-indicator"><span/> Changes pending · Play to recalculate</div></div>}
        </div>
        {apiVersion !== null && apiVersion !== STUDIO_VERSION && <div className="revision-warning">
          <strong>Version mismatch:</strong> UI {STUDIO_VERSION} / API {apiVersion}. Replace the backend files too and restart FastAPI.
        </div>}
        {error && <div className="error-bar"><WifiOff size={15}/><span>{error}</span><button onClick={()=>setError('')}><X size={15}/></button></div>}
        <div className="timeline">
          <div className="timeline-header"><div className="timeline-title"><span className="timeline-play-icon"><Activity size={17}/></span>
            <div><strong>Simulation timeline</strong><small>{totalFrames} slots · {scenario.config.slot_seconds}s per slot</small></div></div>
            <div className="timeline-actions"><span className="time-current">T+{toClock((currentFrame?.time_seconds ?? 0))}</span>
              <button onClick={()=>{setFrameIndex(0);setPlaying(false);}} title="Restart playback"><RefreshCcw size={15}/></button>
              <button className="playback-button" onClick={togglePlayback} disabled={running} title={dirty || !result ? "Recalculate and play updated scenario" : playing ? "Pause" : "Play"}>{running?<RefreshCcw size={16} className="spin"/>:playing?<Pause size={16} fill="currentColor"/>:<Play size={16} fill="currentColor"/>}</button>
            </div></div>
          <div className="trajectory-slot-control"><label htmlFor="slot-seconds">Time slot</label>
            <select id="slot-seconds" value={scenario.config.slot_seconds} onChange={e=>patchScenario(s=>{s.config.slot_seconds=Number(e.target.value);})}>
              {[10,30,60,120,300,600,900,1800,3600].map(v=><option key={v} value={v}>{v<60?`${v} sec`:v<3600?`${v/60} min`:`${v/3600} hour`}</option>)}
            </select><small>Trajectory horizon adjusts on Play</small></div>
          <div className="timeline-scrub"><span>00:00</span><input aria-label="Simulation time slot" type="range" min={0} max={Math.max(0,totalFrames-1)}
            value={frameIndex} onChange={e=>{setFrameIndex(Number(e.target.value));setPlaying(false);}}
            style={{'--progress': `${totalFrames>1 ? 100*frameIndex/(totalFrames-1) : 0}%`}} disabled={!result}/>
            <span>{toClock((totalFrames-1)*scenario.config.slot_seconds)}</span></div>
          <div className="timeline-footer"><span><span className="timeline-dot aqua"/> Link state</span><span><span className="timeline-dot purple"/> QKP buffers</span>
            <span className="timeline-note">Frame {frameIndex+1} of {totalFrames}{dirty?' · press Play to update':''}</span></div>
        </div>
      </div>
    </main>

    <aside className="right-panel">
      <div className="inspector-top"><div><span className="tiny-overline">CONTROL CENTER</span><h2>Inspector <SlidersHorizontal size={17}/></h2></div>
        <IconButton icon={Settings2} label="Export simulation results" onClick={()=>result&&downloadJSON('stratoq-results.json',result)} disabled={!result}/></div>
      {selectedType==='weather' && selected && <div className="weather-quick-controls">
        <div className="weather-quick-heading"><strong>WEATHER TYPE</strong><span>Drag zone directly to move</span></div>
        <div className="weather-type-options" role="group" aria-label="Weather effect">
          {[['fog','☁','Fog / cloud'],['rain','☂','Rain'],['snow','❄','Snow']].map(([value, icon, label]) =>
            <button key={value} type="button" aria-pressed={(selected.effect||'fog')===value}
              className={(selected.effect||'fog')===value?'active':''}
              onClick={()=>modifyItem(selected.id,'effect',value)}>
              <span aria-hidden="true">{icon}</span>{label}
            </button>)}
        </div>
      </div>}
      <div className="inspector-scroll">
        <div className="inspector-section">
          <GroupTitle>NETWORK PERFORMANCE <span className="metrics-caption">SLOT {frameIndex+1}</span></GroupTitle>
          <div className="kpi-grid">
            <div className="kpi-card"><div className="kpi-label"><Activity size={14}/> Served rate</div><b>{fmtRate(served)}</b><small>{satisfaction===null?'—':`${satisfaction}% of requested`}</small></div>
            <div className="kpi-card"><div className="kpi-label"><Wifi size={14}/> Active links</div><b>{currentFrame?activeLinks:'—'} <i>/ {currentFrame?.links.length||'—'}</i></b><small>GS ↔ HAP</small></div>
            <div className="kpi-card"><div className="kpi-label"><Layers3 size={14}/> Key buffers</div><b>{fmtBits(currentFrame?.stored_bits_total)}</b><small>Total stored bits</small></div>
            <div className="kpi-card"><div className="kpi-label"><Gauge size={14}/> Satisfaction</div><b>{satisfaction===null?'—':`${satisfaction}%`}</b><small>Current slot</small></div>
          </div>
          <div className="metric-notice"><Sparkles size={15}/><span>Link rates use a Gaussian-beam BB84 analytical approximation; allocation is a placeholder. Not validated StratoQ results.</span></div>
        </div>
        <div className="inspector-section">
          <GroupTitle>SELECTED OBJECT {selected && <Chip accent={selectedType==='hap'?'warm':'neutral'}>{selectedType.toUpperCase()}</Chip>}</GroupTitle>
          {selected ? <>
            <div className="object-hero"><div className={`object-avatar ${selectedType}`}>
              {selectedType==='hap'?<RadioTower size={24}/>:selectedType==='gs'?<SatelliteDish size={24}/>:selectedType==='weather'?<Cloud size={24}/>:selectedType==='link'?<Wifi size={24}/>:<Activity size={24}/>}</div>
              <div><strong>{selectedType==='link' ? `${nodes.find(n=>n.id===selected.source)?.name || selected.source} ↔ ${nodes.find(n=>n.id===selected.target)?.name || selected.target}` : (selected.name||`Demand ${selected.id}`)}</strong><small>{selectedType==='hap'?'High-altitude platform':selectedType==='gs'?'Ground station':selectedType==='weather'?'Atmospheric region':selectedType==='link'?'Optical link':'Traffic requirement'}</small></div>
              {selectedType !== 'link' && <button className="trash-button" onClick={removeSelected} title="Delete object"><Trash2 size={16}/></button>}
            </div>
            {selectedType==='link' ? <div className="field-stack">
              <label className="field-label"><span>Manually enabled</span>
                <input type="checkbox" checked={selected.enabled} onChange={e=>setLinkEnabled(selected,e.target.checked)} />
              </label>
              <div className="selection-stat"><span>Status</span><b>{!selected.enabled?'Manually disabled':!selected.in_range?'Out of range':dirty?'Pending simulation':selected.active?'Active':'Unavailable'}</b></div>
              <Numeric label="Clear-air visibility (V)" value={selected.visibility_km??100} unit="km" min={0.01} max={500}
                onChange={v=>changeLinkProperty(selected,'visibility_km',v)}/>
              <Numeric label="Link rate cap (optional)" value={selected.capacity_limit_bps??0} unit="bps" min={0}
                onChange={v=>changeLinkProperty(selected,'capacity_limit_bps',v===0?null:v)}/>
              <div className="selection-stat"><span>Weather (fog/rain/snow)</span><b>{(selected.weather_flags||[0,0,0]).join(' / ')}</b></div>
              <div className="selection-stat"><span>Capacity</span><b>{!dirty?fmtRate(selected.capacity_bps):'Run to update'}</b></div>
              <div className="selection-stat"><span>Used by demands</span><b>{!dirty?fmtRate(selected.used_bps):'Run to update'}</b></div>
              <div className="selection-stat"><span>Slant distance</span><b>{selected.distance_km.toFixed(1)} km</b></div>
              <div className="selection-stat"><span>GS elevation</span><b>{Number.isFinite(selected.elevation_deg) ? `${selected.elevation_deg.toFixed(1)}°` : 'Run to update'}</b></div>
              <div className="selection-stat"><span>Weather attenuation</span><b>{Number.isFinite(selected.weather_loss_db) ? `${selected.weather_loss_db.toFixed(1)} dB` : 'Run to update'}</b></div>
              <p className="field-help">Manual failures override physical availability. Click Run StratoQ to reroute demands.</p>
            </div> : selectedType==='demand' ? <div className="field-stack">
              <label className="field-label"><span>Source station</span><select value={selected.source} onChange={e=>modifyItem(selected.id,'source',e.target.value)}>
                {scenario.ground_stations.filter(g=>g.id!==selected.target).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
              <label className="field-label"><span>Destination station</span><select value={selected.target} onChange={e=>modifyItem(selected.id,'target',e.target.value)}>
                {scenario.ground_stations.filter(g=>g.id!==selected.source).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
              <Numeric label="Required rate" value={selected.rate_bps} unit="bps" min={1} max={1e9} onChange={v=>modifyItem(selected.id,'rate_bps',v)}/>
              <div className="selection-stat"><span>Current served rate</span><b>{fmtRate(selectedDemand?.served_bps)}</b></div>
            </div> : <div className="field-stack">
              <TextField label="Display name" value={selected.name} onChange={v=>modifyItem(selected.id,'name',v)} />
              <div className="field-grid"><Numeric label="Latitude" value={selected.lat} step={0.0001} min={-90} max={90}
                unit="° N" onChange={v=>modifyItem(selected.id,'lat',v)}/>
                <Numeric label="Longitude" value={selected.lon} step={0.0001} min={-180} max={180}
                  unit="° E" onChange={v=>modifyItem(selected.id,'lon',v)}/></div>
              {selectedType==='hap'&&<><div className="field-grid"><Numeric label="Altitude" value={selected.altitude_km} unit="km" min={1} max={50} onChange={v=>modifyItem(selected.id,'altitude_km',v)} />
                <Numeric label="Coverage" value={selected.coverage_km} unit="km" min={1} max={500} onChange={v=>modifyItem(selected.id,'coverage_km',v)} /></div></>}
              {(selectedType==='gs'||selectedType==='hap')&&<>
                <Numeric label="QKP max (A_MAX)" value={selected.capacity_bits??(selectedType==='gs'?8000000:12000000)} unit="bits" min={1} onChange={v=>modifyItem(selected.id,'capacity_bits',v)}/>
                <div className="field-grid">
                  <Numeric label="Rx connections (N_RX)" value={selected.n_rx??1} min={0} step={1} onChange={v=>modifyItem(selected.id,'n_rx',v)}/>
                  <Numeric label="Tx connections (N_TX)" value={selected.n_tx??1} min={0} step={1} onChange={v=>modifyItem(selected.id,'n_tx',v)}/>
                </div>
              </>} 
              {(selectedType==='gs'||selectedType==='hap') && <label className="field-label"><span>Model heading <em>{selected.yaw_deg||0}°</em></span>
                <input type="range" min={-180} max={180} step={1} value={selected.yaw_deg||0}
                  onChange={e=>modifyItem(selected.id,'yaw_deg',Number(e.target.value))} /></label>}

              {selectedType==='weather'&&<p className="field-help">Drag the region or its center handle directly in 3D, or drag the region or marker on the map. Play recalculates weather flags for each HAP and link at each slot.</p>}
              {selectedType==='weather' && <div className="weather-intensity-control">
                <strong>{selected.effect==='fog'?'Fog density / visibility':selected.effect==='snow'?'Snowfall rate (water equivalent)':'Rainfall rate'}</strong>
                <div className="field-grid">
                  {selected.effect==='fog' ? <Numeric label="Meteorological visibility" value={selected.visibility_km??0.5} min={0.05} max={100} step={0.05} unit="km" onChange={v=>modifyItem(selected.id,'visibility_km',v)} /> : <Numeric label="Precipitation rate" value={selected.precipitation_rate_mm_h??5} min={0} max={500} step={0.5} unit="mm/h" onChange={v=>modifyItem(selected.id,'precipitation_rate_mm_h',v)} />}
                </div>
                <p className="field-help">{selected.effect==='fog'?'Lower visibility means denser fog.':'Higher rate increases atmospheric loss and particle density. Snow uses liquid-water equivalent mm/h.'} The rate-to-attenuation scaling is approximate; see WEATHER-INTENSITY-V09.md.</p>
              </div>}
              {selectedType==='weather'&&<div className="field-grid"><Numeric label="Region radius" value={selected.radius_km} min={1} max={500} unit="km" onChange={v=>modifyItem(selected.id,'radius_km',v)} />
                <Numeric label="Optional extra loss" value={selected.attenuation_db} min={0} max={40} unit="dB" onChange={v=>modifyItem(selected.id,'attenuation_db',v)}/></div>}
              {selectedType==='hap' && <div className="trajectory-upload">
                <strong>HAP trajectory</strong>
                <label className="trajectory-upload-button">{uploadingTrajectory?'Importing…':'Upload CSV / Excel'}
                  <input type="file" accept=".csv,.xlsx" disabled={uploadingTrajectory} onChange={e=>{uploadTrajectory(selected.id,e.target.files?.[0]);e.target.value='';}} />
                </label>
                <small>{selected.trajectory_name || 'Static position · no trajectory attached'}</small>
                {selected.trajectory_id && <button className="trajectory-clear" onClick={()=>patchScenario(s=>{const h=s.balloons.find(h=>h.id===selected.id);delete h.trajectory_id;delete h.trajectory_name;})}>Remove trajectory</button>}
              </div>}
              {selectedType==='hap' && <div className="selection-stat"><span>Potential optical links</span><b>{topologyLinks.filter(l=>l.target===selected.id).length}</b></div>}
              {selectedType==='gs' && <div className="selection-stat"><span>Potential optical links</span><b>{topologyLinks.filter(l=>l.source===selected.id).length}</b></div>}
            </div>}
          </>:<div className="empty-selection"><MousePointer2 size={25}/><span>Choose an object in the scene to inspect its parameters.</span></div>}
        </div>
        <div className="inspector-section">
          <GroupTitle>SIMULATION CONFIG</GroupTitle>
          <div className="field-grid"><Numeric label="Time slots" value={scenario.config.slots} min={1} max={288} step={1} onChange={v=>patchScenario(s=>s.config.slots=v)} />
            <Numeric label="Slot duration" value={scenario.config.slot_seconds} unit="sec" min={1} max={86400} step={1} onChange={v=>patchScenario(s=>s.config.slot_seconds=v)} /></div>
          <div className="field-grid">
            <label className="field-label"><span>Placeholder routing</span>
              <select value={scenario.config.allocation_mode || 'random'} onChange={e=>patchScenario(s=>s.config.allocation_mode=e.target.value)}>
                <option value="random">Random (seeded)</option><option value="greedy">Greedy (largest QKP)</option>
              </select>
            </label>
            <Numeric label="Random seed" value={scenario.config.allocator_seed ?? 42} min={0} max={2147483647} step={1} onChange={v=>patchScenario(s=>s.config.allocator_seed=v)}/>
          </div>
          <GroupTitle>PHYSICAL CHANNEL · UPSTREAM THEORY</GroupTitle>
          <div className="field-grid">
            <Numeric label="Wavelength" value={scenario.config.optical.wavelength_nm} unit="nm" min={300} onChange={v=>patchScenario(s=>s.config.optical.wavelength_nm=v)}/>
            <Numeric label="Beam waist" value={scenario.config.optical.beam_waist_m} unit="m" min={0.001} onChange={v=>patchScenario(s=>s.config.optical.beam_waist_m=v)}/>
            <Numeric label="GS receiver diameter" value={scenario.config.optical.rx_aperture_down_m} unit="m" min={0.01} onChange={v=>patchScenario(s=>s.config.optical.rx_aperture_down_m=v)}/>
            <Numeric label="HAP receiver diameter" value={scenario.config.optical.rx_aperture_up_m} unit="m" min={0.01} onChange={v=>patchScenario(s=>s.config.optical.rx_aperture_up_m=v)}/>
            <Numeric label="Pulse repetition" value={scenario.config.optical.source_rate_hz} unit="Hz" min={1} onChange={v=>patchScenario(s=>s.config.optical.source_rate_hz=v)}/>
            <Numeric label="Source efficiency" value={scenario.config.optical.source_efficiency} min={0} max={1} onChange={v=>patchScenario(s=>s.config.optical.source_efficiency=v)}/>
            <Numeric label="QBER" value={scenario.config.optical.qber} min={0} max={0.49} onChange={v=>patchScenario(s=>s.config.optical.qber=v)}/>
            <Numeric label="Obscuration ratio" value={scenario.config.optical.obscuration_ratio} min={0} max={0.99} onChange={v=>patchScenario(s=>s.config.optical.obscuration_ratio=v)}/>
            <Numeric label="AO correction order" value={scenario.config.optical.ao_correction_order} step={1} min={0} onChange={v=>patchScenario(s=>s.config.optical.ao_correction_order=v)}/>
            <Numeric label="Wind speed" value={scenario.config.optical.wind_speed_mps ?? 10} unit="m/s" min={0.01} onChange={v=>patchScenario(s=>s.config.optical.wind_speed_mps=v)}/>
            <Numeric label="Parallel workers" value={scenario.config.channel_workers ?? 10} step={1} min={1} max={24} onChange={v=>patchScenario(s=>s.config.channel_workers=v)}/>
            <Numeric label="Turbulence Cn0" value={scenario.config.optical.cn0} min={1e-18} onChange={v=>patchScenario(s=>s.config.optical.cn0=v)}/>
            <Numeric label="Pointing error" value={scenario.config.optical.pointing_error_rad} unit="rad" min={0} onChange={v=>patchScenario(s=>s.config.optical.pointing_error_rad=v)}/>
            <Numeric label="Tracking efficiency" value={scenario.config.optical.tracking_efficiency} min={0} max={1} onChange={v=>patchScenario(s=>s.config.optical.tracking_efficiency=v)}/>
            <Numeric label="Detection efficiency" value={scenario.config.optical.detector_efficiency} min={0} max={1} onChange={v=>patchScenario(s=>s.config.optical.detector_efficiency=v)}/>
          </div>
          <p className="field-help">Link capacities come from upstream balloon_qnet channel_theory (LOWTRAN + AO/turbulence) and BB84 secret-key equations. The allocator is still a demo heuristic. Unchanged physical evaluations are cached.</p>
        </div>
        <div className="inspector-section last"><GroupTitle>API ENGINE</GroupTitle>
          <div className="api-line"><span className={`api-light ${backend}`}/><div><strong>FastAPI · localhost:8000</strong><small>{backend==='online'?'Connection healthy':backend==='checking'?'Checking connection':'Not connected'}</small></div><span className="api-tag">{backend.toUpperCase()}</span></div>
          {physicsStatus && <p className="field-help">Original channel: {physicsStatus.channel_import_ok?'import OK':'import failed'} · LOWTRAN native: {physicsStatus.native_lowtran_present?'installed':'will build on first run / requires build tools'}</p>}
          <button className="secondary-button" onClick={()=>downloadJSON('stratoq-scenario.json',scenario)}><ArrowDownToLine size={15}/> Download scenario JSON</button>
        </div>
      </div>
      <div className="right-footer"><CircleHelp size={15}/><span>v0.8 · balloon_qnet upstream channel · demo allocator</span></div>
    </aside>
  </div>;
}
