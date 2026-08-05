"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Line, Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { GraphEdgeSourceType } from "@/lib/api";
import { EDGE_NEUTRAL, STATE_ACCENT, edgeOpacity, edgeWidth } from "@/lib/graph-visual";

const RECENT_MS = 12 * 86_400_000; // an edge younger than this at the viewed time reads as "recent"
const CURVE_SAMPLES = 18;

export interface SceneNode {
  id: string;
  color: string;
  radius: number;
  label: string;
  seed: [number, number, number];
}

export interface SceneEdge {
  from: number;
  to: number;
  confidence: number;
  source: GraphEdgeSourceType;
  validFrom: number;
  validTo: number | null;
}

interface SceneProps {
  nodes: SceneNode[];
  edges: SceneEdge[];
  selectedId: string | null;
  hoveredId: string | null;
  timeMs: number;
  reducedMotion: boolean;
  layoutKey: string;
  onHover: (id: string | null) => void;
  onSelect: (id: string | null) => void;
}

const tmp = new THREE.Vector3();
const tmpB = new THREE.Vector3();
const ctrl = new THREE.Vector3();
const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3());
const colNeutral = new THREE.Color(EDGE_NEUTRAL);
const colAccent = new THREE.Color(STATE_ACCENT);
const colTmp = new THREE.Color();

function Scene({
  nodes,
  edges,
  selectedId,
  hoveredId,
  timeMs,
  reducedMotion,
  layoutKey,
  onHover,
  onSelect,
}: SceneProps) {
  const { camera } = useThree();
  const controls = useRef<OrbitControlsImpl>(null);

  const positions = useRef<THREE.Vector3[]>([]);
  const velocities = useRef<THREE.Vector3[]>([]);
  const nodeMeshes = useRef<(THREE.Mesh | null)[]>([]);
  const edgeLines = useRef<(THREE.Object3D | null)[]>([]);
  const born = useRef(0);
  const settleEnergy = useRef(1);
  const timeRef = useRef(timeMs);
  timeRef.current = timeMs;

  // Neighbor set of the selection, at the current time, for focus dimming.
  const neighbors = useMemo(() => {
    const set = new Set<string>();
    if (!selectedId) return set;
    for (const e of edges) {
      const a = nodes[e.from]?.id;
      const b = nodes[e.to]?.id;
      if (a === selectedId && b) set.add(b);
      else if (b === selectedId && a) set.add(a);
    }
    return set;
  }, [selectedId, edges, nodes]);

  useMemo(() => {
    positions.current = nodes.map((n) => new THREE.Vector3(...n.seed));
    velocities.current = nodes.map(() => new THREE.Vector3());
    born.current = 0;
    settleEnergy.current = 1;
    if (reducedMotion) for (let i = 0; i < 280; i++) step(1 / 60);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey, reducedMotion]);

  function edgePresent(e: SceneEdge, t: number) {
    return e.validFrom <= t && (e.validTo == null || e.validTo > t);
  }

  function step(dt: number) {
    const pos = positions.current;
    const vel = velocities.current;
    const n = pos.length;
    const kRep = 34;
    const kSpring = 0.08;
    const springLen = 7;
    const gravity = 0.02;
    const damping = 0.86;

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        tmp.subVectors(pos[i], pos[j]);
        let d2 = tmp.lengthSq();
        if (d2 < 0.01) {
          tmp.set(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5);
          d2 = 0.01;
        }
        tmp.normalize().multiplyScalar((kRep / d2) * dt);
        vel[i].add(tmp);
        vel[j].sub(tmp);
      }
    }
    for (const e of edges) {
      tmpB.subVectors(pos[e.to], pos[e.from]);
      const dist = tmpB.length() || 0.01;
      tmpB.normalize().multiplyScalar((dist - springLen) * kSpring * dt);
      vel[e.from].add(tmpB);
      vel[e.to].sub(tmpB);
    }
    let energy = 0;
    for (let i = 0; i < n; i++) {
      tmp.copy(pos[i]).multiplyScalar(-gravity * dt);
      vel[i].add(tmp);
      vel[i].multiplyScalar(damping);
      pos[i].addScaledVector(vel[i], dt * 60);
      energy += vel[i].lengthSq();
    }
    settleEnergy.current = n > 0 ? energy / n : 0;
  }

  useFrame((_, rawDelta) => {
    const dt = Math.min(rawDelta, 1 / 30);
    const t = timeRef.current;
    if (!reducedMotion && settleEnergy.current > 0.0006) step(dt);
    born.current += rawDelta;
    const pos = positions.current;

    // Node presence at time t: a node exists once one of its relationships is active.
    const present = new Set<string>();
    for (const e of edges) {
      if (edgePresent(e, t)) {
        present.add(nodes[e.from].id);
        present.add(nodes[e.to].id);
      }
    }

    for (let i = 0; i < nodeMeshes.current.length; i++) {
      const mesh = nodeMeshes.current[i];
      if (!mesh || !pos[i]) continue;
      mesh.position.copy(pos[i]);

      const delay = reducedMotion ? 0 : i * 0.03;
      const bt = THREE.MathUtils.clamp((born.current - delay) / 0.55, 0, 1);
      const appear = reducedMotion ? 1 : bt * bt * (3 - 2 * bt);

      const node = nodes[i];
      const isSel = node.id === selectedId;
      const isHov = node.id === hoveredId;
      const isNeighbor = neighbors.has(node.id);
      const isPresent = present.has(node.id);
      const focusDim = selectedId && !isSel && !isNeighbor ? 0.24 : 1;
      const presence = isPresent ? 1 : 0.09;
      const emphasis = isSel ? 1.55 : isHov ? 1.28 : 1;
      const target = node.radius * emphasis * appear * (isPresent ? 1 : 0.5);
      mesh.scale.setScalar(THREE.MathUtils.lerp(mesh.scale.x, target, 0.18));

      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.opacity = THREE.MathUtils.lerp(mat.opacity, appear * focusDim * presence, 0.18);
      mat.emissiveIntensity = THREE.MathUtils.lerp(
        mat.emissiveIntensity,
        isSel ? 0.85 : isHov ? 0.5 : 0.12,
        0.18,
      );
      // Selected node picks up a faint teal rim; everyone else stays their family hue.
      (mat.emissive as THREE.Color).lerp(isSel ? colAccent : (mesh.userData.base as THREE.Color), 0.15);
    }

    // Curved, temporally-aware edges.
    for (let i = 0; i < edges.length; i++) {
      const line = edgeLines.current[i];
      if (!line) continue;
      const e = edges[i];
      const a = pos[e.from];
      const b = pos[e.to];
      if (!a || !b) continue;

      // Gentle outward bow so bidirectional edges don't overlap.
      ctrl.addVectors(a, b).multiplyScalar(0.5);
      const bow = ctrl.length() * 0.18 + a.distanceTo(b) * 0.08;
      tmp.copy(ctrl).normalize().multiplyScalar(bow);
      ctrl.add(tmp);
      curve.v0.copy(a);
      curve.v1.copy(ctrl);
      curve.v2.copy(b);
      const pts: number[] = [];
      for (let s = 0; s < CURVE_SAMPLES; s++) {
        curve.getPoint(s / (CURVE_SAMPLES - 1), tmpB);
        pts.push(tmpB.x, tmpB.y, tmpB.z);
      }
      const obj = line as unknown as {
        geometry: { setPositions: (n: number[]) => void };
        computeLineDistances?: () => void;
        material: THREE.Material & { opacity: number; color: THREE.Color; dashed?: boolean };
      };
      obj.geometry.setPositions(pts);
      obj.computeLineDistances?.();

      const active = edgePresent(e, t);
      const recent = active && t - e.validFrom < RECENT_MS && t - e.validFrom >= 0;
      const dimmed =
        !!selectedId &&
        nodes[e.from].id !== selectedId &&
        nodes[e.to].id !== selectedId &&
        !(neighbors.has(nodes[e.from].id) && neighbors.has(nodes[e.to].id));
      const targetOpacity = active ? edgeOpacity(e.confidence, dimmed) : 0;
      obj.material.opacity = THREE.MathUtils.lerp(obj.material.opacity, targetOpacity, 0.16);
      colTmp.copy(recent ? colAccent : colNeutral);
      obj.material.color.lerp(colTmp, 0.12);
    }

    const c = controls.current;
    if (c) {
      if (selectedId) {
        const idx = nodes.findIndex((n) => n.id === selectedId);
        if (idx >= 0 && pos[idx]) {
          c.target.lerp(pos[idx], 0.08);
          tmp.copy(pos[idx]).add(tmpB.set(5.5, 3.5, 11));
          camera.position.lerp(tmp, reducedMotion ? 1 : 0.05);
        }
      } else {
        c.target.lerp(tmpB.set(0, 0, 0), 0.05);
      }
      c.update();
    }
  });

  return (
    <>
      <ambientLight intensity={0.9} />
      <directionalLight position={[10, 14, 8]} intensity={0.65} />
      <directionalLight position={[-8, -6, -10]} intensity={0.22} />

      {edges.map((e, i) => (
        <Line
          key={i}
          ref={(el: THREE.Object3D | null) => {
            edgeLines.current[i] = el;
          }}
          points={Array.from({ length: CURVE_SAMPLES }, () => [0, 0, 0] as [number, number, number])}
          color={EDGE_NEUTRAL}
          lineWidth={edgeWidth(e.confidence)}
          transparent
          opacity={0}
          dashed={e.source === "llm_inferred"}
          dashSize={0.55}
          gapSize={0.4}
        />
      ))}

      {nodes.map((node, i) => (
        <mesh
          key={node.id}
          ref={(el) => {
            nodeMeshes.current[i] = el;
            if (el) el.userData.base = new THREE.Color(node.color);
          }}
          scale={0}
          onPointerOver={(ev: ThreeEvent<PointerEvent>) => {
            ev.stopPropagation();
            onHover(node.id);
            document.body.style.cursor = "pointer";
          }}
          onPointerOut={() => {
            onHover(null);
            document.body.style.cursor = "auto";
          }}
          onClick={(ev: ThreeEvent<MouseEvent>) => {
            ev.stopPropagation();
            onSelect(node.id === selectedId ? null : node.id);
          }}
        >
          <sphereGeometry args={[1, 32, 32]} />
          <meshStandardMaterial
            color={node.color}
            emissive={node.color}
            emissiveIntensity={0.12}
            roughness={0.32}
            metalness={0.04}
            transparent
            opacity={0}
          />
          {(node.id === hoveredId || node.id === selectedId) && (
            <Html center distanceFactor={26} zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
              <div className="translate-y-[-2.4em] whitespace-nowrap rounded-md border border-line bg-panel/95 px-2 py-1 text-[11px] font-medium text-ink shadow-sm backdrop-blur-sm">
                {node.label}
              </div>
            </Html>
          )}
        </mesh>
      ))}

      <OrbitControls
        ref={controls}
        makeDefault
        enableDamping
        dampingFactor={0.08}
        rotateSpeed={0.6}
        minDistance={6}
        maxDistance={60}
        autoRotate={!reducedMotion && !selectedId && !hoveredId}
        autoRotateSpeed={0.32}
      />
    </>
  );
}

export function GraphScene(props: SceneProps) {
  return (
    <Canvas
      camera={{ position: [0, 2, 26], fov: 50 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      onPointerMissed={() => props.onSelect(null)}
    >
      <fog attach="fog" args={["#f2f1ec", 36, 74]} />
      <Scene {...props} />
    </Canvas>
  );
}
