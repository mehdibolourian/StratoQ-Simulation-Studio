/** Bounds of the editable 3D scene in the same world-km coordinates as geo.js.
 * A fixed geographic origin is useful for geometry/drag mapping, but camera,
 * ground plane and axes must adapt when users move the network elsewhere.
 */
import {position3D} from './geo.js';

export function sceneBounds(scenario) {
  const nodes=[...(scenario?.ground_stations||[]),...(scenario?.balloons||[])];
  const x=[],z=[];
  let maxY=16;
  for(const node of nodes) {
    const [nx,ny,nz]=position3D(node);
    if(![nx,ny,nz].every(Number.isFinite))continue;
    x.push(nx);z.push(nz);maxY=Math.max(maxY,ny+10);
  }
  // Use manually arranged weather in the scene extents. ERA5 raster cells
  // may cover a large region and should not continuously zoom the view out.
  for(const weather of scenario?.weather_regions||[]) {
    if(weather.source==='era5')continue;
    const [nx,,nz]=position3D(weather);
    if(!Number.isFinite(nx)||!Number.isFinite(nz))continue;
    const r=Math.max(0,Math.min(400,Number(weather.radius_km)||0));
    x.push(nx-r,nx+r);z.push(nz-r,nz+r);
  }
  const minX=x.length?Math.min(...x):-50, maxX=x.length?Math.max(...x):50;
  const minZ=z.length?Math.min(...z):-50, maxZ=z.length?Math.max(...z):50;
  const centerX=(minX+maxX)/2, centerZ=(minZ+maxZ)/2;
  const extent=Math.max(80,maxX-minX,maxZ-minZ);
  const margin=Math.max(18,extent*.13);
  const spanX=maxX-minX+margin*2,spanZ=maxZ-minZ+margin*2;
  const viewRadius=Math.sqrt((spanX/2)**2+(spanZ/2)**2+(maxY/2)**2);
  const targetY=Math.max(5,Math.min(35,maxY*.30));
  return {minX,maxX,minZ,maxZ,centerX,centerZ,maxY,targetY,extent,margin,
    spanX,spanZ,viewRadius,axisXMin:minX-margin,axisXMax:maxX+margin,
    axisZMin:minZ-margin,axisZMax:maxZ+margin,
    axisHeight:Math.max(35,maxY+12),planeSize:Math.max(300,extent+4*margin)};
}
