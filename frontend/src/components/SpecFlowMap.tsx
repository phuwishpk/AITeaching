import { useMemo, useState } from "react";
import dagre from "@dagrejs/dagre";
import type { FlowPosition } from "./FlowMap";

// ผังของ Flow ที่ AI ออกแบบจากคำสั่งของครูใน Gem (ADR-0004): ขั้นและเส้นไม่ตายตัว จึงจัดตำแหน่งอัตโนมัติด้วย dagre
// เส้นที่วนกลับขั้นเดิม (เช่น ตอบถูกได้ข้อถัดไป) แสดงเป็นสัญลักษณ์ ↻ ที่กล่อง กลไกที่ล็อกไว้ทุก Flow อยู่แถบล่าง

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
  end: "จบ",
};

const W = 168;
const H = 52;

function smooth(points: { x: number; y: number }[]) {
  if (points.length < 3) return `M${points.map((p) => `${p.x},${p.y}`).join(" L")}`;
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
    d += ` Q${points[i].x},${points[i].y} ${i === points.length - 2 ? `${points[i + 1].x},${points[i + 1].y}` : `${mid.x},${mid.y}`}`;
  }
  return d;
}

function labelWidth(text: string) {
  const visible = text.replace(/[ัิ-ฺ็-๎]/g, "");
  return Math.min(180, visible.length * 6.2 + 14);
}

function short(text: string, max: number) {
  const visible = text.replace(/[ัิ-ฺ็-๎]/g, "");
  return visible.length > max ? `${text.slice(0, Math.round(max * (text.length / Math.max(visible.length, 1))))}…` : text;
}

export default function SpecFlowMap({
  nodes,
  edges,
  guards = [],
  positions = [],
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
  selectedNode?: string | null;
  selectedStudent?: string | null;
  onSelectNode?: (id: string) => void;
  onSelectStudent?: (code: string) => void;
  highlightEdges?: string[];
  compact?: boolean;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const layout = useMemo(() => {
    const g = new dagre.graphlib.Graph({ multigraph: true });
    // บนลงล่าง: ขั้นต่อกันเป็นแถว ความกว้างขึ้นกับจำนวนทางแยก จึงพอดีกับคอลัมน์ของหน้า
    g.setGraph({ rankdir: "TB", nodesep: compact ? 24 : 40, ranksep: compact ? 44 : 64, edgesep: 16, marginx: 16, marginy: 22 });
    g.setDefaultEdgeLabel(() => ({}));
    for (const n of nodes) g.setNode(n.id, { width: W, height: H });
    const ids = new Set(nodes.map((n) => n.id));
    for (const e of edges) {
      if (e.source === e.target || !ids.has(e.source) || !ids.has(e.target)) continue;
      const text = e.label || e.text;
      g.setEdge(e.source, e.target, { width: compact ? 1 : labelWidth(text), height: compact ? 1 : 20, labelpos: "c" }, e.id);
    }
    dagre.layout(g);
    const graph = g.graph();
    return {
      width: Math.max((graph.width ?? 400) + 8, 320),
      height: (graph.height ?? 200) + 8,
      boxes: new Map(nodes.map((n) => [n.id, g.node(n.id) as { x: number; y: number }])),
      lines: g.edges().map((e) => ({ id: e.name as string, ...(g.edge(e) as { points: { x: number; y: number }[]; x: number; y: number }) })),
    };
  }, [nodes, edges, compact]);

  const byEdge = useMemo(() => new Map(edges.map((e) => [e.id, e])), [edges]);
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
  const selected = positions.find((p) => p.code === selectedStudent);
  const active = new Set(highlightEdges ?? selected?.last_edges ?? []);

  const chips = (list: FlowPosition[], y: number) =>
    list.length > 0 && (
      <g transform={`translate(2, ${y})`}>
        {list.slice(0, 4).map((p, i) => (
          <g
            key={p.code}
            transform={`translate(${i * 29}, 0)`}
            className={`chip chip-${p.kind} ${p.code === selectedStudent ? "chip-on" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              onSelectStudent?.(p.code);
            }}
          >
            <title>{p.code}</title>
            <rect width={27} height={16} rx={8} />
            <text x={13.5} y={11.5} textAnchor="middle">
              {p.code.replace(/^(SIM|DEMO)-/, "").replace(/^S-/, "")}
            </text>
          </g>
        ))}
        {list.length > 4 && (
          <text x={4 * 29 + 2} y={12} className="chip-more">
            +{list.length - 4}
          </text>
        )}
      </g>
    );

  return (
    <div className="spec-flow">
      <div className="flowmap spec-flowmap">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          // ไม่ย่อจนอ่านป้ายไม่ออก จอแคบให้เลื่อนดูด้านข้างแทน
          style={{ maxWidth: layout.width, minWidth: Math.min(layout.width, compact ? 420 : 760) }}
          role="img"
          aria-label="ผัง Flow ที่ครูออกแบบใน Gem"
        >
          <defs>
            <marker id="sf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head" />
            </marker>
            <marker id="sf-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="arrow-head-on" />
            </marker>
          </defs>
          {layout.lines.map((line) => {
            const edge = byEdge.get(line.id);
            if (!edge) return null;
            const on = active.has(edge.id);
            const text = edge.label || edge.text;
            const d = smooth(line.points);
            const width = labelWidth(text);
            return (
              <g key={edge.id} className={`edge ${on ? "edge-on" : ""}`}>
                <path d={d} markerEnd={on ? "url(#sf-arrow-on)" : "url(#sf-arrow)"} />
                {!compact && (
                  <g className="edge-label">
                    <rect x={line.x - width / 2} y={line.y - 10} width={width} height={20} rx={7} />
                    <text x={line.x} y={line.y + 4} textAnchor="middle">
                      {short(text, 26)}
                    </text>
                  </g>
                )}
                <path d={d} className="edge-hit" onMouseEnter={() => setHover(edge.id)} onMouseLeave={() => setHover(null)}>
                  <title>{`${text}${edge.when ? `\nเงื่อนไข: ${edge.text}` : ""}`}</title>
                </path>
                {compact && hover === edge.id && (
                  <g className="edge-label">
                    <rect x={line.x - width / 2} y={line.y - 10} width={width} height={20} rx={7} />
                    <text x={line.x} y={line.y + 4} textAnchor="middle">
                      {short(text, 26)}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
          {nodes.map((node) => {
            const box = layout.boxes.get(node.id);
            if (!box) return null;
            const students = byNode.get(node.id) ?? [];
            const selfLoops = loops.get(node.id) ?? [];
            const gate = node.kind === "check";
            const classes = [
              "fnode",
              gate ? "fnode-gate" : ["hint", "notify"].includes(node.kind) ? "fnode-step" : "fnode-position",
              `lane-${node.lane}`,
              `snode-${node.kind}`,
              selectedNode === node.id ? "is-selected" : "",
              selected?.step === node.id ? "has-student" : "",
              students.length ? "occupied" : "",
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
                {selfLoops.length > 0 && (
                  <g className={selfLoops.some((e) => active.has(e.id)) ? "return-mark on" : "return-mark"} transform={`translate(${W - 4}, 4)`}>
                    <circle r={7.5} />
                    <path d="M2.5,-3.4 L2.5,0.8 L-2.6,0.8 M-0.8,-1.7 L-2.6,0.8 L-0.8,3.3" />
                    <title>{selfLoops.map((e) => `วนที่ขั้นนี้: ${e.label || e.text}`).join("\n")}</title>
                  </g>
                )}
                {chips(students, H + 6)}
              </g>
            );
          })}
        </svg>
      </div>
      {guards.length > 0 && (
        <div className="spec-guards">
          <span className="xsmall strong muted">ล็อกไว้ทุก Flow (ครูและ AI แก้ไม่ได้) เกิดได้จากทุกขั้น</span>
          <div className="spec-guard-list">
            {guards.map((guard) => {
              const students = byNode.get(guard.id) ?? [];
              return (
                <button
                  key={guard.id}
                  type="button"
                  title={guard.text}
                  className={`spec-guard ${selectedNode === guard.id ? "on" : ""} ${students.length ? "occupied" : ""}`}
                  onClick={() => onSelectNode?.(guard.id)}
                >
                  <span className="xsmall">{guard.label}</span>
                  {students.map((p) => (
                    <span
                      key={p.code}
                      role="button"
                      tabIndex={0}
                      className={`spec-guard-chip ${p.code === selectedStudent ? "on" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectStudent?.(p.code);
                      }}
                    >
                      {p.code.replace(/^(SIM|DEMO)-/, "").replace(/^S-/, "")}
                    </span>
                  ))}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
