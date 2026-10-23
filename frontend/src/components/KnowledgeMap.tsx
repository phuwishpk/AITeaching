import { useMemo } from "react";
import dagre from "@dagrejs/dagre";

// แผนผังความรู้ (Knowledge Map): เส้นจาก Prerequisite ไปยังมโนทัศน์ที่ต้องใช้มันก่อน
// จัดตำแหน่งอัตโนมัติด้วย dagre เพราะครูเพิ่ม Concept เองได้

interface Concept {
  id: string;
  name: string;
  grade?: string;
  prerequisites?: string[];
}

const NODE_W = 168;
const NODE_H = 58;

// เส้นโค้งผ่านจุดที่ dagre ให้มา (โค้งที่จุดกึ่งกลางแต่ละช่วง)
function smooth(points: { x: number; y: number }[]) {
  if (points.length < 3) return `M${points.map((p) => `${p.x},${p.y}`).join(" L")}`;
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const mid = { x: (points[i].x + points[i + 1].x) / 2, y: (points[i].y + points[i + 1].y) / 2 };
    d += ` Q${points[i].x},${points[i].y} ${i === points.length - 2 ? `${points[i + 1].x},${points[i + 1].y}` : `${mid.x},${mid.y}`}`;
  }
  return d;
}

export default function KnowledgeMap({
  concepts,
  target,
  mastery = {},
  counts = {},
}: {
  concepts: Concept[];
  target?: string | null;
  mastery?: Record<string, number | null>;
  counts?: Record<string, number>;
}) {
  const layout = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 26, ranksep: 70, marginx: 12, marginy: 24 });
    g.setDefaultEdgeLabel(() => ({}));
    for (const c of concepts) g.setNode(c.id, { width: NODE_W, height: NODE_H });
    for (const c of concepts) for (const p of c.prerequisites ?? []) if (concepts.some((x) => x.id === p)) g.setEdge(p, c.id);
    dagre.layout(g);
    const graph = g.graph();
    return {
      width: (graph.width ?? 400) + 4,
      height: (graph.height ?? 200) + 4,
      nodes: concepts.map((c) => ({ ...c, ...(g.node(c.id) as { x: number; y: number }) })),
      edges: g.edges().map((e) => ({ id: `${e.v}-${e.w}`, points: (g.edge(e) as { points: { x: number; y: number }[] }).points })),
    };
  }, [concepts]);

  return (
    <div className="kmap">
      <svg
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        width={layout.width}
        role="img"
        aria-label="แผนผังความรู้: มโนทัศน์และความรู้พื้นฐานที่ต้องรู้ก่อน"
      >
        <defs>
          <marker id="km-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" className="arrow-head" />
          </marker>
        </defs>
        {layout.edges.map((edge) => (
          <path
            key={edge.id}
            className="kmap-edge"
            d={smooth(edge.points)}
            markerEnd="url(#km-arrow)"
          />
        ))}
        {layout.nodes.map((node) => {
          const value = mastery[node.id];
          const isTarget = node.id === target;
          return (
            <g key={node.id} transform={`translate(${node.x - NODE_W / 2}, ${node.y - NODE_H / 2})`} className={isTarget ? "knode is-target" : "knode"}>
              <title>{node.name}</title>
              <rect width={NODE_W} height={NODE_H} rx={12} className="knode-box" />
              <text x={12} y={22} className="knode-name">
                {node.name.length > 16 ? `${node.name.slice(0, 15)}…` : node.name}
              </text>
              <text x={12} y={40} className="knode-sub">
                {[node.grade, counts[node.id] != null ? `${counts[node.id]} ข้อ` : null, isTarget ? "เป้าหมาย" : null].filter(Boolean).join(" · ")}
              </text>
              {value != null && (
                <g transform={`translate(12, ${NODE_H - 9})`}>
                  <rect width={NODE_W - 24} height={4} rx={2} className="knode-track" />
                  <rect width={(NODE_W - 24) * Math.max(0, Math.min(1, value))} height={4} rx={2} className="knode-fill" />
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
