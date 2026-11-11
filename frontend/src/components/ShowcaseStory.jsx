import React, {useEffect, useRef} from 'react';
import {createPortal} from 'react-dom';
import {BookOpen, CalendarClock, CheckCircle2, ChevronRight, ExternalLink, X} from 'lucide-react';
import {SHOWCASE_STORIES, clockLabel, measuredCaption, readableBits} from '../lib/showcaseStory.js';

function BeatTime({beat}) {
  return <span className="sq-story-time">T+{clockLabel(beat.fromSeconds)}{beat.toSeconds-beat.fromSeconds>=600?`–${clockLabel(beat.toSeconds)}`:''}</span>;
}

/** Always shown for known built-in experiments, even before a run is available. */
export function StoryRail({presetId,moments,activeId,onJump,onOpen,hasResults,changed=false}) {
  const story=SHOWCASE_STORIES[presetId];
  if(!story)return null;
  return <section className="sq-story sq-story-minimal" aria-label="Key moments in the experiment">
    <div className="sq-story-head"><b>Key moments</b><button type="button" className="sq-story-open" onClick={onOpen}><BookOpen size={13}/> Story</button></div>
    <div className="sq-story-mini-cues" role="group" aria-label="Jump to key moments">
      {moments.map(m=><button key={m.id} type="button"
        className={`sq-story-mini-cue ${activeId===m.id?'is-selected':''} ${m.observed?'is-observed':''}`}
        aria-label={`Jump to ${m.label} at ${clockLabel(m.timeSeconds)}`}
        title={`${m.label}: ${m.why}`} onClick={()=>onJump(m)}>
        <span>{clockLabel(m.timeSeconds)}</span><b>{m.label}</b>
      </button>)}
    </div>
    {activeId&&moments.some(m=>m.id===activeId) && <div className="sq-story-mini-selection">
      {moments.filter(m=>m.id===activeId).map(m=><span key={m.id}>
        <b>{m.label}:</b> {hasResults&&m.observed?measuredCaption(m.metrics):m.why}
      </span>)}
    </div>}
    {changed&&<small className="sq-story-mini-changed">Edited scenario — interpret scheduled cues against its current settings.</small>}
  </section>;
}

export function StoryDialog({presetId,moments,scenario,result,onClose,onJump,comparisons=[],changed=false,onHistoricalWeather}) {
  const closeRef=useRef(null);
  const modalRef=useRef(null);
  const onCloseRef=useRef(onClose);
  onCloseRef.current=onClose;
  const story=SHOWCASE_STORIES[presetId];
  useEffect(()=>{
    if(!story)return;
    const old=document.body.style.overflow;
    document.body.style.overflow='hidden';
    const last=document.activeElement;
    closeRef.current?.focus();
    const onKey=e=>{
      if(e.key==='Escape'){e.preventDefault();onCloseRef.current();}
      if(e.key==='Tab' && modalRef.current){
        const buttons=[...modalRef.current.querySelectorAll('button:not([disabled])')];
        if(!buttons.length)return;
        if(e.shiftKey && document.activeElement===buttons[0]){e.preventDefault();buttons.at(-1).focus();}
        else if(!e.shiftKey && document.activeElement===buttons.at(-1)){e.preventDefault();buttons[0].focus();}
      }
    };
    window.addEventListener('keydown',onKey);
    return ()=>{document.body.style.overflow=old;window.removeEventListener('keydown',onKey);last?.focus?.();};
  },[story]);
  if(!story)return null;
  const valid=Array.isArray(result?.frames) && result.frames.length>0;
  const total=Number(result?.summary?.total_satisfaction);
  return createPortal(<div className="sq-story-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}>
    <div ref={modalRef} role="dialog" aria-modal="true" aria-label={`${story.title}: experiment guide`} className="sq-story-dialog">
      <div className="sq-story-dialog-head"><div><span className="sq-story-eyebrow">STRATOQ · GUIDED EXPERIMENT</span><h2>{story.title}</h2><p>{story.question}</p></div>
        <button type="button" ref={closeRef} aria-label="Close experiment story" onClick={onClose}><X size={19}/></button></div>
      <div className="sq-story-dialog-scroll">
        <div className="sq-story-dialog-intro"><section><h3>The decision being demonstrated</h3><p>{story.mechanism}</p></section>
          <section><h3>How to compare</h3><p>{story.contrast}</p></section></div>
        <div className="sq-story-run-status">{valid?<><CheckCircle2 size={15}/><b>Measured run available</b><span>{Number.isFinite(total)?`${(100*total).toFixed(1)}% of requested keys served over the full run`:'Inspect the measured frames below'}</span></>:
          <><CalendarClock size={15}/><b>Viewing plan only</b><span>Run the experiment to populate measured explanations. No outcome is assumed.</span></>}
          {changed&&<p>Some settings differ from the built-in preset; interpret the guide against your edited configuration.</p>}
        </div>
        <h3 className="sq-story-dialog-subtitle">Walkthrough · click any moment to jump to its slot</h3>
        <div className="sq-story-chapters">
          {moments.map((m,i)=><div key={m.id} className="sq-story-chapter">
            <div className="sq-story-chapter-number">{String(i+1).padStart(2,'0')}</div>
            <div className="sq-story-chapter-main">
              <div className="sq-story-chapter-top"><BeatTime beat={m}/><span className={`sq-story-chapter-status ${m.observed?'observed':''}`}>{m.observed?'Measured cue':'Scheduled inspection'}</span></div>
              <h4>{m.label}</h4><p>{m.why}</p>
              {valid&&<div className="sq-story-chapter-measured"><b>Measured at slot {m.index+1}:</b> {measuredCaption(m.metrics)}
                {!m.observed && <div>No {m.signal.replaceAll('-',' ')} signal was detected within this time window.</div>}</div>}
            </div>
            <button type="button" onClick={()=>onJump(m)} className="sq-story-chapter-jump">Go to slot {m.index+1}<ExternalLink size={13}/></button>
          </div>)}
        </div>
        <section className="sq-story-how"><h3>How to interpret the results</h3><ul>{story.takeaways.map((line,i)=><li key={i}>{line}</li>)}</ul>
          <p>Remember: manually scheduled weather and demand peaks are inputs. An algorithm's link choices, key-pool draw and delivered-key volumes are outputs from the actual physics and solver. QKP consumption in link-key bits must not be equated with end-to-end delivered bits.</p>
        </section>
        {valid&&<div className="sq-story-summary"><div><small>Delivered keys</small><b>{readableBits(result.summary?.total_served_bits)}</b></div><div><small>QKP link-key draw</small><b>{readableBits(result.summary?.total_qkp_drawn_link_bits)}</b></div><div><small>Final buffer</small><b>{readableBits(result.summary?.final_stored_bits)}</b></div></div>}
        {comparisons.length>1&&<section className="sq-story-compare">
          <h3>Compare matching experiment runs</h3>
          <p>Only experiments with matching geometry, trajectories, demand schedules, weather, and time grid appear here. Unrun experiments are not assigned results.</p>
          <div className="sq-story-compare-scroll"><table>
            <thead><tr><th>Experiment</th><th>Total served</th><th>Storm window</th></tr></thead>
            <tbody>{comparisons.map(row=><tr key={row.id}><td>{row.name}</td>
              <td>{row.summary?readableBits(row.summary.total_served_bits):'Not run'}</td>
              <td>{row.summary?.weather_window_satisfaction>=0?`${(100*row.summary.weather_window_satisfaction).toFixed(1)}%`:'—'}</td>
              </tr>)}</tbody></table></div>
          {valid&&result.summary?.algorithm==='optimal'&&!result.summary?.optimality_certified&&<p className="sq-story-solver-warning">The offline MILP result may be a time-limited incumbent. Check its solver gap before claiming proven optimality.</p>}
        </section>}
      </div>
      <div className="sq-story-dialog-footer"><button type="button" className="sq-historical-variant" onClick={onHistoricalWeather}
        title="Open a copy using the bundled actual 2024-06-21 ERA5 reanalysis instead of scripted weather">
        Try historical ERA5 · 2024-06-21</button><button type="button" onClick={onClose}>Close story</button></div>
    </div>
  </div>,document.body);
}
