/** Shared solver-grounded physical-link rendering for both map and 3D.
 * Hue identifies the served demand; luminance represents the *physical link*
 * rate relative to the other links in the same slot. Optical activation and
 * consumption of stored QKP keys are separate facts, not interchangeable.
 */
const HUES = [170,35,266,9,207,105,305,61,232,144,325,85];
const positive = value => Math.max(0, Number(value) || 0);
const clamp01 = value => Math.max(0, Math.min(1, Number(value) || 0));

export const demandHue = index => index < HUES.length ? HUES[index] : (index * 137.508 + 20) % 360;
export const demandColor = (index, relativeRate = 1) =>
  // Three.js Color.setStyle expects comma-separated HSL. The newer CSS
  // space-separated spelling is accepted by MapLibre but rendered WHITE by
  // Three.js on the 3D lines. Keep a single string for both renderers.
  `hsl(${demandHue(index).toFixed(1)}, 91%, ${(31 + 40 * Math.sqrt(clamp01(relativeRate))).toFixed(1)}%)`;

export function linkKeyMode(link) {
  const fresh = positive(link?.fresh_used_bps);
  const qkp = positive(link?.qkp_used_bps);
  if (fresh > 1e-7 && qkp > 1e-7) return 'mixed';
  if (qkp > 1e-7) return 'qkp';
  if (fresh > 1e-7) return 'fresh';
  // For legacy saved runs where per-link fresh/QKP split was not recorded.
  if (link?.allocated && !link?.activated) return 'qkp';
  if (link?.allocated && link?.activated) return 'fresh';
  return 'idle';
}

/** The physical rate users should compare, in bits/s:
 * - optical enabled: newly available optical SKR (capacity_bps)
 * - stored-key-only: actual QKP draw (qkp_used_bps)
 * QKP inventory (stored_bits) is deliberately not treated as a rate.
 */
export function linkVisualRate(link) {
  if (link?.enabled === false || link?.in_range === false) return 0;
  if (link?.activated) return positive(link.capacity_bps) || positive(link.fresh_used_bps) || positive(link.used_bps);
  return positive(link.qkp_used_bps) || (link?.allocated ? positive(link.used_bps) : 0);
}

export function linkRateIntensity(link, frame) {
  const current = linkVisualRate(link);
  if (current <= 1e-7) return 0;
  // Normalize against the same slot, never a future or cached simulation.
  const peers = frame?.links?.length ? frame.links : [link];
  const maximum = Math.max(current, ...peers.map(linkVisualRate));
  return clamp01(current / maximum);
}

/** A link can generate fresh optical keys while also drawing from QKP.
 * Don't infer 'optical OFF' just because all the *used* keys were stored.
 */
export function linkDisplayState(link) {
  const usingQkp = linkKeyMode(link) === 'qkp' || linkKeyMode(link) === 'mixed';
  if (link?.activated && usingQkp) return 'mixed';
  if (link?.activated) return 'fresh';
  if (usingQkp) return 'qkp';
  return 'idle';
}

/** One fallback palette for optical/QKP/idle physical links without a
 * served-demand path. Both map and 3D must draw the same colors. */
export function linkFallbackColor(link) {
  if (!link?.enabled || !link?.in_range) return '#a46768';
  switch (linkDisplayState(link)) {
    case 'qkp': return '#e0a35d';
    case 'fresh': return '#50cbd6';
    case 'mixed': return '#80d4d4';
    default: return '#516679';
  }
}

export function allocationsForLink(link, frame, scenario) {
  const all = frame?.demands || [];
  const orderedIds = (scenario?.demands || []).map(d => d.id);
  const maxRequested = Math.max(1, ...all.map(d => positive(d.requested_bps)));
  const linkIntensity = linkRateIntensity(link, frame);
  const sharedMode = linkKeyMode(link);
  return all.flatMap(d => {
    const path = d.path || [];
    const carried = positive(d.served_bps);
    if (carried <= 1e-7 || path.length < 2) return [];
    const onPath = path.slice(1).some((node, i) =>
      (path[i] === link.source && node === link.target) ||
      (path[i] === link.target && node === link.source));
    if (!onPath) return [];
    const index = Math.max(0, orderedIds.indexOf(d.id));
    // Both link SKR/QKP draw and demand throughput affect brightness. This
    // preserves dimming in storms without conflating the QKP stock with SKR.
    const relative = Math.sqrt(linkIntensity * clamp01(carried / maxRequested));
    return [{id:d.id, name:scenario?.demands?.find(x => x.id === d.id)?.name || d.id,
      color:demandColor(index, relative), rate:carried,
      mode:sharedMode, index, intensity:linkIntensity}];
  });
}

export function linkTooltip(link, frame, scenario) {
  const allocations = allocationsForLink(link, frame, scenario);
  const flows = allocations.map(d => `${d.name}: ${(d.rate / 1000).toFixed(2)} kb/s`).join(' · ');
  const status = linkDisplayState(link) === 'mixed' ? 'Optical ON + QKP draw'
    : linkDisplayState(link) === 'fresh' ? 'Optical ON'
    : linkDisplayState(link) === 'qkp' ? 'QKP draw, optical OFF' : 'Idle optical link';
  const keys = `fresh ${ (positive(link?.fresh_used_bps) / 1000).toFixed(2)} kb/s, QKP ${(positive(link?.qkp_used_bps) / 1000).toFixed(2)} kb/s`;
  return [status, flows, keys].filter(Boolean).join(' · ');
}
