import { useMemo } from "react";
import { EyeOff, Lock, Sparkles } from "lucide-react";
import FlowMap, { type FlowEdge, type FlowNode, type FlowPosition } from "../../components/FlowMap";
import SpecFlowMap, { KIND_TEXT, statusText, type SpecEdge, type SpecGuard, type SpecNode, type TrailHop } from "../../components/SpecFlowMap";
import { Badge, Drawer } from "../../components/ui";
import { api } from "../../lib/api";
import { ago } from "../../lib/format";
import { useLoad, useNow } from "../../lib/hooks";

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
  guidelines?: { text: string; steps: string[] }[];
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

// เส้นทางบนผังของ Gem ทั้ง Session ล่าสุดของนักเรียนที่เลือก (การขยับครั้งล่าสุดเข้มที่สุด)
// โหลดใหม่ทุกครั้งที่นักเรียนคนนั้นขยับ (lastEvent มาจากเหตุการณ์สดของหน้า Admin)
export function useTrail(code: string | null | undefined, lastEvent: { code: string; n: number } | null) {
  const moved = code && lastEvent?.code === code ? lastEvent.n : 0;
  const { data } = useLoad(
    () =>
      code
        ? api<{ hops: (TrailHop & { decision: number })[] }>("admin", `/api/admin/students/${encodeURIComponent(code)}/trail`).then(
            (d) => ({ code, hops: d.hops }),
          )
        : Promise.resolve(null),
    [code, moved],
  );
  return useMemo(() => {
    if (!code || data?.code !== code) return undefined;
    const last = data.hops[data.hops.length - 1]?.decision;
    return data.hops.map((h) => ({ ...h, latest: h.decision === last }));
  }, [code, data]);
}

// เส้นทางของการกระทำหนึ่งครั้ง (หน้ากิจกรรมสด) จาก map_path ของการตัดสินใจ ไม่มี (ข้อมูลเก่า) = ใช้เส้นที่ engine บันทึกแทน
export function eventTrail(decisions: { edges: string[]; detail?: Record<string, unknown> }[]): TrailHop[] | undefined {
  const hops: TrailHop[] = [];
  for (const d of decisions) {
    const path = (d.detail?.map_path as string[] | undefined) ?? [];
    for (let i = 0; i < path.length - 1; i++) hops.push({ n: hops.length + 1, from: path[i], to: path[i + 1], edges: d.edges, latest: true });
  }
  return hops.length ? hops : undefined;
}

// ผังของ Gem ที่เลือก ใช้ในหน้า Gem ของ Admin หัวข้อ 3 และกิจกรรมสด
export function GemFlowMap({
  flow,
  allNodes,
  positions,
  trail,
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
  // เส้นทางที่จะวาดบนผังของ Gem (useTrail หรือ eventTrail)
  trail?: TrailHop[];
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
          trail={trail}
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
        {!!flow.guidelines?.length && (
          <ul className="xsmall" style={{ margin: 0, paddingLeft: 18 }}>
            {flow.guidelines.map((g, i) => (
              <li key={i}>
                {g.text} → {g.steps.map((sid) => flow.nodes.find((n) => n.id === sid)?.label ?? sid).join(", ")}
              </li>
            ))}
          </ul>
        )}
        {flow.params.length > 0 && (
          <span className="xsmall muted">ตัวเลขจากคำสั่งของครู: {flow.params.map((p) => `${p.label} = ${p.value}`).join(" · ")}</span>
        )}
      </span>
    </div>
  );
}

// นักเรียนที่อยู่ขั้นนี้ตอนนี้: กำลังทำอะไร (เวลาเดิน) ข้อไหน ผิดกี่ครั้ง มาถึงยังไง และถ้าตอบตอนนี้จะไปไหน
function StudentsHere({ flow, list, nodeId }: { flow: CustomGemFlow; list: FlowPosition[]; nodeId: string }) {
  const now = useNow(1000);
  const name = (id: string) => flow.nodes.find((n) => n.id === id)?.label ?? id;
  const edgeName = (id: string | null | undefined) => flow.edges.find((e) => e.id === id)?.label || null;
  return (
    <div className="stack stack-sm">
      <span className="small strong">นักเรียนในขั้นนี้ตอนนี้ ({list.length})</span>
      {list.map((p) => {
        const w = p.where;
        const elsewhere = (p.step ?? p.position) !== nodeId;
        return (
          <div key={p.code} className="here-card">
            <span className="row row-sm">
              <span className="mono strong">{p.code}</span>
              <span className={`small ${w?.status ? "here-status" : ""}`}>{statusText(w, now) || w?.doing || p.position}</span>
            </span>
            {elsewhere && <span className="xsmall muted">ยังอยู่ขั้น "{name(p.step ?? "")}" ต้นเหตุอยู่ที่กล่องนี้</span>}
            {w && (
              <>
                <dl className="here-facts xsmall">
                  {w.facts.map((f) => (
                    <div key={f.label}>
                      <dt>{f.label}</dt>
                      <dd>{f.value}</dd>
                    </div>
                  ))}
                </dl>
                {w.came && (
                  <span className="xsmall muted">
                    มาถึงขั้นนี้{w.came.from_label ? `จาก "${w.came.from_label}"` : ""}
                    {w.came.via_labels?.length ? ` ผ่าน "${w.came.via_labels.join(" → ")}"` : ""}: {w.came.label} · {ago(w.came.ts, now)}
                  </span>
                )}
                {w.next ? (
                  <ul className="here-next xsmall">
                    {(["correct", "wrong"] as const).map((k) => {
                      const move = w.next?.[k];
                      if (!move) return null;
                      return (
                        <li key={k}>
                          <span className="strong">{k === "correct" ? "ถ้าตอบถูกตอนนี้" : "ถ้าตอบผิดตอนนี้"}</span> → {move.to_label ?? move.to}
                          {move.then && ` แล้วไปต่อที่ "${move.then_label ?? move.then}"`}
                          {edgeName(move.edge) && <span className="muted"> (เส้น "{edgeName(move.edge)}")</span>}
                          {!move.edge && <span className="muted"> (ไม่มีเส้นที่เป็นจริง ใช้ทางของระบบ)</span>}
                        </li>
                      );
                    })}
                    {w.next.step !== nodeId && <li className="muted">ตัดสินที่ขั้น "{name(w.next.step)}"</li>}
                  </ul>
                ) : (
                  <span className="xsmall muted">ตอนนี้ยังส่งคำตอบไม่ได้</span>
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

// คำอธิบายขั้นของ Flow ที่ AI ออกแบบ: ทำอะไร เส้นออกพร้อมเงื่อนไข และขั้นที่เข้ามา
// positions: นักเรียนที่อยู่ขั้นนี้ (หรือต้นเหตุของสถานะอยู่ที่กล่องนี้) และเส้นที่แต่ละคนจะไปถ้าตอบตอนนี้
export function SpecStepDetail({ flow, nodeId, positions = [] }: { flow: CustomGemFlow; nodeId: string | null; positions?: FlowPosition[] }) {
  const node = flow.nodes.find((n) => n.id === nodeId);
  const guard = flow.guards.find((g) => g.id === nodeId);
  const here = positions.filter((p) => nodeId && ((p.step ?? p.position) === nodeId || p.where?.status?.box === nodeId));
  const short = (code: string) => code.replace(/^(SIM|DEMO)-/, "").replace(/^S-/, "");
  if (guard) {
    return (
      <div className="stack stack-sm">
        <span className="row row-sm">
          <Lock size={14} />
          <span className="subtitle">{guard.label}</span>
          <Badge>ล็อกไว้ทุก Flow</Badge>
        </span>
        <p className="small">{guard.text}</p>
        {here.length > 0 && nodeId && <StudentsHere flow={flow} list={here} nodeId={nodeId} />}
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
  // เส้นที่นักเรียนแต่ละคนจะไปถ้าตอบตอนนี้ (พรีวิวจาก engine ตัดสินที่ขั้นทำโจทย์ของนักเรียนคนนั้น)
  const deciding = positions.filter((p) => p.where?.next?.step === node.id);
  return (
    <div className="stack stack-sm">
      <span className="row row-sm">
        <span className="subtitle">{node.label}</span>
        <Badge tone="info">{KIND_TEXT[node.kind] ?? node.kind}</Badge>
        {node.start && <Badge tone="accent">ขั้นแรก</Badge>}
      </span>
      <p className="small">{node.about}</p>
      {here.length > 0 && <StudentsHere flow={flow} list={here} nodeId={node.id} />}
      {out.length > 0 && (
        <>
          <span className="small strong">ไปต่อที่ไหน (ตรวจตามลำดับ เส้นแรกที่เป็นจริงชนะ)</span>
          <ol className="step-list">
            {out.map((e) => {
              const tags = deciding.flatMap((p) =>
                (["correct", "wrong"] as const)
                  .filter((k) => p.where?.next?.[k]?.edge === e.id)
                  .map((k) => `${short(p.code)} ถ้า${k === "correct" ? "ถูก" : "ผิด"}`),
              );
              return (
                <li key={e.id} className="small">
                  <span className="strong">{e.label || "ไปต่อ"}</span> → {name(e.target)}
                  {tags.map((t) => (
                    <Badge key={t} tone="warning">
                      {t}
                    </Badge>
                  ))}
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
              );
            })}
          </ol>
        </>
      )}
      {incoming.length > 0 && <p className="xsmall muted">มาจาก: {incoming.join(", ")}</p>}
    </div>
  );
}

export function SpecStepDrawer({
  flow,
  nodeId,
  positions,
  onClose,
}: {
  flow: CustomGemFlow;
  nodeId: string | null;
  positions?: FlowPosition[];
  onClose: () => void;
}) {
  const title = flow.nodes.find((n) => n.id === nodeId)?.label ?? flow.guards.find((g) => g.id === nodeId)?.label ?? "";
  return (
    <Drawer open={!!nodeId} onClose={onClose} title={title}>
      <SpecStepDetail flow={flow} nodeId={nodeId} positions={positions} />
    </Drawer>
  );
}
