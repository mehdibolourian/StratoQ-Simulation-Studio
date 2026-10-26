import React, { useEffect, useRef } from 'react';
import { Map as MapLibreMap, Marker, NavigationControl, setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { geoCircle } from '../lib/geo';

setWorkerUrl(workerUrl);
const emptyFC = () => ({ type: 'FeatureCollection', features: [] });

function coverageFeature(h) {
  return {type: 'Feature', properties: {id: h.id}, geometry: {type: 'Polygon', coordinates: [geoCircle({...h, radius_km: h.coverage_km})]}};
}

export default function GeoMap({ scenario, frame, topologyLinks, selectedId, onSelect, onPositionChange }) {
  const container = useRef(null);
  const mapRef = useRef(null);
  const markers = useRef([]);
  const handlers = useRef({onSelect, onPositionChange});
  handlers.current = {onSelect, onPositionChange};
  const latest = useRef({weather:scenario.weather_regions});
  latest.current = {weather:scenario.weather_regions};

  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new MapLibreMap({
      container: container.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
      center: [-81.00655, 48.6212], zoom: 8.25, pitch: 40, bearing: -15,
      attributionControl: true,
    });
    mapRef.current = map;
    map.addControl(new NavigationControl({ visualizePitch: true }), 'top-right');
    map.on('load', () => {
      map.addSource('coverage', {type: 'geojson', data: emptyFC()});
      map.addLayer({id: 'coverage-fills', type: 'fill', source: 'coverage', paint: {'fill-color': '#67e6d6', 'fill-opacity': 0.065}});
      map.addLayer({id: 'coverage-edges', type: 'line', source: 'coverage', paint: {'line-color': '#51c9c2', 'line-width': 1.2, 'line-dasharray': [3, 2], 'line-opacity': 0.55}});
      map.addSource('weather', {type: 'geojson', data: emptyFC()});
      map.addLayer({id: 'weather-fills', type: 'fill', source: 'weather', paint: {'fill-color': ['get', 'color'], 'fill-opacity': 0.18}});
      map.addLayer({id: 'weather-edges', type: 'line', source: 'weather', paint: {'line-color': ['get', 'color'], 'line-width': 1.8}});
      map.addSource('links', {type: 'geojson', data: emptyFC()});
      map.addLayer({id: 'link-lines', type: 'line', source: 'links', paint: {'line-color': ['get', 'color'], 'line-width': ['case', ['get','selected'], 5, 2.6], 'line-opacity': 0.85}});
      // MapLibre weather polygon is draggable (not only its small marker).
      // Keep drag state outside React so layer updates cannot interrupt it.
      let weatherDrag = null;
      map.on('mousedown', 'weather-fills', event => {
        const id = event.features?.[0]?.properties?.id;
        if (!id || event.originalEvent.button !== 0) return;
        const feature = event.features?.[0];
        if (!feature) return;
        const active = latest.current.weather.find(w => w.id === id);
        if (!active) return;
        event.preventDefault();
        weatherDrag = {
          id, startLat:active.lat, startLon:active.lon,
          pointerLat:event.lngLat.lat, pointerLon:event.lngLat.lng,
        };
        map.dragPan.disable();
        map.getCanvas().style.cursor = 'grabbing';
        handlers.current.onSelect(id);
      });
      map.on('mousemove', event => {
        if (!weatherDrag) return;
        const d = weatherDrag;
        const lat = Math.max(-90, Math.min(90, d.startLat + event.lngLat.lat - d.pointerLat));
        const lon = Math.max(-180, Math.min(180, d.startLon + event.lngLat.lng - d.pointerLon));
        handlers.current.onPositionChange(d.id, Number(lat.toFixed(5)), Number(lon.toFixed(5)));
      });
      const endWeatherDrag = () => {
        if (!weatherDrag) return;
        weatherDrag = null;
        map.dragPan.enable();
        map.getCanvas().style.cursor = '';
      };
      map.on('mouseup', endWeatherDrag);
      map.on('mouseout', endWeatherDrag);
      map.on('mouseenter', 'weather-fills', () => {if (!weatherDrag) map.getCanvas().style.cursor='grab';});
      map.on('mouseleave', 'weather-fills', () => {if (!weatherDrag) map.getCanvas().style.cursor='';});
            map.on('click', 'link-lines', e => { const id = e.features?.[0]?.properties?.id; if(id) handlers.current.onSelect(id); });
      map.on('mouseenter','link-lines',()=>{map.getCanvas().style.cursor='pointer';});
      map.on('mouseleave','link-lines',()=>{map.getCanvas().style.cursor='';});
    });
    return () => {markers.current.forEach(m => m.remove()); markers.current = []; map.remove(); mapRef.current = null;};
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    function updateLayers() {
      const gsById = Object.fromEntries(scenario.ground_stations.map(x => [x.id, x]));
      const hapById = Object.fromEntries(scenario.balloons.map(x => [x.id, x]));
      const links = (topologyLinks || frame?.links || []).map(l => {
        const gs = gsById[l.source], hap = hapById[l.target];
        if (!gs || !hap) return null;
        return {type: 'Feature', geometry: {type: 'LineString', coordinates: [[gs.lon, gs.lat], [hap.lon, hap.lat]]},
          properties: {id:l.id, selected:l.id===selectedId, color: l.id===selectedId ? '#f8cf91' : (!l.enabled || !l.in_range) ? '#e18485' : l.active ? '#59dccc' : '#516679'}};
      }).filter(Boolean);
      map.getSource('links')?.setData({type:'FeatureCollection', features: links});
      map.getSource('coverage')?.setData({type:'FeatureCollection', features: scenario.balloons.map(coverageFeature)});
      map.getSource('weather')?.setData({type:'FeatureCollection', features: scenario.weather_regions.map(w =>
        ({type:'Feature', geometry:{type:'Polygon', coordinates:[geoCircle(w)]}, properties:{id:w.id,color:w.effect==='rain'?'#73aaf0':w.effect==='snow'?'#e0efff':'#b49aff'}}))});
    }
    if (map.isStyleLoaded() && map.getSource('links')) updateLayers();
    else map.once('load', updateLayers);
  }, [scenario, frame, topologyLinks, selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    const tracked = scenario.balloons.find(b => b.trajectory_id);
    if (!map || !tracked || !map.loaded()) return;
    const bounds = map.getBounds();
    if (!bounds.contains([tracked.lon, tracked.lat])) {
      map.easeTo({center:[tracked.lon, tracked.lat], duration:400});
    }
  }, [scenario]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markers.current.forEach(m => m.remove());
    markers.current = [];
    const nodes = [...scenario.ground_stations.map(n=>({...n, icon:'⌁', type:'gs'})),
      ...scenario.balloons.map(n=>({...n, icon:'▲', type:'hap'})),
      ...scenario.weather_regions.map(n=>({...n, icon:n.effect==='rain'?'☂':n.effect==='snow'?'❄':'☁', type:'weather'}))];
    nodes.forEach(node => {
      const el = document.createElement('button');
      el.className = `map-marker ${node.type} ${selectedId===node.id ? 'selected' : ''}`;
      el.textContent = node.icon;
      el.title = `${node.name} (drag to reposition)`;
      el.setAttribute('aria-label', `Select or drag ${node.name}`);
      el.addEventListener('click', (e) => {e.stopPropagation(); handlers.current.onSelect(node.id);});
      const marker = new Marker({element:el, draggable: true})
        .setLngLat([node.lon,node.lat]).addTo(map);
      marker.on('dragend', () => { const p=marker.getLngLat(); handlers.current.onPositionChange(node.id, Number(p.lat.toFixed(5)), Number(p.lng.toFixed(5))); });
      markers.current.push(marker);
    });
    return () => {markers.current.forEach(m=>m.remove()); markers.current=[];};
  }, [scenario, selectedId]);

  return <div className="map-host">
    <div ref={container} className="map-canvas" />
    <div className="map-hint">Drag weather region or marker to reposition</div>
  </div>;
}
