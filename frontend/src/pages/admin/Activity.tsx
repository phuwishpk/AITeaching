import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, Bell, Bot, Check, ChevronRight, Flag, Hand, Hourglass, MousePointerClick, Play, Timer, UserRound, X } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago, clock, mmss, num } from "../../lib/format";
import { Badge, Card, CardHead, Empty, Spinner } from "../../components/ui";
import { useAdmin } from "./AdminApp";
import { useStudentPicker } from "./Topic2";
import { CodePicker } from "./shared";
import NodeInspector from "./NodeInspector";
import { eventTrail, GemFlowMap, SpecStepDrawer, type GemFlow } from "./gemFlow";
import { answerText, ItemView, type ItemBrief } from "../../components/AnswerSheet";

interface ActivityInput {
  action: string;
  target: string | null;
  data: Record<string, any>;
  item?: ItemBrief | null;
}

interface ActivityDecision {
  id: number;
  set_id?: string;
  from: string;
  to: string;
  rule: string;
  edges: string[];
  path: string[];
  path_labels: string[];
  // Flow ของ Gem: map_path คือกล่องในผังที่การตัดสินใจนี้พาผ่าน
  detail?: Record<string, unknown>;
}

interface ActivityEvent {
  code: string;
  ts: number;
  source: "student" | "system" | "teacher";
  inputs: ActivityInput[];
  decisions: ActivityDecision[];
  edges: string[];
  steps: string[];
  rules: { id: string; title: string }[];
  position: string | null;
  // Flow ที่ครูออกแบบใน Gem: ขั้นของ Flow ที่นักเรียนไปอยู่ต่อ
  step?: string | null;
  step_label?: string | null;
  // เฉพาะเส้นทางตั้งแต่ต้นจนจบ: ลำดับขั้น และจุดเริ่มหรือจุดจบ
  n?: number;
  milestone?: "start" | "completed" | "ended" | null;
}

interface JourneyRun {
  id: number;
  set_name: string;
  started: number;
  ended: number | null;
  outcome: string;
  resumed: boolean;
  // เรียนกับ Gem ตัวไหน Gem Version ไหน และคลังรุ่นไหน (null = ชุดคำถามที่ไม่ใช่ Gem)
  gem: { id: string; name: string; version: number | null; bank_version: number | null } | null;
}

// การทำงานของครูต่อนักเรียนคนนี้ (Q4): แจ้งเตือนที่ส่งถึงครู และสิ่งที่ครูทำ พร้อมเวลาที่ใช้ตอบสนอง
interface TeacherEntry {
  ts: number;
  kind: string;
  text: string;
  level?: string;
  after_alert?: number;
}

interface JourneyData {
  runs: JourneyRun[];
  run: (JourneyRun & { set_id: string }) | null;
  steps: ActivityEvent[];
  teacher: TeacherEntry[];
  summary: {
    steps: number;
    answers: number;
    correct: number;
    items: number;
    hints: number;
    duration: number;
    position: string | null;
    position_label: string | null;
    finished: boolean;
    alerts: number;
    responses: number;
  } | null;
}

const CHOICES: Record<string, string> = { rest: "พักก่อน", easier: "ทำต่อแบบง่ายลง", stop: "หยุดวันนี้" };

// แปลงร่องรอยดิบเป็นประโยคที่อ่านรู้เรื่อง: นักเรียนทำอะไร ป้อนอะไรเข้ามา
export function describeInput(input: ActivityInput) {
  const d = input.data ?? {};
  switch (input.action) {
    case "answer": {
      const result = d.correct ? "ถูก" : d.rapid ? "ผิดและเร็วเกินเวลาอ่าน" : "ผิด";
      const diag = d.diagnosis?.tag_name ? ` · ${d.diagnosis.class === "slip" ? "Slip" : d.diagnosis.class === "misconception" ? "Misconception" : "จัดประเภทไม่ได้"}: ${d.diagnosis.tag_name}` : "";
      return { text: `ตอบ "${answerText(input.item, d.raw)}" ในข้อ ${input.target}`, sub: `เวลาคิด ${num(d.rt, 1)} วินาที · ${result}${diag}` };
    }
    case "hint_request":
      return { text: "กดขอคำใบ้", sub: `กดครั้งที่ ${d.presses_in_window ?? 1} ในช่วงเวลาตรวจ` };
    case "hint_abuse":
      return { text: "กดขอคำใบ้รัวจนปุ่มถูกพัก", sub: `Hint Abuse Index ${d.index}` };
    case "chat":
      return {
        text: `พิมพ์แชต: "${d.message}"`,
        sub: [d.pii_removed?.length ? `ลบข้อมูลส่วนตัว ${d.pii_removed.join(" ")}` : null, d.distress?.level ? `พบคำว่า "${d.distress.matched}"` : null]
          .filter(Boolean)
          .join(" · "),
      };
    case "invalid_answer":
      return { text: `พิมพ์ "${d.raw}" ซึ่งผิดรูปแบบ`, sub: "ไม่นับเป็น Attempt" };
    case "duplicate_ignored":
      return { text: `ส่ง "${d.raw}" ซ้ำ`, sub: "รวบเป็นการส่งครั้งเดียว" };
    case "undo":
      return { text: "กดยกเลิกคำตอบล่าสุด", sub: d.raw ? `คำตอบที่ยกเลิก "${d.raw}"` : "" };
    case "restart_item":
      return { text: "กดเริ่มข้อนี้ใหม่", sub: `Error Count เดิม ${d.error_count ?? 0} ยังอยู่` };
    case "content_revisit":
      return { text: "เปิดทบทวนเนื้อหา", sub: input.target ?? "" };
    case "choose_path":
      return { text: `เลือกทางต่อ: ${CHOICES[input.target ?? ""] ?? input.target}`, sub: "" };
    case "walkthrough_done":
      return { text: "อ่านตัวอย่างทีละขั้นจบ", sub: "" };
    case "resume_session":
      return { text: "กลับเข้าชุดคำถามต่อจากเดิม", sub: "" };
    default:
      return { text: input.action, sub: input.target ?? "" };
  }
}

function summary(event: ActivityEvent): { text: string; sub: string; math?: string | null } {
  const shown = event.inputs.filter((i) => i.action !== "misconception");
  if (event.edges.includes("e_start")) return { text: "กดเริ่มชุดคำถาม", sub: event.decisions[0]?.rule ?? "" };
  if (shown.length) return { ...describeInput(shown[0]), math: shown[0].item?.math };
  if (event.source === "teacher") return { text: "ครูสั่ง Manual Override", sub: event.decisions[0]?.rule ?? "" };
  return { text: "ระบบเปลี่ยนสถานะเอง", sub: event.decisions[0]?.rule ?? "" };
}

const SOURCE_ICON = {
  student: <UserRound size={15} />,
  system: <Timer size={15} />,
  teacher: <Hand size={15} />,
};

const SOURCE_LABEL = { student: "นักเรียนป้อน", system: "ตัวจับเวลาของระบบ", teacher: "ครูสั่ง" };

export default function Activity() {
  const { flow, liveVersion } = useAdmin();
  const { students, code, setCode } = useStudentPicker();
  const [scope, setScope] = useState<"one" | "all">("all");
  const [includeSim, setIncludeSim] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [follow, setFollow] = useState(true);
  const [inspect, setInspect] = useState<string | null>(null);
  const [session, setSession] = useState<number | null>(null);
  const now = useNow(5000);
  const one = scope === "one" && !!code;

  const query = `?include_sim=${includeSim}&limit=60`;
  const feed = useLoad(() => (one ? Promise.resolve(null) : api<ActivityEvent[]>("admin", `/api/admin/activity${query}`)), [query, one]);
  // รายคน: ทุกการกระทำใน Session เดียว เรียงเป็นขั้นที่ 1 ถึงขั้นสุดท้าย
  const trip = useLoad(
    () => (one ? api<JourneyData>("admin", `/api/admin/students/${code}/journey${session ? `?session=${session}` : ""}`) : Promise.resolve(null)),
    [one, code, session],
  );

  useEffect(() => setSession(null), [code]);

  // ข้อมูลสดเข้ามา: โหลดใหม่แบบรวบหลายเหตุการณ์ติดกัน
  useEffect(() => {
    if (!liveVersion) return;
    const id = setTimeout(one ? trip.reload : feed.reload, 500);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveVersion]);

  const events = useMemo(() => (one ? trip.data?.steps : feed.data) ?? [], [one, trip.data, feed.data]);
  // รายการล่าสุดอยู่บนสุดของ feed แต่อยู่ท้ายสุดของเส้นทาง
  const latest = one ? events[events.length - 1] : events[0];
  useEffect(() => {
    if (!latest) return;
    if (follow || !events.some((e) => keyOf(e) === selected)) setSelected(keyOf(latest));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  const pick = (k: string) => {
    setSelected(k);
    setFollow(false);
    // เลือกรายการที่อยู่ล่าง ๆ แล้วเลื่อนกลับมาให้เห็นโจทย์และคำตอบตัวใหญ่
    const detail = document.querySelector(".event-detail");
    if (detail && detail.getBoundingClientRect().top < 70) detail.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  const event = events.find((e) => keyOf(e) === selected) ?? null;
  // ผังของ Gem ที่นักเรียนในเหตุการณ์นี้เรียนอยู่ (ผังไม่ตายตัว แต่ละ Gem มีเฉพาะขั้นที่ครูเปิดใช้)
  const eventSet = event?.decisions.find((d) => d.set_id)?.set_id ?? (one ? trip.data?.run?.set_id : undefined);
  const [setId, setSetId] = useState<string | null>(null);
  useEffect(() => {
    if (eventSet) setSetId(eventSet);
  }, [eventSet]);
  const gemFlow = useLoad(() => (setId ? api<GemFlow>("admin", `/api/gems/flow-of-set/${setId}`).catch(() => null) : Promise.resolve(null)), [setId]);
  const active = (flow?.positions ?? []).filter((p) => p.kind !== "sim" && !["COMPLETED", "SESSION_ENDED"].includes(p.position));

  if (!flow) return <Spinner />;

  return (
    <div className="page topic stack stack-lg">
      <header className="topic-head fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">กิจกรรมสด</p>
          <h1 className="title-xl">นักเรียนทำอะไร และการกระทำนั้นเข้าไปตรงไหน</h1>
          <p className="lead">
            ทุกครั้งที่นักเรียนป้อนอะไรเข้ามา หน้านี้บอกว่าการกระทำนั้นเข้าไปที่ขั้นไหนของผัง ผ่านด่านอะไรบ้าง กฎข้อไหนทำงาน และนักเรียนไปอยู่ตรงไหนต่อ
          </p>
        </div>
        <div className="row">
          <div className="seg" role="group" aria-label="ขอบเขต">
            <button aria-pressed={scope === "all"} onClick={() => setScope("all")}>
              ทุกคน
            </button>
            <button aria-pressed={scope === "one"} onClick={() => setScope("one")}>
              รายคน
            </button>
          </div>
          {scope === "one" ? (
            <CodePicker codes={students} value={code} onChange={setCode} label="นักเรียน" />
          ) : (
            <label className="check">
              <input type="checkbox" checked={includeSim} onChange={(e) => setIncludeSim(e.target.checked)} />
              รวมนักเรียนจำลอง
            </label>
          )}
        </div>
      </header>

      <section className="stack stack-sm">
        <h2 className="subtitle">ตอนนี้แต่ละคนทำอะไรอยู่</h2>
        {active.length === 0 ? (
          <p className="small faint">ยังไม่มีนักเรียนจริงหรือนักเรียนสาธิตที่กำลังทำชุดคำถาม</p>
        ) : (
          <div className="now-grid">
            {active.map((p) => (
              <button
                key={p.code}
                className={`now-card ${scope === "one" && code === p.code ? "is-on" : ""}`}
                onClick={() => {
                  setScope("one");
                  setCode(p.code);
                }}
              >
                <span className="row row-sm">
                  <span className={`chip-dot chip-kind-${p.kind}`} />
                  <span className="mono strong small">{p.code}</span>
                  <span className="xsmall faint">{ago(p.since, now)}</span>
                </span>
                <span className="small">{flow.labels[p.position] ?? p.position}</span>
                <span className="xsmall faint">
                  {p.item ? `ข้อ ${p.item}` : "ไม่มีโจทย์"}
                  {p.hint_level ? ` · คำใบ้ L${p.hint_level}` : ""}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      <div className="activity-grid">
        {one ? (
          <JourneyCard
            trip={trip.data}
            loading={trip.loading}
            selected={selected}
            onSelect={pick}
            onSession={setSession}
            labels={flow.labels}
            follow={follow}
            onFollow={setFollow}
          />
        ) : (
          <Card className="activity-list-card">
            <CardHead
              title="การกระทำล่าสุด"
              sub="ใหม่สุดอยู่บน กดรายการเพื่อดูเส้นทาง"
              actions={
                <label className="check xsmall">
                  <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
                  ตามรายการล่าสุด
                </label>
              }
            />
            {feed.loading && !feed.data && <Spinner />}
            {feed.data && events.length === 0 && <Empty>ยังไม่มีการกระทำ ลองเปิดหน้านักเรียนแล้วตอบสักข้อ</Empty>}
            <ol className="activity-list">
              {events.map((e) => {
                const s = summary(e);
                const k = keyOf(e);
                return (
                  <li key={k}>
                    <button
                      className={k === selected ? "is-on" : ""}
                      onClick={() => pick(k)}
                    >
                      <span className={`activity-src src-${e.source}`} title={SOURCE_LABEL[e.source]}>
                        {SOURCE_ICON[e.source]}
                      </span>
                      <span className="stack grow" style={{ gap: 1 }}>
                        <span className="row row-sm xsmall">
                          <span className="mono strong">{e.code}</span>
                          <span className="faint num">{clock(e.ts)}</span>
                        </span>
                        <span className="small activity-text">{s.text}</span>
                        {s.math && <span className="activity-math mono">{s.math}</span>}
                        {e.position && <span className="xsmall faint">→ {flow.labels[e.position] ?? e.position}</span>}
                      </span>
                      <ChevronRight size={16} className="faint" />
                    </button>
                  </li>
                );
              })}
            </ol>
          </Card>
        )}

        <div className="stack">
          {event ? <EventDetail event={event} labels={flow.labels} /> : <Card className="card-pad"><Empty>เลือกการกระทำจากรายการ</Empty></Card>}
          <Card className="flow-card">
            <CardHead
              title="เส้นทางของการกระทำนี้ในผัง"
              sub="เส้นสีเข้มคือเส้นทางที่การกระทำที่เลือกเดินผ่าน กล่องที่เน้นคือที่ที่นักเรียนไปอยู่ต่อ กดกล่องเพื่อดูรายละเอียดและปรับแต่ง"
            />
            {gemFlow.data && <p className="xsmall muted flow-of">ผังของ Gem: {gemFlow.data.name}</p>}
            <GemFlowMap
              flow={gemFlow.data ?? { nodes: flow.nodes, edges: flow.edges, disabled: {}, alerts: {} }}
              allNodes={flow.nodes}
              note={false}
              positions={event ? flow.positions.filter((p) => p.code === event.code) : []}
              selectedStudent={event?.code}
              selectedNode={gemFlow.data?.custom ? event?.step : event?.position}
              highlightEdges={event?.edges ?? []}
              trail={gemFlow.data?.custom && event ? eventTrail(event.decisions) : undefined}
              onSelectNode={setInspect}
            />
          </Card>
        </div>
      </div>
      {gemFlow.data?.custom ? (
        <SpecStepDrawer flow={gemFlow.data} nodeId={inspect} onClose={() => setInspect(null)} />
      ) : (
        <NodeInspector nodeId={inspect} onClose={() => setInspect(null)} onNavigate={setInspect} />
      )}
    </div>
  );
}

const MILESTONE = {
  start: { label: "เริ่ม", icon: <Play size={12} /> },
  completed: { label: "จบชุด", icon: <Flag size={12} /> },
  ended: { label: "จบ Session", icon: <Flag size={12} /> },
};

// เส้นทางตั้งแต่ต้นจนจบของหนึ่ง Session: ขั้นที่ 1 คือจุดเริ่ม ขั้นสุดท้ายคือจุดจบ
function JourneyCard({
  trip,
  loading,
  selected,
  onSelect,
  onSession,
  labels,
  follow,
  onFollow,
}: {
  trip: JourneyData | null;
  loading: boolean;
  selected: string | null;
  onSelect: (key: string) => void;
  onSession: (id: number) => void;
  labels: Record<string, string>;
  follow: boolean;
  onFollow: (on: boolean) => void;
}) {
  const sum = trip?.summary;
  const steps = trip?.steps ?? [];
  // ขั้นของนักเรียนกับการทำงานของครู เรียงตามเวลาเดียวกัน ขั้นของนักเรียนมีเลข ส่วนของครูไม่นับเป็นขั้น
  const timeline: ({ step: ActivityEvent; ts: number } | { teacher: TeacherEntry; ts: number })[] = [
    ...steps.map((step) => ({ step, ts: step.ts })),
    ...(trip?.teacher ?? []).map((teacher) => ({ teacher, ts: teacher.ts })),
  ].sort((a, b) => a.ts - b.ts);
  return (
    <Card className="activity-list-card">
      <CardHead
        title="ตั้งแต่ต้นจนจบ"
        sub="ทุกการกระทำใน Session นี้เรียงตามลำดับ กดขั้นเพื่อดูว่าเข้าไปตรงไหนในผัง"
        actions={
          <label className="check xsmall">
            <input type="checkbox" checked={follow} onChange={(e) => onFollow(e.target.checked)} />
            ตามขั้นล่าสุด
          </label>
        }
      />
      {loading && !trip && <Spinner />}
      {trip && !trip.run && <Empty>นักเรียนคนนี้ยังไม่เคยเริ่มชุดคำถาม</Empty>}
      {trip?.run && sum && (
        <div className="journey-head">
          {trip.runs.length > 1 ? (
            <select className="input" value={trip.run.id} onChange={(e) => onSession(Number(e.target.value))} aria-label="เลือก Session">
              {trip.runs.map((r, i) => (
                <option key={r.id} value={r.id}>
                  {i === 0 ? "ล่าสุด · " : ""}
                  {r.set_name} · {new Date(r.started * 1000).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" })} · {r.outcome}
                </option>
              ))}
            </select>
          ) : (
            <span className="small strong">{trip.run.set_name}</span>
          )}
          {trip.run.gem && (
            <span className="xsmall muted">
              เรียนกับ Gem เวอร์ชัน {trip.run.gem.version ?? "–"} · คลังโจทย์รุ่นที่ {trip.run.gem.bank_version ?? "–"}
            </span>
          )}
          <dl className="journey-stats">
            <div>
              <dt>ทั้งหมด</dt>
              <dd>{sum.steps} ขั้น</dd>
            </div>
            <div>
              <dt>ตอบ / ถูก</dt>
              <dd>
                {sum.answers} / {sum.correct}
              </dd>
            </div>
            <div>
              <dt>คำใบ้</dt>
              <dd>{sum.hints} ครั้ง</dd>
            </div>
            <div>
              <dt>ใช้เวลา</dt>
              <dd>{mmss(sum.duration)}{sum.duration < 60 ? " วินาที" : " นาที"}</dd>
            </div>
            <div>
              <dt>แจ้งครู / ครูตอบ</dt>
              <dd>
                {sum.alerts} / {sum.responses}
              </dd>
            </div>
          </dl>
        </div>
      )}
      <ol className="journey">
        {timeline.map((entry) => {
          if ("teacher" in entry) return <TeacherRow key={`t-${entry.teacher.ts}-${entry.teacher.kind}`} entry={entry.teacher} />;
          const e = entry.step;
          const s = summary(e);
          const k = keyOf(e);
          const ms = e.milestone ? MILESTONE[e.milestone] : null;
          return (
            <li key={k} className={`journey-step ${e.milestone ? `ms-${e.milestone}` : ""}`}>
              <button className={k === selected ? "is-on" : ""} onClick={() => onSelect(k)}>
                <span className="journey-n num">{e.n}</span>
                <span className="stack grow" style={{ gap: 2, minWidth: 0 }}>
                  <span className="row row-sm xsmall">
                    <span className="strong">ขั้นที่ {e.n}</span>
                    {ms && (
                      <span className="journey-flag">
                        {ms.icon}
                        {ms.label}
                      </span>
                    )}
                    <span className="faint num">{clock(e.ts)}</span>
                    <span className={`activity-src src-${e.source} activity-src-sm`} title={SOURCE_LABEL[e.source]}>
                      {SOURCE_ICON[e.source]}
                    </span>
                  </span>
                  <span className="small activity-text">{s.text}</span>
                  {s.math && <span className="activity-math mono">{s.math}</span>}
                  {s.sub && !e.milestone && <span className="xsmall muted">{s.sub}</span>}
                  {e.position && <span className="xsmall faint">→ {labels[e.position] ?? e.position}</span>}
                </span>
              </button>
            </li>
          );
        })}
        {sum && !sum.finished && steps.length > 0 && (
          <li className="journey-step journey-open">
            <span className="journey-n">
              <Hourglass size={13} />
            </span>
            <span className="small muted">
              ยังไม่จบ ตอนนี้อยู่ที่ <span className="strong">{sum.position_label ?? "–"}</span>
            </span>
          </li>
        )}
      </ol>
    </Card>
  );
}

function TeacherRow({ entry }: { entry: TeacherEntry }) {
  const alert = entry.kind === "alert";
  return (
    <li className={`journey-step journey-teacher ${alert ? `is-alert level-${entry.level}` : ""}`}>
      <span className="journey-n">{alert ? <Bell size={13} /> : <Hand size={13} />}</span>
      <span className="stack grow" style={{ gap: 2, minWidth: 0 }}>
        <span className="row row-sm xsmall">
          <span className="strong">{alert ? `แจ้งครู${entry.level === "urgent" ? " (ด่วน)" : entry.level === "silent" ? " (เงียบ)" : ""}` : "ครู"}</span>
          <span className="faint num">{clock(entry.ts)}</span>
        </span>
        <span className="small activity-text">{entry.text}</span>
        {entry.after_alert != null && (
          <span className="xsmall journey-response">ครูตอบสนองหลังแจ้งเตือน {entry.after_alert < 60 ? `${Math.round(entry.after_alert)} วินาที` : `${mmss(entry.after_alert)} นาที`}</span>
        )}
      </span>
    </li>
  );
}

function keyOf(e: ActivityEvent) {
  return `${e.code}-${e.ts}`;
}

function EventDetail({ event, labels }: { event: ActivityEvent; labels: Record<string, string> }) {
  const inputs = event.inputs.filter((i) => i.action !== "misconception");
  const answer = inputs.find((i) => ["answer", "invalid_answer", "duplicate_ignored"].includes(i.action));
  return (
    <Card className="card-pad stack event-detail">
      <div className="spread">
        <span className="row row-sm">
          <span className={`activity-src src-${event.source}`}>{SOURCE_ICON[event.source]}</span>
          <span className="strong">{SOURCE_LABEL[event.source]}</span>
          <span className="mono small">{event.code}</span>
        </span>
        <span className="xsmall faint num">{new Date(event.ts * 1000).toLocaleString("th-TH")}</span>
      </div>

      {answer?.item && <AnswerHero input={answer} />}

      <div className="step-block">
        <span className="step-label">1 · สิ่งที่ป้อนเข้ามา</span>
        {inputs.length ? (
          inputs.map((input, i) => {
            const d = describeInput(input);
            return (
              <div key={i} className="stack stack-sm">
                <div className="stack" style={{ gap: 2 }}>
                  <span className="strong">{d.text}</span>
                  {d.sub && <span className="small muted">{d.sub}</span>}
                </div>
                {input.item && input.item.format === "mcq" && <ItemView item={input.item} chosen={input.data?.raw ? [input.data.raw] : []} />}
              </div>
            );
          })
        ) : (
          <span className="small muted">
            {event.edges.includes("e_start")
              ? "นักเรียนกดเริ่มชุดคำถาม ระบบเลือกโจทย์ข้อแรกให้"
              : event.source === "teacher"
                ? "ครูสั่งจากหน้าครู"
                : "ไม่มีการป้อนจากนักเรียน ระบบเปลี่ยนสถานะเมื่อครบเวลาหรือเงื่อนไข"}
          </span>
        )}
      </div>

      <div className="step-block">
        <span className="step-label">2 · เข้าไปที่ไหนในผัง</span>
        {event.decisions.length === 0 &&
          (event.steps.length ? (
            <>
              <ol className="path-steps">
                {event.steps.map((label, i) => (
                  <li key={i} className={i === event.steps.length - 1 ? "is-last" : ""}>
                    {i > 0 && <ArrowRight size={13} aria-hidden />}
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
              <span className="xsmall faint">นักเรียนยังอยู่ตำแหน่งเดิมในผัง การกระทำนี้จบที่ขั้นสุดท้ายด้านบน</span>
            </>
          ) : (
            <span className="small muted">บันทึกเป็นร่องรอยอย่างเดียว ไม่ได้เปลี่ยนตำแหน่งในผัง</span>
          ))}
        {event.decisions.map((d) => (
          <div key={d.id} className="stack stack-sm">
            {d.path_labels.length > 0 && (
              <ol className="path-steps">
                {d.path_labels.map((label, i) => (
                  <li key={i} className={i === d.path_labels.length - 1 ? "is-last" : ""}>
                    {i > 0 && <ArrowRight size={13} aria-hidden />}
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
            )}
            <div className="callout callout-accent">
              <span className="small">
                <span className="strong">ระบบตัดสินว่า: </span>
                {d.rule}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="step-block">
        <span className="step-label">3 · กฎที่เกี่ยวข้อง และผลลัพธ์</span>
        <div className="pill-list">
          {event.rules.map((r) => (
            <Link key={r.id} to={`/admin/rules#${r.id}`} className="rule-pill">
              <span className="mono">{r.id}</span>
              {r.title}
            </Link>
          ))}
          {!event.rules.length && <span className="small faint">ไม่มี</span>}
        </div>
        {event.position && (
          <span className="small row row-sm">
            <MousePointerClick size={15} />
            นักเรียนไปอยู่ที่ <Badge tone="accent">{labels[event.position] ?? event.position}</Badge>
          </span>
        )}
        {event.inputs.some((i) => i.action === "chat") && (
          <span className="xsmall faint row row-sm">
            <Bot size={13} />
            ข้อความแชตที่แสดงเป็นฉบับที่ลบข้อมูลส่วนตัวแล้ว
          </span>
        )}
      </div>
    </Card>
  );
}

// โจทย์และคำตอบตัวใหญ่ อ่านได้จากหลังห้องตอนฉายจอ
function AnswerHero({ input }: { input: ActivityInput }) {
  const item = input.item!;
  const d = input.data ?? {};
  const result =
    input.action === "invalid_answer"
      ? { label: "ผิดรูปแบบ", tone: "neutral" }
      : input.action === "duplicate_ignored"
        ? { label: "ส่งซ้ำ", tone: "neutral" }
        : d.correct
          ? { label: "ถูก", tone: "success" }
          : d.rapid
            ? { label: "เร็วเกิน", tone: "warning" }
            : { label: "ผิด", tone: "calm" };
  return (
    <div className="qa-hero">
      <div className="qa-question">
        <span className="qa-label">โจทย์ {item.id}</span>
        <span className="qa-prompt">{item.prompt}</span>
        {item.math && <span className="qa-math">{item.math}</span>}
      </div>
      <div className="qa-answers">
        <div className={`qa-box qa-${result.tone}`}>
          <span className="qa-label">นักเรียนตอบ</span>
          <span className="qa-value">{answerText(item, d.raw ?? "")}</span>
          <span className="qa-result">
            {result.tone === "success" ? <Check size={18} /> : result.tone === "calm" ? <X size={18} /> : null}
            {result.label}
            {d.rt != null && <span className="qa-time">· คิด {num(d.rt, 1)} วินาที</span>}
          </span>
        </div>
        <div className="qa-box">
          <span className="qa-label">คำตอบที่ถูก</span>
          <span className="qa-value">{item.correct}</span>
          {d.diagnosis?.tag_name && <span className="qa-result qa-diag">{d.diagnosis.tag_name}</span>}
        </div>
      </div>
    </div>
  );
}
