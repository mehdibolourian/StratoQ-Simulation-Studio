// Full bipartite set of *potential* GS↔HAP links; independent of last run.
export function potentialLinks(scenario, frame = null, includeResults = true) {
  const results = includeResults ? new Map((frame?.links || []).map(l => [l.id, l])) : new Map();
  const overrides = new Map((scenario.link_overrides || []).map(o => [`${o.source}:${o.target}`, o]));
  return scenario.ground_stations.flatMap(gs => scenario.balloons.map(hap => {
    const id = `${gs.id}:${hap.id}`;
    const info = results.get(id);
    const override = overrides.get(id);
    const enabled = info ? Boolean(info.enabled) : override?.enabled !== false;
    const dy = (gs.lat-hap.lat)*111.195;
    const dx = (gs.lon-hap.lon)*111.195*Math.cos(gs.lat*Math.PI/180);
    const geometricInRange = Math.hypot(dx,dy) <= hap.coverage_km;
    // The backend's per-slot geometry is authoritative after simulation.
    const inRange = info ? Boolean(info.in_range) : geometricInRange;
    const active = enabled && inRange && (info ? info.active : false);
    return {
      id, source: gs.id, target: hap.id, enabled, in_range: inRange, active,
      activated: Boolean(info?.activated),
      allocated: Boolean(info?.allocated),
      visibility_km: info?.visibility_km ?? override?.visibility_km ?? 100,
      capacity_limit_bps: info?.capacity_limit_bps ?? override?.capacity_limit_bps ?? null,
      weather_flags: info?.weather_flags ?? [0,0,0],
      capacity_bps: enabled && inRange ? (info?.capacity_bps ?? null) : 0,
      used_bps: enabled && inRange ? (info?.used_bps ?? null) : 0,
      stored_bits: info?.stored_bits ?? null,
      distance_km: info?.distance_km ?? Math.hypot(dx,dy,hap.altitude_km),
      elevation_deg: info?.elevation_deg ?? null,
      weather_loss_db: info?.weather_loss_db ?? null,
    };
  }));
}


/** One authoritative link state for both the inspector and the 3D/map viewers.
 * The backend reports which optical channels were actually switched on and
 * which were used for routing. Never substitute visual availability for an
 * allocator decision or suppress a frame flag with a second frontend test.
 */
export function resolveVisualLinks(topologyLinks = [], frame = null) {
  const state = new Map((frame?.links || []).map(link => [link.id, link]));
  const base = topologyLinks?.length ? topologyLinks : (frame?.links || []);
  return base.map(link => {
    const authoritative = state.get(link.id);
    return authoritative ? {
      ...link, ...authoritative,
      activated: authoritative.activated === true,
      allocated: authoritative.allocated === true,
    } : { ...link, activated: false, allocated: false };
  });
}
