import { useMemo, useState } from "react";

// ผังตรรกะสด: node และ edge มาจาก backend/app/engine/flow.py (ADR-0002)
// ไฟล์นี้กำหนดแค่ตำแหน่งบนจอ เส้นที่วนกลับไปจุดเริ่ม (ตอบใหม่ / ข้อถัดไป) แสดงเป็นสัญลักษณ์ ↩ ที่ node ต้นทาง
// เพื่อไม่ให้มีเส้นยาวพาดทับกันทั้งผัง

export interface FlowNode {
  id: string;
  label: string;
  kind: "position" | "gate" | "step" | "event";
  lane: string;
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface FlowPosition {
  code: string;
  kind: string;
  position: string;
  path: string;
  item: string | null;
  last_edges: string[];
  last_rule?: string | null;
}

const COL = [84, 268, 452, 636, 820, 1004, 1188, 1372];
const ROW = [56, 156, 256, 356, 456, 556];
const W = 150;
const H = 44;
const GATE_H = 50;
const LANE_X = [1468, 1500, 1532];
const WIDTH = 1566;
const HEIGHT = 646;

const LAYOUT: Record<string, [number, number]> = {
  ANSWERING: [0, 2],
  E_SUBMIT: [1, 2],
  G_CLEAN: [2, 2],
  G1: [3, 2],
  G_MASTERY: [4, 1],
  ISOMORPHIC_TEST: [4, 0],
  G_FINISH: [5, 1],
  G_PATH: [5, 0],
  COMPLETED: [6, 1],
  SESSION_ENDED: [6, 0],
  G_ISOCHK: [4, 2],
  G2: [5, 2],
  G_DIAG: [6, 2],
  G3: [7, 2],
  RAPID_GUESS_LOCK: [5, 3],
  DELIBERATE_DELAY: [7, 3],
  HINT_L1: [6, 3],
  HINT_L2: [6, 4],
  G_TREND: [7, 5],
  HINT_L3: [6, 5],
  IMPASSE: [4, 5],
  G_ROUNDS: [3, 5],
  REMEDIAL: [2, 5],
  CIRCUIT_BREAKER: [1, 5],
  WALKTHROUGH: [0, 5],
  STAGNATION_DEADLOCK: [3, 4],
  IDLE_PAUSE: [0, 3],
  CHOOSING_PATH: [1, 3],
  SAFETY_STOP: [2, 3],
  // Gem (ADR-0003)
  LIVE_GEN: [7, 0],
  AI_OUTAGE: [7, 1],
  TEACHER_REVIEW: [1, 4],
};

interface Box {
  x: number;
  y: number;
  h: number;
}

type Pt = [number, number];

// เส้นที่ต้องอ้อมทางขวาหรือล่าง ไม่ให้ทับ node อื่น ป้ายของเส้นเหล่านี้วางในช่องทางเดินเอง
const ROUTE_LABELS: Record<string, Pt> = {
  e_g3_2: [LANE_X[0], 316],
  e_g3_3: [LANE_X[1], 396],
};

const ROUTES: Record<string, (s: Box, t: Box) => Pt[]> = {
  e_g3_2: (s, t) => [[s.x + W / 2, s.y - 8], [LANE_X[0], s.y - 8], [LANE_X[0], t.y], [t.x + W / 2, t.y]],
  e_g3_3: (s, t) => [[s.x + W / 2, s.y], [LANE_X[1], s.y], [LANE_X[1], t.y], [t.x + W / 2, t.y]],
  // สองเส้นที่เข้า Impasse วิ่งใต้แถวล่างแล้วขึ้นทางคอลัมน์ที่ว่าง เข้าทางขวา ไม่ผ่านชิปนักเรียน
  e_g3_4: (s, t) => [[s.x + W / 2, s.y + 8], [LANE_X[2], s.y + 8], [LANE_X[2], 630], [COL[5] + 10, 630], [COL[5] + 10, t.y + 8], [t.x + W / 2, t.y + 8]],
  e_trend_yes: (s, t) => [[s.x, s.y + GATE_H / 2], [s.x, 612], [COL[5] - 10, 612], [COL[5] - 10, t.y - 8], [t.x + W / 2, t.y - 8]],
  e_rounds_root: (s, t) => [[s.x, s.y + GATE_H / 2], [s.x, 628], [t.x + W / 2 - 8, 628], [t.x + W / 2 - 8, t.y + H / 2]],
  // ไปสร้างโจทย์สดวิ่งเหนือแถวบนสุด ไม่ผ่านกล่องจบ Session
  e_path_live: (s, t) => [[s.x, s.y - s.h / 2], [s.x, 12], [t.x, 12], [t.x, t.y - t.h / 2]],
  // ไปและกลับระหว่างสร้างโจทย์สดกับ AI ขัดข้อง: สองเส้นขนานกัน
  e_live_fail: (s, t) => [[s.x + 22, s.y + s.h / 2], [t.x + 22, t.y - t.h / 2]],
  e_outage_retry: (s, t) => [[s.x - 22, s.y - s.h / 2], [t.x - 22, t.y + t.h / 2]],
};

// เส้นที่วนกลับ: แสดงเป็นสัญลักษณ์ ↩ ที่ต้นทางแทนการลากเส้น
const RETURN_TARGETS = new Set(["ANSWERING", "E_SUBMIT"]);
const RETURN_EDGES = new Set([
  "e_iso_retry",
  "e_remedial_next",
  "e_walk_round",
  "e_hint_button",
  "e_distress",
  "e_choose_on",
  "e_choose_stop",
]);

function boxOf(id: string, nodes: Map<string, FlowNode>): Box | null {
  const at = LAYOUT[id];
  if (!at) return null;
  return { x: COL[at[0]], y: ROW[at[1]], h: nodes.get(id)?.kind === "gate" ? GATE_H : H };
}

// จุดที่เส้นจากจุดศูนย์กลางตัดขอบกล่อง
function border(from: Box, to: Box): Pt {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (dx === 0 && dy === 0) return [from.x, from.y];
  const scale = Math.min(W / 2 / Math.abs(dx || 1e-9), from.h / 2 / Math.abs(dy || 1e-9));
  return [from.x + dx * scale, from.y + dy * scale];
}

function pathFrom(points: Pt[]) {
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1];
    const [x, y] = points[i];
    const [nx, ny] = points[i + 1];
    const r = 10;
    const inX = x - Math.sign(x - px) * Math.min(r, Math.abs(x - px) / 2);
    const inY = y - Math.sign(y - py) * Math.min(r, Math.abs(y - py) / 2);
    const outX = x + Math.sign(nx - x) * Math.min(r, Math.abs(nx - x) / 2);
    const outY = y + Math.sign(ny - y) * Math.min(r, Math.abs(ny - y) / 2);
    d += ` L${inX},${inY} Q${x},${y} ${outX},${outY}`;
  }
  const last = points[points.length - 1];
  return `${d} L${last[0]},${last[1]}`;
}

// ความกว้างป้ายโดยประมาณ: สระและวรรณยุกต์ภาษาไทยที่อยู่บนล่างไม่กินที่
function labelWidth(text: string) {
  const visible = text.replace(/[\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]/g, "");
  return visible.length * 6.4 + 12;
}

// ตำแหน่งป้ายกำกับ: กลางช่วงที่ยาวที่สุดของเส้น
function labelPoint(points: Pt[]): Pt {
  let best = 0;
  let bestLength = -1;
  for (let i = 0; i < points.length - 1; i++) {
    const length = Math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]);
    if (length > bestLength) {
      bestLength = length;
      best = i;
    }
  }
  return [(points[best][0] + points[best + 1][0]) / 2, (points[best][1] + points[best + 1][1]) / 2];
}

export default function FlowMap({
  nodes,
  edges,
  positions,
  selectedNode,
  selectedStudent,
  onSelectNode,
  onSelectStudent,
  highlightEdges,
  focusLane,
}: {
  nodes: FlowNode[];
  edges: FlowEdge[];
  positions: FlowPosition[];
  selectedNode?: string | null;
  selectedStudent?: string | null;
  onSelectNode?: (id: string) => void;
  onSelectStudent?: (code: string) => void;
  // เส้นที่จะเน้นแทนเส้นทางล่าสุดของนักเรียนที่เลือก เช่น เส้นทางของเหตุการณ์ในอดีต
  highlightEdges?: string[];
  // กลุ่มที่กำลังดูคำอธิบาย: กล่องและเส้นของกลุ่มอื่นจะจางลง
  focusLane?: string | null;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const isReturn = (e: FlowEdge) =>
    (RETURN_TARGETS.has(e.target) && !(e.source === "ANSWERING" && e.target === "E_SUBMIT")) || RETURN_EDGES.has(e.id);
  const drawn = edges.filter((e) => LAYOUT[e.source] && LAYOUT[e.target] && !isReturn(e) && e.source !== e.target);
  const returnsBySource = useMemo(() => {
    const map = new Map<string, FlowEdge[]>();
    for (const e of edges) if (isReturn(e)) map.set(e.source, [...(map.get(e.source) ?? []), e]);
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edges]);

  const byNode = useMemo(() => {
    const map = new Map<string, FlowPosition[]>();
    for (const p of positions) map.set(p.position, [...(map.get(p.position) ?? []), p]);
    for (const list of map.values()) list.sort((a, b) => (a.kind === "real" ? -1 : 0) - (b.kind === "real" ? -1 : 0));
    return map;
  }, [positions]);

  const selected = positions.find((p) => p.code === selectedStudent);
  const activeEdges = new Set(highlightEdges ?? selected?.last_edges ?? []);
  const inFocus = (id: string) => !focusLane || nodeMap.get(id)?.lane === focusLane;
  const activeReturn = new Set(edges.filter((e) => activeEdges.has(e.id) && isReturn(e)).map((e) => e.source));

  return (
    <div className={focusLane ? "flowmap has-focus" : "flowmap"}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="ผังตรรกะของระบบ พร้อมตำแหน่งนักเรียนแต่ละคน">
        <defs>
          <marker id="fm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arrow-head" />
          </marker>
          <marker id="fm-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arrow-head-on" />
          </marker>
        </defs>

        {drawn.map((edge) => {
          const s = boxOf(edge.source, nodeMap);
          const t = boxOf(edge.target, nodeMap);
          if (!s || !t) return null;
          const route = ROUTES[edge.id];
          const points: Pt[] = route ? route(s, t) : [border(s, t), border(t, s)];
          const on = activeEdges.has(edge.id);
          const fromGate = nodeMap.get(edge.source)?.kind === "gate";
          const showLabel = edge.label && (fromGate || hover === edge.id || on);
          const width = labelWidth(edge.label);
          const [lx, baseY] = ROUTE_LABELS[edge.id] ?? labelPoint(points);
          // ป้ายกว้างกว่าช่องระหว่างกล่องที่อยู่แถวเดียวกัน: ยกขึ้นไปไว้เหนือกล่อง
          const cramped = points.length === 2 && Math.abs(points[0][1] - points[1][1]) < 1 && width > Math.abs(points[1][0] - points[0][0]) - 4;
          const ly = cramped ? baseY - 34 : baseY;
          const d = pathFrom(points);
          return (
            <g key={edge.id} className={`edge ${on ? "edge-on" : ""} ${inFocus(edge.source) || inFocus(edge.target) ? "" : "is-dim"}`}>
              <path d={d} markerEnd={on ? "url(#fm-arrow-on)" : "url(#fm-arrow)"} />
              {showLabel && (
                <g className="edge-label">
                  <rect x={lx - width / 2} y={ly - 10} width={width} height={20} rx={7} />
                  <text x={lx} y={ly + 4} textAnchor="middle">
                    {edge.label}
                  </text>
                </g>
              )}
              <path d={d} className="edge-hit" onMouseEnter={() => setHover(edge.id)} onMouseLeave={() => setHover(null)}>
                <title>{edge.label || `${edge.source} → ${edge.target}`}</title>
              </path>
            </g>
          );
        })}

        {nodes.map((node) => {
          const box = boxOf(node.id, nodeMap);
          if (!box) return null;
          const lines = node.label.split("\n");
          const students = byNode.get(node.id) ?? [];
          const returns = returnsBySource.get(node.id) ?? [];
          const chipY = box.h + 6;
          const classes = [
            "fnode",
            `fnode-${node.kind}`,
            `lane-${node.lane}`,
            selectedNode === node.id ? "is-selected" : "",
            selected?.position === node.id ? "has-student" : "",
            students.length ? "occupied" : "",
            inFocus(node.id) ? "" : "is-dim",
          ].join(" ");
          return (
            <g
              key={node.id}
              className={classes}
              transform={`translate(${box.x - W / 2}, ${box.y - box.h / 2})`}
              onClick={() => onSelectNode?.(node.id)}
              role="button"
              tabIndex={0}
              aria-label={`${lines.join(" ")} มีนักเรียน ${students.length} คน`}
              onKeyDown={(e) => e.key === "Enter" && onSelectNode?.(node.id)}
            >
              <rect width={W} height={box.h} rx={node.kind === "gate" ? 14 : 11} className="fnode-box" />
              {node.kind === "gate" ? (
                <rect x={9} y={box.h / 2 - 3.5} width={7} height={7} transform={`rotate(45 12.5 ${box.h / 2})`} className="fnode-mark" />
              ) : (
                <circle cx={12.5} cy={box.h / 2} r={3.5} className="fnode-mark" />
              )}
              <text x={W / 2 + 5} y={box.h / 2 - (lines.length - 1) * 7.5 + 4.5} textAnchor="middle" className="fnode-text">
                {lines.map((line, i) => (
                  <tspan key={i} x={W / 2 + 5} dy={i === 0 ? 0 : 15}>
                    {line}
                  </tspan>
                ))}
              </text>
              {returns.length > 0 && (
                <g className={activeReturn.has(node.id) ? "return-mark on" : "return-mark"} transform={`translate(${W - 4}, 4)`}>
                  <circle r={7.5} />
                  <path d="M2.5,-3.4 L2.5,0.8 L-2.6,0.8 M-0.8,-1.7 L-2.6,0.8 L-0.8,3.3" />
                  <title>
                    {returns
                      .map((r) => `ไป ${(nodeMap.get(r.target)?.label ?? r.target).replace("\n", " ")}${r.label ? `: ${r.label}` : ""}`)
                      .join("\n")}
                  </title>
                </g>
              )}
              {students.length > 0 && (
                <g transform={`translate(2, ${chipY})`}>
                  {students.slice(0, 4).map((p, i) => (
                    <g
                      key={p.code}
                      transform={`translate(${i * 29}, 0)`}
                      className={`chip chip-${p.kind} ${p.code === selectedStudent ? "chip-on" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectStudent?.(p.code);
                      }}
                    >
                      <title>{`${p.code} · ${p.path}`}</title>
                      <rect width={27} height={16} rx={8} />
                      <text x={13.5} y={11.5} textAnchor="middle">
                        {p.code.replace(/^(SIM|DEMO)-/, "").replace(/^S-/, "")}
                      </text>
                    </g>
                  ))}
                  {students.length > 4 && (
                    <text x={4 * 29 + 2} y={12} className="chip-more">
                      +{students.length - 4}
                    </text>
                  )}
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
