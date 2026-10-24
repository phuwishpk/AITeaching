import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { ArrowRight, MousePointerClick, SlidersHorizontal } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago, clock, PATH_LABELS } from "../../lib/format";
import FlowMap from "../../components/FlowMap";
import PrincipleCard from "../../components/PrincipleCard";
import { BarList } from "../../components/charts";
import { Badge, Card, CardHead, Empty, Spinner } from "../../components/ui";
import { TopicHeader, useAdmin } from "./AdminApp";
import { useStudentPicker } from "./Topic2";
import { CodePicker, Section, TopicLink } from "./shared";
import NodeInspector from "./NodeInspector";
import AnswerSheet from "./AnswerSheet";
import { Button } from "../../components/ui";

const KINDS = [
  { id: "real", label: "นักเรียนจริง" },
  { id: "demo", label: "นักเรียนสาธิต" },
  { id: "sim", label: "นักเรียนจำลอง" },
];

const LADDER = [
  { when: "ผิดครั้งที่ 1", what: "Deliberate Delay 15 วินาที ให้ลองแก้เองก่อน แล้วจึงเปิดคำใบ้ระดับ 1", level: "L1 สะกิดความคิด" },
  { when: "ผิดครั้งที่ 2", what: "อธิบายกฎหรือหลักการที่เกี่ยวข้องสั้น ๆ", level: "L2 อธิบายกฎ" },
  { when: "ผิดครั้งที่ 3", what: "Fuzzy ดูว่าเวลาคิดยาวขึ้นต่อเนื่องไหม ถ้าใช่เป็น Impasse ถ้าไม่ใช่ให้ L3", level: "L3 ชี้ขั้นแรก หรือ Impasse" },
  { when: "ผิดครั้งที่ 4 ขึ้นไป", what: "พักข้อนี้ แล้วพาไปทบทวน Prerequisite (Remedial Loop)", level: "Impasse" },
];

interface BugRow {
  id: string;
  type: "misconception" | "slip";
  name: string;
  description: string;
  response: string;
  prerequisite: string | null;
  hits: { total: number; misconception: number; slip: number; unclassified: number };
}

export default function Topic3() {
  const { flow, liveVersion } = useAdmin();
  const [params, setParams] = useSearchParams();
  const [kinds, setKinds] = useState<string[]>(["real", "demo", "sim"]);
  const { students, code, setCode, detail } = useStudentPicker();
  const bugs = useLoad(() => api<BugRow[]>("admin", "/api/admin/bug-library"), [Math.floor(liveVersion / 20)]);
  const now = useNow(5000);
  const node = params.get("node") ?? "G3";
  const [inspect, setInspect] = useState<string | null>(null);

  useEffect(() => {
    if (params.get("node")) document.getElementById("flow-card")?.scrollIntoView({ block: "start" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const positions = useMemo(() => (flow?.positions ?? []).filter((p) => kinds.includes(p.kind)), [flow?.positions, kinds]);
  const selected = flow?.positions.find((p) => p.code === code);
  const atNode = positions.filter((p) => p.position === node);
  const card = flow?.cards[node];
  const nodeInfo = flow?.nodes.find((n) => n.id === node);

  if (!flow) return <Spinner />;

  return (
    <div className="page page-wide topic stack stack-lg">
      <TopicHeader
        id="3"
        lead="ผังนี้คือตรรกะจริงที่ engine ใช้ตัดสินทุกคำตอบ ชิปบนกล่องคือนักเรียนที่อยู่ตรงนั้นตอนนี้ เส้นสีเข้มคือเส้นทางล่าสุดของนักเรียนที่เลือก"
      >
        <div className="row">
          <TopicLink to="activity">ดูทีละการกระทำ</TopicLink>
          <CodePicker codes={students} value={code} onChange={setCode} label="ติดตาม" />
        </div>
      </TopicHeader>

      <Card id="flow-card" className="flow-card">
        <div className="flow-toolbar">
          <div className="row row-sm" role="group" aria-label="แสดงนักเรียนกลุ่ม">
            {KINDS.map((k) => {
              const on = kinds.includes(k.id);
              const count = (flow.positions ?? []).filter((p) => p.kind === k.id).length;
              return (
                <button
                  key={k.id}
                  className={`chip-toggle chip-kind-${k.id} ${on ? "on" : ""}`}
                  aria-pressed={on}
                  onClick={() => setKinds(on ? kinds.filter((x) => x !== k.id) : [...kinds, k.id])}
                >
                  <span className="chip-dot" />
                  {k.label} {count}
                </button>
              );
            })}
          </div>
          <ul className="flow-legend xsmall muted">
            <li>
              <span className="lg-node" />
              ตำแหน่งที่นักเรียนอยู่ได้
            </li>
            <li>
              <span className="lg-gate" />
              ด่านตัดสินใจ
            </li>
            <li>
              <span className="lg-step" />
              ขั้นประมวลผล
            </li>
            <li>
              <span className="lg-return">↩</span>
              เส้นวนกลับ ชี้เพื่อดูปลายทาง
            </li>
            <li className="strong">กดกล่องเพื่อดูว่าทำอะไรและปรับแต่ง</li>
          </ul>
        </div>
        <FlowMap
          nodes={flow.nodes}
          edges={flow.edges}
          positions={positions}
          selectedNode={node}
          selectedStudent={code}
          onSelectNode={(id) => {
            setParams({ node: id }, { replace: true });
            setInspect(id);
          }}
          onSelectStudent={setCode}
        />
      </Card>

      <div className="grid grid-2 t3-grid">
        <Card className="card-pad stack">
          <div className="spread">
            <span className="eyebrow">ขั้นที่เลือก</span>
            <span className="xsmall faint row row-sm">
              <MousePointerClick size={14} />
              กดกล่องในผังเพื่อเปลี่ยน
            </span>
          </div>
          {card ? <PrincipleCard card={card} /> : <p className="small muted">{nodeInfo?.label}</p>}
          <Button variant="soft" icon={<SlidersHorizontal size={16} />} onClick={() => setInspect(node)} style={{ alignSelf: "flex-start" }}>
            ดูข้อมูลที่ใช้และปรับแต่งขั้นนี้
          </Button>
          <div className="stack stack-sm">
            <span className="small strong">นักเรียนที่อยู่ตรงนี้ ({atNode.length})</span>
            <div className="pill-list">
              {atNode.map((p) => (
                <button key={p.code} className={`chip-toggle chip-kind-${p.kind} ${p.code === code ? "on" : ""}`} onClick={() => setCode(p.code)}>
                  <span className="chip-dot" />
                  {p.code}
                  <span className="xsmall faint">{ago(p.since, now)}</span>
                </button>
              ))}
              {!atNode.length && <span className="small faint">ไม่มี</span>}
            </div>
          </div>
        </Card>

        <Card className="card-pad stack">
          <div className="spread">
            <span className="eyebrow">Decision Trace ของ {code ?? "–"}</span>
            {selected && <Badge tone="accent">{flow.labels[selected.position] ?? selected.position}</Badge>}
          </div>
          {!selected && <Empty>เลือกนักเรียนจากชิปในผังหรือจากรายการด้านบน</Empty>}
          {selected && (
            <>
              <dl className="kv">
                <div>
                  <dt>เส้นทาง</dt>
                  <dd>{PATH_LABELS[selected.path] ?? selected.path}</dd>
                </div>
                <div>
                  <dt>ข้อปัจจุบัน</dt>
                  <dd className="mono">{selected.item ?? "–"}</dd>
                </div>
                <div>
                  <dt>ระดับคำใบ้</dt>
                  <dd>{selected.hint_level ? `L${selected.hint_level}` : "ยังไม่ใช้"}</dd>
                </div>
                <div>
                  <dt>รอบซ่อมเสริม</dt>
                  <dd>{selected.remedial_round ?? "–"}</dd>
                </div>
              </dl>
              <div className="callout callout-accent">
                <div className="stack stack-sm">
                  <span className="xsmall strong">กฎล่าสุดที่ทำงาน</span>
                  <span className="small">{selected.last_rule ?? "–"}</span>
                  {!!selected.last_edges.length && (
                    <span className="row row-sm xsmall">
                      {selected.last_edges.map((e, i) => (
                        <span key={i} className="row row-sm">
                          {i > 0 && <ArrowRight size={11} />}
                          <code>{e}</code>
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              </div>
              <ol className="timeline timeline-compact">
                {(detail.data?.decisions ?? []).slice(0, 6).map((d) => (
                  <li key={d.id}>
                    <span className="timeline-time num">{clock(d.ts)}</span>
                    <div className="stack" style={{ gap: 2 }}>
                      <span className="small">{d.rule}</span>
                      {d.from_pos !== d.to_pos && (
                        <span className="row row-sm xsmall faint">
                          {flow.labels[d.from_pos] ?? d.from_pos}
                          <ArrowRight size={12} />
                          {flow.labels[d.to_pos] ?? d.to_pos}
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </Card>
      </div>

      <AnswerSheet code={code} />

      <Section num="3.2" title="บันไดคำใบ้และการสับราง (Scaffolding Logic)" sub="กฎเหล็ก: ไม่เฉลยคำตอบสำเร็จรูป ทุกระดับเป็นคำถามนำให้คิดต่อ และคำใบ้ระดับ 3 แสดงแค่ขั้นแรก">
        <div className="grid grid-2">
          <Card>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>เมื่อ</th>
                    <th>ระบบทำอะไร</th>
                    <th>ผล</th>
                  </tr>
                </thead>
                <tbody>
                  {LADDER.map((row) => (
                    <tr key={row.when}>
                      <td className="small strong nowrap">{row.when}</td>
                      <td className="small muted">{row.what}</td>
                      <td className="small nowrap">{row.level}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div className="stack">
            <Card className="card-pad stack stack-sm">
              <h3 className="subtitle">Hint Floor</h3>
              <p className="small muted">
                ถ้าคำตอบตรงกับ Misconception ใน Bug Library คำใบ้เริ่มที่ระดับ 2 ทันทีและบันทึกให้ครูเห็น ถ้าเป็นการคำนวณพลาดของคนที่มีประวัติทำถูก (Mastery ≥ 0.5)
                นับเป็น Slip ได้แค่ระดับ 1 สะกิดให้ตรวจทาน
              </p>
            </Card>
            <Card className="card-pad stack stack-sm">
              <h3 className="subtitle">Isomorphic Test และ Remedial Loop</h3>
              <p className="small muted">
                ผ่านข้อด้วยคำใบ้แล้ว ข้อถัดไปเปลี่ยนตัวเลขแต่คงโครงสร้างและปิดคำใบ้ ถ้าไม่ผ่าน ข้อที่ผ่านด้วยคำใบ้ได้น้ำหนัก 0 ส่วนการติด Impasse
                จะพักข้อนั้นแล้วพาไปทบทวนพื้นฐาน ถูก 2 ข้อติดกันจึงกลับข้อเดิม และส่งซ่อมเสริมได้ไม่เกิน 2 รอบก่อนส่งต่อครู
              </p>
            </Card>
          </div>
        </div>
      </Section>

      <Section num="3.3" title="คลังข้อผิดพลาด (Bug Library): Slip กับ Misconception" sub="จำนวนครั้งที่พบนับจากคำตอบจริงของทุกคนในระบบ">
        <Card>
          {bugs.loading && !bugs.data && <Spinner />}
          {bugs.data && (
            <div className="table-wrap">
              <table className="table bug-table">
                <thead>
                  <tr>
                    <th>ประเภท</th>
                    <th>ความผิดพลาด</th>
                    <th>ลักษณะและตัวอย่าง</th>
                    <th>การตอบสนองของระบบ</th>
                    <th style={{ minWidth: 150 }}>พบแล้ว</th>
                  </tr>
                </thead>
                <tbody>
                  {bugs.data.map((b) => (
                    <tr key={b.id}>
                      <td>
                        <Badge tone={b.type === "slip" ? "calm" : "info"}>{b.type === "slip" ? "Slip" : "Misconception"}</Badge>
                        <div className="xsmall faint mono" style={{ marginTop: 4 }}>
                          {b.id}
                        </div>
                      </td>
                      <td className="small strong">{b.name}</td>
                      <td className="small muted">{b.description}</td>
                      <td className="small">
                        {b.type === "slip" ? "คำใบ้ระดับ 1 " : "คำใบ้ระดับ 2 และบันทึกให้ครู "}
                        <span className="muted">· {b.response}</span>
                      </td>
                      <td>
                        <BarList
                          rows={[{ key: b.id, label: "", value: b.hits.total, valueText: `${b.hits.total} ครั้ง`, color: b.type === "slip" ? "var(--series-2)" : "var(--series-1)" }]}
                          max={Math.max(1, ...bugs.data!.map((x) => x.hits.total))}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </Section>

      <Card>
        <CardHead title="ตำแหน่งของทุกคนตอนนี้" sub="ตารางเดียวกับผังด้านบน สำหรับอ่านโดยไม่ต้องชี้" />
        <div className="table-wrap" style={{ maxHeight: 320 }}>
          <table className="table">
            <thead>
              <tr>
                <th>รหัส</th>
                <th>ประเภท</th>
                <th>ตำแหน่ง</th>
                <th>เส้นทาง</th>
                <th>ข้อ</th>
                <th>กฎล่าสุด</th>
                <th>อยู่มาแล้ว</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.code} className="clickable" onClick={() => setCode(p.code)}>
                  <td className="mono small">{p.code}</td>
                  <td className="small">{KINDS.find((k) => k.id === p.kind)?.label}</td>
                  <td className="small">{flow.labels[p.position] ?? p.position}</td>
                  <td className="small">{PATH_LABELS[p.path] ?? p.path}</td>
                  <td className="mono small">{p.item ?? "–"}</td>
                  <td className="small muted">{p.last_rule ?? "–"}</td>
                  <td className="small faint nowrap">{ago(p.since, now)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <NodeInspector nodeId={inspect} onClose={() => setInspect(null)} />
    </div>
  );
}
