import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, CircleSlash, Hand, Play, RotateCcw, ShieldCheck, X } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { ago, ALERT_LABEL, ALERT_TONE, clock, num, PATH_LABELS, pct, POSITION_TONE } from "../../lib/format";
import type { AiLog, Alert, Item, StaffView, StoredDecision } from "../../lib/types";
import AiLogCard from "../../components/AiLog";
import { BarList, RtBars } from "../../components/charts";
import { Badge, Button, Drawer, Empty, Field, Segmented, Spinner, Tabs, useToast } from "../../components/ui";
import { ClusterMark, riskLevel } from "./Overview";
import { useTeacher } from "./TeacherApp";
import ChatPanel from "./ChatPanel";

interface Answer {
  ts: number;
  item: string;
  raw?: string;
  correct?: boolean;
  rt?: number;
  rapid?: boolean;
  isomorphic?: boolean;
  error_count?: number;
  diagnosis?: { class?: string; tag?: string | null; tag_name?: string | null };
}

interface Detail {
  code: string;
  name: string | null;
  states: StaffView[];
  decisions: StoredDecision[];
  answers: Answer[];
  ai_logs: AiLog[];
  alerts: Alert[];
  cluster: { key: string; name: string } | null;
}

const MODE_LABEL: Record<string, string> = {
  main: "โจทย์หลัก",
  isomorphic: "ข้อคู่ขนาน (ไม่มีคำใบ้)",
  challenge: "โจทย์ท้าทาย",
  remedial: "โจทย์ทบทวน",
  extra: "โจทย์เพิ่ม",
};

const CLASS_LABEL: Record<string, string> = {
  misconception: "Misconception",
  slip: "Slip",
  unclassified: "ยังจัดประเภทไม่ได้",
};

const RISK_INPUTS: Record<string, string> = {
  error_rate: "อัตราตอบผิด",
  disengagement: "สัญญาณถอดใจ",
  slowness: "เวลาคิดเทียบที่คาด",
};

export type DrawerTab = "now" | "messages" | "timeline" | "answers" | "ai";

export default function StudentDrawer({
  code,
  tab,
  onTab,
  onClose,
}: {
  code: string | null;
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
  onClose: () => void;
}) {
  const { lastEvent, nameOf, unread } = useTeacher();
  const setTab = onTab;
  const detail = useLoad(() => (code ? api<Detail>("teacher", `/api/teacher/students/${code}`) : Promise.resolve(null)), [code]);

  // นักเรียนคนนี้มีความเคลื่อนไหว: โหลดใหม่ (รวบหลายเหตุการณ์ติดกันเป็นครั้งเดียว)
  useEffect(() => {
    if (!code || lastEvent?.code !== code) return;
    const id = setTimeout(detail.reload, 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  // เปิดแท็บข้อความมาโดยตรง (เช่น จากปุ่มตอบกลับ) ถือว่าอ่านแล้ว
  useEffect(() => {
    if (code && tab === "messages") onTab("messages");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const data = detail.data;
  const name = data?.name ?? (code ? nameOf(code) : null);

  return (
    <Drawer
      open={!!code}
      onClose={onClose}
      title={
        <div className="stack" style={{ gap: 2 }}>
          <span className="subtitle">{name ?? code}</span>
          <span className="row row-sm xsmall faint">
            <span className="mono">{code}</span>
            {data?.cluster && (
              <>
                ·<ClusterMark cluster={data.cluster} />
              </>
            )}
          </span>
        </div>
      }
    >
      {detail.loading && !data && <Spinner />}
      {detail.error && <Empty>{detail.error}</Empty>}
      {data && (
        <div className="stack">
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { id: "now", label: "ตอนนี้และ Override" },
              { id: "messages", label: unread[data.code] ? `ข้อความ (${unread[data.code]} ใหม่)` : "ข้อความ" },
              { id: "timeline", label: "ไทม์ไลน์การตัดสินใจ" },
              { id: "answers", label: "คำตอบ" },
              { id: "ai", label: `AI (${data.ai_logs.length})` },
            ]}
          />
          {tab === "now" && (
            <div className="stack stack-lg">
              {data.states.length === 0 && <Empty>นักเรียนคนนี้ยังไม่เริ่มชุดคำถามใด</Empty>}
              {data.states.map((state) => (
                <StatePanel key={state.set_id} state={state} code={data.code} onDone={detail.reload} />
              ))}
              {data.alerts.length > 0 && (
                <section className="stack stack-sm">
                  <h4 className="small strong">การแจ้งเตือนของนักเรียนคนนี้</h4>
                  {data.alerts.map((a) => (
                    <div key={a.id} className="row row-sm small">
                      <Badge tone={ALERT_TONE[a.level]}>{ALERT_LABEL[a.level]}</Badge>
                      <span className="grow">{a.message}</span>
                      <span className="xsmall faint">{ago(a.ts)}</span>
                    </div>
                  ))}
                </section>
              )}
            </div>
          )}
          {tab === "messages" && <ChatPanel code={data.code} name={name ?? data.code} position={data.states[0]?.position ?? null} />}
          {tab === "timeline" && <Timeline decisions={data.decisions} />}
          {tab === "answers" && <Answers answers={data.answers} />}
          {tab === "ai" && (
            <div className="stack stack-sm">
              {data.ai_logs.length === 0 && <Empty>ยังไม่มีการเรียก AI ของนักเรียนคนนี้</Empty>}
              {data.ai_logs.map((log) => (
                <AiLogCard key={log.id} log={log} />
              ))}
            </div>
          )}
        </div>
      )}
    </Drawer>
  );
}

function StatePanel({ state, code, onDone }: { state: StaffView; code: string; onDone: () => void }) {
  const names = state.concept_names ?? {};
  const risk = riskLevel(state.risk?.score);
  const item = state.item;
  const mastery = Object.entries(state.mastery ?? {});
  return (
    <section className="stack">
      <div className="spread">
        <div className="stack" style={{ gap: 2 }}>
          <span className="eyebrow">{state.set_name}</span>
          <span className="row row-sm">
            {state.position && (
              <Badge tone={POSITION_TONE[state.position] ?? "neutral"} dot>
                {state.teacher_text}
              </Badge>
            )}
            <span className="xsmall faint">ตั้งแต่ {clock(state.position_since)}</span>
          </span>
        </div>
        <span className="small muted">เส้นทาง {state.path ? PATH_LABELS[state.path] ?? state.path : "–"}</span>
      </div>

      {item && (
        <div className="callout callout-calm">
          <div className="stack stack-sm grow">
            <span className="small">
              <span className="strong mono">{item.id}</span> · {MODE_LABEL[item.mode] ?? item.mode} · {state.item_concept_name}
            </span>
            <span className="small muted">
              ตอบผิดในข้อนี้ {item.error_count} ครั้ง · คำใบ้ถึงระดับ {item.hint_level}
              {item.hint_floor > 1 ? ` (เริ่มที่ระดับ ${item.hint_floor} ตาม Hint Floor)` : ""}
              {item.last_class ? ` · ล่าสุดเป็น ${CLASS_LABEL[item.last_class] ?? item.last_class}` : ""}
            </span>
            {state.remedial && (
              <span className="small muted">
                กำลังทบทวน {state.remedial_concept_name} รอบที่ {state.remedial.round} · ถูกติดกัน {state.remedial.streak} ข้อ · พักข้อ{" "}
                <span className="mono">{state.remedial.suspended}</span> ไว้
              </span>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-2">
        <div className="stack stack-sm">
          <h4 className="small strong">Mastery ต่อมโนทัศน์</h4>
          <BarList
            max={1}
            rows={mastery.map(([concept, value]) => ({
              key: concept,
              label: names[concept] ?? concept,
              sub: [concept === state.target ? "เป้าหมาย" : null, state.cross_format?.[concept] ? "Cross-Format: ลดน้ำหนักปรนัย" : null]
                .filter(Boolean)
                .join(" · "),
              value: value ?? 0,
              valueText: value == null ? "ยังไม่มีข้อมูล" : pct(value),
              color: "var(--accent)",
            }))}
          />
        </div>
        <div className="stack stack-sm">
          <h4 className="small strong row row-sm">
            Risk Score (Fuzzy)
            {state.risk && (
              <span className="row row-sm">
                <span className="num">{Math.round(state.risk.score)}</span>
                <Badge tone={risk.tone}>{risk.label}</Badge>
              </span>
            )}
          </h4>
          <dl className="kv">
            {Object.entries(state.risk?.inputs ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt>{RISK_INPUTS[key] ?? key}</dt>
                <dd className="num">{key === "slowness" ? `${num(value, 2)} เท่า` : pct(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="xsmall faint">แสดงเฉพาะครู นักเรียนไม่เห็นตัวเลขนี้ (Anti-Labeling)</p>
        </div>
      </div>

      <div className="stack stack-sm">
        <h4 className="small strong">ตัวแปรจากร่องรอยดิจิทัล</h4>
        <div className="trace-grid">
          <TraceStat label="Attempt ทั้งหมด" value={num(state.attempts)} />
          <TraceStat label="Item Accuracy" value={pct(state.accuracy)} />
          <TraceStat label="Response Time เฉลี่ย" value={state.avg_rt != null ? `${num(state.avg_rt, 1)} วิ` : "–"} />
          <TraceStat label="First Attempt Success" value={num(state.first_attempt_success)} />
          <TraceStat label="Hint Abuse Index" value={num(state.hint_abuse_index)} />
          <TraceStat label="Rapid Guess" value={num(state.rapid_total)} />
          <TraceStat label="Content Revisit" value={num(state.content_revisits)} />
          <TraceStat label="Idle Pause" value={num(state.idle_count)} />
        </div>
      </div>

      {item && item.rts.length > 0 && (
        <div className="stack stack-sm">
          <h4 className="small strong">เวลาคิดแต่ละครั้งในข้อนี้ (ใช้ดูแนวโน้มก่อนตัดสิน Impasse)</h4>
          <RtBars values={item.rts} />
        </div>
      )}

      <OverridePanel state={state} code={code} onDone={onDone} />
    </section>
  );
}

function TraceStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="trace-stat">
      <span className="xsmall faint">{label}</span>
      <span className="strong num">{value}</span>
    </div>
  );
}

type OverrideAction = "set_item" | "set_path" | "set_mastery" | "end_session";

function OverridePanel({ state, code, onDone }: { state: StaffView; code: string; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [action, setAction] = useState<OverrideAction>("set_item");
  const [reason, setReason] = useState("");
  const [itemId, setItemId] = useState("");
  const [path, setPath] = useState(state.path ?? "STANDARD");
  const [concept, setConcept] = useState(state.target ?? "");
  const [value, setValue] = useState(0.6);
  const subject = useLoad(
    () => (state.subject_id ? api<{ items: Item[] }>("teacher", `/api/teacher/subjects/${state.subject_id}`) : Promise.resolve(null)),
    [state.subject_id],
  );
  const items = useMemo(() => subject.data?.items ?? [], [subject.data]);
  const names = state.concept_names ?? {};

  const send = async (name: string, params: Record<string, unknown> = {}) => {
    setBusy(name);
    try {
      await api("teacher", `/api/teacher/students/${code}/override`, {
        body: { set_id: state.set_id, action: name, params, reason },
      });
      toast("ส่งคำสั่งแล้ว ระบบบันทึกไว้ในประวัติการแทรกแซง", "success");
      setReason("");
      onDone();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ส่งคำสั่งไม่สำเร็จ", "warning");
    } finally {
      setBusy(null);
    }
  };

  const primary =
    state.position === "SAFETY_STOP"
      ? { action: "release", label: "ครูคุยกับนักเรียนแล้ว ให้เรียนต่อ", icon: <ShieldCheck size={16} /> }
      : state.position === "STAGNATION_DEADLOCK"
        ? { action: "release", label: "ปลดล็อก ให้ลองข้อนี้ใหม่", icon: <Hand size={16} /> }
        : state.ended
          ? { action: "resume", label: "เปิดให้เรียนต่อ", icon: <Play size={16} /> }
          : { action: "reset_item", label: "เริ่มข้อนี้ใหม่", icon: <RotateCcw size={16} /> };

  return (
    <section className="override">
      <div className="spread">
        <div className="stack" style={{ gap: 2 }}>
          <h4 className="subtitle">Manual Override</h4>
          <p className="xsmall muted">ครูเป็นผู้ตัดสินใจขั้นสุดท้ายเสมอ ทุกคำสั่งถูกบันทึกพร้อมเหตุผล</p>
        </div>
        <Button variant="primary" icon={primary.icon} loading={busy === primary.action} onClick={() => send(primary.action)}>
          {primary.label}
        </Button>
      </div>
      <Segmented
        label="คำสั่งเพิ่มเติม"
        value={action}
        onChange={setAction}
        options={[
          { id: "set_item", label: "เปลี่ยนโจทย์" },
          { id: "set_path", label: "ตั้งเส้นทาง" },
          { id: "set_mastery", label: "แก้ Mastery" },
          { id: "end_session", label: "จบ Session" },
        ]}
      />
      {action === "set_item" && (
        <Field label="ให้ทำโจทย์ข้อ">
          <select className="select" value={itemId} onChange={(e) => setItemId(e.target.value)}>
            <option value="">เลือกโจทย์</option>
            {Object.entries(groupBy(items, (it) => it.concept)).map(([c, list]) => (
              <optgroup key={c} label={names[c] ?? c}>
                {list.map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.id} · {it.math || it.prompt.slice(0, 40)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>
      )}
      {action === "set_path" && (
        <Segmented
          label="เส้นทาง"
          value={path}
          onChange={setPath}
          options={Object.entries(PATH_LABELS).map(([id, label]) => ({ id, label }))}
        />
      )}
      {action === "set_mastery" && (
        <div className="grid grid-2">
          <Field label="มโนทัศน์">
            <select className="select" value={concept} onChange={(e) => setConcept(e.target.value)}>
              {Object.keys(state.mastery ?? {}).map((c) => (
                <option key={c} value={c}>
                  {names[c] ?? c}
                </option>
              ))}
            </select>
          </Field>
          <Field label={`ค่าใหม่: ${pct(value)}`}>
            <input type="range" min={0} max={1} step={0.05} value={value} onChange={(e) => setValue(Number(e.target.value))} />
          </Field>
        </div>
      )}
      {action === "end_session" && (
        <p className="small muted">จบ Session นี้ ความคืบหน้ายังอยู่ครบ นักเรียนกลับมาเริ่ม Session ใหม่ต่อจากเดิมได้</p>
      )}
      <Field label="เหตุผล (ไม่บังคับ)">
        <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="เช่น คุยกับนักเรียนแล้ว เข้าใจเรื่องเครื่องหมายแล้ว" />
      </Field>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Button
          variant={action === "end_session" ? "danger" : "secondary"}
          icon={action === "end_session" ? <CircleSlash size={16} /> : <Check size={16} />}
          loading={busy === action}
          disabled={action === "set_item" && !itemId}
          onClick={() =>
            send(
              action,
              action === "set_item" ? { item_id: itemId } : action === "set_path" ? { path } : action === "set_mastery" ? { concept, value } : {},
            )
          }
        >
          ส่งคำสั่ง
        </Button>
      </div>
    </section>
  );
}

function groupBy<T>(list: T[], key: (value: T) => string) {
  const out: Record<string, T[]> = {};
  for (const value of list) (out[key(value)] ??= []).push(value);
  return out;
}

function Timeline({ decisions }: { decisions: StoredDecision[] }) {
  if (!decisions.length) return <Empty>ยังไม่มีการตัดสินใจ</Empty>;
  return (
    <ol className="timeline">
      {decisions.map((d, i) => (
        <li key={i}>
          <span className="timeline-time num">{clock(d.ts)}</span>
          <div className="stack" style={{ gap: 2 }}>
            <span className="small">{d.rule}</span>
            {d.from_pos !== d.to_pos && (
              <span className="row row-sm xsmall faint">
                {d.from_text}
                <ArrowRight size={12} />
                {d.to_text}
              </span>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Answers({ answers }: { answers: Answer[] }) {
  if (!answers.length) return <Empty>ยังไม่มีคำตอบ</Empty>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>เวลา</th>
            <th>ข้อ</th>
            <th>คำตอบ</th>
            <th>ผล</th>
            <th className="num">เวลาคิด</th>
            <th>การวินิจฉัย</th>
          </tr>
        </thead>
        <tbody>
          {answers.map((a, i) => (
            <tr key={i}>
              <td className="xsmall faint num">{clock(a.ts)}</td>
              <td className="mono small">{a.item}</td>
              <td className="mono small">{a.raw}</td>
              <td>
                {a.correct ? (
                  <Badge tone="success">
                    <Check size={13} />
                    ถูก
                  </Badge>
                ) : a.rapid ? (
                  <Badge tone="warning">ตอบเร็วเกิน (โมฆะ)</Badge>
                ) : (
                  <Badge tone="calm">
                    <X size={13} />
                    ยังไม่ถูก
                  </Badge>
                )}
              </td>
              <td className="num small">{a.rt != null ? `${num(a.rt, 1)} วิ` : "–"}</td>
              <td className="small">
                {a.diagnosis?.class ? (
                  <span>
                    {CLASS_LABEL[a.diagnosis.class] ?? a.diagnosis.class}
                    {a.diagnosis.tag_name ? `: ${a.diagnosis.tag_name}` : ""}
                  </span>
                ) : (
                  <span className="faint">{a.isomorphic ? "ข้อคู่ขนาน" : "–"}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
