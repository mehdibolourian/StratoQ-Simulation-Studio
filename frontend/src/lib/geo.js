/** Local tangent plane centered on the Northern Ontario demo, in kilometers.
 * The Cartesian scene uses X=east, Z=south, Y=altitude. Geometry/model sizes
 * are intentionally exaggerated to be readable at regional scales.
 */
export const CENTER = { lat: 48.6212, lon: -81.00655 };
const LON_KM = 111.32 * Math.cos(CENTER.lat * Math.PI / 180);
const LAT_KM = 111.32;
export const ALT_SCALE = 1.13;
export function position3D(node) {
  return [(node.lon - CENTER.lon) * LON_KM,
    (node.altitude_km || 0) * ALT_SCALE,
    -(node.lat - CENTER.lat) * LAT_KM];
}
export function fromWorld(x, z) {
  return { lon: CENTER.lon + x / LON_KM, lat: CENTER.lat - z / LAT_KM };
}
export function flatDistance(a, b) {
  const ax = position3D(a), bx = position3D(b);
  return Math.hypot(ax[0] - bx[0], ax[2] - bx[2]);
}
export function geoCircle(region, segments = 60) {
  const ring = [];
  for (let i = 0; i <= segments; i++) {
    const angle = 2 * Math.PI * i / segments;
    ring.push([region.lon + (region.radius_km / LON_KM) * Math.cos(angle),
      region.lat + (region.radius_km / LAT_KM) * Math.sin(angle)]);
  }
  return ring;
}
