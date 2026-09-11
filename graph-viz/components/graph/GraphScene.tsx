"use client";

import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Line, Html, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { LineMaterial, OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { GraphEdgeSourceType } from "@/lib/api";
import { edgeOpacity, edgeWidth, type GraphPalette } from "@/lib/graph-visual";

const RECENT_MS = 12 * 86_400_000; // an edge younger than this at the viewed time reads as "recent"
const CURVE_SAMPLES = 18;
const FLOW_TRAIL = 4; // dots per featured edge — head + 3 tapering ghosts, reads as a comet not a bead
const FLOW_TRAIL_SPACING = 0.05; // phase gap between trail dots, in curve-fraction units
const FLOW_CAPACITY = 96 * FLOW_TRAIL; // shared pool of "data flowing" particles across featured edges
const FLOW_SPEED = 0.32;

// Idle "breathing" life: with nothing selected or hovered, a random node quietly pulses every few
// seconds so the graph reads as alive rather than inert until touched.
const PULSE_MIN_GAP = 2.2;
const PULSE_MAX_GAP = 4.4;
const PULSE_DURATION = 1.1;

let glowTexture: THREE.Texture | null = null;
// Soft radial falloff, generated once, tinted per-node via sprite/material color.
function getGlowTexture(): THREE.Texture {
  if (glowTexture) return glowTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, "rgba(255,255,255,0.95)");
  g.addColorStop(0.35, "rgba(255,255,255,0.45)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  glowTexture = new THREE.CanvasTexture(canvas);
  return glowTexture;
}

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
  /** Resolved theme colours — the scene re-skins when the workspace theme changes. */
  palette: GraphPalette;
  onHover: (id: string | null) => void;
  onSelect: (id: string | null) => void;
}

const tmp = new THREE.Vector3();
const tmpB = new THREE.Vector3();
const tmpFlow = new THREE.Vector3();
const ctrl = new THREE.Vector3();
const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3());
const colTmp = new THREE.Color();
const flowDummy = new THREE.Object3D();
const flowHide = new THREE.Object3D();
flowHide.scale.setScalar(0);
flowHide.updateMatrix();

function Scene({
  nodes,
  edges,
  selectedId,
  hoveredId,
  timeMs,
  reducedMotion,
  layoutKey,
  palette,
  onHover,
  onSelect,
}: SceneProps) {
  const { camera } = useThree();
  const colNeutral = useMemo(() => new THREE.Color(palette.edge), [palette.edge]);
  const colAccent = useMemo(() => new THREE.Color(palette.accent), [palette.accent]);
  const controls = useRef<OrbitControlsImpl>(null);

  const positions = useRef<THREE.Vector3[]>([]);
  const velocities = useRef<THREE.Vector3[]>([]);
  const nodeMeshes = useRef<(THREE.Mesh | null)[]>([]);
  const glowSprites = useRef<(THREE.Sprite | null)[]>([]);
  const edgeLines = useRef<(THREE.Object3D | null)[]>([]);
  const flowMesh = useRef<THREE.InstancedMesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);
  const born = useRef(0);
  const settleEnergy = useRef(1);
  const timeRef = useRef(timeMs);
  timeRef.current = timeMs;
  const pulse = useRef({ idx: -1, until: 0, next: PULSE_MIN_GAP });
  const glow = useMemo(() => (typeof document === "undefined" ? null : getGlowTexture()), []);

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

    // Idle life: pick a new random node to softly pulse every couple of seconds, but only while
    // nothing is already claiming attention — a real selection/hover always wins.
    const p = pulse.current;
    if (reducedMotion || selectedId || hoveredId) {
      p.idx = -1;
    } else if (born.current >= p.next && nodeMeshes.current.length > 0) {
      p.idx = Math.floor(Math.random() * nodeMeshes.current.length);
      p.until = born.current + PULSE_DURATION;
      p.next = p.until + PULSE_MIN_GAP + Math.random() * (PULSE_MAX_GAP - PULSE_MIN_GAP);
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

      // Idle breathing pulse envelope for whichever node the ambient-life timer picked (0 for
      // everyone else) — a gentle 0→1→0 rise/fall over PULSE_DURATION, never fighting a real
      // selection or hover since those suppress pulse.current.idx entirely above.
      const pulsing = i === p.idx && born.current < p.until;
      const pulsePhase = pulsing ? 1 - (p.until - born.current) / PULSE_DURATION : 0;
      const pulseEnv = pulsing ? Math.sin(Math.PI * THREE.MathUtils.clamp(pulsePhase, 0, 1)) : 0;

      const emphasis = isSel ? 1.55 : isHov ? 1.28 : 1 + pulseEnv * 0.22;
      const target = node.radius * emphasis * appear * (isPresent ? 1 : 0.5);
      mesh.scale.setScalar(THREE.MathUtils.lerp(mesh.scale.x, target, 0.18));

      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.opacity = THREE.MathUtils.lerp(mat.opacity, appear * focusDim * presence, 0.18);
      mat.emissiveIntensity = THREE.MathUtils.lerp(
        mat.emissiveIntensity,
        isSel ? 0.85 : isHov ? 0.5 : 0.12 + pulseEnv * 0.4,
        0.18,
      );
      // Selected node picks up a faint signal-colour rim; everyone else stays their family hue.
      (mat.emissive as THREE.Color).lerp(isSel ? colAccent : (mesh.userData.base as THREE.Color), 0.15);

      // Soft additive halo behind the node — a cheap stand-in for bloom that still reads as glow.
      const sprite = glowSprites.current[i];
      if (sprite) {
        sprite.position.copy(pos[i]);
        const haloScale =
          node.radius * emphasis * appear * (isPresent ? 1 : 0.5) * (isSel ? 4.4 : isHov ? 3.8 : 3.1 + pulseEnv * 1.4);
        sprite.scale.setScalar(THREE.MathUtils.lerp(sprite.scale.x, haloScale, 0.16));
        const smat = sprite.material as THREE.SpriteMaterial;
        const haloOpacity = appear * focusDim * presence * (isSel ? 0.6 : isHov ? 0.42 : 0.2 + pulseEnv * 0.35);
        smat.opacity = THREE.MathUtils.lerp(smat.opacity, haloOpacity, 0.16);
      }
    }

    // The selection ring: a pulsing halo of accent light orbiting the chosen node.
    if (ringRef.current) {
      const idx = selectedId ? nodes.findIndex((n) => n.id === selectedId) : -1;
      if (idx >= 0 && pos[idx]) {
        ringRef.current.visible = true;
        ringRef.current.position.copy(pos[idx]);
        const ringPulse = 1 + (reducedMotion ? 0 : 0.14 * Math.sin(born.current * 3.1));
        const ringScale = nodes[idx].radius * 2.1 * ringPulse;
        ringRef.current.scale.setScalar(ringScale);
        ringRef.current.rotation.z += reducedMotion ? 0 : dt * 0.5;
        ringRef.current.rotation.x = Math.PI / 2.2;
        const rmat = ringRef.current.material as THREE.MeshBasicMaterial;
        rmat.opacity = THREE.MathUtils.lerp(rmat.opacity, 0.5 + 0.3 * Math.sin(born.current * 3.1), 0.2);
      } else {
        ringRef.current.visible = false;
      }
    }

    // Curved, temporally-aware edges. A bounded pool of particles rides the featured ones so
    // relationships read as live signal flow, not static wiring.
    let flowCount = 0;
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
        material: LineMaterial & { opacity: number; color: THREE.Color; dashed?: boolean };
      };
      obj.geometry.setPositions(pts);
      obj.computeLineDistances?.();

      const active = edgePresent(e, t);
      const recent = active && t - e.validFrom < RECENT_MS && t - e.validFrom >= 0;
      const isSelEdge =
        !!selectedId && (nodes[e.from].id === selectedId || nodes[e.to].id === selectedId);
      const dimmed =
        !!selectedId &&
        nodes[e.from].id !== selectedId &&
        nodes[e.to].id !== selectedId &&
        !(neighbors.has(nodes[e.from].id) && neighbors.has(nodes[e.to].id));
      const featured = active && !reducedMotion && (recent || isSelEdge);
      const targetOpacity = active ? edgeOpacity(e.confidence, dimmed) * (featured ? 1.15 : 1) : 0;
      obj.material.opacity = THREE.MathUtils.lerp(obj.material.opacity, targetOpacity, 0.16);
      colTmp.copy(recent || isSelEdge ? colAccent : colNeutral);
      obj.material.color.lerp(colTmp, 0.12);
      const widthTarget =
        edgeWidth(e.confidence) * (featured ? 1.5 + 0.25 * Math.sin(born.current * 3 + i) : 1);
      obj.material.linewidth = THREE.MathUtils.lerp(obj.material.linewidth, widthTarget, 0.15);

      if (featured && flowMesh.current && flowCount < FLOW_CAPACITY) {
        // A short comet — a bright head plus tapering ghost dots trailing behind it along the same
        // curve — instead of one bead sliding along the wire. Reads as motion, not a static marker.
        const headPhase = (((born.current * FLOW_SPEED + i * 0.173) % 1) + 1) % 1;
        const shimmer = 0.15 + 0.06 * Math.sin(born.current * 6 + i * 1.7);
        for (let k = 0; k < FLOW_TRAIL && flowCount < FLOW_CAPACITY; k++) {
          const trailPhase = (((headPhase - k * FLOW_TRAIL_SPACING) % 1) + 1) % 1;
          curve.getPoint(trailPhase, tmpFlow);
          flowDummy.position.copy(tmpFlow);
          const falloff = 1 - k / FLOW_TRAIL; // 1 at the head, tapering to near-zero at the tail
          flowDummy.scale.setScalar(shimmer * falloff * falloff);
          flowDummy.updateMatrix();
          flowMesh.current.setMatrixAt(flowCount, flowDummy.matrix);
          flowCount++;
        }
      }
    }

    if (flowMesh.current) {
      for (let k = flowCount; k < FLOW_CAPACITY; k++) {
        flowMesh.current.setMatrixAt(k, flowHide.matrix);
      }
      flowMesh.current.instanceMatrix.needsUpdate = true;
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
      <ambientLight intensity={0.95} />
      <directionalLight position={[10, 14, 8]} intensity={0.7} />
      <directionalLight position={[-8, -6, -10]} intensity={0.24} color="#c7d2fe" />
      <pointLight position={[0, 4, 14]} intensity={0.5} color={palette.accentSoft} distance={40} />

      {/* Halos render first, additively, so they sit as soft light behind the crisp node spheres. */}
      {glow &&
        nodes.map((node, i) => (
          <sprite key={`glow-${node.id}`} ref={(el) => { glowSprites.current[i] = el; }} scale={0}>
            <spriteMaterial
              map={glow}
              color={node.color}
              transparent
              opacity={0}
              depthWrite={false}
              blending={THREE.AdditiveBlending}
            />
          </sprite>
        ))}

      {edges.map((e, i) => (
        <Line
          key={i}
          ref={(el: THREE.Object3D | null) => {
            edgeLines.current[i] = el;
          }}
          points={Array.from({ length: CURVE_SAMPLES }, () => [0, 0, 0] as [number, number, number])}
          color={palette.edge}
          lineWidth={edgeWidth(e.confidence)}
          transparent
          opacity={0}
          dashed={e.source === "llm_inferred"}
          dashSize={0.55}
          gapSize={0.4}
        />
      ))}

      {/* A bounded pool of instanced particles rides featured edges — recent changes and the
          selected node's relationships glow and visibly travel, so the graph reads as live. */}
      <instancedMesh ref={flowMesh} args={[undefined, undefined, FLOW_CAPACITY]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial
          color={palette.accentSoft}
          transparent
          opacity={0.85}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </instancedMesh>

      {/* Pulsing accent ring around the selected node — the one place motion carries meaning. */}
      <mesh ref={ringRef} visible={false}>
        <torusGeometry args={[1, 0.045, 12, 56]} />
        <meshBasicMaterial color={palette.accent} transparent opacity={0} depthWrite={false} />
      </mesh>

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
          <sphereGeometry args={[1, 40, 40]} />
          <meshStandardMaterial
            color={node.color}
            emissive={node.color}
            emissiveIntensity={0.16}
            roughness={0.22}
            metalness={0.12}
            envMapIntensity={0.6}
            transparent
            opacity={0}
          />
          {(node.id === hoveredId || node.id === selectedId) && (
            <Html center distanceFactor={26} zIndexRange={[10, 0]} style={{ pointerEvents: "none" }}>
              <div
                className="translate-y-[-2.4em] whitespace-nowrap rounded-md border bg-panel/95 px-2 py-1 text-[11px] font-medium text-ink shadow-md backdrop-blur-sm"
                style={{
                  borderColor: node.id === selectedId ? "var(--color-signal)" : "var(--color-line)",
                  boxShadow:
                    node.id === selectedId
                      ? "0 0 0 1px color-mix(in srgb, var(--color-signal) 14%, transparent), 0 8px 20px -6px color-mix(in srgb, var(--color-signal) 34%, transparent)"
                      : undefined,
                }}
              >
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
      <fog attach="fog" args={[props.palette.fog, 34, 72]} />
      <Scene {...props} />
    </Canvas>
  );
}
