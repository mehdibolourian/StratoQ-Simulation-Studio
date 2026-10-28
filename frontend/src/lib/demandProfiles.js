// Matches backend/stratoq_demo/demand_profiles.py. Zero-mean peaks are
// normalized so the user's selected rate is the simulated-horizon mean.
const gaussian = (hour, center, width) => {
  const distance = Math.abs(((hour - center + 12 + 48) % 24) - 12);
  return Math.exp(-0.5 * (distance / Math.max(0.3, width)) ** 2);
};
export function demandSeries(d, slots, dt) {
  if (slots < 1) return [];
  const mean = Number(d.rate_bps) || 0;
  if (!d.pattern || d.pattern === 'constant') return Array(slots).fill(mean);
  const centre = Number(d.peak_hour ?? 14);
  const width = Number(d.peak_width_hours ?? 3);
  const heights = Array.from({length:slots}, (_, t) => {
    const hour = (((t+0.5)*dt/3600)%24);
    let g = gaussian(hour, centre, width);
    if (d.pattern === 'dual_peak') g += Number(d.second_peak_ratio_pct ?? 65)/100 * gaussian(hour, Number(d.second_peak_hour ?? 21), width);
    if (d.pattern === 'bursty') g = ((((t+0.5)*dt/3600 - centre) % Number(d.burst_interval_hours ?? 6)) + Number(d.burst_interval_hours ?? 6)) % Number(d.burst_interval_hours ?? 6) < Number(d.burst_duration_minutes ?? 45)/60 ? 1 : 0;
    return g;
  });
  const avg = heights.reduce((a,b)=>a+b,0)/slots;
  const spread = Math.max(...heights)-avg;
  const uplift = Number(d.peak_uplift_pct ?? 70)/100;
  if(spread < 1e-12 || uplift === 0) return Array(slots).fill(mean);
  const raw = heights.map(x=>Math.max(0,1 + uplift*(x-avg)/spread));
  const norm = raw.reduce((a,b)=>a+b,0)/slots;
  return raw.map(x=>mean*x/norm);
}
export function simulationHorizonSeconds(scenario) {
  const durations = (scenario.balloons || []).filter(h=>h.trajectory_id)
    .map(h=>Number(h.trajectory_duration_seconds)).filter(x=>Number.isFinite(x)&&x>0);
  const horizon = durations.length ? Math.min(...durations) : 86400;
  return scenario.config.weather_source === 'era5' ? Math.min(86400,horizon) : horizon;
}
export function slotCount(scenario) {
  return Math.max(1, Math.ceil(simulationHorizonSeconds(scenario)/Number(scenario.config.slot_seconds||300)));
}
