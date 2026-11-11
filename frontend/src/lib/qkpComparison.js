/** Compare a storage ablation only when every other experiment input matches.
 * Never compare different geometry/weather/demand/solver settings just because
 * two tabs have "storm" in their name. */
export function matchingQkpInputs(a,b) {
  if(!a?.config || !b?.config)return false;
  const normalize=s=>{
    const config={...s.config};delete config.qkp_enabled;
    return JSON.stringify({...s,config});
  };
  return normalize(a)===normalize(b);
}

/** Differences are *percentage points*, not relative percent gains.
 * Missing or stale/failed results produce no apparent improvement. */
export function qkpComparisonDelta(withQkp,withoutQkp){
  if(!withQkp||!withoutQkp)return null;
  const a=Number(withQkp.total_satisfaction),b=Number(withoutQkp.total_satisfaction);
  const c=Number(withQkp.weather_window_satisfaction),d=Number(withoutQkp.weather_window_satisfaction);
  if(![a,b,c,d].every(Number.isFinite)||Math.min(a,b,c,d)<0)return null;
  return {total:100*(a-b),storm:100*(c-d)};
}
