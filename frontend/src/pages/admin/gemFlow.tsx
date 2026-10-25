import { EyeOff, Lock, Sparkles } from "lucide-react";
import FlowMap, { type FlowEdge, type FlowNode, type FlowPosition } from "../../components/FlowMap";
import SpecFlowMap, { KIND_TEXT, type SpecEdge, type SpecGuard, type SpecNode } from "../../components/SpecFlowMap";
import { Badge, Drawer } from "../../components/ui";

// ผังของ Gem แต่ละตัว ไม่ใช่ผังตายตัว มีสองแบบ
// 1) ผังมาตรฐาน (backend/app/gems/design.py): กล่องของเครื่องมือที่ครูปิดไม่อยู่ในผัง และเส้นต่อไปยังขั้นที่ engine ใช้จริง
// 2) Flow ที่ AI ออกแบบจากคำสั่งของครู (ADR-0004, flowspec.py): ขั้นและเส้นตามที่ออกแบบ จัดตำแหน่งอัตโนมัติ

export interface StandardGemFlow {
  custom?: false;
  gem_id?: string;
  name?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  disabled: Record<string, string>;
  alerts: Record<string, { key: string; label: string; level: string; mode: "notify" | "pause" }[]>;
}

export interface CustomGemFlow {
  custom: true;
  gem_id?: string;
  name?: string;
  nodes: SpecNode[];
  edges: SpecEdge[];
  guards: SpecGuard[];
  summary: string;
  source: string | null;
  reviewed: boolean;
  warnings: string[];
  locked: { title: string; text: string }[];
  params: { key: string; label: string; value: number }[];
  disabled: Record<string, string>;
  alerts: Record<string, never>;
}

export type GemFlow = StandardGemFlow | CustomGemFlow;

// บอกว่ากล่องไหนไม่อยู่ในผังของ Gem นี้เพราะครูปิดเครื่องมือ (รวมกล่องตามเหตุผลเดียวกัน)
// allNodes คือผังเต็มของระบบ ใช้หาชื่อของกล่องที่ไม่อยู่ในผังนี้
export function HiddenNote({ disabled, allNodes }: { disabled: Record<string, string>; allNodes: FlowNode[] }) {
  const name = new Map(allNodes.map((n) => [n.id, n.label.replace("\n", " ")]));
  const groups = new Map<string, string[]>();
  for (const [node, reason] of Object.entries(disabled)) groups.set(reason, [...(groups.get(reason) ?? []), name.get(node) ?? node]);
  if (!groups.size) return <p className="xsmall muted">Gem นี้เปิดเครื่องมือการสอนครบ ผังจึงมีทุกขั้น</p>;
  return (
    <ul className="hidden-note">
      {[...groups].map(([reason, nodes]) => (
        <li key={reason} className="xsmall">
          <EyeOff size={13} />
          <span>
            <span className="strong">{reason}</span> · ไม่อยู่ในผัง: {nodes.join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

// ผังของ Gem ที่เลือก ใช้ในหน้า Gem ของ Admin หัวข้อ 3 และกิจกรรมสด
export function GemFlowMap({
  flow,
  allNodes,
  positions,
  selectedNode,
  selectedStudent,
  onSelectNode,
  onSelectStudent,
  highlightEdges,
  focusLane,
  note = true,
}: {
  flow: GemFlow;
  allNodes: FlowNode[];
  positions: FlowPosition[];
  selectedNode?: string | null;
  selectedStudent?: string | null;
  onSelectNode?: (id: string) => void;
  onSelectStudent?: (code: string) => void;
  highlightEdges?: string[];
  focusLane?: string | null;
  note?: boolean;
}) {
  if (flow.custom) {
    return (
      <div className="stack">
        {note && <CustomNote flow={flow} />}
        <SpecFlowMap
          nodes={flow.nodes}
          edges={flow.edges}
          guards={flow.guards}
          positions={positions}
          selectedNode={selectedNode}
          selectedStudent={selectedStudent}
          onSelectNode={onSelectNode}
          onSelectStudent={onSelectStudent}
          highlightEdges={highlightEdges}
        />
      </div>
    );
  }
  return (
    <>
      <FlowMap
        nodes={flow.nodes}
        edges={flow.edges}
        marks={flow.alerts}
        positions={positions}
        selectedNode={selectedNode}
        selectedStudent={selectedStudent}
        focusLane={focusLane}
        onSelectNode={onSelectNode}
        onSelectStudent={onSelectStudent}
        highlightEdges={highlightEdges}
      />
      {note && (
        <div className="flow-foot">
          <HiddenNote disabled={flow.disabled} allNodes={allNodes} />
        </div>
      )}
    </>
  );
}

export function CustomNote({ flow }: { flow: CustomGemFlow }) {
  return (
    <div className="callout callout-info">
      <Sparkles size={16} />
      <span className="stack stack-sm" style={{ gap: 4 }}>
        <span className="row row-sm">
          <span className="small strong">Flow ที่ AI ออกแบบจากคำสั่งของครู</span>
          {flow.source === "teacher" ? <Badge tone="info">ครูแก้เอง</Badge> : null}
          {flow.reviewed ? <Badge tone="success">ครูตรวจแล้ว</Badge> : <Badge tone="warning">ครูยังไม่ได้ตรวจ</Badge>}
        </span>
        {flow.summary && <span className="small">{flow.summary}</span>}
        {flow.params.length > 0 && (
          <span className="xsmall muted">ตัวเลขจากคำสั่งของครู: {flow.params.map((p) => `${p.label} = ${p.value}`).join(" · ")}</span>
        )}
      </span>
    </div>
  );
}

// คำอธิบายขั้นของ Flow ที่ AI ออกแบบ: ทำอะไร เส้นออกพร้อมเงื่อนไข และขั้นที่เข้ามา
export function SpecStepDetail({ flow, nodeId }: { flow: CustomGemFlow; nodeId: string | null }) {
  const node = flow.nodes.find((n) => n.id === nodeId);
  const guard = flow.guards.find((g) => g.id === nodeId);
  if (guard) {
    return (
      <div className="stack stack-sm">
        <span className="row row-sm">
          <Lock size={14} />
          <span className="subtitle">{guard.label}</span>
          <Badge>ล็อกไว้ทุก Flow</Badge>
        </span>
        <p className="small">{guard.text}</p>
        <ul className="flow-locked">
          {flow.locked.map((l) => (
            <li key={l.title} className="xsmall">
              <Lock size={12} />
              <span>
                <span className="strong">{l.title}</span> · {l.text}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (!node) return <p className="small muted">กดกล่องในผังเพื่อดูว่าขั้นนี้ทำอะไรและไปต่อที่ไหน</p>;
  const name = (id: string) => flow.nodes.find((n) => n.id === id)?.label ?? id;
  const out = flow.edges.filter((e) => e.source === node.id);
  const incoming = [...new Set(flow.edges.filter((e) => e.target === node.id && e.source !== node.id).map((e) => name(e.source)))];
  return (
    <div className="stack stack-sm">
      <span className="row row-sm">
        <span className="subtitle">{node.label}</span>
        <Badge tone="info">{KIND_TEXT[node.kind] ?? node.kind}</Badge>
        {node.start && <Badge tone="accent">ขั้นแรก</Badge>}
      </span>
      <p className="small">{node.about}</p>
      {out.length > 0 && (
        <>
          <span className="small strong">ไปต่อที่ไหน (ตรวจตามลำดับ เส้นแรกที่เป็นจริงชนะ)</span>
          <ol className="step-list">
            {out.map((e) => (
              <li key={e.id} className="small">
                <span className="strong">{e.label || "ไปต่อ"}</span> → {name(e.target)}
                <br />
                <span className="xsmall muted">
                  ถ้า {e.text}
                  {e.when && (
                    <>
                      {" "}
                      · <span className="mono">{e.when}</span>
                    </>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
      {incoming.length > 0 && <p className="xsmall muted">มาจาก: {incoming.join(", ")}</p>}
    </div>
  );
}

export function SpecStepDrawer({ flow, nodeId, onClose }: { flow: CustomGemFlow; nodeId: string | null; onClose: () => void }) {
  const title = flow.nodes.find((n) => n.id === nodeId)?.label ?? flow.guards.find((g) => g.id === nodeId)?.label ?? "";
  return (
    <Drawer open={!!nodeId} onClose={onClose} title={title}>
      <SpecStepDetail flow={flow} nodeId={nodeId} />
    </Drawer>
  );
}
