import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowDownToLine, ArrowUpFromLine, ArrowRight, Box, Check, ChevronDown, CircleHelp,
  Cloud, CloudRain, CalendarDays, Crosshair, Eye, EyeOff, Gauge, Layers3, Map, Maximize2, MousePointer2,
  Pause, Play, Plus, RadioTower, RefreshCcw, Rotate3D, SatelliteDish,
  Settings2, SlidersHorizontal, Sparkles, Trash2, Wifi, WifiOff, X, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, GripVertical, Pencil, Copy, BrainCircuit,
} from 'lucide-react';
import Network3D from './components/Network3D.jsx';
import GeoMap from './components/GeoMap.jsx';
import LearningLab from './components/LearningLab.jsx';
import {StoryRail, StoryDialog} from './components/ShowcaseStory.jsx';
import {SHOWCASE_STORIES, buildStoryMoments} from './lib/showcaseStory.js';
import {matchingQkpInputs, qkpComparisonDelta} from './lib/qkpComparison.js';
import {upgradeLegacyShowcase} from './lib/curatedWorkspace.js';
import { INITIAL_SCENARIO } from './lib/sample.js';
import BUILTINS from './lib/builtinExperiments.json';
import { CENTER, flatDistance } from './lib/geo.js';
import { potentialLinks } from './lib/topology.js';
import {allocationsForLink, demandColor, linkKeyMode} from './lib/linkVisuals.js';
import { demandSeries, simulationHorizonSeconds, slotCount } from './lib/demandProfiles.js';

const STUDIO_VERSION = '1.0.5'; // Stable backend API handshake; UI showcase v1.3.2
const EMPTY_WEATHER = [];
const clone = (obj) => structuredClone(obj);
function migrateAllocator(scenario) {
  const result=clone(scenario);
  if (result.config?.allocation_mode === 'random') result.config.allocation_mode = 'mcr_q';
  else if (result.config?.allocation_mode === 'greedy') result.config.allocation_mode = 'scar_q';
  else if (!result.config?.allocation_mode) result.config.allocation_mode = 'scar_q';
  result.config.slots = slotCount(result);
  return result;
}
const fmtRate = (n) => !Number.isFinite(n) ? '—' : `${(n / 1000).toFixed(1)} kb/s`;
const fmtKeys = (n) => !Number.isFinite(n) ? '—' : n >= 1e9 ? `${(n/1e9).toFixed(3)} Gb` : n >= 1e6 ? `${(n/1e6).toFixed(3)} Mb` : `${Math.round(n).toLocaleString()} bits`;
const fmtBits = (n) => !Number.isFinite(n) ? '—' : n >= 1e6 ? `${(n/1e6).toFixed(2)} Mb` : `${(n/1000).toFixed(0)} kb`;
const toClock = (secs) => `${String(Math.floor(secs/3600)).padStart(2,'0')}:${String(Math.floor(secs%3600/60)).padStart(2,'0')}`;

function DemandPreview({ demand, slots, seconds }) {
  const rates = useMemo(() => demandSeries(demand, slots, seconds), [demand, slots, seconds]);
  if(!rates.length) return null;
  const n = Math.min(180, rates.length);
  const sampled = Array.from({length:n},(_,i)=>rates[Math.min(rates.length-1,Math.floor(i*(rates.length-1)/Math.max(1,n-1)))]);
  const peak = Math.max(...sampled, 1);
  const points = sampled.map((value,i)=>`${(i/(n-1||1)*268).toFixed(1)},${(80 - 70*value/peak).toFixed(1)}`).join(' ');
  const area = `0,80 ${points} 268,80`;
  return <div className="demand-preview" aria-label="Demand rate pattern preview">
    <div className="demand-preview-head"><b>Rate profile</b><span>Mean {fmtRate(demand.rate_bps)} · Peak {fmtRate(peak)}</span></div>
    <svg viewBox="0 0 280 100" preserveAspectRatio="none" role="img" aria-label="Requested key rate over simulated time">
      <line x1="6" y1="80" x2="274" y2="80" stroke="#516171" strokeWidth="1"/>
      <polygon points={area} fill="rgba(145,154,190,.16)"/>
      <polyline points={points} fill="none" stroke="#abb3d0" strokeWidth="2.3" strokeLinejoin="round"/>
      <text x="5" y="94" fill="#8f9bad" fontSize="9">0h</text>
      <text x="274" y="94" textAnchor="end" fill="#8f9bad" fontSize="9">{(slots*seconds/3600).toFixed(1)}h</text>
    </svg>
  </div>;
}
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
function EntityItem({ item, icon: Icon, subtitle, selected, onClick, color }) {
  return <button className={`entity-item ${selected?'selected':''}`} onClick={onClick}>
    <span className="entity-icon" style={color?{color}:undefined}><Icon size={16}/></span><span className="entity-copy"><b>{item.name}</b><small>{subtitle}</small></span>
    <span className="entity-indicator" /></button>;
}
function downloadJSON(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href=url; a.download=filename; a.click(); setTimeout(()=>URL.revokeObjectURL(url), 200);
}

// Optional real historical weather scenario, using the validated bundled
// Open-Meteo ERA5 NetCDF, not invented rain or a future weather forecast.
const HISTORICAL_WEATHER={day:'2024-06-21',id:'3dc42073ef98e69faf58'};
const WORKSPACE_KEY = 'stratoq.workspace.v104';
const makeExperiment = (scenario, name='New experiment') => ({
  id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())+Math.random(),
  name, scenario: migrateAllocator(scenario), baselineScenario: migrateAllocator(scenario),
  selectedId: null, result: null, dirty: true, frameIndex: 0,
});
const makeBuiltin = (preset) => ({
  ...makeExperiment(preset.scenario,preset.title),
  builtin: {id:preset.id, family:preset.family, angle:preset.angle, watch:preset.watch},
  selectedId: preset.scenario.balloons[0]?.id || null,
});
function readWorkspace() {
  try {
    const stored = JSON.parse(localStorage.getItem(WORKSPACE_KEY) || 'null');
    if (stored?.experiments?.length && stored.experiments.every(e => isScenario(e.scenario))) {
      const restored=stored.experiments.map(e=>({...e,scenario:migrateAllocator(e.scenario),
        baselineScenario:isScenario(e.baselineScenario)?migrateAllocator(e.baselineScenario):null,
        result:null,dirty:true}));
      const activeId=restored.some(e=>e.id===stored.activeId)?stored.activeId:restored[0].id;
      return upgradeLegacyShowcase(restored,activeId,BUILTINS.experiments,makeBuiltin,migrateAllocator,isScenario) || {experiments:restored,activeId};
    }
  }catch(err){console.warn('Unable to restore Studio workspace:',err);}
  const firsts=BUILTINS.experiments.map(makeBuiltin);
  return {experiments:firsts,activeId:firsts[0].id};
}
function isScenario(obj) {
  return obj && typeof obj==='object' && !Array.isArray(obj) &&
    Array.isArray(obj.ground_stations) && Array.isArray(obj.balloons) &&
    Array.isArray(obj.demands) && Array.isArray(obj.weather_regions) &&
    obj.config && typeof obj.config==='object';
}
export default function App() {
  const [activeScreen, setActiveScreen] = useState('studio');
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
  const filesMenuRef=useRef(null);
  const [storyOpen,setStoryOpen]=useState(false);
  const [timelineExpanded,setTimelineExpanded]=useState(false);
  const [selectedMomentId,setSelectedMomentId]=useState(null);
  const workspaceRef=useRef(null);
  const resizeRef=useRef(null);
  const latestSnapshot=useRef(null);
  const latestExperiments=useRef(experiments);
  const activeIdRef=useRef(activeId);
  const [mode, setMode] = useState('3d');
  const [showLabels, setShowLabels] = useState(true);
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
  useEffect(()=>{
    const closeOutside=(event)=>{
      if(filesMenuRef.current?.open && !filesMenuRef.current.contains(event.target))
        filesMenuRef.current.open=false;
    };
    const closeEscape=(event)=>{
      if(event.key==='Escape' && filesMenuRef.current?.open) filesMenuRef.current.open=false;
    };
    document.addEventListener('pointerdown',closeOutside);
    document.addEventListener('keydown',closeEscape);
    return ()=>{document.removeEventListener('pointerdown',closeOutside);document.removeEventListener('keydown',closeEscape);};
  },[]);
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
    setStoryOpen(false);setSelectedMomentId(null);
    ++requestId.current; ++weatherRequestId.current;
    setScenario(migrateAllocator(exp.scenario));setSelectedId(exp.selectedId || null);
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
  function addBuiltinExperiment(presetId) {
    const preset=BUILTINS.experiments.find(p=>p.id===presetId);
    if(!preset)return;
    const saved=saveCurrent();
    // Reuse already-open unmodified presets rather than creating duplicate tabs.
    const current=saved.find(e=>e.builtin?.id===preset.id &&
      JSON.stringify(e.scenario)===JSON.stringify(migrateAllocator(preset.scenario)));
    if(current){ if(current.id!==activeIdRef.current){setExperiments(saved);setActiveId(current.id);loadExperiment(current);}return; }
    const next=makeBuiltin(preset);
    setExperiments([...saved,next]);setActiveId(next.id);loadExperiment(next);
  }
  function switchQkpCase() {
    const target=activeExperiment?.builtin?.id==='qkp-disabled'?'qkp-enabled':'qkp-disabled';
    const counterpart=BUILTINS.experiments.find(p=>p.id===target);
    if(!counterpart)return;
    const saved=saveCurrent();
    const existing=saved.find(e=>e.builtin?.id===target &&
      matchingQkpInputs(e.scenario,scenario) && e.scenario.config.qkp_enabled===counterpart.scenario.config.qkp_enabled);
    if(existing){setExperiments(saved);setActiveId(existing.id);loadExperiment(existing);}
    else addBuiltinExperiment(target);
  }
  function createHistoricalVariant() {
    const saved=saveCurrent();
    const copy=clone(scenario);
    copy.weather_regions=[]; // Never combine scripted storm with ERA5 silently.
    copy.config.weather_source='era5';
    copy.config.era5_date=HISTORICAL_WEATHER.day;
    copy.config.era5_dataset_id=HISTORICAL_WEATHER.id;
    const next=makeExperiment(copy,`${activeExperiment.name} · ERA5 ${HISTORICAL_WEATHER.day}`);
    next.selectedId=selectedId;
    setExperiments([...saved,next]);setActiveId(next.id);loadExperiment(next);
  }
  function replaceInitialExamples() {
    if (!window.confirm('Replace all tabs with the four matched 24-hour demos (SCAR-Q, MCR-Q, Optimal QKP on, Optimal QKP off)? Export your workspace first to preserve edits.'))return;
    const next=BUILTINS.experiments.map(makeBuiltin);
    setExperiments(next);setActiveId(next[0].id);loadExperiment(next[0]);
  }
  function duplicateExperiment() {
    const saved=saveCurrent();const current=saved.find(e=>e.id===activeIdRef.current);
    const next={...makeExperiment(current.scenario,`${current.name} copy`),selectedId:current.selectedId,
      builtin:current.builtin ? clone(current.builtin) : null};
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
        const restored=payload.experiments.map(e=>({...makeExperiment(e.scenario,e.name || 'Experiment'),id:e.id || makeExperiment(e.scenario).id, selectedId:e.selectedId || null,builtin:e.builtin || null,
          baselineScenario:isScenario(e.baselineScenario)?migrateAllocator(e.baselineScenario):migrateAllocator(e.scenario)}));
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
    if (currentFrame?.manual_weather_regions) copy.weather_regions = currentFrame.manual_weather_regions;
    // Time-dependent manual weather is computed by the backend physics snapshot.
    // Backend integrates the ERA5 raster independently (no duplicate attenuation).
    if (useEra5) copy.weather_regions = [...copy.weather_regions, ...historicalRegions];
    return copy;
  }, [scenario, currentFrame, useEra5, historicalRegions]);
  const nodes = useMemo(() => [...scenario.ground_stations, ...scenario.balloons, ...scenario.weather_regions], [scenario]);
  const topologyLinks = useMemo(() => potentialLinks(visualScenario, currentFrame, !dirty), [visualScenario, currentFrame, dirty]);
  const selectedLink = topologyLinks.find(l => l.id === selectedId);
  const selected = nodes.find(n => n.id === selectedId) || scenario.demands.find(n => n.id === selectedId) || selectedLink;
  const selectedType = selectedLink ? 'link'
    : scenario.ground_stations.some(n=>n.id===selectedId) ? 'gs'
    : scenario.balloons.some(n=>n.id===selectedId) ? 'hap'
    : scenario.weather_regions.some(n=>n.id===selectedId) ? 'weather' : 'demand';
  const activeLinks = currentFrame?.links.filter(l => l.activated).length || 0;
  const qkpOnlyLinks = currentFrame?.links.filter(l => l.allocated && !l.activated).length || 0;
  const slotSolver = currentFrame?.optimizer;
  const solverSummary = result?.summary;
  const computedSlots = slotCount(scenario);
  const horizonHours = simulationHorizonSeconds(scenario)/3600;
  const served = currentFrame?.served_bps_total;
  const requested = currentFrame?.demands.reduce((n,d)=>n+d.requested_bps,0) ?? scenario.demands.reduce((n,d)=>n+d.rate_bps,0);
  const satisfaction = currentFrame && requested > 0 ? Math.round(100*served/requested) : null;
  const firstLink = currentFrame?.links.find(l=>l.target===selectedId || l.source===selectedId) || currentFrame?.links[0];
  const builtinPreset=BUILTINS.experiments.find(p=>p.id===activeExperiment?.builtin?.id);
  // All four demos use the same physical scenario; the two Optimal cases
  // differ only in whether QKP storage is enabled.
  const storyPresetId=SHOWCASE_STORIES[activeExperiment?.builtin?.id] ? activeExperiment.builtin.id : null;
  const isQkpStudy=['qkp-enabled','qkp-disabled'].includes(storyPresetId);
  // Scenario story labels are always visible, even before the first simulation
  // or when a saved tab uses a different slot length.  Measured markers only
  // use actual solver frames; they never manufacture allocation outcomes.
  const story=SHOWCASE_STORIES[storyPresetId];
  const moments=useMemo(()=>buildStoryMoments(storyPresetId,scenario,!dirty?result:null),
    [storyPresetId,scenario,dirty,result]);
  const storyChanged=!!builtinPreset && (
    ['slot_seconds','horizon_seconds','allocation_mode','qkp_enabled'].some(k=>
      scenario.config?.[k]!==builtinPreset.scenario.config?.[k]) ||
    ['balloons','ground_stations','demands','weather_regions'].some(k=>
      JSON.stringify(scenario[k]||[])!==JSON.stringify(builtinPreset.scenario[k]||[])));
  const pinnedMoment=moments.find(m=>m.id===selectedMomentId);
  const currentMoment=(pinnedMoment && frameIndex>=pinnedMoment.fromIndex && frameIndex<=pinnedMoment.toIndex ? pinnedMoment : null) ||
    moments.find(m=>m.fromIndex<=frameIndex && m.toIndex>=frameIndex) || null;
  const storyMomentId=currentMoment?.id||null;
  const jumpToStoryMoment=(moment)=>{
    setPlaying(false);setFrameIndex(moment.index);setSelectedMomentId(moment.id);
  };
  // Compare only physically matched, completed scenarios; do not mix legacy tabs.
  const matchedExperiments=experiments.map(e=>e.id===activeId?{...e,scenario,dirty,result}:e).filter(e=>
    e.builtin?.family===activeExperiment?.builtin?.family &&
    (isQkpStudy ? matchingQkpInputs(e.scenario,scenario) : (
      (e.scenario.config.qkp_enabled!==false)===(scenario.config.qkp_enabled!==false) &&
      e.scenario?.config?.slot_seconds===scenario.config.slot_seconds &&
      simulationHorizonSeconds(e.scenario)===simulationHorizonSeconds(scenario) &&
      JSON.stringify(e.scenario.config.optical)===JSON.stringify(scenario.config.optical) &&
      ['ground_stations','balloons','demands','weather_regions','link_overrides'].every(field=>
        JSON.stringify(e.scenario[field]||[])===JSON.stringify(scenario[field]||[])))));
  // One row per QKP mode; never compare stale or physically different inputs.
  const comparableBuiltins=isQkpStudy ? [true,false].map(on=>
    matchedExperiments.find(e=>e.id===activeId && (e.scenario.config.qkp_enabled!==false)===on) ||
    matchedExperiments.find(e=>(e.scenario.config.qkp_enabled!==false)===on && !e.dirty && e.result?.summary) ||
    matchedExperiments.find(e=>(e.scenario.config.qkp_enabled!==false)===on)
  ).filter(Boolean) : matchedExperiments;
  const comparedSummary=(e)=>e && (e.id===activeId ? (!dirty?result?.summary:null) : (!e.dirty?e.result?.summary:null));
  const onSummary=comparedSummary(comparableBuiltins.find(e=>e.scenario.config.qkp_enabled!==false));
  const offSummary=comparedSummary(comparableBuiltins.find(e=>e.scenario.config.qkp_enabled===false));
  const qkpDelta=isQkpStudy ? qkpComparisonDelta(onSummary,offSummary) : null;

  function patchScenario(mutator) {
    setScenario(old => { const next = clone(old); mutator(next); return next; });
    requestId.current += 1; // Discard responses computed for older scenarios.
    setRunning(false); setDirty(true); setPlaying(false); setPhysicsProgress(null);
  }
  function modifyItem(id, field, value) {
    patchScenario(s=>{for(const group of ['ground_stations','balloons','weather_regions','demands']) {
      const obj=s[group].find(o=>o.id===id); if(obj) {
        obj[field]=value;
        if (group==='balloons' && obj.trajectory_id && (field==='lat'||field==='lon')) {
          obj.trajectory_origin_mode='shifted';
          obj.trajectory_start_lat=obj.lat; obj.trajectory_start_lon=obj.lon;
        }
        break;}
    }});
  }
  function onPositionChange(id, lat, lon) {
    patchScenario(s=>{const n=[...s.ground_stations,...s.balloons,...s.weather_regions].find(x=>x.id===id);
      if (n) { n.lat=Math.max(-90,Math.min(90,lat)); n.lon=Math.max(-180,Math.min(180,lon));
        if (n.trajectory_id) { n.trajectory_origin_mode='shifted';n.trajectory_start_lat=n.lat;n.trajectory_start_lon=n.lon; }
      }});
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
      patchScenario(s=>s.demands.push({id,source:s.ground_stations[0].id,target:s.ground_stations[1].id,rate_bps:6000,pattern:"constant"}));
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
        if (hap) Object.assign(hap, {trajectory_id:payload.trajectory_id,trajectory_name:payload.filename, trajectory_duration_seconds:payload.duration_seconds, trajectory_origin_mode:'original',trajectory_start_lat:null,trajectory_start_lon:null,trajectory_source_lat:payload.first.lat,trajectory_source_lon:payload.first.lon, ...payload.first});
        s.config.slots = slotCount(s);
      });
    } catch(e) { setError(`Trajectory import: ${e.message}`); }
    finally {setUploadingTrajectory(false);}
  }
  function setTrajectoryOrigin(hapId, mode) {
    patchScenario(s=>{
      const h=s.balloons.find(h=>h.id===hapId);
      if (!h || !h.trajectory_id)return;
      h.trajectory_origin_mode=mode;
      if(mode==='original'){
        if(h.trajectory_source_lat!=null)h.lat=h.trajectory_source_lat;
        if(h.trajectory_source_lon!=null)h.lon=h.trajectory_source_lon;
        h.trajectory_start_lat=null;h.trajectory_start_lon=null;
      }else{
        h.trajectory_start_lat=h.lat;
        h.trajectory_start_lon=h.lon;
      }
    });
  }
  function setTrajectoryStart(hapId, axis, value) {
    patchScenario(s=>{
      const h=s.balloons.find(h=>h.id===hapId);
      if(!h||!Number.isFinite(value))return;
      const field=axis==='lat'?'trajectory_start_lat':'trajectory_start_lon';
      h[field]=value;
      h.trajectory_origin_mode='shifted';
      h[axis]=value;
      if(h.trajectory_start_lat==null)h.trajectory_start_lat=h.lat;
      if(h.trajectory_start_lon==null)h.trajectory_start_lon=h.lon;
    });
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
      s.config.slots=slotCount(s);
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
    patchScenario(s=>{s.config.weather_source=enabled?'era5':'manual';if(enabled)s.config.slots=slotCount(s);});
  }
  async function restoreWeatherBeforeRun(caseInput, runId) {
    if (caseInput.config.weather_source !== 'era5') return caseInput;
    const day = caseInput.config.era5_date;
    if (!day) throw new Error('Select a historical UTC date before running with ERA5.');
    const oldId = caseInput.config.era5_dataset_id;
    if (oldId) {
      const lookup = await fetch(`/api/era5/datasets/${encodeURIComponent(oldId)}/metadata?date_utc=${encodeURIComponent(day)}`, {cache:'no-store'});
      if (lookup.ok) return caseInput; // exact saved dataset was restored from disk
      if (lookup.status !== 404) {
        const details = await lookup.json().catch(()=>null);
        throw new Error(details?.detail || `Unable to validate saved ERA5 dataset: HTTP ${lookup.status}`);
      }
    }
    // The original cache file is unavailable. Retrieve the requested real ERA5
    // data from Open-Meteo, showing progress, without approximating weather.
    // This can take time on a cold start; completed grid batches are cached.
    setEra5Loading(true);
    setEra5Job({status:'running', stage:`Restoring ERA5 ${day} from Open-Meteo…`});
    try {
      const response=await fetch('/api/open-meteo/jobs', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({date_utc:day, scenario:caseInput})});
      const job=await response.json().catch(()=>null);
      if(!response.ok)throw new Error(job?.detail || `Open-Meteo retrieval HTTP ${response.status}`);
      let state=job;
      while(runId===requestId.current && (state.status==='queued' || state.status==='running')) {
        await new Promise(resolve=>setTimeout(resolve,1700));
        const progress=await fetch(`/api/open-meteo/jobs/${job.id}`, {cache:'no-store'});
        if(!progress.ok)throw new Error(`Open-Meteo retrieval interrupted (HTTP ${progress.status}); retry the simulation.`);
        state=await progress.json();
        if(runId===requestId.current)setEra5Job(state);
      }
      if(runId!==requestId.current)return null;
      if(state.status!=='complete' || !state.dataset?.dataset_id)
        throw new Error(state.error || 'Open-Meteo could not restore the selected ERA5 date.');
      const recovered=clone(caseInput);
      recovered.config.era5_dataset_id=state.dataset.dataset_id;
      // Keep the saved experiment in sync with the newly downloaded dataset ID.
      setScenario(prev => prev.config.era5_dataset_id===oldId && prev.config.era5_date===day
        ? {...prev, config:{...prev.config,era5_dataset_id:state.dataset.dataset_id}} : prev);
      setEra5Preview([]);setEra5Meta(state.dataset);
      setEra5Job({status:'complete',stage:'ERA5 restored from Open-Meteo',dataset:state.dataset});
      return recovered;
    } finally {if(runId===requestId.current)setEra5Loading(false);}
  }

  async function runSim(caseInput=scenario, {silent=false, autoPlay=false}={}) {
    const id=++requestId.current;
    setRunning(true);setError('');setPlaying(false);
    setPhysicsProgress({stage:'queued',completed:0,total:0,cached:0,computed:0});
    try {
      // The real upstream LOWTRAN + turbulence/AO channel can take minutes on
      // larger topologies; start a monitored backend job instead of blocking UI.
      const readyCase=await restoreWeatherBeforeRun(caseInput,id);
      if(id!==requestId.current || !readyCase)return;
      const response=await fetch('/api/simulations', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readyCase)});
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
      setError(`Simulation failed: ${e.message}. See FastAPI terminal. No approximate rates were substituted.`);
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
    // The reset button restores the current tab's original scenario. The
    // 2-GS/1-HAP template is ONLY used for creating a new experiment.
    const original=activeExperiment?.baselineScenario || builtinPreset?.scenario || activeExperiment?.scenario || scenario;
    const resetCase=migrateAllocator(original);
    const first=resetCase.balloons[0]?.id || resetCase.ground_stations[0]?.id || null;
    ++requestId.current; // Cancel stale simulation/poll responses before resetting.
    setScenario(resetCase);setSelectedId(first);setFrameIndex(0);setSceneKey(k=>k+1);
    setPlaying(false);setResult(null);setDirty(true);setRunning(false);setPhysicsProgress(null);
    setEra5Preview([]);setEra5Meta(null);setEra5Job(null);setError('');
    setExperiments(current=>current.map(e=>e.id===activeId?{...e,scenario:resetCase,selectedId:first,result:null,dirty:true,frameIndex:0}:e));
  }
  const totalFrames=(!dirty ? result?.frames.length : computedSlots)||computedSlots;
  const selectedDemand=result?.frames[frameIndex]?.demands.find(d=>d.id===selectedId);

  if (activeScreen==='learning') return <div className="ll-page" data-ui-build="1.2.2-learning">
    <header className="ll-topbar"><div className="ll-brand"><img src="/favicon.svg?v=115" alt="StratoQ icon"/><strong>Strato<span>Q</span></strong><small>SIMULATION STUDIO</small></div>
      <nav aria-label="Main workspace"><button onClick={()=>setActiveScreen('studio')}>Network Studio</button><button className="selected" onClick={()=>setActiveScreen('learning')}><BrainCircuit size={16}/> Learning Lab</button></nav></header>
    <LearningLab studioScenario={scenario} />
  </div>;

  return <div className="app-shell" data-ui-build="1.2.7" style={{gridTemplateColumns:`${leftOpen?`${leftWidth}px`:'0px'} minmax(0,1fr) ${rightOpen?`${rightWidth}px`:'0px'}`}}>
    <input ref={importRef} type="file" accept=".json,application/json" hidden onChange={e=>{importFile(e.target.files?.[0]);e.target.value='';}}/>
    <input ref={workspaceRef} type="file" accept=".json,application/json" hidden onChange={e=>{importFile(e.target.files?.[0]);e.target.value='';}}/>
    <aside className={`left-panel ${leftOpen?"":"is-collapsed"}`}>
      <div className="panel-resizer resizer-left" onPointerDown={e=>beginResize("left",e)} title="Drag to resize left panel"/>
      <div className="brand-wrap">
        <div className="brand-symbol"><img className="brand-atom-mark" src="/favicon.svg?v=115" alt="StratoQ three-orbit atom emblem" /></div>
        <div className="brand-wordmark"><div className="brand-title">Strato<span>Q</span></div><div className="brand-product">SIMULATION STUDIO</div></div>
      </div>
      <div className="side-scroll">
        <details className="section-pad workspace-section collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Workspace</span><span className="section-summary">{activeExperiment?.name}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="workspace-current"><strong title={activeExperiment?.name}>{activeExperiment?.name}</strong>
            <button className="workspace-rename" onClick={()=>renameExperiment(activeId)} title="Rename experiment" aria-label="Rename experiment"><Pencil size={13}/></button></div>
          <div className="workspace-actions"><button onClick={createExperiment}><Plus size={13}/> New</button>
            <button onClick={duplicateExperiment} title="Duplicate current experiment"><Copy size={13}/> Duplicate</button></div>
          <div className="builtin-launcher">
            <label htmlFor="builtin-select">Built-in showcase experiments</label>
            <select id="builtin-select" defaultValue="" onChange={e=>{if(e.target.value)addBuiltinExperiment(e.target.value);e.target.value='';}}>
              <option value="">Open a built-in experiment…</option>
              {BUILTINS.experiments.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
            <button type="button" onClick={replaceInitialExamples}>Reset to four demos</button>
            <small>Four 24-hour cases · one network, one balloon flight, one weather timeline. Compare the algorithms first, then toggle QKP for Optimal.</small>
          </div>
          <div className="workspace-tabs" role="tablist" aria-label="Experiments">
            {experiments.map(e=><div className={`workspace-tab ${e.id===activeId?'active':''}`} key={e.id}>
              <button role="tab" aria-selected={e.id===activeId} onClick={()=>changeExperiment(e.id)} title={e.name}>{e.name}</button>
              <button className="tab-close" aria-label={`Close ${e.name}`} onClick={()=>closeExperiment(e.id)}><X size={12}/></button>
            </div>)}
          </div>
          {activeExperiment?.builtin && <details className="builtin-comparison" open={isQkpStudy}>
            <summary>{isQkpStudy?'QKP on vs off · results':'Algorithms · results'} <ChevronDown size={13}/></summary>
            {isQkpStudy && <div className="qkp-control-actions">
              <button type="button" onClick={switchQkpCase}>
                <Copy size={13}/> Switch to QKP {scenario.config.qkp_enabled===false?'on':'off'}
              </button>
              <small>The two Optimal tabs use the same 24-hour inputs; only QKP storage changes. Run each before comparing measured service.</small>
            </div>}
            {comparableBuiltins.map(e=>{
              const sum=comparedSummary(e);
              return <div key={e.id} className="builtin-comparison-row"><span>{isQkpStudy?(e.scenario.config.qkp_enabled===false?'QKP off':'QKP on'):e.name.replace(/^\d+ · /,'')} · whole horizon</span><strong>{sum ? `${(100*Number(sum.total_satisfaction||0)).toFixed(1)}%` : 'Not run'}</strong></div>;
            })}
            {isQkpStudy && comparableBuiltins.map(e=>{
              const sum=comparedSummary(e);
              return <div key={`${e.id}-weather`} className="builtin-comparison-row">
                <span>{e.scenario.config.qkp_enabled===false?'QKP off':'QKP on'} · severe weather</span>
                <strong>{sum?.weather_window_satisfaction>=0?`${(100*sum.weather_window_satisfaction).toFixed(1)}%`:'Not run'}{sum?` · ${fmtKeys(sum.total_qkp_drawn_link_bits)} QKP draw`:''}</strong>
              </div>;
            })}
            {qkpDelta && <div className="builtin-comparison-row qkp-comparison-delta">
              <span>QKP effect · full day / storm</span>
              <strong>{qkpDelta.total.toFixed(1)} / {qkpDelta.storm.toFixed(1)} percentage points</strong>
            </div>}
            <small>Percentages are delivered/requested end-to-end SKR, not link capacity. Only completed, still-current runs are compared. QKP draw is link-key consumption, not end-to-end delivery. MILP results can be time-limited; check both gaps.</small>
          </details>}
        </div></details>
        <div className="side-divider"/>
        <details className="section-pad collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Network elements</span><span className="section-summary">{scenario.ground_stations.length + scenario.balloons.length + scenario.demands.length + scenario.weather_regions.length} items</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="add-list">
            <ButtonRow icon={SatelliteDish} text="Ground stations" count={scenario.ground_stations.length} onClick={()=>add('gs')} accent="aqua"/>
            <ButtonRow icon={RadioTower} text="HAP balloons" count={scenario.balloons.length} onClick={()=>add('hap')} accent="amber"/>
            <ButtonRow icon={Cloud} text="Weather regions" count={scenario.weather_regions.length} onClick={()=>add('weather')} accent="violet"/>
            <ButtonRow icon={Activity} text="Traffic demands" count={scenario.demands.length} onClick={()=>add('demand')} accent="lime"/>
          </div>
          </div>
        </details>
        <div className="side-divider"/>
        <details className="section-pad collapsible-block era5-panel">
          <summary className="collapsible-heading"><span className="section-heading-label">Weather · ERA5</span><span className="section-summary">{useEra5 ? "Enabled" : "Off"}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
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
          </div>
        </details>
        <div className="side-divider"/>
        <details className="section-pad collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Scene objects</span><span className="section-summary">{selected ? (selected.name || selected.id) : "Select an object"}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="object-list">
            {scenario.balloons.map(h=><EntityItem key={h.id} item={h} icon={RadioTower} subtitle={`${h.altitude_km} km · ${h.coverage_km} km range`}
              selected={selectedId===h.id} onClick={()=>setSelectedId(h.id)} />)}
            {scenario.ground_stations.map(g=><EntityItem key={g.id} item={g} icon={SatelliteDish} subtitle={`${g.lat.toFixed(3)}° N  ${Math.abs(g.lon).toFixed(3)}° W`}
              selected={selectedId===g.id} onClick={()=>setSelectedId(g.id)} />)}
            {scenario.weather_regions.map(w=><EntityItem key={w.id} item={w} icon={Cloud} subtitle={`${w.effect || 'fog'} · ${w.radius_km} km · ${w.effect==='fog' ? `${w.visibility_km??0.5} km vis.` : `${w.precipitation_rate_mm_h??5} mm/h`}`} selected={selectedId===w.id} onClick={()=>setSelectedId(w.id)}/>)}
            {scenario.demands.map((d,i)=><EntityItem color={demandColor(i)} key={d.id} item={{name:`Demand ${d.id.slice(2,7)}`}} icon={Activity}
              subtitle={`${fmtRate(d.rate_bps)} mean · ${d.pattern||"constant"}`} selected={selectedId===d.id} onClick={()=>setSelectedId(d.id)} />)}
          </div>
          </div>
        </details>
      </div>
      <div className="left-bottom">
        <button className="primary-button" onClick={()=>runSim()} disabled={running}>
          {running ? <RefreshCcw size={17} className="spin"/> : <Play size={17} fill="currentColor" />}
          {running?'Computing…':'Run simulation'} <ArrowRight size={16}/>
        </button>
        {running && physicsProgress && <div className="physics-progress" role="status" aria-live="polite">
          <div className="physics-progress-meta"><b>{physicsProgress.stage==='channel'?'Calculating upstream channel':physicsProgress.stage==='era5-sampling'?'Sampling ERA5 weather along links…':'Preparing physical setup…'}</b>
          <span>{physicsProgress.total?`${physicsProgress.completed}/${physicsProgress.total}`:'Initializing'}</span></div>
          <div className="physics-progress-track"><div style={{width:`${physicsProgress.total?Math.min(100,100*physicsProgress.completed/physicsProgress.total):3}%`}} /></div>
          <small>{physicsProgress.cached||0} reused · {physicsProgress.computed||0} computed · {physicsProgress.workers||0} workers</small>
        </div>}
        <div className="run-hint"><span className={`status-pin ${backend}`} />
          {backend==='online'?'Backend connected':backend==='checking'?'Connecting…':'Backend unavailable'}
        </div>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div className="topbar-identity"><button className="panel-toggle" onClick={()=>setLeftOpen(v=>!v)} title={leftOpen?'Collapse workspace':'Expand workspace'}>{leftOpen?<PanelLeftClose size={18}/>:<PanelLeftOpen size={18}/>}</button><span className="topbar-current">{activeExperiment?.name}</span></div>
        <div className="topbar-right"><button className="ll-enter-button" onClick={()=>setActiveScreen('learning')}><BrainCircuit size={16}/> Learning Lab</button>
          <details ref={filesMenuRef} className="header-file-menu">
            <summary>Files <ChevronDown size={14}/></summary>
            <div className="header-file-options">
              <button onClick={()=>{filesMenuRef.current.open=false;importRef.current?.click();}}><ArrowUpFromLine size={14}/> Import experiment / workspace</button>
              <button onClick={()=>{filesMenuRef.current.open=false;downloadJSON('stratoq-experiment.json',scenario);}}><ArrowDownToLine size={14}/> Export experiment</button>
              <button onClick={()=>{filesMenuRef.current.open=false;exportWorkspace();}}><ArrowDownToLine size={14}/> Export workspace</button>
            </div>
          </details>
          <button className="panel-toggle" onClick={()=>setRightOpen(v=>!v)} title={rightOpen?'Collapse inspector':'Expand inspector'}>{rightOpen?<PanelRightClose size={18}/>:<PanelRightOpen size={18}/>}</button>
        </div>
      </header>
      <div className="stage-shell">
        <div className="stage-top">
          <div>
            <h1>Network <span className="h1-mark">{mode==='3d'?'· 3D':'· Map'}</span></h1>
          </div>
          <div className="sq-stage-actions">
            {story && <button type="button" className="sq-stage-guide" onClick={()=>setStoryOpen(true)}><CircleHelp size={15}/> Experiment story</button>}
            <div className="view-toggle"><button className={mode==='3d'?'active':''} onClick={()=>setMode('3d')}><Box size={16}/> 3D scene</button>
              <button className={mode==='map'?'active':''} onClick={()=>setMode('map')}><Map size={16}/> Map view</button></div>
          </div>
        </div>
        <div className="scene-wrapper">
          <div className="scene-view">
            {mode==='3d' ? <Network3D key={sceneKey} scenario={visualScenario} frame={currentFrame} topologyLinks={topologyLinks} selectedId={selectedId}
              onSelect={setSelectedId} dragMode={dragMode} onPositionChange={onPositionChange} autoRotate={autoRotate} showLabels={showLabels} />
              : <GeoMap scenario={visualScenario} frame={currentFrame} topologyLinks={topologyLinks} selectedId={selectedId} onSelect={setSelectedId} onPositionChange={onPositionChange} />}
          </div>
          <div className="scene-corner top-right">
            <div className="toolbox">
              {mode==='3d' && <><button type="button" className={`scene-label-toggle ${showLabels?'active':''}`}
                onClick={()=>setShowLabels(v=>!v)} aria-pressed={showLabels}
                aria-label={showLabels?'Hide 3D topology labels':'Show 3D topology labels'}
                title={showLabels?'Hide node, QKP, weather, axis and link labels':'Show node, QKP, weather, axis and link labels'}>
                {showLabels?<Eye size={16}/>:<EyeOff size={16}/>}<span>Labels {showLabels?'on':'off'}</span>
              </button><span className="tool-divider"/><IconButton icon={MousePointer2} label={dragMode?'Turn off moving objects':'Move selected objects by dragging'}
                active={dragMode} onClick={()=>setDragMode(v=>!v)} />
              <IconButton icon={Rotate3D} label="Auto-orbit camera" active={autoRotate} onClick={()=>setAutoRotate(v=>!v)} />
              <span className="tool-divider" />
              <IconButton icon={Crosshair} label="Reset 3D camera" onClick={()=>setSceneKey(v=>v+1)} /></>}
              {mode==='map'&&<IconButton icon={Crosshair} label="Switch to the resettable 3D scene" onClick={()=>setMode('3d')} />}
              <IconButton icon={RefreshCcw} label="Restore original experiment settings" onClick={reset} />
            </div>
          </div>
          <div className="scene-corner bottom-left sq-demand-legend" aria-label="Demand path color and source legend">
            <div className="sq-demand-legend-list">
              {scenario.demands.map((d,i)=><button type="button" key={d.id} className={`sq-demand-tag ${selectedId===d.id?'is-selected':''}`} onClick={()=>setSelectedId(d.id)} title={`${d.source} → ${d.target}`}><i style={{background:demandColor(i)}}/>{d.name||d.id}</button>)}
            </div>
            <div className="sq-demand-key"><span><b className="sq-key-line"/> Optical ON</span><span><b className="sq-key-line dashed"/> QKP only</span><span><b className="sq-key-line mixed"/> Both</span><span>Brighter / thicker = higher link SKR or QKP draw</span></div>
          </div>
          {running&&physicsProgress&&<div className="scene-corner bottom-right"><div className="pending-indicator">Physical model · {physicsProgress.total?`${physicsProgress.completed}/${physicsProgress.total}`:'preparing'} · {physicsProgress.cached||0} cached</div></div>}
          {dirty&&!running&&<div className="scene-corner bottom-right"><div className="pending-indicator"><span/> Changes pending · Play to recalculate</div></div>}
        </div>
        {apiVersion !== null && apiVersion !== STUDIO_VERSION && <div className="revision-warning">
          <strong>Version mismatch:</strong> UI {STUDIO_VERSION} / API {apiVersion}. Replace the backend files too and restart FastAPI.
        </div>}
        {error && <div className="error-bar"><WifiOff size={15}/><span>{error}</span><button onClick={()=>setError('')}><X size={15}/></button></div>}
        <div className={`timeline ${timelineExpanded?'sq-timeline-expanded':'sq-timeline-compact'}`}>
          <div className="timeline-header"><div className="timeline-title"><span className="timeline-play-icon"><Activity size={17}/></span>
            <div><strong>Playback</strong>{timelineExpanded&&<small>{totalFrames} slots · {scenario.config.slot_seconds}s per slot{useEra5?' · ERA5 UTC':''}</small>}</div></div>
            <div className="timeline-actions"><span className="time-current">{useEra5&&era5Date ? `${era5Date} ${toClock((currentFrame?.time_seconds ?? frameIndex*scenario.config.slot_seconds))} UTC` : `T+${toClock((currentFrame?.time_seconds ?? 0))}`}</span>
              {timelineExpanded&&<button onClick={()=>{setFrameIndex(0);setPlaying(false);}} title="Restart playback"><RefreshCcw size={15}/></button>}
              <button className="sq-timeline-expand" type="button" title={timelineExpanded?"Minimize timeline":"Expand timeline and story"} aria-label={timelineExpanded?"Minimize timeline":"Expand timeline and story"} aria-expanded={timelineExpanded} onClick={()=>setTimelineExpanded(v=>!v)}><ChevronDown size={16}/></button>
              <button className="playback-button" onClick={togglePlayback} disabled={running} title={dirty || !result ? "Recalculate and play updated scenario" : playing ? "Pause" : "Play"}>{running?<RefreshCcw size={16} className="spin"/>:playing?<Pause size={16} fill="currentColor"/>:<Play size={16} fill="currentColor"/>}</button>
            </div></div>
          {timelineExpanded&&<div className="trajectory-slot-control"><label htmlFor="slot-seconds">Time slot</label>
            <select id="slot-seconds" value={scenario.config.slot_seconds} onChange={e=>patchScenario(s=>{s.config.slot_seconds=Number(e.target.value);s.config.slots=slotCount(s);})}>
              {[10,30,60,120,300,600,900,1800,3600].map(v=><option key={v} value={v}>{v<60?`${v} sec`:v<3600?`${v/60} min`:`${v/3600} hour`}</option>)}
            </select><small>{horizonHours.toFixed(1)}h horizon{scenario.balloons.some(h=>h.trajectory_id)?" · trajectory":" · default"}</small></div>}
          <div className="timeline-scrub"><span>00:00</span><input aria-label="Simulation time slot" type="range" min={0} max={Math.max(0,totalFrames-1)}
            value={frameIndex} onChange={e=>{setFrameIndex(Number(e.target.value));setPlaying(false);setSelectedMomentId(null);}}
            style={{'--progress': `${totalFrames>1 ? 100*frameIndex/(totalFrames-1) : 0}%`}} disabled={!result}/>
            <span>{toClock(totalFrames*scenario.config.slot_seconds)}</span></div>
          {timelineExpanded&&story && <StoryRail presetId={storyPresetId} moments={moments} activeId={storyMomentId}
            onJump={jumpToStoryMoment} onOpen={()=>setStoryOpen(true)}
            hasResults={!!result&&!dirty} horizonSeconds={simulationHorizonSeconds(scenario)} changed={storyChanged}/>}
          {storyOpen && story && <StoryDialog presetId={storyPresetId} moments={moments}
            scenario={scenario} result={!dirty?result:null} changed={storyChanged}
            comparisons={comparableBuiltins.map(e=>({id:e.id,name:e.name,
              summary:comparedSummary(e)||null}))}
            onClose={()=>setStoryOpen(false)} onHistoricalWeather={()=>{setStoryOpen(false);createHistoricalVariant();}}
            onJump={moment=>{jumpToStoryMoment(moment);setStoryOpen(false);}}/>}
          {timelineExpanded&&<div className="timeline-footer"><span className="timeline-note">Frame {frameIndex+1} / {totalFrames}{dirty?' · changes pending':''}</span></div>}
        </div>
      </div>
    </main>

    <aside className={`right-panel ${rightOpen?"":"is-collapsed"}`}>
      <div className="panel-resizer resizer-right" onPointerDown={e=>beginResize("right",e)} title="Drag to resize inspector"/>
      <div className="inspector-top"><div><h2>Inspector</h2></div>
        <IconButton icon={ArrowDownToLine} label="Export simulation results" onClick={()=>result&&downloadJSON('stratoq-results.json',result)} disabled={!result}/></div>
      <div className="inspector-scroll">
        <details className="inspector-section collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Performance</span><span className="section-summary">{solverSummary ? `${Number(100*(solverSummary.total_satisfaction??0)).toFixed(1)}% served` : `Slot ${frameIndex+1}`}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="kpi-grid">
            <div className="kpi-card"><div className="kpi-label"><Activity size={14}/> Served rate</div><b>{fmtRate(served)}</b><small>{satisfaction===null?'—':`${satisfaction}% of requested`}</small></div>
            <div className="kpi-card"><div className="kpi-label"><Wifi size={14}/> Optical / QKP</div><b>{currentFrame?`${activeLinks} / ${qkpOnlyLinks}`:'—'}</b><small>Fresh generation / stored-key-only links</small></div>
            <div className="kpi-card"><div className="kpi-label"><Layers3 size={14}/> Key buffers</div><b>{fmtBits(currentFrame?.stored_bits_total)}</b><small>Total stored bits</small></div>
            <div className="kpi-card"><div className="kpi-label"><Gauge size={14}/> Satisfaction</div><b>{satisfaction===null?'—':`${satisfaction}%`}</b><small>Current slot</small></div>
          </div>
          {slotSolver ? <div className="solver-audit" data-solver-status={slotSolver.solver_status}>
            <div className="solver-audit-title"><Gauge size={15}/><b>{slotSolver.offline_full_horizon ? "GUROBI OFFLINE · FULL HORIZON" : `GUROBI ALLOCATION · SLOT ${frameIndex+1}`}</b><strong>{slotSolver.solver_status}</strong></div>
            {solverSummary && <div className="solver-key-totals">
              <div><small>Total served keys</small><strong>{fmtKeys(solverSummary.total_served_bits)}</strong></div>
              <div><small>Total requested keys</small><strong>{fmtKeys(solverSummary.total_requested_bits)}</strong></div>
              <div className="solver-total-coverage"><small>Overall served / requested</small><strong>{Number(100*(solverSummary.total_satisfaction??0)).toFixed(1)}%</strong></div>
            </div>}
            {solverSummary?.algorithm==='optimal' && <p className="offline-gap-note">Achieved gap: {Number(100*(solverSummary.achieved_mip_gap??0)).toFixed(2)}% · Requested ≤ {Number(100*(solverSummary.requested_mip_gap??0.01)).toFixed(2)}% · {solverSummary.optimality_certified?'Gap target certified':'Incumbent; not certified optimal'}</p>}
            <details className="solver-detail-disclosure"><summary>Solver details <ChevronDown size={13}/></summary><div className="solver-audit-stats">
              <span>Models optimized <b>{slotSolver.offline_full_horizon ? 1 : slotSolver.candidate_solves}</b></span>
              <span>Solver time <b>{Number(slotSolver.offline_full_horizon ? solverSummary?.gurobi_runtime_seconds : slotSolver.gurobi_runtime_seconds||0).toFixed(4)} s</b></span>
              <span>Selected routes <b>{slotSolver.selected_paths}</b></span>
              <span>Activated optical links <b>{slotSolver.activated_links}</b></span>
              <span>Positive-capacity links <b>{slotSolver.positive_capacity_links}</b></span>
              <span>Variables / constraints <b>{slotSolver.gurobi_variable_count} / {slotSolver.gurobi_constraint_count}</b></span>
            </div>
            <div className={`solver-audit-note ${!slotSolver.activated_links?'inactive':''}`}>{slotSolver.selection_note}</div>
            <small className="solver-audit-footer">Gurobi {slotSolver.gurobi_version} · {solverSummary?.gurobi_optimized_models??0} solves</small></details>
          </div> : <div className="compact-note">Run to view allocation results.</div>}
        </div></details>
        <details className="inspector-section collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Selected object</span><span className="section-summary">{selected ? (selected.name || selected.id) : 'None'}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
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
              <div className="selection-stat"><span>Status</span><b>{!selected.enabled?'Manually disabled':!selected.in_range?'Out of range':dirty?'Pending simulation':selected.activated?'Optically activated':selected.allocated?'Using stored keys':selected.active?'Available · idle':'Unavailable'}</b></div>
              <Numeric label="Clear-air visibility (V)" value={selected.visibility_km??100} unit="km" min={0.01} max={500}
                onChange={v=>changeLinkProperty(selected,'visibility_km',v)}/>
              <Numeric label="Link rate cap (optional)" value={selected.capacity_limit_bps??0} unit="bps" min={0}
                onChange={v=>changeLinkProperty(selected,'capacity_limit_bps',v===0?null:v)}/>
              <div className="selection-stat"><span>Weather (fog/rain/snow)</span><b>{(selected.weather_flags||[0,0,0]).join(' / ')}</b></div>
              <div className="selection-stat"><span>Capacity</span><b>{!dirty?fmtRate(selected.capacity_bps):'Run to update'}</b></div>
              <div className="selection-stat"><span>Used by demands</span><b>{!dirty?fmtRate(selected.used_bps):'Run to update'}</b></div>
              {!dirty&&currentFrame&&<div className="sq-link-breakdown">
                <strong>Carried demands</strong>
                {allocationsForLink(selected,currentFrame,scenario).map(d=><div key={d.id} className="sq-link-demand"><i style={{background:d.color}}/>{d.name}<b>{fmtRate(d.rate)}</b></div>)}
                {!allocationsForLink(selected,currentFrame,scenario).length&&<small>No served demand uses this link in this slot.</small>}
                <div className="sq-link-flow-kind">{linkKeyMode(selected)==='qkp'?'Dashed: stored keys':linkKeyMode(selected)==='mixed'?'Solid + dashed: fresh and stored link keys':linkKeyMode(selected)==='fresh'?'Solid: fresh link keys':'No carried key flow'}
                  <small>Fresh {fmtRate(selected.fresh_used_bps||0)} · QKP {fmtRate(selected.qkp_used_bps||0)}</small>
                  {selected.capacity_bps>1e-8&&<small>Fresh capacity used: {(100*Math.min(1,(selected.fresh_used_bps||0)/selected.capacity_bps)).toFixed(0)}%{(selected.fresh_used_bps||0)>=.9*selected.capacity_bps?' · Possible physical bottleneck':''}</small>}
                </div>
              </div>}
              <div className="selection-stat"><span>Slant distance</span><b>{selected.distance_km.toFixed(1)} km</b></div>
              <div className="selection-stat"><span>GS elevation</span><b>{Number.isFinite(selected.elevation_deg) ? `${selected.elevation_deg.toFixed(1)}°` : 'Run to update'}</b></div>
              <div className="selection-stat"><span>Weather attenuation</span><b>{Number.isFinite(selected.weather_loss_db) ? `${selected.weather_loss_db.toFixed(1)} dB` : 'Run to update'}</b></div>
            </div> : selectedType==='demand' ? <div className="field-stack">
              <label className="field-label"><span>Source station</span><select value={selected.source} onChange={e=>modifyItem(selected.id,'source',e.target.value)}>
                {scenario.ground_stations.filter(g=>g.id!==selected.target).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
              <label className="field-label"><span>Destination station</span><select value={selected.target} onChange={e=>modifyItem(selected.id,'target',e.target.value)}>
                {scenario.ground_stations.filter(g=>g.id!==selected.source).map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
              <Numeric label="Mean required key rate" value={selected.rate_bps} unit="bps" min={1} max={1e9} onChange={v=>modifyItem(selected.id,'rate_bps',v)}/>
              <label className="field-label"><span>Demand pattern</span><select value={selected.pattern||'constant'} onChange={e=>modifyItem(selected.id,'pattern',e.target.value)}>
                <option value="constant">Constant</option><option value="diurnal">Diurnal · Gaussian bell</option>
                <option value="dual_peak">Two daily peaks</option><option value="bursty">Periodic bursts</option></select></label>
              {(selected.pattern&&selected.pattern!=='constant') && <>
                <div className="field-grid"><Numeric label={selected.pattern==='bursty'?'Burst offset':'Peak hour (0–24)'} value={selected.peak_hour??14} min={0} max={23.99} onChange={v=>modifyItem(selected.id,'peak_hour',v)}/>
                  <Numeric label="Peak uplift" value={selected.peak_uplift_pct??70} min={0} max={200} unit="%" onChange={v=>modifyItem(selected.id,'peak_uplift_pct',v)}/></div>
                {selected.pattern!=='bursty' && <Numeric label="Peak width (σ)" value={selected.peak_width_hours??3} min={0.3} max={12} unit="hours" onChange={v=>modifyItem(selected.id,'peak_width_hours',v)}/>}
                {selected.pattern==='dual_peak' && <div className="field-grid"><Numeric label="Second peak hour" value={selected.second_peak_hour??21} min={0} max={23.99} onChange={v=>modifyItem(selected.id,'second_peak_hour',v)}/>
                  <Numeric label="Second peak strength" value={selected.second_peak_ratio_pct??65} min={0} max={200} unit="%" onChange={v=>modifyItem(selected.id,'second_peak_ratio_pct',v)}/></div>}
                {selected.pattern==='bursty' && <div className="field-grid"><Numeric label="Burst every" value={selected.burst_interval_hours??6} min={0.5} max={24} unit="hours" onChange={v=>modifyItem(selected.id,'burst_interval_hours',v)}/>
                  <Numeric label="Burst length" value={selected.burst_duration_minutes??45} min={1} max={1440} unit="min" onChange={v=>modifyItem(selected.id,'burst_duration_minutes',v)}/></div>}
              </>}
              <DemandPreview demand={selected} slots={computedSlots} seconds={scenario.config.slot_seconds} />
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

              {selectedType==='weather' && <label className="field-label"><span>Weather type</span>
                <select value={selected.effect||'fog'} onChange={e=>modifyItem(selected.id,'effect',e.target.value)}>
                  <option value="fog">Fog / cloud</option><option value="rain">Rain</option><option value="snow">Snow</option>
                </select></label>}
              {selectedType==='weather' && <div className="weather-intensity-control">
                <strong>{selected.effect==='fog'?'Fog density / visibility':selected.effect==='snow'?'Snowfall rate (water equivalent)':'Rainfall rate'}</strong>
                <div className="field-grid">
                  {selected.effect==='fog' ? <Numeric label="Meteorological visibility" value={selected.visibility_km??0.5} min={0.05} max={100} step={0.05} unit="km" onChange={v=>modifyItem(selected.id,'visibility_km',v)} /> : <Numeric label="Precipitation rate" value={selected.precipitation_rate_mm_h??5} min={0} max={500} step={0.5} unit="mm/h" onChange={v=>modifyItem(selected.id,'precipitation_rate_mm_h',v)} />}
                </div>
                {selected.effect==='snow' && <label className="field-label"><span>Snow type (optical attenuation fit)</span>
                  <select value={selected.snow_type||'wet'} onChange={e=>modifyItem(selected.id,'snow_type',e.target.value)}>
                    <option value="wet">Wet snow</option><option value="dry">Dry snow</option>
                  </select></label>}

              </div>}
              {selectedType==='weather' && <details className="weather-time-settings"><summary>Time-varying weather profile</summary>
                <div className="field-grid">
                  <Numeric label="Starts at" value={(selected.active_from_seconds||0)/3600} min={0} max={24} step={.25} unit="h" onChange={v=>modifyItem(selected.id,'active_from_seconds',Math.round(v*3600))}/>
                  <Numeric label="Ends at" value={(selected.active_until_seconds??86400)/3600} min={0} max={24} step={.25} unit="h" onChange={v=>modifyItem(selected.id,'active_until_seconds',Math.round(v*3600))}/>
                  <Numeric label="Fade in/out" value={(selected.ramp_seconds||0)/60} min={0} max={720} step={5} unit="min" onChange={v=>modifyItem(selected.id,'ramp_seconds',Math.round(v*60))}/>
                  <Numeric label="Eastward drift" value={selected.drift_lon_deg_per_hour||0} min={-2} max={2} step={.01} unit="°/h" onChange={v=>modifyItem(selected.id,'drift_lon_deg_per_hour',v)}/>
                </div><small>Deterministic demo weather, not ERA5. Existing fog/rain optical laws are applied to every time-slot snapshot.</small>
              </details>}
              {selectedType==='weather'&&<div className="field-grid"><Numeric label="Region radius" value={selected.radius_km} min={1} max={500} unit="km" onChange={v=>modifyItem(selected.id,'radius_km',v)} />
                <Numeric label="Optional extra loss" value={selected.attenuation_db} min={0} max={40} unit="dB" onChange={v=>modifyItem(selected.id,'attenuation_db',v)}/></div>}
              {selectedType==='hap' && <div className="trajectory-upload">
                <strong>HAP trajectory</strong>
                <label className="trajectory-upload-button">{uploadingTrajectory?'Importing…':'Upload CSV / Excel'}
                  <input type="file" accept=".csv,.xlsx" disabled={uploadingTrajectory} onChange={e=>{uploadTrajectory(selected.id,e.target.files?.[0]);e.target.value='';}} />
                </label>
                <small>{selected.trajectory_name || 'Static position · no trajectory attached'}</small>
                {selected.trajectory_id && <button className="trajectory-clear" onClick={()=>patchScenario(s=>{const h=s.balloons.find(h=>h.id===selected.id);delete h.trajectory_id;delete h.trajectory_name;delete h.trajectory_duration_seconds;s.config.slots=slotCount(s);})}>Remove trajectory</button>}
              </div>}
              {selectedType==='hap' && <div className="selection-stat"><span>Potential optical links</span><b>{topologyLinks.filter(l=>l.target===selected.id).length}</b></div>}
              {selectedType==='hap' && currentFrame && <div className="selection-stat"><span>Slot {frameIndex+1}: optical / QKP-only</span><b>{topologyLinks.filter(l=>l.target===selected.id&&l.activated).length} / {topologyLinks.filter(l=>l.target===selected.id&&l.allocated&&!l.activated).length}</b></div>}
              {selectedType==='hap' && selected.trajectory_id && <div className="trajectory-origin-controls">
                <label className="field-label"><span>Trajectory start (geographic translation)</span>
                  <select value={selected.trajectory_origin_mode||'original'} onChange={e=>setTrajectoryOrigin(selected.id,e.target.value)}>
                    <option value="original">Original segment first point</option>
                    <option value="shifted">Shift first point to selected location</option>
                  </select></label>
                {selected.trajectory_origin_mode==='shifted'&&<div className="field-grid">
                  <Numeric label="Target start latitude" value={selected.trajectory_start_lat??selected.lat} min={-90} max={90} step={.001} onChange={v=>setTrajectoryStart(selected.id,'lat',v)}/>
                  <Numeric label="Target start longitude" value={selected.trajectory_start_lon??selected.lon} min={-180} max={180} step={.001} onChange={v=>setTrajectoryStart(selected.id,'lon',v)}/>
                </div>}
                <small>Translates the full track while preserving relative motion and altitude. Dragging a trajectory HAP switches to shifted mode; no wind recalculation is performed.</small>
              </div>}
              {selectedType==='hap' && selected.trajectory_id && currentFrame?.positions?.[selected.id] && <div className="selection-stat"><span>Current HAP position (trajectory)</span><b>{currentFrame.positions[selected.id].lat?.toFixed(4)}°, {currentFrame.positions[selected.id].lon?.toFixed(4)}°</b></div>}
              {selectedType==='gs' && <div className="selection-stat"><span>Potential optical links</span><b>{topologyLinks.filter(l=>l.source===selected.id).length}</b></div>}
              {selectedType==='gs' && currentFrame && <div className="selection-stat"><span>Slot {frameIndex+1}: optical / QKP-only</span><b>{topologyLinks.filter(l=>l.source===selected.id&&l.activated).length} / {topologyLinks.filter(l=>l.source===selected.id&&l.allocated&&!l.activated).length}</b></div>}
            </div>}
          </>:<div className="empty-selection"><MousePointer2 size={20}/><span>Select an object in the scene.</span></div>}
          </div>
        </details>
        <details className="inspector-section collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Simulation</span><span className="section-summary">{(scenario.config.allocation_mode||'scar_q').toUpperCase()} · {scenario.config.slot_seconds}s</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="field-grid"><label className="field-label"><span>Time slots · calculated</span><div className="number-shell"><strong>{computedSlots.toLocaleString()}</strong></div></label>
            <Numeric label="Slot duration" value={scenario.config.slot_seconds} unit="sec" min={10} max={86400} step={10} onChange={v=>patchScenario(s=>{s.config.slot_seconds=Math.max(10,v);s.config.slots=slotCount(s);})} /></div>
          <div className="compact-note">{horizonHours.toFixed(1)}h · {scenario.balloons.some(h=>h.trajectory_id)?'trajectory':'24h default'}</div>
          <label className="field-label"><span>Experiment horizon · hours</span><div className="number-shell"><input type="number" min={.1} max={24} step={.5} value={(scenario.config.horizon_seconds??simulationHorizonSeconds(scenario))/3600} onChange={e=>patchScenario(s=>{const h=Math.max(360,Math.min(86400,Math.round(Number(e.target.value)*3600)||360));s.config.horizon_seconds=h;s.config.slots=slotCount(s);})}/><i>h</i></div></label>
          {scenario.config.allocation_mode==='optimal' && <label className="era5-switch"><input type="checkbox" checked={scenario.config.qkp_enabled!==false} onChange={e=>patchScenario(s=>s.config.qkp_enabled=e.target.checked)}/><span>Enable QKP storage (for storm comparison)</span></label>}
          <div className="allocator-picker">
            <label className="field-label"><span>Resource allocation algorithm</span>
              <select value={['scar_q','mcr_q','optimal'].includes(scenario.config.allocation_mode) ? scenario.config.allocation_mode : 'scar_q'}
                onChange={e=>patchScenario(s=>s.config.allocation_mode=e.target.value)}>
                <option value="scar_q">SCAR-Q · Greedy</option>
                <option value="mcr_q">MCR-Q · Monte Carlo</option><option value="optimal">Optimal · MILP</option>
              </select>
            </label>
              {scenario.config.allocation_mode === 'mcr_q' && <div className="field-grid">
              <Numeric label="Monte Carlo samples" value={scenario.config.mcr_samples ?? 3} min={1} max={100} step={1} onChange={v=>patchScenario(s=>s.config.mcr_samples=Math.max(1,Math.min(100,Math.round(v))))} />
              <Numeric label="Random seed" value={scenario.config.allocator_seed ?? 42} min={0} max={2147483647} step={1} onChange={v=>patchScenario(s=>s.config.allocator_seed=Math.max(0,Math.round(v)))} />
            </div>}
            {scenario.config.allocation_mode === 'optimal' && <>
              <div className="field-grid">
                <Numeric label="Optimality gap" value={100*(scenario.config.optimality_gap??0.01)} unit="%" min={0} max={50} step={0.1} onChange={v=>patchScenario(s=>s.config.optimality_gap=Math.max(0,Math.min(50,v))/100)}/>
                <Numeric label="Time limit" value={scenario.config.optimal_time_limit_seconds??300} unit="sec" min={1} max={86400} step={1} onChange={v=>patchScenario(s=>s.config.optimal_time_limit_seconds=Math.max(1,Math.round(v)))}/>
              </div>
            </>}
          </div>
          </div>
        </details>
        <details className="inspector-section collapsible-block">
          <summary className="collapsible-heading"><span className="section-heading-label">Physical channel</span><span className="section-summary">Optical parameters</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
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
          </div>
        </details>
        <details className="inspector-section collapsible-block last">
          <summary className="collapsible-heading"><span className="section-heading-label">System</span><span className="section-summary">{backend==='online'?'Connected':backend==='checking'?'Connecting':'Offline'}</span><ChevronDown size={15}/></summary>
          <div className="collapsible-content">
          <div className="api-line"><span className={`api-light ${backend}`}/><div><strong>FastAPI · localhost:8000</strong></div></div>
          {physicsStatus && <p className="field-help">Original channel: {physicsStatus.channel_import_ok?'import OK':'import failed'} · LOWTRAN native: {physicsStatus.native_lowtran_present?'installed':'will build on first run / requires build tools'}</p>}
          </div>
        </details>
      </div>
      <div className="right-footer"><div className="waterloo-credit"><a className="waterloo-logo-link" href="https://uwaterloo.ca/" target="_blank" rel="noreferrer" aria-label="University of Waterloo"><img className="waterloo-logo-full" src="https://uwaterloo.ca/brand/sites/ca.brand/files/universityofwaterloo_logo_horiz_rev.png" alt="University of Waterloo" loading="lazy" /></a><span>Developed at the <a className="lab-link" href="https://rboutaba-cs.github.io/watqkd/" target="_blank" rel="noreferrer">Networks Lab</a></span></div></div>
    </aside>
  </div>;
}
