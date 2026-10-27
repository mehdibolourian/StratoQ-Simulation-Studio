import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownToLine, ArrowUpFromLine, ArrowRight, Box, Check, ChevronDown, CircleHelp,
  Cloud, CloudRain, CalendarDays, Crosshair, Gauge, Layers3, Map, Maximize2, MousePointer2,
  Pause, Play, Plus, RadioTower, RefreshCcw, Rotate3D, SatelliteDish,
  Settings2, SlidersHorizontal, Sparkles, Trash2, Wifi, WifiOff, X, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, GripVertical, Pencil, Copy,
} from 'lucide-react';
import Network3D from './components/Network3D.jsx';
import GeoMap from './components/GeoMap.jsx';
import { INITIAL_SCENARIO } from './lib/sample.js';
import { CENTER, flatDistance } from './lib/geo.js';
import { potentialLinks } from './lib/topology.js';

const STUDIO_VERSION = '1.0.5';
const EMPTY_WEATHER = [];
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

const WORKSPACE_KEY = 'stratoq.workspace.v104';
const makeExperiment = (scenario, name='Experiment 1') => ({
  id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())+Math.random(),
  name, scenario: clone(scenario), selectedId: null, result: null, dirty: true, frameIndex: 0,
});
function readWorkspace() {
  try {
    const stored = JSON.parse(localStorage.getItem(WORKSPACE_KEY) || 'null');
    if (stored?.experiments?.length && stored.experiments.every(e => e.scenario?.config && Array.isArray(e.scenario.ground_stations))) {
      return {experiments:stored.experiments.map(e => ({...e, result:null, dirty:true})),
        activeId:stored.experiments.some(e=>e.id===stored.activeId) ? stored.activeId : stored.experiments[0].id};
    }
  }catch(_){}
  const first=makeExperiment(INITIAL_SCENARIO,'Experiment 1'); first.selectedId='hap-1';
  return {experiments:[first],activeId:first.id};
}
function isScenario(obj) {
  return obj && typeof obj==='object' && !Array.isArray(obj) &&
    Array.isArray(obj.ground_stations) && Array.isArray(obj.balloons) &&
    Array.isArray(obj.demands) && Array.isArray(obj.weather_regions) &&
    obj.config && typeof obj.config==='object';
}
export default function App() {
  const [initialWorkspace] = useState(readWorkspace);
  const [experiments, setExperiments] = useState(initialWorkspace.experiments);
  const [activeId, setActiveId] = useState(initialWorkspace.activeId);
  const activeExperiment = experiments.find(e=>e.id===activeId) || experiments[0];
  const [scenario, setScenario] = useState(() => clone(initialWorkspace.experiments.find(e=>e.id===initialWorkspace.activeId).scenario));
  const [selectedId, setSelectedId] = useState(() => initialWorkspace.experiments.find(e=>e.id===initialWorkspace.activeId).selectedId);
  const [leftWidth, setLeftWidth] = useState(() => Number(localStorage.getItem('stratoq.left.width')) || 263);
  const [rightWidth, setRightWidth] = useState(() => Number(localStorage.getItem('stratoq.right.width')) || 332);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const importRef=useRef(null);
  const workspaceRef=useRef(null);
  const resizeRef=useRef(null);
  const latestSnapshot=useRef(null);
  const latestExperiments=useRef(experiments);
  const activeIdRef=useRef(activeId);
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
  const [era5Job, setEra5Job] = useState(null);
  const [era5Loading, setEra5Loading] = useState(false);
  const [era5Elapsed, setEra5Elapsed] = useState(0);
  const [era5Preview, setEra5Preview] = useState([]);
  const [era5Meta, setEra5Meta] = useState(null);
  const requestId = useRef(0);
  const weatherRequestId = useRef(0);
  latestSnapshot.current = {scenario, selectedId, result, dirty, frameIndex};
  latestExperiments.current = experiments;
  activeIdRef.current = activeId;
  useEffect(() => {
    // Persist editable scenarios only. Simulation results can be huge and are not durable.
    try {
      const snapshot=latestSnapshot.current;
      const saved=latestExperiments.current.map(e=>e.id===activeIdRef.current ?
        {...e, scenario:snapshot.scenario, selectedId:snapshot.selectedId, result:null, dirty:true} :
        {...e, result:null, dirty:true});
      localStorage.setItem(WORKSPACE_KEY, JSON.stringify({experiments:saved,activeId:activeIdRef.current}));
    } catch (err) {console.warn('Workspace auto-save unavailable:',err);}
  }, [scenario, selectedId, experiments, activeId]);
  useEffect(()=>{try {localStorage.setItem('stratoq.left.width',String(leftWidth));localStorage.setItem('stratoq.right.width',String(rightWidth));}catch(_){}},[leftWidth,rightWidth]);
  useEffect(()=>{
    const move=e=>{
      const direction=resizeRef.current;
      if (!direction) return;
      if (direction==='left') setLeftWidth(Math.max(210,Math.min(500,e.clientX)));
      if (direction==='right') setRightWidth(Math.max(260,Math.min(540,window.innerWidth-e.clientX)));
    };
    const stop=()=>{resizeRef.current=null;document.body.style.cursor='';document.body.style.userSelect='';};
    window.addEventListener('pointermove',move);window.addEventListener('pointerup',stop);
    return ()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',stop);};
  },[]);
  function beginResize(side,e) {e.preventDefault();resizeRef.current=side;document.body.style.cursor='col-resize';document.body.style.userSelect='none';}
  function saveCurrent() {
    const snap=latestSnapshot.current;
    return latestExperiments.current.map(e=>e.id===activeIdRef.current ? {...e,...snap} : e);
  }
  function loadExperiment(exp) {
    ++requestId.current; ++weatherRequestId.current;
    setScenario(clone(exp.scenario));setSelectedId(exp.selectedId || null);
    setResult(exp.result || null);setDirty(exp.dirty ?? true);setFrameIndex(exp.frameIndex || 0);
    setRunning(false);setPlaying(false);setPhysicsProgress(null);setError('');
    setEra5Preview([]);setEra5Meta(null);setEra5Job(null);setEra5Loading(false);
    setSceneKey(k=>k+1);
  }
  function changeExperiment(id) {
    if(id===activeIdRef.current) return;
    const saved=saveCurrent();const next=saved.find(e=>e.id===id);if(!next)return;
    setExperiments(saved);setActiveId(id);loadExperiment(next);
  }
  function createExperiment() {
    const saved=saveCurrent();
    const next=makeExperiment(INITIAL_SCENARIO,`Experiment ${saved.length+1}`);
    next.selectedId='hap-1';setExperiments([...saved,next]);setActiveId(next.id);loadExperiment(next);
  }
  function duplicateExperiment() {
    const saved=saveCurrent();const current=saved.find(e=>e.id===activeIdRef.current);
    const next={...makeExperiment(current.scenario,`${current.name} copy`),selectedId:current.selectedId};
    setExperiments([...saved,next]);setActiveId(next.id);loadExperiment(next);
  }
  function renameExperiment(id) {
    const current=latestExperiments.current.find(e=>e.id===id);if(!current)return;
    const name=window.prompt('Experiment name',current.name)?.trim();
    if(name) setExperiments(old=>old.map(e=>e.id===id?{...e,name:name.slice(0,64)}:e));
  }
  function closeExperiment(id) {
    const saved=saveCurrent();if(saved.length===1){setError('Keep at least one experiment open.');return;}
    const remaining=saved.filter(e=>e.id!==id);setExperiments(remaining);
    if(id===activeIdRef.current){setActiveId(remaining[0].id);loadExperiment(remaining[0]);}
  }
  function exportWorkspace() {
    const saved=saveCurrent().map(({result,dirty,frameIndex,...e})=>e);
    downloadJSON('stratoq-workspace.json',{format:'stratoq-workspace',version:1,activeId:activeIdRef.current,experiments:saved});
  }
  async function importFile(file) {
    if(!file)return;
    try {
      const payload=JSON.parse(await file.text());
      if(payload?.format==='stratoq-workspace' && Array.isArray(payload.experiments) && payload.experiments.length &&
        payload.experiments.every(e=>isScenario(e.scenario))) {
        const restored=payload.experiments.map(e=>({...makeExperiment(e.scenario,e.name || 'Experiment'),id:e.id || makeExperiment(e.scenario).id, selectedId:e.selectedId || null}));
        const chosen=restored.find(e=>e.id===payload.activeId)||restored[0];
        setExperiments(restored);setActiveId(chosen.id);loadExperiment(chosen);
      } else if(isScenario(payload)) {
        const saved=saveCurrent();const next=makeExperiment(payload,file.name.replace(/\.json$/i,'') || 'Imported experiment');
        setExperiments([...saved,next]);setActiveId(next.id);loadExperiment(next);
      } else throw new Error('Not a StratoQ experiment or workspace JSON file.');
    }catch(e){setError(`Import failed: ${e.message}`);}
  }

  useEffect(() => {
    if (!era5Loading) return;
    const started = Date.now();
    setEra5Elapsed(0);
    const timer = setInterval(() => setEra5Elapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [era5Loading]);

  const currentFrame = !dirty ? result?.frames[frameIndex] : null;
  const useEra5 = scenario.config.weather_source === 'era5';
  const historicalRegions = useEra5 ? (currentFrame?.historical_weather_regions || era5Preview) : EMPTY_WEATHER;
  const era5Date = scenario.config.era5_date || '';
  const visualScenario = useMemo(() => {
    const copy = clone(scenario);
    if (currentFrame?.positions) copy.balloons.forEach(h => { const p = currentFrame.positions[h.id]; if (p) Object.assign(h, p); });
    // Display-only ERA5 grid cells. Manual regions are kept unchanged.
    // Backend integrates the ERA5 raster independently (no duplicate attenuation).
    if (useEra5) copy.weather_regions = [...copy.weather_regions, ...historicalRegions];
    return copy;
  }, [scenario, currentFrame, useEra5, historicalRegions]);
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
        lat:CENTER.lat,lon:CENTER.lon,radius_km:16,attenuation_db:0,effect:"fog",visibility_km:0.5,precipitation_rate_mm_h:5,snow_type:"wet"}));
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
  function setEra5Date(value) {
    patchScenario(s=>{
      s.config.era5_date=value||null;
      s.config.era5_dataset_id=null;
      s.config.weather_source='manual';
    });
    setEra5Preview([]);setEra5Meta(null);setEra5Job(null);
  }
  function activateEra5(meta) {
    patchScenario(s=>{
      s.config.weather_source='era5';
      s.config.era5_date=meta.date_utc;
      s.config.era5_dataset_id=meta.dataset_id;
      s.config.slots=Math.min(1500,Math.ceil(86400/s.config.slot_seconds));
    });
    setEra5Meta(meta);setFrameIndex(0);
  }
  async function retrieveEra5() {
    const thisWeatherRequest=++weatherRequestId.current;
    if(!era5Date){setError('Select a historical UTC date first.');return;}
    setEra5Loading(true);setEra5Job({stage:'Connecting to Open-Meteo…',status:'running'});setError('');
    try {
      const response=await fetch('/api/open-meteo/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({date_utc:era5Date,scenario})});
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail||`HTTP ${response.status}`);
      if(thisWeatherRequest!==weatherRequestId.current)return;
      let state=data;
      while(thisWeatherRequest===weatherRequestId.current && (state.status==='queued'||state.status==='running')) {
        await new Promise(resolve=>setTimeout(resolve,1700));
        const progress=await fetch(`/api/open-meteo/jobs/${data.id}`,{cache:'no-store'});
        if(!progress.ok)throw new Error(progress.status === 404
          ? 'The ERA5 download job disappeared (backend restarted). Restart FastAPI and retry; completed Open-Meteo batches will be reused.'
          : `ERA5 status HTTP ${progress.status}`);
        state=await progress.json();
        if(thisWeatherRequest!==weatherRequestId.current)return;
        setEra5Job(state);
      }
      if(thisWeatherRequest!==weatherRequestId.current)return;
      if(state.status!=='complete')throw new Error(state.error||'ERA5 retrieval failed');
      activateEra5(state.dataset);
    }catch(e){if(thisWeatherRequest===weatherRequestId.current)setError(`ERA5: ${e.message}`);}
    finally{if(thisWeatherRequest===weatherRequestId.current)setEra5Loading(false);}
  }
  async function uploadERA5(file) {
    if(!file)return;
    const thisWeatherRequest=++weatherRequestId.current;
    if(!era5Date){setError('Choose a UTC date before uploading ERA5 NetCDF.');return;}
    setEra5Loading(true);setError('');setEra5Job({stage:'Parsing local ERA5…',status:'running'});
    try {
      const form=new FormData();form.append('file',file);form.append('date_utc',era5Date);
      const response=await fetch('/api/era5/upload',{method:'POST',body:form});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
      if(thisWeatherRequest!==weatherRequestId.current)return;
      activateEra5(data);setEra5Job({status:'complete',stage:'ready',dataset:data});
    }catch(e){if(thisWeatherRequest===weatherRequestId.current)setError(`ERA5 import: ${e.message}`);}
    finally{if(thisWeatherRequest===weatherRequestId.current)setEra5Loading(false);}
  }
  useEffect(()=>{
    const datasetId=scenario.config.era5_dataset_id;
    if(!useEra5||!datasetId||currentFrame?.historical_weather_regions){return;}
    let alive=true;
    fetch(`/api/era5/datasets/${encodeURIComponent(datasetId)}/frame?date_utc=${encodeURIComponent(era5Date)}&slot_seconds=${scenario.config.slot_seconds}&slot=${Math.min(frameIndex,Math.floor((86400-1)/scenario.config.slot_seconds))}`,{cache:'no-store'})
      .then(async r=>{const data=await r.json();if(!r.ok)throw new Error(data.detail||'ERA5 preview failed');return data;})
      .then(data=>{if(alive){setEra5Preview(data.regions);setEra5Meta(data.dataset);}})
      .catch(e=>{if(alive)setError(`ERA5 preview: ${e.message}`)});
    return ()=>{alive=false;};
  },[scenario.config.era5_dataset_id,scenario.config.slot_seconds,era5Date,frameIndex,useEra5,dirty]);
  function toggleEra5(enabled) {
    if(enabled && !scenario.config.era5_dataset_id){setError('Load a historical ERA5 dataset before enabling historical weather.');return;}
    patchScenario(s=>{s.config.weather_source=enabled?'era5':'manual';if(enabled)s.config.slots=Math.min(1500,Math.ceil(86400/s.config.slot_seconds));});
  }
  async function runSim(caseInput=scenario, {silent=false, autoPlay=false}={}) {
    const id=++requestId.current;
    if(caseInput.config.weather_source==='era5' && !caseInput.config.era5_dataset_id){
      setError('Load ERA5 historical weather first, or switch back to Manual only.');return;
    }
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
    setPlaying(false); setDirty(true); setEra5Preview([]);setEra5Meta(null);setEra5Job(null);runSim(resetCase);
  }
  const totalFrames=(!dirty ? result?.frames.length : scenario.config.slots)||scenario.config.slots;
  const selectedDemand=result?.frames[frameIndex]?.demands.find(d=>d.id===selectedId);

  return <div className="app-shell" data-ui-build="1.0.7" style={{gridTemplateColumns:`${leftOpen?`${leftWidth}px`:'0px'} minmax(0,1fr) ${rightOpen?`${rightWidth}px`:'0px'}`}}>
    <input ref={importRef} type="file" accept=".json,application/json" hidden onChange={e=>{importFile(e.target.files?.[0]);e.target.value='';}}/>
    <input ref={workspaceRef} type="file" accept=".json,application/json" hidden onChange={e=>{importFile(e.target.files?.[0]);e.target.value='';}}/>
    <aside className={`left-panel ${leftOpen?"":"is-collapsed"}`}>
      <div className="panel-resizer resizer-left" onPointerDown={e=>beginResize("left",e)} title="Drag to resize left panel"/>
      <div className="brand-wrap">
        <div className="brand-symbol"><img className="brand-atom-mark" src="/favicon.svg?v=107" alt="StratoQ three-orbit atom emblem" /></div>
        <div className="brand-wordmark"><div className="brand-title">Strato<span>Q</span></div><div className="brand-product">SIMULATION STUDIO</div></div>
      </div>
      <div className="side-scroll">
        <div className="section-pad workspace-section">
          <div className="eyebrow">WORKSPACE <span className="eyebrow-hint">{experiments.length} EXPERIMENT{experiments.length!==1?'S':''}</span></div>
          <div className="workspace-current"><span className="project-status"/><strong title={activeExperiment?.name}>{activeExperiment?.name}</strong>
            <button className="workspace-rename" onClick={()=>renameExperiment(activeId)} title="Rename experiment" aria-label="Rename experiment"><Pencil size={13}/></button></div>
          <div className="workspace-actions"><button onClick={createExperiment}><Plus size={13}/> New</button>
            <button onClick={duplicateExperiment} title="Duplicate current experiment"><Copy size={13}/> Duplicate</button></div>
          <div className="workspace-tabs" role="tablist" aria-label="Experiments">
            {experiments.map(e=><div className={`workspace-tab ${e.id===activeId?'active':''}`} key={e.id}>
              <button role="tab" aria-selected={e.id===activeId} onClick={()=>changeExperiment(e.id)} title={e.name}>{e.name}</button>
              <button className="tab-close" aria-label={`Close ${e.name}`} onClick={()=>closeExperiment(e.id)}><X size={12}/></button>
            </div>)}
          </div>
          <p className="workspace-note">Experiments auto-save locally in this browser. Export a workspace file for reliable backup.</p>
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
        <section className="section-pad era5-panel">
          <GroupTitle><CalendarDays size={13}/> HISTORICAL WEATHER · ERA5</GroupTitle>
          <label className="era5-switch"><input type="checkbox" checked={useEra5} onChange={e=>toggleEra5(e.target.checked)}/>
            <span>Use ERA5 historical weather</span></label>
          <label className="era5-date-label"><span>Date (UTC)</span>
            <input aria-label="ERA5 historical date UTC" type="date" value={era5Date} max={new Date(Date.now()-7*86400000).toISOString().slice(0,10)} onChange={e=>setEra5Date(e.target.value)} /></label>
          <button className="era5-load" type="button" onClick={retrieveEra5} disabled={era5Loading||!era5Date}>
            <CloudRain size={14}/>{era5Loading?'Retrieving ERA5…':'Load ERA5 from Open-Meteo'}</button>
          <label className="era5-import">Import local ERA5 .nc / .zip
            <input type="file" accept=".nc,.nc4,.zip" disabled={era5Loading} onChange={e=>{uploadERA5(e.target.files?.[0]);e.target.value='';}}/></label>
          {era5Job?.stage && <div className="era5-progress" role="status" aria-live="polite">
            <div className="era5-progress-label"><small>{era5Job.status==='failed'?'Error: ':''}{era5Job.stage}</small>
              <small>{era5Loading?`${Math.floor(era5Elapsed/60)}m ${String(era5Elapsed%60).padStart(2,'0')}s`:''}</small></div>
            {(era5Loading || era5Job.status==='complete') && <>
              <div className="era5-progress-track" aria-label="Completed Open-Meteo grid batches">
                <div style={{width:`${Math.min(100,100*(era5Job.completed_steps||0)/(era5Job.total_steps||1))}%`}} />
                {era5Loading && <span className="era5-progress-active" />}
              </div>
              <small className="era5-progress-caption">
                {era5Job.completed_steps||0}/{era5Job.total_steps||1} grid batches completed
                {era5Job.transferred_bytes>0 ? ` · ${(era5Job.transferred_bytes/1024).toFixed(1)} KB received for current file` : ''}
              </small>
              <small className="era5-progress-note">Sequential Open-Meteo requests; completed batches are cached locally.</small>
            </>}
          </div>}
          {scenario.config.era5_dataset_id && <small className="era5-loaded">{useEra5?'● Historical mode active':'○ ERA5 loaded, paused'} · {era5Date}</small>}
          <p className="era5-help">ERA5 reanalysis via Open-Meteo (no CDS queue or API key). 0.25° grid, UTC; snow uses Open-Meteo’s fixed snow-to-water conversion. Manual weather remains additive; fog is a proxy.</p>
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
          <div className="physics-progress-meta"><b>{physicsProgress.stage==='channel'?'Calculating upstream channel':physicsProgress.stage==='era5-sampling'?'Sampling ERA5 weather along links…':'Preparing physical setup…'}</b>
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
        <div className="topbar-identity"><button className="panel-toggle" onClick={()=>setLeftOpen(v=>!v)} title={leftOpen?'Collapse workspace':'Expand workspace'}>{leftOpen?<PanelLeftClose size={18}/>:<PanelLeftOpen size={18}/>}</button><span className="topbar-current">{activeExperiment?.name}</span></div>
        <div className="topbar-right">
          <Chip accent="demo">STRATOQ · {STUDIO_VERSION} · UI 1.0.7</Chip>
          <button className="header-text-button" onClick={()=>downloadJSON('stratoq-experiment.json',scenario)}><ArrowDownToLine size={15}/> Export experiment</button>
          <button className="header-text-button" onClick={()=>importRef.current?.click()}><ArrowUpFromLine size={15}/> Import</button>
          <button className="header-text-button workspace-export" onClick={exportWorkspace}><ArrowDownToLine size={15}/> Export workspace</button>
          <button className="panel-toggle" onClick={()=>setRightOpen(v=>!v)} title={rightOpen?'Collapse inspector':'Expand inspector'}>{rightOpen?<PanelRightClose size={18}/>:<PanelRightOpen size={18}/>}</button>
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
            <div><strong>Simulation timeline</strong><small>{totalFrames} slots · {scenario.config.slot_seconds}s per slot{useEra5?' · ERA5 UTC':''}</small></div></div>
            <div className="timeline-actions"><span className="time-current">{useEra5&&era5Date ? `${era5Date} ${toClock((currentFrame?.time_seconds ?? frameIndex*scenario.config.slot_seconds))} UTC` : `T+${toClock((currentFrame?.time_seconds ?? 0))}`}</span>
              <button onClick={()=>{setFrameIndex(0);setPlaying(false);}} title="Restart playback"><RefreshCcw size={15}/></button>
              <button className="playback-button" onClick={togglePlayback} disabled={running} title={dirty || !result ? "Recalculate and play updated scenario" : playing ? "Pause" : "Play"}>{running?<RefreshCcw size={16} className="spin"/>:playing?<Pause size={16} fill="currentColor"/>:<Play size={16} fill="currentColor"/>}</button>
            </div></div>
          <div className="trajectory-slot-control"><label htmlFor="slot-seconds">Time slot</label>
            <select id="slot-seconds" value={scenario.config.slot_seconds} onChange={e=>patchScenario(s=>{s.config.slot_seconds=Number(e.target.value);if(s.config.weather_source==='era5')s.config.slots=Math.min(1500,Math.ceil(86400/s.config.slot_seconds));})}>
              {[10,30,60,120,300,600,900,1800,3600].map(v=><option key={v} value={v}>{v<60?`${v} sec`:v<3600?`${v/60} min`:`${v/3600} hour`}</option>)}
            </select><small>Trajectory horizon adjusts on Play</small></div>
          <div className="timeline-scrub"><span>00:00</span><input aria-label="Simulation time slot" type="range" min={0} max={Math.max(0,totalFrames-1)}
            value={frameIndex} onChange={e=>{setFrameIndex(Number(e.target.value));setPlaying(false);}}
            style={{'--progress': `${totalFrames>1 ? 100*frameIndex/(totalFrames-1) : 0}%`}} disabled={!result}/>
            <span>{toClock((totalFrames-1)*scenario.config.slot_seconds)}</span></div>
          <div className="timeline-footer"><span><span className="timeline-dot aqua"/> Link state</span><span><span className="timeline-dot purple"/> QKP buffers</span>
            <span className="timeline-note">Frame {frameIndex+1} of {totalFrames}{useEra5?` · ${historicalRegions.length} ERA5 cells shown · ${scenario.weather_regions.length} manual`:''}{dirty?' · press Play to update':''}</span></div>
        </div>
      </div>
    </main>

    <aside className={`right-panel ${rightOpen?"":"is-collapsed"}`}>
      <div className="panel-resizer resizer-right" onPointerDown={e=>beginResize("right",e)} title="Drag to resize inspector"/>
      <div className="inspector-top"><div><span className="tiny-overline">CONTROL CENTER</span><h2>Inspector <SlidersHorizontal size={17}/></h2></div>
        <IconButton icon={ArrowDownToLine} label="Export simulation results" onClick={()=>result&&downloadJSON('stratoq-results.json',result)} disabled={!result}/></div>
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
                {selected.effect==='snow' && <label className="field-label"><span>Snow type (optical attenuation fit)</span>
                  <select value={selected.snow_type||'wet'} onChange={e=>modifyItem(selected.id,'snow_type',e.target.value)}>
                    <option value="wet">Wet snow</option><option value="dry">Dry snow</option>
                  </select></label>}
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
          {useEra5 && <p className="field-help">Historical ERA5 date: {era5Date} UTC. At most 24 h; changing the time slot resamples the same hourly dataset. Manual regions add to ERA5 attenuation. ERA5 animation shows up to 75 visual cells; link physics samples the full grid.</p>}
          <div className="field-grid"><Numeric label="Time slots" value={scenario.config.slots} min={1} max={1500} step={1} onChange={v=>patchScenario(s=>s.config.slots=v)} />
            <Numeric label="Slot duration" value={scenario.config.slot_seconds} unit="sec" min={1} max={86400} step={1} onChange={v=>patchScenario(s=>{s.config.slot_seconds=v;if(s.config.weather_source==='era5')s.config.slots=Math.min(1500,Math.ceil(86400/v));})} /></div>
          <div className="field-grid">
            <label className="field-label"><span>Placeholder routing</span>
              <select value={scenario.config.allocation_mode || 'random'} onChange={e=>patchScenario(s=>s.config.allocation_mode=e.target.value)}>
                <option value="random">Random (seeded)</option><option value="greedy">Greedy (largest QKP)</option>
              </select>
            </label>
            <Numeric label="Random seed" value={scenario.config.allocator_seed ?? 42} min={0} max={2147483647} step={1} onChange={v=>patchScenario(s=>s.config.allocator_seed=v)}/>
          </div>
          <div className="inspector-subsection-heading"><GroupTitle>PHYSICAL CHANNEL · UPSTREAM THEORY</GroupTitle></div>
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
          <button className="secondary-button" onClick={()=>importRef.current?.click()}><ArrowUpFromLine size={15}/> Import experiment / workspace JSON</button>
        </div>
      </div>
      <div className="right-footer"><div className="waterloo-credit"><a className="waterloo-shield-link" href="https://uwaterloo.ca/" target="_blank" rel="noreferrer" aria-label="University of Waterloo"><span className="waterloo-shield-crop"><img className="waterloo-shield-source" src="https://uwaterloo.ca/brand/sites/ca.brand/files/universityofwaterloo_logo_horiz_rev_rgb.png" alt="University of Waterloo shield" loading="lazy" referrerPolicy="no-referrer" /></span></a><span>Developed at the <a className="lab-link" href="https://rboutaba-cs.github.io/watqkd/" target="_blank" rel="noreferrer">Networks Lab</a><small>University of Waterloo</small></span></div></div>
    </aside>
  </div>;
}
