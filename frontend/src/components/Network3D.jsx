import React, { useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Grid, Html, Line, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { CENTER, fromWorld, position3D } from '../lib/geo';

const CYAN = '#56e9dc';
const GOLD = '#ffd09a';
const formatRate = value => value >= 1e6 ? `${(value / 1e6).toFixed(2)} Mbps` : `${((value || 0) / 1e3).toFixed(1)} kbps`;
const formatBits = value => value >= 1e6 ? `${(value / 1e6).toFixed(2)} Mb` : value >= 1e3 ? `${(value / 1e3).toFixed(1)} kb` : `${Math.round(value || 0)} b`;

function KeyTank({ fraction = 0, isBalloon = false }) {
  const fill = useRef();
  const level = useRef(Math.max(0.015, fraction));
  const height = 1.55;
  useFrame((_, delta) => {
    level.current = THREE.MathUtils.damp(level.current, Math.max(0.015, Math.min(1, fraction)), 5, delta);
    if (fill.current) {
      fill.current.scale.y = level.current;
      fill.current.position.y = -height / 2 + (height * level.current) / 2;
    }
  });
  const color = isBalloon ? '#efc58d' : '#5be0cf';
  return <group position={isBalloon ? [4.3, 1.1, 0] : [3.3, 1.1, 0]}>
    <mesh><cylinderGeometry args={[0.54, 0.54, 1.8, 32, 1, true]} />
      <meshStandardMaterial color="#7c99a7" metalness={0.35} roughness={0.25} transparent opacity={0.22} side={THREE.DoubleSide} depthWrite={false} /></mesh>
    <mesh position={[0, -0.02, 0]}><cylinderGeometry args={[0.53, 0.53, 1.55, 32, 1, true]} />
      <meshBasicMaterial color="#b8d8e1" wireframe transparent opacity={0.38} /></mesh>
    <mesh ref={fill} position={[0, -height/4, 0]}>
      <cylinderGeometry args={[0.46, 0.46, height, 32]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.2} metalness={0.3} roughness={0.28} transparent opacity={0.84} /></mesh>
    {[-0.93, 0.93].map(y => <mesh key={y} position={[0,y,0]}>
      <cylinderGeometry args={[0.57, 0.57, 0.10, 32]} />
      <meshStandardMaterial color="#647e8c" metalness={0.6} roughness={0.28} /></mesh>)}
    <Html position={[0, -1.25, 0]} center distanceFactor={65} style={{pointerEvents:'none'}}>
      <div className="qkp-tank-label">QKP</div>
    </Html>
  </group>;
}


function Badge({ title, kind, active, qkp }) {
  const pct = qkp ? Math.round(100 * qkp.fill_fraction) : null;
  return <div className={`world-label compact-node-label ${kind} ${active ? 'is-selected' : ''}`}
    title={`${kind === 'balloon' ? 'HAP' : 'GS'} ${title} · QKP ${qkp ? `${formatBits(qkp.stored_bits)} / ${formatBits(qkp.capacity_bits)}` : 'not calculated'}`}>
    <span className="world-label-dot" />
    <strong>{kind === 'balloon' ? 'HAP' : 'GS'} · {title}</strong>
    <span className="node-qkp-short">QKP {pct == null ? '—' : `${pct}%`}</span>
  </div>;
}

function BalloonModel({ yaw = 0 }) {
  const root = useRef();

  useFrame(({ clock }) => {
    if (!root.current) return;
    const t = clock.elapsedTime;
    root.current.rotation.y = (yaw * Math.PI) / 180 + Math.sin(t * 0.36) * 0.035;
    root.current.rotation.z = Math.sin(t * 0.58) * 0.012;
    root.current.position.y = Math.sin(t * 0.85) * 0.07;
  });

  const envelope = '#f9e8ce';
  const payload = '#7a9fb8';
  const payloadTrim = '#354e65';
  const cable = '#c2cbd2';

  // The envelope is deliberately much larger than the suspended payload.
  // Models are exaggerated for visibility and are not physically to scale.
  const upperCorners = [
    [-0.43, 2.50, -0.43], [0.43, 2.50, -0.43],
    [-0.43, 2.50,  0.43], [0.43, 2.50,  0.43],
  ];
  const lowerCorners = [
    [-0.77, 0.82, -0.47], [0.77, 0.82, -0.47],
    [-0.77, 0.82,  0.47], [0.77, 0.82,  0.47],
  ];

  return (
    <group ref={root}>
      {/* Clean, softly illuminated gas envelope. */}
      {/* Apply scaling via a separate group, preserving the sphere's normals. */}
      <group position={[0, 5.35, 0]} scale={[2.7, 3.05, 2.7]}>
        <mesh castShadow>
          <sphereGeometry args={[1, 48, 36]} />
          <meshStandardMaterial color={envelope} roughness={0.85} metalness={0.01} />
        </mesh>
      </group>

      {/* Gathered material and collar at the bottom of the envelope. */}
      <mesh position={[0, 2.37, 0]} castShadow>
        <coneGeometry args={[0.44, 0.64, 24]} />
        <meshStandardMaterial color="#e0cfb7" roughness={0.88} />
      </mesh>
      <mesh position={[0, 2.13, 0]} castShadow>
        <cylinderGeometry args={[0.23, 0.28, 0.23, 18]} />
        <meshStandardMaterial color="#9a866f" metalness={0.18} roughness={0.68} />
      </mesh>

      {/* Four suspension cables: one per payload corner. */}
      {upperCorners.map((point, i) => (
        <Line key={i} points={[point, lowerCorners[i]]} color={cable} lineWidth={1.65} />
      ))}

      {/* Payload module, intentionally colored differently from the balloon. */}
      <mesh position={[0, 0.38, 0]} castShadow>
        <boxGeometry args={[1.7, 0.86, 1.12]} />
        <meshStandardMaterial color={payload} metalness={0.34} roughness={0.43} />
      </mesh>
      <mesh position={[0, 0.84, 0]} castShadow>
        <boxGeometry args={[1.84, 0.12, 1.24]} />
        <meshStandardMaterial color={payloadTrim} metalness={0.42} roughness={0.37} />
      </mesh>
      <mesh position={[0, -0.12, 0]} castShadow>
        <boxGeometry args={[1.12, 0.16, 0.84]} />
        <meshStandardMaterial color={payloadTrim} metalness={0.4} roughness={0.43} />
      </mesh>

      {/* A single compact downward-facing optical terminal. */}
      <group position={[0, -0.31, 0]}>
        <mesh castShadow>
          <cylinderGeometry args={[0.23, 0.28, 0.35, 20]} />
          <meshStandardMaterial color="#c9d6e1" metalness={0.65} roughness={0.28} />
        </mesh>
        <mesh position={[0, -0.22, 0]} rotation={[Math.PI, 0, 0]}>
          <cylinderGeometry args={[0.15, 0.22, 0.14, 20]} />
          <meshStandardMaterial color="#283f5b" metalness={0.7} roughness={0.17} />
        </mesh>
        <mesh position={[0, -0.30, 0]}>
          <circleGeometry args={[0.145, 20]} />
          <meshBasicMaterial color="#61dace" side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  );
}

function GroundModel({ yaw = 0 }) {
  // The reflector, rim, struts and feed share one local +Y optical axis.
  // Tilting this group therefore keeps the feed precisely in front of the dish.
  const dishRadius = 1.55;
  const apertureAngle = 1.08;
  const rimRadius = dishRadius * Math.sin(apertureAngle);
  const reflectorOffset = dishRadius * Math.cos(apertureAngle);
  const feedHeight = 1.28;

  return <group rotation={[0, (yaw * Math.PI) / 180, 0]}>
    {/* Stable ground base and azimuth pedestal. */}
    <mesh position={[0, 0.22, 0]} receiveShadow castShadow>
      <cylinderGeometry args={[1.95, 2.24, 0.44, 28]} />
      <meshStandardMaterial color="#2c5061" metalness={0.5} roughness={0.55} />
    </mesh>
    <mesh position={[0, 1.1, 0]} castShadow>
      <cylinderGeometry args={[0.32, 0.5, 1.75, 12]} />
      <meshStandardMaterial color="#b4d5db" metalness={0.55} roughness={0.3} />
    </mesh>
    <mesh position={[0, 2.0, 0]} castShadow>
      <sphereGeometry args={[0.42, 16, 12]} />
      <meshStandardMaterial color="#657e91" metalness={0.5} roughness={0.38} />
    </mesh>

    {/* A true concave spherical cap. Its opening and feed point along +Y. */}
    <group position={[0, 2.5, 0]} rotation={[0.36, 0, -0.35]}>
      <mesh position={[0, reflectorOffset, 0]} castShadow>
        <sphereGeometry args={[dishRadius, 48, 28, 0, Math.PI * 2, Math.PI - apertureAngle, apertureAngle]} />
        <meshStandardMaterial color="#d2e6e8" side={THREE.DoubleSide} metalness={0.4} roughness={0.38} />
      </mesh>
      {/* Torus defaults to an XY plane; turn it into the reflector's XZ rim. */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[rimRadius, 0.075, 10, 52]} />
        <meshStandardMaterial color="#7ff0df" metalness={0.45} emissive="#1e887b" emissiveIntensity={0.15} />
      </mesh>
      {/* Three structural struts converge on the feed, not through the dish. */}
      {[0, (2 * Math.PI) / 3, (4 * Math.PI) / 3].map((angle) => (
        <Line key={angle}
          points={[
            [rimRadius * Math.cos(angle), 0, rimRadius * Math.sin(angle)],
            [0, feedHeight, 0],
          ]}
          color="#a9bdca" lineWidth={1.7} />
      ))}
      <mesh position={[0, feedHeight - 0.18, 0]}>
        <cylinderGeometry args={[0.08, 0.12, 0.28, 12]} />
        <meshStandardMaterial color="#e1e8f2" metalness={0.45} roughness={0.3} />
      </mesh>
      <mesh position={[0, feedHeight, 0]}>
        <cylinderGeometry args={[0.18, 0.10, 0.28, 16]} />
        <meshStandardMaterial color="#617f98" metalness={0.55} roughness={0.25} />
      </mesh>
      <mesh position={[0, feedHeight + 0.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.18, 20]} />
        <meshBasicMaterial color={CYAN} side={THREE.DoubleSide} />
      </mesh>
    </group>

    <mesh position={[0, 0.2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <torusGeometry args={[2.65, 0.038, 8, 55]} />
      <meshBasicMaterial color={CYAN} transparent opacity={0.38} />
    </mesh>
  </group>;
}

function ModelNode({ item, type, selected, dragMode, onSelect, onPositionChange, onDragStart, onDragEnd, qkp }) {
  const pos = position3D(item);
  const isBalloon = type === 'balloon';
  const planeRef = useRef(null);
  const offsetRef = useRef([0, 0]);
  const hitPlane = (e) => {
    const v = new THREE.Vector3();
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -pos[1]);
    return e.ray.intersectPlane(plane, v) ? v : null;
  };
  function handleDown(e) {
    e.stopPropagation();
    onSelect(item.id);
    if (!dragMode) return;
    const hit = hitPlane(e);
    if (!hit) return;
    offsetRef.current = [pos[0] - hit.x, pos[2] - hit.z];
    planeRef.current = pos[1];
    e.target.setPointerCapture(e.pointerId);
    onDragStart();
  }
  function handleMove(e) {
    if (planeRef.current === null) return;
    e.stopPropagation();
    const point = new THREE.Vector3();
    if (e.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -planeRef.current), point)) {
      const coords = fromWorld(point.x + offsetRef.current[0], point.z + offsetRef.current[1]);
      onPositionChange(item.id, Number(coords.lat.toFixed(5)), Number(coords.lon.toFixed(5)));
    }
  }
  function handleUp(e) {
    if (planeRef.current === null) return;
    e.stopPropagation();
    planeRef.current = null;
    try { e.target.releasePointerCapture(e.pointerId); } catch { /* released by browser */ }
    onDragEnd();
  }
  return <group position={pos}>
    {selected && <mesh position={[0, isBalloon ? 0 : 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[3.5, 3.58, 72]} /><meshBasicMaterial color={isBalloon ? GOLD : CYAN} side={THREE.DoubleSide} transparent opacity={0.7} /></mesh>}
    <group onPointerDown={handleDown} onPointerMove={handleMove} onPointerUp={handleUp}
      onPointerOver={() => { document.body.style.cursor = dragMode ? 'grab' : 'pointer'; }}
      onPointerOut={() => { document.body.style.cursor = 'auto'; }}>
      {isBalloon ? <BalloonModel yaw={item.yaw_deg} /> : <GroundModel yaw={item.yaw_deg} />}
      <mesh visible={false} position={[0, isBalloon ? 5.1 : 1.6, 0]}>
        <sphereGeometry args={[isBalloon ? 3.35 : 3.2, 16, 12]} />
        <meshBasicMaterial />
      </mesh>
    </group>
    <KeyTank fraction={qkp?.fill_fraction || 0} isBalloon={isBalloon} />
    {/* Compact label offset to the right, with a leader that avoids the model. */}
    <Line points={isBalloon ? [[2.0, 7.45, 0], [4.4, 8.65, 0]] : [[1.4, 3.6, 0], [3.8, 4.85, 0]]}
      color={isBalloon ? GOLD : CYAN} transparent opacity={0.58} lineWidth={1} />
    <Html position={isBalloon ? [4.4, 8.65, 0] : [3.8, 4.85, 0]}
      center={false} distanceFactor={43} transform={false}
      style={{ pointerEvents: 'none', userSelect: 'none' }}>
      <div style={{ transform: 'translate(7px, -50%)' }}>
        <Badge title={item.name}
          kind={type} active={selected} qkp={qkp} />
      </div>
    </Html>
  </group>;
}

function WeatherParticles({ effect, radius, visibilityKm=0.5, precipitationRate=5 }) {
  const group = useRef();
  const isFog = effect === 'fog';
  const isRain = effect === 'rain';
  // Deterministic particle distribution. Visuals are illustrative, not meteorology.
  const density = isFog ? Math.max(0.3, Math.min(3.5, 0.5 / Math.max(0.05, visibilityKm)))
    : Math.max(0, Math.min(4, precipitationRate / (isRain ? 5 : 2)));
  const count = isFog ? Math.round(14 * density) : Math.round(100 * Math.sqrt(density));
  const points = React.useMemo(() => Array.from({length: count}, (_, i) => {
    const angle = i * 2.399963;
    const radial = Math.sqrt((i + 0.5) / count) * radius * 0.88;
    return [Math.cos(angle)*radial, 1 + ((i*17)%31)/31*13, Math.sin(angle)*radial];
  }), [count, radius]);
  useFrame(({clock}) => {
    if (!group.current) return;
    const speed = isRain ? 4.5 * Math.max(0.5, Math.sqrt(density)) : isFog ? 0.18 : 0.85 * Math.max(0.5, Math.sqrt(density));
    group.current.children.forEach((obj, i) => {
      obj.position.y = 1 + ((points[i][1] - 1 - clock.elapsedTime*speed + 1000) % 14);
      if (isFog) obj.position.x = points[i][0] + Math.sin(clock.elapsedTime*0.2 + i)*0.4;
    });
  });
  return <group ref={group}>
    {points.map(([x,y,z],i) => isFog ?
      <mesh key={i} raycast={() => null} position={[x,y,z]} scale={[Math.min(7,radius*.38),1.6,Math.min(7,radius*.38)]}>
        <sphereGeometry args={[1,10,8]}/>
        <meshStandardMaterial color="#a6b5cf" transparent opacity={0.07} depthWrite={false}/>
      </mesh> : isRain ?
      <mesh key={i} raycast={() => null} position={[x,y,z]}><cylinderGeometry args={[.018,.018,.8,4]}/>
        <meshBasicMaterial color="#8fbcff" transparent opacity={.55} depthWrite={false}/>
      </mesh> :
      <mesh key={i} raycast={() => null} position={[x,y,z]}><sphereGeometry args={[.10,5,5]}/>
        <meshBasicMaterial color="#f3f7ff" transparent opacity={.78} depthWrite={false}/>
      </mesh>)}
  </group>;
}

function Cloud({ weather, selected, onSelect, dragMode, onPositionChange, onDragStart, onDragEnd }) {
  const [x,,z] = position3D(weather);
  const dragging = useRef(false);
  const offset = useRef([0,0]);
  const radius = weather.radius_km;
  const effect = weather.effect || 'fog';
  const hue = effect === 'rain' ? '#6eabed' : effect === 'snow' ? '#dcecff' : '#aa8bff';
  function intersection(e) {
    const hit = new THREE.Vector3();
    return e.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),hit) ? hit : null;
  }
  function down(e) {
    // Weather zones drag directly; unlike GS/HAP they do not need the Move toggle.
    e.stopPropagation();
    onSelect(weather.id);
    const hit = intersection(e);
    if (!hit) return;
    offset.current = [x - hit.x, z - hit.z];
    dragging.current = true;
    try { e.target.setPointerCapture(e.pointerId); } catch { /* browser fallback */ }
    onDragStart();
    document.body.style.cursor = 'grabbing';
  }
  function move(e) {
    if (!dragging.current)return;
    e.stopPropagation();const hit=intersection(e);if(!hit)return;
    const loc=fromWorld(hit.x+offset.current[0],hit.z+offset.current[1]);
    onPositionChange(weather.id, Number(loc.lat.toFixed(5)), Number(loc.lon.toFixed(5)));
  }
  function up(e) {
    if(!dragging.current)return;
    e.stopPropagation();dragging.current=false;
    try{e.target.releasePointerCapture(e.pointerId);}catch{}document.body.style.cursor="auto";onDragEnd();
  }
  return <group position={[x,0,z]}
    onPointerDown={down} onPointerMove={move} onPointerUp={up}
    onPointerCancel={up} onPointerMissed={() => { if (dragging.current) {dragging.current=false;onDragEnd();} }}
    onClick={e=>{e.stopPropagation();onSelect(weather.id);}}
    onPointerOver={()=>{document.body.style.cursor=dragging.current?'grabbing':'grab';}}
    onPointerOut={()=>{if(!dragging.current) document.body.style.cursor='auto';}}>
    {/* A raised visible grab handle keeps pointer hits above ground and particles. */}
    <mesh position={[0,1.7,0]} castShadow>
      <sphereGeometry args={[1.05,20,12]} />
      <meshStandardMaterial color={hue} emissive={hue} emissiveIntensity={selected ? .38 : .13} roughness={.45} />
    </mesh>
    <mesh position={[0,2.0,0]} rotation={[-Math.PI/2,0,0]}>
      <torusGeometry args={[1.30,.11,10,30]}/>
      <meshBasicMaterial color={selected?'#ffffff':hue}/>
    </mesh>
    <mesh position={[0,.01,0]} rotation={[-Math.PI/2,0,0]}>
      <circleGeometry args={[radius,64]}/>
      <meshBasicMaterial color={hue} transparent opacity={selected?.21:.085} side={THREE.DoubleSide} depthWrite={false}/>
    </mesh>
    <mesh position={[0,0.035,0]} rotation={[-Math.PI/2,0,0]}>
      <ringGeometry args={[Math.max(.1,radius-.16),radius,64]}/>
      <meshBasicMaterial color={selected?'#ffffff':hue} transparent opacity={.8} side={THREE.DoubleSide}/>
    </mesh>
    <WeatherParticles effect={effect} radius={radius} visibilityKm={weather.visibility_km??0.5} precipitationRate={weather.precipitation_rate_mm_h??5}/>
    <Html position={[0,15,0]} center distanceFactor={75} style={{pointerEvents:'none'}}>
      <div className="weather-label">{effect==='rain'?'☂':effect==='snow'?'❄':'☁'} {effect} · {radius} km · {effect==='fog' ? `${weather.visibility_km??0.5} km vis` : `${weather.precipitation_rate_mm_h??5} mm/h`}</div>
    </Html>
  </group>;
}

function Scene({ scenario, frame, topologyLinks, selectedId, onSelect, dragMode, onPositionChange, autoRotate }) {
  const [dragging, setDragging] = useState(false);
  const orbitRef = useRef();
  const { camera } = useThree();
  const trajectoryHap = scenario.balloons.find(b => b.trajectory_id);
  const followPoint = trajectoryHap ? position3D(trajectoryHap) : null;
  // Keep distant uploaded trajectories visible without snapping on every slot.
  useFrame(() => {
    const control = orbitRef.current;
    if (!followPoint || !control || dragging) return;
    const target = control.target;
    const dx = followPoint[0] - target.x;
    const dz = followPoint[2] - target.z;
    const distance = Math.hypot(dx, dz);
    if (distance > 75) {
      const step = Math.min(1, (distance - 55) / Math.max(distance, 1));
      const move = new THREE.Vector3(dx * step, 0, dz * step);
      camera.position.add(move);
      control.target.add(move);
      control.update();
    }
  });
  const links = topologyLinks || frame?.links || [];
  const qkps = Object.fromEntries((frame?.qkps || []).map(q => [q.node_id, q]));
  const coords = Object.fromEntries([...scenario.ground_stations, ...scenario.balloons].map(n => [n.id, position3D(n)]));
  return <>
    <color attach="background" args={['#0a1826']} />
    <fog attach="fog" args={['#0a1826', 180, 650]} />
    <ambientLight intensity={1.6} />
    <hemisphereLight args={['#c2eaff', '#263747', 2.3]} />
    <directionalLight position={[35, 70, 10]} intensity={2.7} color="#f9e7d4" castShadow shadow-mapSize={[2048, 2048]} />
    <pointLight position={[-38, 20, 5]} intensity={140} distance={105} color="#28b4b9" />
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.17, 0]} receiveShadow>
      <planeGeometry args={[300, 300]} />
      <meshStandardMaterial color="#0d202f" roughness={0.95} />
    </mesh>
    <Grid args={[180, 180]} position={[0, -0.14, 0]} cellSize={4} cellThickness={0.55}
      cellColor="#24465a" sectionSize={20} sectionThickness={1.2} sectionColor="#326378"
      fadeDistance={135} fadeStrength={1.8} infiniteGrid />
    {/* Axis labels provide geospatial context, not a precisely scaled Earth globe. */}
    <Line points={[[-59, 0, 58], [62, 0, 58]]} color="#728aa3" lineWidth={1.2} />
    <Line points={[[-59, 0, 58], [-59, 0, -58]]} color="#728aa3" lineWidth={1.2} />
    <Line points={[[-59, 0, 58], [-59, 34, 58]]} color="#d6a877" lineWidth={1.8} />
    <Html position={[-59, 36, 58]} center distanceFactor={100} style={{pointerEvents:'none'}}><div className="axis-label">ALT ↑</div></Html>
    <Html position={[55, 0, 61]} center distanceFactor={100} style={{pointerEvents:'none'}}><div className="axis-label">LONGITUDE →</div></Html>
    <Html position={[-61, 0, -56]} center distanceFactor={100} style={{pointerEvents:'none'}}><div className="axis-label">LATITUDE ↑</div></Html>
    <Html position={[0, 0, 52]} center distanceFactor={100} style={{pointerEvents:'none'}}><div className="axis-label subtle">{CENTER.lat.toFixed(3)}° N · {Math.abs(CENTER.lon).toFixed(3)}° W</div></Html>
    {scenario.weather_regions.map(w => <Cloud key={w.id} weather={w} selected={selectedId === w.id} onSelect={onSelect} dragMode={dragMode} onPositionChange={onPositionChange} onDragStart={()=>setDragging(true)} onDragEnd={()=>setDragging(false)} />)}
    {links.map(link => {
      const a = coords[link.source], b = coords[link.target];
      if (!a || !b) return null;
      const isHap = id => scenario.balloons.some(h => h.id === id);
      const endpoints = [
        [a[0], a[1] + (isHap(link.source) ? -0.25 : 2.5), a[2]],
        [b[0], b[1] + (isHap(link.target) ? -0.25 : 2.5), b[2]],
      ];
      const cap = link.capacity_bps || 0;
      const isSelected = selectedId === link.id;
      const unavailable = !link.enabled || !link.in_range;
      const used = link.used_bps || 0;
      const midpoint = endpoints[0].map((v, i) => (v + endpoints[1][i]) / 2);
      midpoint[1] += 1.4;
      return <group key={link.id}>
        {/* Wide transparent pick target; links can be clicked even when disabled. */}
        <Line points={endpoints} color="#ffffff" lineWidth={15} transparent opacity={0.005}
          onClick={e=>{e.stopPropagation();onSelect(link.id);}}
          onPointerOver={()=>{document.body.style.cursor='pointer';}}
          onPointerOut={()=>{document.body.style.cursor='auto';}} />
        <Line points={endpoints}
          color={isSelected ? '#f8cf91' : unavailable ? '#e18485' : link.active ? '#4de5d6' : '#4d8b9a'} lineWidth={isSelected ? 4 : link.active ? 2.5 : 1.5}
          transparent opacity={isSelected ? 1 : unavailable ? 0.55 : link.active ? 0.88 : 0.45} />
        {/* Tiny single-line rate tag. Full information stays in the link inspector. */}
        {(link.capacity_bps != null || isSelected) && <Html position={midpoint} center distanceFactor={36} style={{pointerEvents:'none'}}>
          <div className={`link-throughput-label compact-link-label ${isSelected ? 'selected' : ''}`}
            title={`Capacity: ${formatRate(cap)} · Used: ${formatRate(used)}`}>
            {!link.enabled ? 'OFF' : !link.in_range ? 'OOR' : link.capacity_bps == null ? '…' : `${formatRate(cap)} / ${formatRate(used)}`}
          </div>
        </Html>}
        {link.active && <Line points={endpoints}
          color="#7cfdf3" lineWidth={5.5} transparent opacity={0.095} />}
      </group>;
    })}
    {frame?.demands?.filter(d=> d.path.length > 0).map(d => {
      const a = coords[d.source], b = coords[d.target];
      if (!a || !b) return null;
      return <Line key={d.id} points={[[a[0], 0.28, a[2]], [0.5*(a[0]+b[0]), 0.28, 0.5*(a[2]+b[2])], [b[0], 0.28, b[2]]]}
        color="#b0a1ff" lineWidth={1} transparent opacity={0.7} dashed dashSize={1.2} gapSize={1.1} />;
    })}
    {scenario.ground_stations.map(gs => <ModelNode key={gs.id} item={gs} type="ground" selected={selectedId===gs.id}
      dragMode={dragMode} onSelect={onSelect} onPositionChange={onPositionChange} onDragStart={()=>setDragging(true)} onDragEnd={()=>setDragging(false)} qkp={qkps[gs.id]} />)}
    {scenario.balloons.map(hap => <ModelNode key={hap.id} item={hap} type="balloon" selected={selectedId===hap.id}
      dragMode={dragMode} onSelect={onSelect} onPositionChange={onPositionChange} onDragStart={()=>setDragging(true)} onDragEnd={()=>setDragging(false)} qkp={qkps[hap.id]} />)}
    <OrbitControls ref={orbitRef} makeDefault enabled={!dragging} target={[0, 6, 0]} minDistance={20}
      maxDistance={600} minPolarAngle={0.10} maxPolarAngle={Math.PI * 0.48}
      enableDamping dampingFactor={0.075} autoRotate={autoRotate && !dragging} autoRotateSpeed={0.32} />
  </>;
}

export default function Network3D(props) {
  return <div className="three-host">
    <Canvas camera={{ position: [67, 51, 79], fov: 43, near: 0.15, far: 1400 }}
      shadows dpr={[1, 1.75]} gl={{ antialias: true, alpha: false }}>
      <Scene {...props} />
    </Canvas>
  </div>;
}
