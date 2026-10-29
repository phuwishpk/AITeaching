import { useEffect, useMemo, useState } from "react";
import dagre from "@dagrejs/dagre";
import type { Where } from "../lib/types";
import type { FlowPosition } from "./FlowMap";

// ผังของ Flow ที่ AI ออกแบบจากคำสั่งของครูใน Gem (ADR-0004): ขั้นและเส้นไม่ตายตัว จึงจัดตำแหน่งอัตโนมัติด้วย dagre
// เส้นที่วนกลับขั้นเดิม (เช่น ตอบถูกได้ข้อถัดไป) แสดงเป็นสัญลักษณ์ ↻ ที่กล่อง กลไกที่ล็อกไว้ทุก Flow เป็นแถวกล่องด้านล่าง
// ชิปของนักเรียนอยู่ที่ขั้นที่นักเรียนอยู่ แชตและกลไกที่พักแล้วกลับขั้นเดิม (Idle Pause, ล็อก Rapid Guess ฯลฯ) ไม่พาชิปออกจากขั้น
// แต่ขึ้นป้ายสถานะใต้ชิป มีเส้นประโยงไปกล่องที่เป็นต้นเหตุ และชิปจาง ๆ ในกล่องนั้น นักเรียนที่เลือกมีป้ายบอกส่วนของขั้นเสมอ
// เส้นทางของนักเรียน (trail) วาดตามการขยับจริงพร้อมเลขลำดับ การขยับที่ไม่มีเส้นในผังวาดเป็นเส้นโค้งระหว่างกล่อง

export interface SpecNode {
  id: string;
  label: string;
  kind: string;
  lane: string;
  about: string;
  start: boolean;
}

export interface SpecEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  when: string;
  text: string;
}

export interface SpecGuard {
  id: string;
  label: string;
  text: string;
}

// การขยับหนึ่งช่วงบนผัง (กล่อง → กล่อง) ลำดับที่ n ของ Session หรือของการกระทำที่เลือก
export interface TrailHop {
  n: number;
  from: string;
  to: string;
  edges?: string[];
  // การขยับครั้งล่าสุด: เส้นเข้มที่สุด และกล่องที่ผ่านถูกเน้น
  latest?: boolean;
}

export const KIND_TEXT: Record<string, string> = {
  item: "ทำโจทย์",
  hint: "คำใบ้",
  lesson: "บทเรียนย่อ",
  reflect: "อธิบายความคิด",
  break: "พักสายตา",
  notify: "แจ้งครู",
  teacher: "หยุดรอครู",
  check: "ด่านตัดสินใจ",
  activity: "กิจกรรมที่ AI สร้าง",
  widget: "Widget",
  chat: "แชต",
  guard: "ล็อกไว้ทุก Flow",
  end: "จบ",
};

const W = 168;
const H = 52;
// กล่องของกลไกที่ล็อกไว้ (แถวล่าง) และพื้นที่ใต้กล่องสำหรับชิป
const GW = 132;
const GH = 34;
const GGAP = 12;
const GROW = GH + 50;
// ป้ายของเส้นที่ใช้ทางเดียวกัน (หลายเส้นทิศเดียวกันระหว่างกล่องคู่เดียวกัน) เรียงซ้อนกันห่างกันเท่านี้
const LABEL_STEP = 22;
const NO_GUARDS: SpecGuard[] = [];
const NO_POSITIONS: FlowPosition[] = [];

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Hit {
  numbers: number[];
  latest: boolean;
}

function smooth(points: { x: number; y: number }[]) {
  if (points.length < 3) return `M${points.map((p) => `${p.x},${p.y}`).join(" L")}`;
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
    d += ` Q${points[i].x},${points[i].y} ${i === points.length - 2 ? `${points[i + 1].x},${points[i + 1].y}` : `${mid.x},${mid.y}`}`;
  }
  return d;
}

// เส้นโค้งจากกล่อง a ไปกล่อง b (ไม่มีเส้นนี้ในผัง) กล่องแถวเดียวกันโค้งลงใต้กล่องทั้งสอง
function connector(a: Box, b: Box) {
  if (Math.abs(a.y - b.y) < 4) {
    const sy = a.y + a.h / 2;
    const ey = b.y + b.h / 2;
    const dip = Math.max(sy, ey) + 40;
    return { d: `M${a.x},${sy} C${a.x},${dip} ${b.x},${dip} ${b.x},${ey}`, mid: { x: (a.x + b.x) / 2, y: (sy + ey + 6 * dip) / 8 } };
  }
  const down = b.y > a.y;
  const sy = a.y + (down ? a.h / 2 : -a.h / 2);
  const ey = b.y + (down ? -b.h / 2 : b.h / 2);
  const my = (sy + ey) / 2;
  return { d: `M${a.x},${sy} C${a.x},${my} ${b.x},${my} ${b.x},${ey}`, mid: { x: (a.x + b.x) / 2, y: my } };
}

// เวลาในป้ายสถานะ: ต่ำกว่า 1 นาทีเป็นวินาที
function span(seconds: number) {
  const s = Math.max(0, Math.ceil(seconds));
  return s < 60 ? `${s} วิ` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} นาที`;
}

// ป้ายสถานะ: นับถอยหลังถ้ารู้เวลาจบ ไม่รู้ก็บอกว่าเป็นมานานเท่าไรแล้ว
export function statusText(where: Where | null | undefined, now: number) {
  const status = where?.status;
  if (!status) return "";
  if (status.until) return `${status.label} · เหลือ ${span(status.until - now)}`;
  if (status.since && !status.thinking) return `${status.label} · ${span(now - status.since)}`;
  return status.label;
}

function labelWidth(text: string) {
  const visible = text.replace(/[ัิ-ฺ็-๎]/g, "");
  return Math.min(180, visible.length * 6.2 + 14);
}

function short(text: string, max: number) {
  const visible = text.replace(/[ัิ-ฺ็-๎]/g, "");
  return visible.length > max ? `${text.slice(0, Math.round(max * (text.length / Math.max(visible.length, 1))))}…` : text;
}

function add(map: Map<string, Hit>, key: string, hop: TrailHop) {
  const hit = map.get(key) ?? { numbers: [], latest: false };
  hit.numbers.push(hop.n);
  hit.latest = hit.latest || !!hop.latest;
  map.set(key, hit);
}

// เลขลำดับการขยับบนเส้น (ผ่านเส้นเดิมหลายครั้งแสดง 3 ครั้งล่าสุด)
function TrailBadge({ x, y, hit }: { x: number; y: number; hit: Hit }) {
  const text = hit.numbers.length > 3 ? `…${hit.numbers.slice(-3).join(",")}` : hit.numbers.join(",");
  const width = text.length * 6.6 + 12;
  return (
    <g className={`trail-badge ${hit.latest ? "latest" : ""}`} transform={`translate(${x}, ${y})`}>
      <title>{`ลำดับการขยับ: ${hit.numbers.join(", ")}`}</title>
      <rect x={-width / 2} y={-8} width={width} height={16} rx={8} />
      <text y={4} textAnchor="middle">
        {text}
      </text>
    </g>
  );
}

export default function SpecFlowMap({
  nodes,
  edges,
  guards = NO_GUARDS,
  positions = NO_POSITIONS,
  trail,
  selectedNode,
  selectedStudent,
  onSelectNode,
  onSelectStudent,
  highlightEdges,
  compact,
}: {
  nodes: SpecNode[];
  edges: SpecEdge[];
  guards?: SpecGuard[];
  positions?: FlowPosition[];
  // เส้นทางที่จะวาด ไม่ส่งมา = เน้นแค่เส้นของการย้ายครั้งล่าสุด (highlightEdges หรือ last_edges ของนักเรียนที่เลือก)
  trail?: TrailHop[];
  selectedNode?: string | null;
  selectedStudent?: string | null;
  onSelectNode?: (id: string) => void;
  onSelectStudent?: (code: string) => void;
  highlightEdges?: string[];
  compact?: boolean;
}) {
  const [hover, setHover] = useState<string | null>(null);
  // ป้ายที่มีเวลาเดินทุกวินาที
  const timed = positions.some((p) => p.where?.status?.since || p.where?.status?.until);
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!timed) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [timed]);
  const layout = useMemo(() => {
    // เส้นทิศเดียวกันระหว่างกล่องคู่เดียวกัน (เช่น ผิดครั้ง1 กับ ผิดสะเพร่าครั้ง1 ไปคำใบ้ระดับ 1 ทั้งคู่) ใช้ทางเดียว ป้ายเรียงซ้อนกัน
    // dagre จัดผังที่มีเส้นซ้ำทิศเดียวกันปนเส้นย้อนกลับไม่ได้ บางผังพังด้วย "Not possible to find intersection inside of the rectangle"
    const ids = new Set(nodes.map((n) => n.id));
    const groups = new Map<string, SpecEdge[]>();
    for (const e of edges) {
      if (e.source === e.target || !ids.has(e.source) || !ids.has(e.target)) continue;
      const key = `${e.source}>${e.target}`;
      groups.set(key, [...(groups.get(key) ?? []), e]);
    }
    const build = (keep: (list: SpecEdge[]) => boolean) => {
      const g = new dagre.graphlib.Graph();
      // บนลงล่าง: ขั้นต่อกันเป็นแถว ความกว้างขึ้นกับจำนวนทางแยก จึงพอดีกับคอลัมน์ของหน้า
      g.setGraph({ rankdir: "TB", nodesep: compact ? 24 : 40, ranksep: compact ? 44 : 64, edgesep: 16, marginx: 16, marginy: 22 });
      g.setDefaultEdgeLabel(() => ({}));
      for (const n of nodes) g.setNode(n.id, { width: W, height: H });
      for (const list of groups.values()) {
        if (!keep(list)) continue;
        const width = compact ? 1 : Math.max(...list.map((e) => labelWidth(e.label || e.text)));
        g.setEdge(list[0].source, list[0].target, { width, height: compact ? 1 : list.length * LABEL_STEP - 2, labelpos: "c" });
      }
      dagre.layout(g);
      return g;
    };
    // ทางสำรองถ้า dagre ยังพังด้วยเหตุอื่น: จัดด้วยเส้นเดียวต่อกล่องคู่ (ไม่สนทิศ) แล้วจึงไม่มีเส้นเลย
    // เส้นที่ไม่ได้ใช้จัดผังวาดเป็นเส้นโค้งระหว่างกล่อง ผังจึงขึ้นเสมอ ไม่เป็นจอขาว
    let g: ReturnType<typeof build>;
    try {
      g = build(() => true);
    } catch {
      const pairs = new Set<string>();
      try {
        g = build((list) => {
          const pair = [list[0].source, list[0].target].sort().join("\u0000");
          if (pairs.has(pair)) return false;
          pairs.add(pair);
          return true;
        });
      } catch {
        g = build(() => false);
      }
    }
    const graph = g.graph();
    const graphWidth = (graph.width ?? 400) + 8;
    // เผื่อที่ใต้แถวล่างสุดให้ชิปและป้ายสถานะ
    const graphHeight = (graph.height ?? 200) + (compact ? 8 : 48);
    // แถวกลไกที่ล็อกไว้ขึ้นบรรทัดใหม่ตามความกว้าง ผังที่แคบกว่าแถวนี้เลื่อนมากึ่งกลาง
    const width = Math.max(graphWidth, guards.length ? 640 : 320);
    const dx = (width - graphWidth) / 2;
    const cols = Math.max(1, Math.floor((width - 16) / (GW + GGAP)));
    const rows = Math.ceil(guards.length / cols);
    const guardTop = graphHeight + 40;
    const guardBoxes = new Map<string, Box>(
      guards.map((guard, i) => {
        const row = Math.floor(i / cols);
        const inRow = Math.min(cols, guards.length - row * cols);
        const left = (width - (inRow * GW + (inRow - 1) * GGAP)) / 2;
        return [guard.id, { x: left + (i % cols) * (GW + GGAP) + GW / 2, y: guardTop + row * GROW + GH / 2, w: GW, h: GH }];
      }),
    );
    return {
      width,
      height: rows ? guardTop + rows * GROW : graphHeight,
      graphHeight,
      boxes: new Map<string, Box>(
        nodes.map((n) => {
          const box = g.node(n.id) as { x: number; y: number };
          return [n.id, { x: box.x + dx, y: box.y, w: W, h: H }];
        }),
      ),
      guardBoxes,
      lines: [...groups].map(([key, members]) => {
        const { source, target } = members[0];
        if (g.hasEdge(source, target)) {
          const line = g.edge(source, target) as { points: { x: number; y: number }[]; x: number; y: number };
          return { key, members, x: line.x + dx, y: line.y, d: smooth(line.points.map((p) => ({ x: p.x + dx, y: p.y }))) };
        }
        const a = g.node(source) as { x: number; y: number };
        const b = g.node(target) as { x: number; y: number };
        const line = connector({ x: a.x + dx, y: a.y, w: W, h: H }, { x: b.x + dx, y: b.y, w: W, h: H });
        return { key, members, x: line.mid.x, y: line.mid.y, d: line.d };
      }),
    };
  }, [nodes, edges, guards, compact]);

  const loops = useMemo(() => {
    const map = new Map<string, SpecEdge[]>();
    for (const e of edges) if (e.source === e.target) map.set(e.source, [...(map.get(e.source) ?? []), e]);
    return map;
  }, [edges]);
  const byNode = useMemo(() => {
    const map = new Map<string, FlowPosition[]>();
    for (const p of positions) {
      const at = p.step ?? p.position;
      map.set(at, [...(map.get(at) ?? []), p]);
    }
    return map;
  }, [positions]);
  // นักเรียนที่ยังอยู่ขั้นของตัวเอง แต่ต้นเหตุของสถานะอยู่อีกกล่อง (แชต หรือกลไกที่ล็อกไว้)
  const byCause = useMemo(() => {
    const map = new Map<string, FlowPosition[]>();
    for (const p of positions) {
      const box = p.where?.status?.box;
      if (box && box !== (p.step ?? p.position)) map.set(box, [...(map.get(box) ?? []), p]);
    }
    return map;
  }, [positions]);
  const nameOf = useMemo(() => new Map([...nodes.map((n) => [n.id, n.label] as const), ...guards.map((g) => [g.id, g.label] as const)]), [nodes, guards]);
  // แต่ละช่วงของเส้นทาง: ใช้เส้นในผังถ้ามี (เส้นที่ engine บันทึกก่อน) ไม่มีก็เป็นเส้นโค้งระหว่างกล่อง
  const paths = useMemo(() => {
    const onEdge = new Map<string, Hit>();
    const onLoop = new Map<string, Hit>();
    const free = new Map<string, Hit>();
    const passed = new Set<string>();
    for (const hop of trail ?? []) {
      if (hop.latest) {
        passed.add(hop.from);
        passed.add(hop.to);
      }
      const between = edges.filter((e) => e.source === hop.from && e.target === hop.to);
      const edge = between.find((e) => hop.edges?.includes(e.id)) ?? between[0];
      if (edge) add(onEdge, edge.id, hop);
      else if (hop.from === hop.to) add(onLoop, hop.from, hop);
      else add(free, `${hop.from}>${hop.to}`, hop);
    }
    return { onEdge, onLoop, free, passed };
  }, [trail, edges]);
  const selected = positions.find((p) => p.code === selectedStudent);
  const active = new Set(trail ? paths.onEdge.keys() : (highlightEdges ?? selected?.last_edges ?? []));
  const boxOf = (id: string) => layout.boxes.get(id) ?? layout.guardBoxes.get(id);
  const badges: { key: string; x: number; y: number; hit: Hit }[] = [];

  const codeOf = (p: FlowPosition) => p.code.replace(/^(SIM|DEMO)-/, "").replace(/^S-/, "");
  // ชิปของนักเรียนในกล่อง ต่อด้วยชิปจาง ๆ ของนักเรียนที่อยู่ขั้นอื่นแต่ต้นเหตุอยู่ที่กล่องนี้ (cause)
  const chips = (list: FlowPosition[], y: number, cause: FlowPosition[] = []) => {
    const all = [...list.map((p) => ({ p, ghost: false })), ...cause.map((p) => ({ p, ghost: true }))];
    return (
      all.length > 0 && (
        <g transform={`translate(2, ${y})`}>
          {all.slice(0, 4).map(({ p, ghost }, i) => (
            <g
              key={`${p.code}-${ghost}`}
              transform={`translate(${i * 29}, 0)`}
              className={`chip chip-${p.kind} ${ghost ? "chip-ghost" : ""} ${p.code === selectedStudent ? "chip-on" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelectStudent?.(p.code);
              }}
            >
              <title>
                {ghost
                  ? `${p.code} · ${p.where?.status?.label ?? ""} (ยังอยู่ขั้น ${nameOf.get(p.step ?? "") ?? p.step})`
                  : `${p.code} · ${p.where?.doing ?? ""}`}
              </title>
              <rect width={27} height={16} rx={8} />
              <text x={13.5} y={11.5} textAnchor="middle">
                {codeOf(p)}
              </text>
              {p.thinking && <circle cx={26} cy={1} r={3.5} className="chip-think" />}
            </g>
          ))}
          {all.length > 4 && (
            <text x={4 * 29 + 2} y={12} className="chip-more">
              +{all.length - 4}
            </text>
          )}
        </g>
      )
    );
  };
  // ป้ายใต้ชิป: นักเรียนที่เลือกบอกส่วนของขั้นเสมอ คนอื่นบอกเฉพาะตอนสถานะไม่ปกติ (พัก ล็อก คุยกับ AI รอคำใบ้)
  const notes = (list: FlowPosition[], y: number) => {
    const shown = list.filter((p) => p.code === selectedStudent || p.where?.status);
    if (!shown.length) return null;
    return (
      <g transform={`translate(0, ${y})`}>
        {shown.slice(0, 2).map((p, i) => {
          const text = short(`${codeOf(p)} · ${statusText(p.where, now) || p.where?.brief || p.where?.doing || ""}`, 34);
          const width = Math.min(230, text.replace(/[ัิ-ฺ็-๎]/g, "").length * 6 + 16);
          return (
            <g key={p.code} transform={`translate(0, ${i * 19})`} className={`chip-note ${p.where?.status ? "is-status" : ""}`}>
              <title>{p.where?.doing ?? p.code}</title>
              <rect width={width} height={17} rx={8.5} />
              <text x={8} y={12}>
                {text}
              </text>
            </g>
          );
        })}
        {shown.length > 2 && (
          <text x={4} y={2 * 19 + 11} className="chip-more">
            +{shown.length - 2}
          </text>
        )}
      </g>
    );
  };
  // เส้นประจากขั้นที่นักเรียนอยู่ไปกล่องที่เป็นต้นเหตุของสถานะ (กล่องละเส้นต่อคู่ขั้น)
  const causeLines = new Map<string, string>();
  for (const p of positions) {
    const box = p.where?.status?.box;
    const at = p.step ?? p.position;
    const a = boxOf(at);
    const b = box ? boxOf(box) : undefined;
    if (box && box !== at && a && b && !causeLines.has(`${at}>${box}`)) causeLines.set(`${at}>${box}`, connector(a, b).d);
  }

  return (
    <div className="spec-flow">
      <div className="flowmap spec-flowmap">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          // ไม่ย่อจนอ่านป้ายไม่ออก จอแคบให้เลื่อนดูด้านข้างแทน
          style={{ maxWidth: layout.width, minWidth: Math.min(layout.width, compact ? 420 : 760) }}
          role="img"
          aria-label="ผัง Flow ที่ครูออกแบบในติวเตอร์"
        >
          <defs>
            <marker id="sf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head" />
            </marker>
            <marker id="sf-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head-on" />
            </marker>
            <marker id="sf-arrow-trail" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head-trail" />
            </marker>
          </defs>
          {layout.lines.map((line) => {
            const lit = line.members.filter((e) => active.has(e.id));
            const on = lit.length > 0;
            // เส้นทางย้อนหลังที่ไม่ใช่การขยับครั้งล่าสุดเป็นสีจาง
            const past = on && lit.every((e) => paths.onEdge.get(e.id) && !paths.onEdge.get(e.id)?.latest);
            const top = line.y - (line.members.length * LABEL_STEP - 2) / 2;
            // ป้ายของทุกเส้นที่ใช้ทางนี้ เรียงจากบนลงล่าง ป้ายที่ติดไฟคือเส้นที่ผ่านจริง
            const labels = line.members.map((e, k) => {
              const text = e.label || e.text;
              const width = labelWidth(text);
              const y = top + k * LABEL_STEP;
              const hit = paths.onEdge.get(e.id);
              if (hit) badges.push({ key: e.id, x: line.x + width / 2 + 14, y: y + 10, hit });
              return (
                <g key={e.id} className={`edge-label ${active.has(e.id) ? "is-on" : ""}`}>
                  <rect x={line.x - width / 2} y={y} width={width} height={20} rx={7} />
                  <text x={line.x} y={y + 14} textAnchor="middle">
                    {short(text, 26)}
                  </text>
                </g>
              );
            });
            return (
              <g key={line.key} className={`edge ${on ? (past ? "edge-trail" : "edge-on") : ""}`}>
                <path d={line.d} markerEnd={on ? (past ? "url(#sf-arrow-trail)" : "url(#sf-arrow-on)") : "url(#sf-arrow)"} />
                {!compact && labels}
                <path d={line.d} className="edge-hit" onMouseEnter={() => setHover(line.key)} onMouseLeave={() => setHover(null)}>
                  <title>
                    {line.members.map((e) => `${e.label || e.text}${e.when ? `\nเงื่อนไข: ${e.text}` : ""}`).join("\n\n")}
                  </title>
                </path>
                {compact && hover === line.key && labels}
              </g>
            );
          })}
          {[...paths.free].map(([key, hit]) => {
            const [from, to] = key.split(">");
            const a = boxOf(from);
            const b = boxOf(to);
            if (!a || !b) return null;
            const line = connector(a, b);
            badges.push({ key, x: line.mid.x, y: line.mid.y, hit });
            return (
              <g key={key} className={`edge edge-free ${hit.latest ? "edge-on" : "edge-trail"}`}>
                <path d={line.d} markerEnd={hit.latest ? "url(#sf-arrow-on)" : "url(#sf-arrow-trail)"} />
              </g>
            );
          })}
          {[...causeLines].map(([key, d]) => (
            <path key={`cause-${key}`} d={d} className="cause-line" />
          ))}
          {nodes.map((node) => {
            const box = layout.boxes.get(node.id);
            if (!box) return null;
            const students = byNode.get(node.id) ?? [];
            const cause = byCause.get(node.id) ?? [];
            const selfLoops = loops.get(node.id) ?? [];
            const loopHits = [...selfLoops.map((e) => paths.onEdge.get(e.id)), paths.onLoop.get(node.id)].filter((h): h is Hit => !!h);
            const loopOn = selfLoops.some((e) => active.has(e.id)) || loopHits.length > 0;
            if (loopHits.length) {
              const numbers = loopHits.flatMap((h) => h.numbers).sort((x, y) => x - y);
              badges.push({ key: `loop-${node.id}`, x: box.x + W / 2 - 4, y: box.y - H / 2 - 12, hit: { numbers, latest: loopHits.some((h) => h.latest) } });
            }
            const gate = node.kind === "check";
            const classes = [
              "fnode",
              gate ? "fnode-gate" : ["hint", "notify"].includes(node.kind) ? "fnode-step" : "fnode-position",
              `lane-${node.lane}`,
              `snode-${node.kind}`,
              selectedNode === node.id ? "is-selected" : "",
              selected?.step === node.id ? "has-student" : "",
              paths.passed.has(node.id) ? "is-passed" : "",
              students.length ? "occupied" : "",
              cause.length ? "is-cause" : "",
            ].join(" ");
            return (
              <g
                key={node.id}
                className={classes}
                transform={`translate(${box.x - W / 2}, ${box.y - H / 2})`}
                onClick={() => onSelectNode?.(node.id)}
                role="button"
                tabIndex={0}
                aria-label={`${node.label} (${KIND_TEXT[node.kind] ?? node.kind}) มีนักเรียน ${students.length} คน`}
                onKeyDown={(e) => e.key === "Enter" && onSelectNode?.(node.id)}
              >
                <title>{node.about}</title>
                <rect width={W} height={H} rx={gate ? 16 : 11} className="fnode-box" />
                {gate ? (
                  <rect x={9} y={H / 2 - 3.5} width={7} height={7} transform={`rotate(45 12.5 ${H / 2})`} className="fnode-mark" />
                ) : (
                  <circle cx={12.5} cy={H / 2} r={3.5} className="fnode-mark" />
                )}
                <text x={W / 2 + 6} y={H / 2 - 3} textAnchor="middle" className="fnode-text">
                  {short(node.label, 20)}
                </text>
                <text x={W / 2 + 6} y={H / 2 + 13} textAnchor="middle" className="snode-kind">
                  {KIND_TEXT[node.kind] ?? node.kind}
                </text>
                {node.start && (
                  <g className="snode-start" transform="translate(0, -9)">
                    <rect width={38} height={16} rx={8} />
                    <text x={19} y={11.5} textAnchor="middle">
                      เริ่ม
                    </text>
                  </g>
                )}
                {(selfLoops.length > 0 || loopHits.length > 0) && (
                  <g className={loopOn ? "return-mark on" : "return-mark"} transform={`translate(${W - 4}, 4)`}>
                    <circle r={7.5} />
                    <path d="M2.5,-3.4 L2.5,0.8 L-2.6,0.8 M-0.8,-1.7 L-2.6,0.8 L-0.8,3.3" />
                    <title>{selfLoops.length ? selfLoops.map((e) => `วนที่ขั้นนี้: ${e.label || e.text}`).join("\n") : "วนที่ขั้นนี้"}</title>
                  </g>
                )}
                {chips(students, H + 6, cause)}
                {notes(students, H + 26)}
              </g>
            );
          })}
          {guards.length > 0 && (
            <g className="sguard-row">
              <line x1={8} x2={layout.width - 8} y1={layout.graphHeight + 6} y2={layout.graphHeight + 6} className="sguard-rule" />
              <text x={10} y={layout.graphHeight + 26} className="sguard-title">
                ล็อกไว้ทุก Flow (ครูและ AI แก้ไม่ได้) เกิดได้จากทุกขั้น
              </text>
              {guards.map((guard) => {
                const box = layout.guardBoxes.get(guard.id);
                if (!box) return null;
                const students = byNode.get(guard.id) ?? [];
                const cause = byCause.get(guard.id) ?? [];
                const classes = [
                  "fnode",
                  "sguard",
                  selectedNode === guard.id ? "is-selected" : "",
                  selected?.step === guard.id ? "has-student" : "",
                  paths.passed.has(guard.id) ? "is-passed" : "",
                  students.length ? "occupied" : "",
                  cause.length ? "is-cause" : "",
                ].join(" ");
                return (
                  <g
                    key={guard.id}
                    className={classes}
                    transform={`translate(${box.x - GW / 2}, ${box.y - GH / 2})`}
                    onClick={() => onSelectNode?.(guard.id)}
                    role="button"
                    tabIndex={0}
                    aria-label={`${guard.label} (ล็อกไว้ทุก Flow) มีนักเรียน ${students.length} คน`}
                    onKeyDown={(e) => e.key === "Enter" && onSelectNode?.(guard.id)}
                  >
                    <title>{guard.text}</title>
                    <rect width={GW} height={GH} rx={GH / 2} className="fnode-box" />
                    <text x={GW / 2} y={GH / 2 + 4} textAnchor="middle" className="fnode-text">
                      {short(guard.label, 18)}
                    </text>
                    {chips(students, GH + 4, cause)}
                    {notes(students, GH + 24)}
                  </g>
                );
              })}
            </g>
          )}
          {badges.map((b) => (
            <TrailBadge key={b.key} x={b.x} y={b.y} hit={b.hit} />
          ))}
        </svg>
      </div>
    </div>
  );
}
