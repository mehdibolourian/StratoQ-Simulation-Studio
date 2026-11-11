/** Refresh retired/duplicate showcase tabs without discarding user edits.
 * An experiment is safe to replace only when its current scenario is identical
 * to the baseline saved when that tab was created. A modified tab is preserved.
 */
export function upgradeLegacyShowcase(saved, activeId, presets, makeBuiltin, normalize, isScenario) {
  const byId=new Map(presets.map(p=>[p.id,p]));
  const originals=saved.filter(e=>e.builtin?.id && isScenario(e.baselineScenario) &&
    JSON.stringify(normalize(e.scenario))===JSON.stringify(normalize(e.baselineScenario)));
  const outdated=originals.some(e=>!byId.has(e.builtin.id) ||
    JSON.stringify(normalize(e.scenario))!==JSON.stringify(normalize(byId.get(e.builtin.id).scenario)));
  const seen=new Set();
  const duplicates=originals.some(e=>{if(seen.has(e.builtin.id))return true;seen.add(e.builtin.id);return false;});
  if(!outdated && !duplicates)return null;
  const preserved=saved.filter(e=>!originals.includes(e));
  const curated=presets.map(makeBuiltin);
  const oldActive=saved.find(e=>e.id===activeId);
  const kept=preserved.find(e=>e.id===activeId);
  const replacement=curated.find(e=>e.builtin.id===oldActive?.builtin?.id) ||
    curated.find(e=>e.builtin.id==='qkp-enabled' && oldActive?.builtin?.id==='corridor-opt') || curated[0];
  return {experiments:[...curated,...preserved],activeId:kept?.id||replacement.id};
}
