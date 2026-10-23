import React, { useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Grid, Html, Line, OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { CENTER, fromWorld, position3D } from '../lib/geo';

const CYAN = '#56e9dc';
const GOLD = '#ffd09a';

function Badge({ title, subtitle, kind, active }) {
  return <div className={`world-label ${kind} ${active ? 'is-selected' : ''}`}>
    <span className="world-label-dot" />
    <span><strong>{title}</strong>{subtitle && <small>{subtitle}</small>}</span>
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

function ModelNode({ item, type, selected, dragMode, onSelect, onPositionChange, onDragStart, onDragEnd }) {
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
    {/* Compact label offset to the right, with a leader that avoids the model. */}
    <Line points={isBalloon ? [[2.0, 7.45, 0], [3.5, 8.45, 0]] : [[1.4, 3.6, 0], [2.9, 4.65, 0]]}
      color={isBalloon ? GOLD : CYAN} transparent opacity={0.58} lineWidth={1} />
    <Html position={isBalloon ? [3.5, 8.45, 0] : [2.9, 4.65, 0]}
      center={false} distanceFactor={68} transform={false}
      style={{ pointerEvents: 'none', userSelect: 'none' }}>
      <div style={{ transform: 'translate(7px, -50%)' }}>
        <Badge title={item.name} subtitle={isBalloon ? `${item.altitude_km} km altitude` : 'Ground station'}
          kind={type} active={selected} />
      </div>
    </Html>
  </group>;
}

function Cloud({ weather, selected, onSelect }) {
  const x = position3D(weather)[0], z = position3D(weather)[2];
  return <group position={[x, 0, z]} onClick={(e) => { e.stopPropagation(); onSelect(weather.id); }}>
    <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[weather.radius_km, 48]} />
      <meshBasicMaterial color="#aa8bff" transparent opacity={0.08} depthWrite={false} side={THREE.DoubleSide} /></mesh>
    <mesh position={[0, 0.035, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[weather.radius_km - 0.15, weather.radius_km, 64]} />
      <meshBasicMaterial color={selected ? '#fff' : '#b4a3ff'} transparent opacity={0.64} side={THREE.DoubleSide} /></mesh>
    {[[-3.8, 8.5, 0, 4], [0.5, 9.6, 0, 5.4], [4.4, 8.1, 1.6, 3.9], [1, 8.1, -3.1, 4]].map(([xx, yy, zz, s], i) =>
      <mesh key={i} position={[xx, yy, zz]} scale={[s * 1.2, s * 0.55, s]}>
        <sphereGeometry args={[1, 18, 12]} />
        <meshStandardMaterial color="#8b9fc1" transparent opacity={0.55} depthWrite={false} />
      </mesh>)}
    <Html position={[0, 13, 0]} center distanceFactor={80} style={{pointerEvents: 'none'}}>
      <div className="weather-label">☁ {weather.attenuation_db} dB · {weather.radius_km} km</div>
    </Html>
  </group>;
}

function Scene({ scenario, frame, selectedId, onSelect, dragMode, onPositionChange, autoRotate }) {
  const [dragging, setDragging] = useState(false);
  const links = frame?.links || [];
  const coords = Object.fromEntries([...scenario.ground_stations, ...scenario.balloons].map(n => [n.id, position3D(n)]));
  return <>
    <color attach="background" args={['#0a1826']} />
    <fog attach="fog" args={['#0a1826', 108, 205]} />
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
    {scenario.weather_regions.map(w => <Cloud key={w.id} weather={w} selected={selectedId === w.id} onSelect={onSelect} />)}
    {links.map(link => {
      const a = coords[link.source], b = coords[link.target];
      if (!a || !b) return null;
      const isHap = id => scenario.balloons.some(h => h.id === id);
      const endpoints = [
        [a[0], a[1] + (isHap(link.source) ? -0.25 : 2.5), a[2]],
        [b[0], b[1] + (isHap(link.target) ? -0.25 : 2.5), b[2]],
      ];
      return <group key={link.id}>
        <Line points={endpoints}
          color={link.active ? '#4de5d6' : '#4d687a'} lineWidth={link.active ? 2.5 : 1.1}
          transparent opacity={link.active ? 0.88 : 0.24} />
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
      dragMode={dragMode} onSelect={onSelect} onPositionChange={onPositionChange} onDragStart={()=>setDragging(true)} onDragEnd={()=>setDragging(false)} />)}
    {scenario.balloons.map(hap => <ModelNode key={hap.id} item={hap} type="balloon" selected={selectedId===hap.id}
      dragMode={dragMode} onSelect={onSelect} onPositionChange={onPositionChange} onDragStart={()=>setDragging(true)} onDragEnd={()=>setDragging(false)} />)}
    <OrbitControls makeDefault enabled={!dragging} target={[0, 6, 0]} minDistance={20}
      maxDistance={185} minPolarAngle={0.10} maxPolarAngle={Math.PI * 0.48}
      enableDamping dampingFactor={0.075} autoRotate={autoRotate && !dragging} autoRotateSpeed={0.32} />
  </>;
}

export default function Network3D(props) {
  return <div className="three-host">
    <Canvas camera={{ position: [67, 51, 79], fov: 43, near: 0.15, far: 420 }}
      shadows dpr={[1, 1.75]} gl={{ antialias: true, alpha: false }}>
      <Scene {...props} />
    </Canvas>
  </div>;
}
