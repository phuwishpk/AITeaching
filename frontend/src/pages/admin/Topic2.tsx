import { useEffect, useMemo, useState } from "react";
import { EyeOff, GraduationCap, Layers, MonitorSmartphone, UserRoundSearch } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { clock, num, PATH_LABELS, pct } from "../../lib/format";
import type { StaffView } from "../../lib/types";
import KnowledgeMap from "../../components/KnowledgeMap";
import { Badge, Card, CardHead, Empty, Spinner } from "../../components/ui";
import { encouragement } from "../student/Workspace";
import { TopicHeader, useAdmin } from "./AdminApp";
import { CodePicker, Section, TopicLink, useTopics } from "./shared";

export interface AdminStudentRow {
  code: string;
  kind: string;
  persona: string | null;
  position: string | null;
}

export interface AdminStudentDetail {
  code: string;
  kind: string | null;
  persona: string | null;
  states: (StaffView & { student_view: any; risk_detail: any })[];
  decisions: { id: number; ts: number; from_pos: string; to_pos: string; rule: string; edges: string[]; detail: Record<string, any> }[];
  traces: { ts: number; action: string; target: string | null; data: Record<string, any> }[];
  features: { avg_rt: number; accuracy: number; session_min: number } | null;
  cluster: { key: string; name: string } | null;
}

// เลือกนักเรียนเริ่มต้น: คนที่กำลังเรียนอยู่ ให้ความสำคัญกับนักเรียนจริงและนักเรียนสาธิตก่อน
export function useStudentPicker() {
  const { lastEvent } = useAdmin();
  const students = useLoad(() => api<AdminStudentRow[]>("admin", "/api/admin/students"));
  const [code, setCode] = useState<string | null>(null);
  useEffect(() => {
    if (code || !students.data) return;
    const rank = (s: AdminStudentRow) => (s.position ? 0 : 3) + (s.kind === "demo" ? 0 : s.kind === "real" ? 1 : 2);
    const first = [...students.data].sort((a, b) => rank(a) - rank(b))[0];
    if (first) setCode(first.code);
  }, [students.data, code]);
  const detail = useLoad(
    () => (code ? api<AdminStudentDetail>("admin", `/api/admin/students/${code}`) : Promise.resolve(null)),
    [code],
  );
  useEffect(() => {
    if (!code || lastEvent?.code !== code) return;
    const id = setTimeout(detail.reload, 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);
  return { students: students.data ?? [], code, setCode, detail };
}

const FEATURE_VALUE: Record<string, (s: StaffView) => string> = {
  "Response Time": (s) => (s.avg_rt != null ? `${num(s.avg_rt, 1)} วินาที (เฉลี่ย)` : "–"),
  "First Attempt Success": (s) => `${num(s.first_attempt_success)} ข้อ`,
  "Item Accuracy": (s) => pct(s.accuracy),
  "Hint Abuse Index": (s) => num(s.hint_abuse_index),
  "Content Revisit": (s) => `${num(s.content_revisits)} ครั้ง`,
  "Error Count": (s) => (s.item ? `${s.item.error_count} ครั้ง ในข้อ ${s.item.id}` : "–"),
};

const ACTION_LABEL: Record<string, string> = {
  answer: "ส่งคำตอบ",
  hint_request: "กดขอคำใบ้",
  hint_abuse: "กดคำใบ้รัว",
  chat: "พิมพ์แชต",
  choose_path: "เลือกทางต่อ",
  content_revisit: "เปิดทบทวนเนื้อหา",
  undo: "ยกเลิกคำตอบ",
  restart_item: "เริ่มข้อใหม่",
  resume_session: "กลับเข้า Session",
  invalid_answer: "คำตอบผิดรูปแบบ (ไม่นับ)",
  duplicate_ignored: "ส่งซ้ำ (รวบเป็นครั้งเดียว)",
  misconception: "บันทึก Misconception",
  walkthrough_done: "อ่านตัวอย่างจบ",
};

export default function Topic2() {
  const data = useTopics();
  const { students, code, setCode, detail } = useStudentPicker();
  const map = useLoad(
    () => api<any>("admin", `/api/admin/knowledge-map${code ? `?code=${code}` : ""}`),
    [code, detail.data],
  );
  const labeling = useLoad(
    () => (code ? api<any>("admin", `/api/admin/anti-labeling/${code}`).catch(() => null) : Promise.resolve(null)),
    [code, detail.data],
  );
  const state = detail.data?.states[0];
  const models = data?.topics["2"]?.models ?? [];
  const mapping = data?.topics["2"]?.data_mapping ?? [];
  const icons = useMemo(
    () => ({
      domain: <Layers size={18} />,
      student: <UserRoundSearch size={18} />,
      pedagogical: <GraduationCap size={18} />,
      ui: <MonitorSmartphone size={18} />,
    }),
    [],
  );

  if (!data) return <Spinner />;

  return (
    <div className="page topic stack stack-lg">
      <TopicHeader id="2" lead="ระบบ ITS แบ่งเป็น 4 แบบจำลองที่ทำงานร่วมกัน ฝั่งหน้าบ้านเก็บร่องรอยและแสดงผล (LA) ฝั่งหลังบ้านคำนวณและตัดสินใจ (EDM)">
        <CodePicker codes={students} value={code} onChange={setCode} label="ดูข้อมูลจริงของ" />
      </TopicHeader>

      <Card className="card-pad">
        <figure className="figure">
          <ArchitectureDiagram />
          <figcaption className="xsmall muted">
            ร่องรอยจากหน้านักเรียนผ่านการกรองและกฎ 3 ด่านก่อน แล้วโมดูล 2 ประเมินสถานะผู้เรียน ส่วนข้อความแชตไปถึง LLM หลังลบข้อมูลส่วนตัว
            และทุกคำตอบของ LLM ต้องผ่าน Guard ก่อนถึงนักเรียน
          </figcaption>
        </figure>
      </Card>

      <div className="grid grid-4">
        {models.map((m: { key: keyof typeof icons; name: string; question: string; principle: string }, i: number) => (
          <Card key={m.key} className="card-pad stack stack-sm model-card">
            <span className="row row-sm">
              <span className="role-icon role-icon-sm">{icons[m.key]}</span>
              <span className="eyebrow">2.{i + 1}</span>
            </span>
            <h3 className="subtitle">{m.name}</h3>
            <p className="small strong">{m.question}</p>
            <p className="small muted">{m.principle}</p>
          </Card>
        ))}
      </div>

      <Section
        num="2.1"
        title="Domain Model: แผนผังความรู้"
        sub="มโนทัศน์เป้าหมายกับความรู้พื้นฐานที่ต้องรู้ก่อน แถบใต้แต่ละกล่องคือ Mastery ของนักเรียนที่เลือก"
      >
        <Card className="card-pad">
          {map.data ? (
            <KnowledgeMap concepts={map.data.concepts} target={map.data.target} mastery={map.data.mastery} counts={map.data.items} />
          ) : (
            <Spinner />
          )}
        </Card>
      </Section>

      <Section
        num="2.2"
        title="Student Model: จากร่องรอยดิจิทัลเป็นตัวแปร"
        sub="ทุกการกระทำบันทึกเป็น [วัน-เวลา] + [รหัสผู้เรียน] + [คำสั่งการกระทำ] + [วัตถุเป้าหมาย] แล้วแปลงเป็นตัวแปร (Feature Engineering)"
      >
        <div className="grid grid-2">
          <Card>
            <CardHead title="ร่องรอยล่าสุด (Digital Traces)" sub={code ? `ของ ${code}` : undefined} />
            <div className="table-wrap">
              <table className="table trace-table">
                <thead>
                  <tr>
                    <th>วัน-เวลา</th>
                    <th>รหัสผู้เรียน</th>
                    <th>การกระทำ</th>
                    <th>วัตถุเป้าหมาย</th>
                  </tr>
                </thead>
                <tbody>
                  {(detail.data?.traces ?? []).slice(0, 10).map((t, i) => (
                    <tr key={i}>
                      <td className="mono xsmall">{new Date(t.ts * 1000).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "medium" })}</td>
                      <td className="mono xsmall">{code}</td>
                      <td className="small">
                        {ACTION_LABEL[t.action] ?? t.action}
                        {t.action === "answer" && t.data?.rt != null && <span className="xsmall faint"> · {num(t.data.rt, 1)} วิ</span>}
                      </td>
                      <td className="mono xsmall">{t.target ?? "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!detail.data?.traces.length && <Empty>ยังไม่มีร่องรอย</Empty>}
            </div>
          </Card>
          <Card>
            <CardHead title="ตัวแปรที่ได้ (Features)" sub="ค่าจริงของนักเรียนที่เลือก คำนวณใหม่ทุกครั้งที่มีการกระทำ" />
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>ร่องรอย</th>
                    <th>ตัวแปร</th>
                    <th>ค่าตอนนี้</th>
                  </tr>
                </thead>
                <tbody>
                  {mapping.map((m: { trace: string; variable: string }) => (
                    <tr key={m.variable}>
                      <td className="small muted">{m.trace}</td>
                      <td className="small strong nowrap">{m.variable}</td>
                      <td className="small num nowrap">{state ? FEATURE_VALUE[m.variable]?.(state) ?? "–" : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {detail.data?.features && (
              <p className="xsmall faint" style={{ padding: "0 22px 18px" }}>
                ตัวแปรที่ K-Means ใช้: เวลาคิดเฉลี่ย {num(detail.data.features.avg_rt, 1)} วิ · ตอบถูก {pct(detail.data.features.accuracy)} · Session เฉลี่ย{" "}
                {num(detail.data.features.session_min, 1)} นาที (<TopicLink to="4">แท็บ 4</TopicLink>)
              </p>
            )}
          </Card>
        </div>
      </Section>

      <Section num="2.3" title="Pedagogical Model: สอนอย่างไร" sub="Constructivism ให้นักเรียนเผชิญความไม่สมดุลทางปัญญาและสร้างความรู้เอง โดยมีกลยุทธ์ 3 ด้านคอยประคองให้อยู่ใน ZPD">
        <div className="grid grid-4">
          <StrategyCard title="Productive Struggle" text="หน่วงเวลา 15 วินาทีหลังผิดครั้งแรก ให้ลองแก้เองก่อน ถ้าแก้ได้เองได้น้ำหนัก 0.8 โดยไม่ต้องใช้คำใบ้" node="DELIBERATE_DELAY" />
          <StrategyCard title="Scaffolding Strategies" text="คำใบ้ 3 ระดับแบบ Socratic สะกิด อธิบายกฎ ชี้ขั้นแรก ไม่มีระดับไหนที่เฉลย" node="HINT_L1" />
          <StrategyCard title="Content Sequencing" text="ติด Impasse แล้วพาไปทบทวน Prerequisite ตามแผนผังความรู้ ผ่านแล้วกลับข้อเดิม" node="REMEDIAL" />
          <StrategyCard title="Dynamic Difficulty" text="Fuzzy Logic เลือกความยากข้อถัดไปจาก Mastery และเวลาคิด ให้ท้าทายพอดีกับเขตพัฒนาการ" node="G_PATH" />
        </div>
      </Section>

      <Section
        num="2.4"
        title="User Interface: Anti-Labeling"
        sub="โจทย์กับคำใบ้อยู่หน้าจอเดียวกันเพื่อลด Split-Attention และนักเรียนไม่เห็นตัวเลขความเสี่ยงหรือชื่อกลุ่ม เห็นเพียงแถบความก้าวหน้ากับข้อความเชิงบวก"
      >
        {labeling.data ? <AntiLabeling data={labeling.data} /> : <Card className="card-pad"><Empty>เลือกนักเรียนที่เริ่มเรียนแล้วเพื่อเทียบสองมุมมอง</Empty></Card>}
      </Section>
    </div>
  );
}

function StrategyCard({ title, text, node }: { title: string; text: string; node: string }) {
  return (
    <Card className="card-pad stack stack-sm">
      <h3 className="subtitle">{title}</h3>
      <p className="small muted grow">{text}</p>
      <TopicLink to={`3?node=${node}`}>ดูในผังตรรกะ</TopicLink>
    </Card>
  );
}

export function AntiLabeling({ data, linkToEthics = true }: { data: { student_view: any; staff_view: StaffView }; linkToEthics?: boolean }) {
  const s = data.student_view;
  const t = data.staff_view;
  return (
    <div className="grid grid-2">
      <Card className="card-pad stack">
        <div className="spread">
          <span className="eyebrow">สิ่งที่นักเรียนเห็น</span>
          <Badge tone="accent">หน้านักเรียน</Badge>
        </div>
        <div className="mini-screen stack">
          <span className="small muted">
            {s.set?.name} · {s.target?.name}
          </span>
          <div className="spread small">
            <span className="muted">ความชำนาญเรื่องนี้</span>
            <span className="muted">{encouragement(s.mastery ?? 0, false)}</span>
          </div>
          <div className="mastery">
            <div className="mastery-fill" style={{ width: `${Math.max(4, (s.mastery ?? 0) * 100)}%` }} />
          </div>
          {s.item && <div className="problem-math small-math">{s.item.math ?? s.item.prompt}</div>}
          {s.label && <p className="small muted">{s.label}</p>}
        </div>
        <ul className="point-list small">
          <li>ไม่มีตัวเลข Risk Score ไม่มีชื่อกลุ่ม</li>
          <li>ไม่มีสีแดงเตือน ใช้ข้อความเชิงบวกแทน</li>
          <li>แถบความก้าวหน้าเริ่มที่อย่างน้อย 4% เสมอ ไม่ให้เห็นแถบว่าง</li>
        </ul>
      </Card>
      <Card className="card-pad stack">
        <div className="spread">
          <span className="eyebrow">สิ่งที่ครูเห็น (คนเดียวกัน เวลาเดียวกัน)</span>
          <Badge tone="calm">
            <EyeOff size={13} />
            ซ่อนจากนักเรียน
          </Badge>
        </div>
        <dl className="kv">
          <div>
            <dt>ตำแหน่งในผัง</dt>
            <dd>{t.position_label}</dd>
          </div>
          <div>
            <dt>Risk Score (Fuzzy)</dt>
            <dd className="num">{t.risk ? Math.round(t.risk.score) : "–"}</dd>
          </div>
          <div>
            <dt>เส้นทาง</dt>
            <dd>{t.path ? PATH_LABELS[t.path] ?? t.path : "–"}</dd>
          </div>
          <div>
            <dt>Mastery เป้าหมาย</dt>
            <dd className="num">{t.target ? pct(t.mastery?.[t.target]) : "–"}</dd>
          </div>
          <div>
            <dt>อัตราตอบถูก</dt>
            <dd className="num">{pct(t.accuracy)}</dd>
          </div>
          <div>
            <dt>Rapid Guess / Hint Abuse</dt>
            <dd className="num">
              {num(t.rapid_total)} / {num(t.hint_abuse_index)}
            </dd>
          </div>
          <div>
            <dt>การตัดสินใจล่าสุด</dt>
            <dd>
              {t.last_decision?.rule ?? "–"} <span className="xsmall faint">{clock(t.last_decision?.ts)}</span>
            </dd>
          </div>
        </dl>
        <p className="xsmall muted">
          ตัวเลขอยู่ฝั่งครูเท่านั้น เพื่อไม่ให้ผลพยากรณ์กลายเป็นคำทำนายที่เป็นจริงเอง
          {linkToEthics && (
            <>
              {" "}
              (<TopicLink to="7">แท็บ 7</TopicLink>)
            </>
          )}
        </p>
      </Card>
    </div>
  );
}

function DBox({ x, y, w, h = 56, title, sub, tone }: { x: number; y: number; w: number; h?: number; title: string; sub: string; tone?: "accent" | "muted" }) {
  return (
    <g className={`dg-box ${tone === "accent" ? "dg-accent" : tone === "muted" ? "dg-muted" : ""}`}>
      <rect x={x} y={y} width={w} height={h} rx={11} />
      <text x={x + 14} y={y + (h > 50 ? 24 : 20)} className="dg-box-title">
        {title}
      </text>
      <text x={x + 14} y={y + (h > 50 ? 42 : 35)} className="dg-box-sub">
        {sub}
      </text>
    </g>
  );
}

function DArrow({ d, label, lx, ly, anchor = "middle" }: { d: string; label: string; lx: number; ly: number; anchor?: "start" | "middle" | "end" }) {
  return (
    <g className="dg-arrow">
      <path d={d} markerEnd="url(#arch-head)" />
      <text x={lx} y={ly} textAnchor={anchor} className="dg-label">
        {label}
      </text>
    </g>
  );
}

function ArchitectureDiagram() {
  return (
    <svg viewBox="0 0 900 420" className="diagram" role="img" aria-label="สถาปัตยกรรม: หน้านักเรียนส่งร่องรอยไปโมดูล 1 กรองและใช้กฎ 3 ด่าน โมดูล 2 ใช้ Fuzzy และ K-Means ประเมินผู้เรียนและส่งให้หน้าครู โมดูล 3 ใช้ RAG และ LLM สร้างคำใบ้ผ่าน Guard">
      <defs>
        <marker id="arch-head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>
      <text x={20} y={16} className="dg-title">
        หน้าบ้าน · Learning Analytics
      </text>
      <text x={300} y={16} className="dg-title">
        หลังบ้าน · Educational Data Mining
      </text>
      <text x={670} y={16} className="dg-title">
        ข้อมูลและบริการ
      </text>

      <DBox x={20} y={30} w={210} title="หน้านักเรียน" sub="โจทย์ · คำใบ้ · แชต · Mastery Bar" tone="accent" />
      <DBox x={20} y={290} w={210} title="หน้าครู" sub="Risk · กลุ่ม · แจ้งเตือน · Override" tone="accent" />
      <DBox x={300} y={30} w={300} title="โมดูล 1 · Data Cleaning + กฎ 3 ด่าน" sub="Nested If-Else · Rapid Guess · Hint Abuse" />
      <DBox x={300} y={160} w={240} title="โมดูล 2 · Fuzzy Logic + K-Means" sub="Impasse · ความยาก · Risk · กลุ่มผู้เรียน" />
      <DBox x={300} y={290} w={300} title="โมดูล 3 · RAG + LLM + Guard" sub="Socratic · Context Framing 4 กรอบ" />
      <DBox x={670} y={30} w={210} title="Digital Traces" sub="SQLite ในเครื่อง · รหัสแทนชื่อ" tone="muted" />
      <DBox x={670} y={290} w={210} title="เนื้อหา · Bug Library" sub="เอกสารวิชาสำหรับ RAG" tone="muted" />
      <DBox x={670} y={366} w={210} h={46} title="Claude / Gemini" sub="ใช้เมื่อมี API key" tone="muted" />

      <DArrow d="M230,48 L298,48" label="ร่องรอย" lx={264} ly={41} />
      <DArrow d="M300,70 L232,70" label="คำใบ้ · เส้นทาง" lx={266} ly={86} />
      <DArrow d="M600,58 L668,58" label="บันทึก" lx={634} ly={51} />
      <DArrow d="M360,86 L360,158" label="RT · Error Count" lx={352} ly={126} anchor="end" />
      <DArrow d="M460,158 L460,88" label="Impasse · ความยาก" lx={468} ly={126} anchor="start" />
      <DArrow d="M584,86 L584,288" label="แชตที่ลบชื่อแล้ว" lx={592} ly={210} anchor="start" />
      <DArrow d="M300,182 L110,182 L110,288" label="Risk · กลุ่ม · แจ้งเตือน" lx={205} ly={175} />
      <DArrow d="M160,288 L160,204 L298,204" label="Manual Override" lx={229} ly={221} />
      <DArrow d="M600,312 L668,312" label="ค้น BM25" lx={634} ly={305} />
      <DArrow d="M450,346 L450,389 L668,389" label="prompt 4 กรอบ → ผ่าน Guard" lx={558} ly={382} />
    </svg>
  );
}
