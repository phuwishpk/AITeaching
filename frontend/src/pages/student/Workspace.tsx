import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CircleCheck,
  Coffee,
  Lightbulb,
  MessageCircle,
  Phone,
  RotateCcw,
  Send,
  Sparkles,
  Undo2,
} from "lucide-react";
import { api, clearAuth, getAuth } from "../../lib/api";
import { useCountdown, useLive } from "../../lib/hooks";
import { mmss } from "../../lib/format";
import { TopBar } from "../../components/Shell";
import { Badge, Button, Modal, Spinner } from "../../components/ui";
import { StudentLogin } from "../Login";

interface Hint {
  level: number;
  text: string | null;
  status: string;
}

interface View {
  position: string;
  label: string;
  set: { id: string; name: string; subject: string };
  target: { id: string; name: string };
  mastery: number;
  item: { id: string; prompt: string; math: string | null; format: "numeric" | "mcq" | "short"; options: { id: string; text: string }[] } | null;
  item_mode: string | null;
  concept_name: string | null;
  item_number: number;
  progress: { main_done: number; main_total: number; max_items: number };
  error_count: number;
  hints: Hint[];
  hint_button: { visible: boolean; cooldown: number | null; unlock_in: number };
  timers: { delay: number | null; lock: number | null; break: number | null };
  can_undo: boolean;
  undo_window: number;
  idle_timeout: number;
  walkthrough: { title: string; problem: string; steps: string[] } | null;
  remedial: { concept_name: string; round: number } | null;
  ended: boolean;
  end_reason: string | null;
}

interface Result {
  kind: string;
  message?: string;
  socratic?: string;
  remaining?: number;
  itemNumber?: number; // ข้อความผูกกับข้อที่แสดงอยู่ เปลี่ยนข้อแล้วข้อความเก่าไม่ค้าง
}

// ข้อที่เพิ่งทำถูก แสดงก่อนพาไปข้อถัดไป
interface Solved {
  message: string;
  prompt: string;
  math: string | null;
  answer: string;
  nextIso: boolean;
}

type ChatMessage = { from: "me" | "tutor" | "teacher" | "system"; text: string; note?: string };

interface StoredMessage {
  sender: "student" | "tutor" | "teacher" | "system";
  text: string;
}

const fromSender = (m: StoredMessage): ChatMessage => ({ from: m.sender === "student" ? "me" : m.sender, text: m.text });

const LETTERS: Record<string, string> = { a: "ก", b: "ข", c: "ค", d: "ง" };
const LEVEL_NAMES = ["สะกิดความคิด", "อธิบายกฎ", "ชี้นำขั้นแรก"];
const ANSWER_POSITIONS = ["ANSWERING", "HINT_L1", "HINT_L2", "HINT_L3", "ISOMORPHIC_TEST", "REMEDIAL", "DELIBERATE_DELAY"];

export function encouragement(mastery: number, dropped: boolean) {
  if (dropped) return "ไม่เป็นไรนะ มาฝึกเพิ่มอีกนิด เดี๋ยวก็คล่อง";
  if (mastery >= 0.8) return "ใกล้สำเร็จแล้ว ทำได้ดีมาก";
  if (mastery >= 0.5) return "เก่งขึ้นเรื่อย ๆ ไปต่อกันเลย";
  if (mastery > 0) return "กำลังไปได้ดี ค่อย ๆ ไปทีละข้อ";
  return "เริ่มกันเลย ไม่ต้องรีบ คิดให้ครบก่อนตอบ";
}

export default function Workspace() {
  const [auth, setAuthState] = useState(() => getAuth("student"));
  if (!auth) return <StudentLogin onDone={() => setAuthState(getAuth("student"))} />;
  return <Room code={auth.code ?? ""} onLogout={() => { clearAuth("student"); setAuthState(null); }} />;
}

function Room({ code, onLogout }: { code: string; onLogout: () => void }) {
  const { setId = "" } = useParams();
  const navigate = useNavigate();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Result | null>(null);
  const [solved, setSolved] = useState<Solved | null>(null);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [teacherIn, setTeacherIn] = useState(false);
  const [socratic, setSocratic] = useState<string | null>(null);
  const [notesOpen, setNotesOpen] = useState(false);
  const previousMastery = useRef<number | null>(null);
  const [dropped, setDropped] = useState(false);
  const base = `/api/student/sets/${setId}`;

  const applyView = useCallback((next: View) => {
    if (previousMastery.current != null && next.mastery < previousMastery.current - 0.001) setDropped(true);
    else if (previousMastery.current != null && next.mastery > previousMastery.current) setDropped(false);
    previousMastery.current = next.mastery;
    setView(next);
  }, []);

  const refresh = useCallback(async () => {
    try {
      applyView(await api<View>("student", `${base}/state`));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดไม่สำเร็จ");
    }
  }, [base, applyView]);

  useEffect(() => {
    api<View>("student", `${base}/start`, { body: { restart: false } })
      .then(applyView)
      .catch((err) => setError(err.message));
    api<{ messages: StoredMessage[]; mode: string }>("student", `${base}/messages`)
      .then((data) => {
        setChat(data.messages.map(fromSender));
        setTeacherIn(data.mode === "teacher");
      })
      .catch(() => {});
  }, [base, applyView]);

  useEffect(() => {
    const expired = () => onLogout();
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, [onLogout]);

  // ครูปลดล็อก หรือคำใบ้จาก AI พร้อมแล้ว: เซิร์ฟเวอร์ส่งสถานะใหม่มาทาง WebSocket
  useLive("student", (message) => {
    if (message.type === "state" && message.view?.set?.id === setId) applyView(message.view);
    if (message.type === "message" && ["teacher", "system"].includes(message.message?.sender))
      setChat((list) => [...list, fromSender(message.message)]);
    if (message.type === "chat_mode") setTeacherIn(message.mode === "teacher");
  });

  const act = useCallback(
    async (path: string, body?: unknown) => {
      try {
        const response = await api<{ result?: Result; view: View; reply?: string; source?: string; to_teacher?: boolean }>("student", `${base}/${path}`, {
          body: body ?? {},
        });
        applyView(response.view);
        return response;
      } catch (err) {
        setError(err instanceof Error ? err.message : "ทำรายการไม่สำเร็จ");
        return null;
      }
    },
    [base, applyView],
  );

  // Idle Pause: ไม่มีการกระทำนานเกินกำหนด ระบบพักบทเรียนให้
  const lastActive = useRef(Date.now());
  useEffect(() => {
    const touch = () => (lastActive.current = Date.now());
    const events = ["pointerdown", "keydown", "pointermove", "touchstart", "scroll"];
    events.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    return () => events.forEach((name) => window.removeEventListener(name, touch));
  }, []);
  useEffect(() => {
    if (!view || !ANSWER_POSITIONS.includes(view.position)) return;
    const id = setInterval(() => {
      if (Date.now() - lastActive.current > view.idle_timeout * 1000) {
        lastActive.current = Date.now();
        act("idle");
      }
    }, 1000);
    return () => clearInterval(id);
  }, [view, act]);

  useEffect(() => setSocratic(null), [view?.item?.id, view?.item_number]);

  if (!view) {
    return (
      <>
        <TopBar role={`นักเรียน · ${code}`} onLogout={onLogout} narrow />
        <main className="page page-student">{error ? <p className="empty">{error}</p> : <Spinner label="กำลังเตรียมโจทย์" />}</main>
      </>
    );
  }

  const answering = ANSWER_POSITIONS.includes(view.position) || view.position === "RAPID_GUESS_LOCK";

  return (
    <>
      <TopBar role={`นักเรียน · ${code}`} onLogout={onLogout} narrow>
        <Link to="/student" className="btn btn-ghost btn-sm" aria-label="กลับไปเลือกชุดคำถาม">
          <ArrowLeft size={16} />
          <span className="btn-label">ชุดคำถาม</span>
        </Link>
      </TopBar>
      <main className="page workspace">
        <section className="ws-head fade-in">
          <div className="stack stack-sm grow">
            <p className="eyebrow">
              {view.set.subject} · {view.set.name}
            </p>
            <h1 className="title-lg">{view.target.name}</h1>
          </div>
          <div className="ws-mastery">
            <div className="spread small">
              <span className="muted">ความชำนาญเรื่องนี้</span>
              <span className="muted">{encouragement(view.mastery, dropped)}</span>
            </div>
            <div className="mastery" role="img" aria-label="แถบความชำนาญ">
              <div className="mastery-fill" style={{ width: `${Math.max(4, view.mastery * 100)}%` }} />
            </div>
            <QuestionProgress view={view} />
          </div>
        </section>

        {error && (
          <div className="callout callout-calm" role="status">
            {error}
            <Button variant="ghost" size="sm" onClick={() => { setError(null); refresh(); }}>
              ลองอีกครั้ง
            </Button>
          </div>
        )}

        <div className="ws-grid">
          <div className="stack">
            {solved && answering && view.item ? (
              <SolvedCard solved={solved} onNext={() => setSolved(null)} />
            ) : answering && view.item ? (
              <ProblemCard
                view={view}
                feedback={feedback?.itemNumber === view.item_number ? feedback : null}
                onSubmit={async (answer) => {
                  const before = view;
                  const response = await act("answer", { answer });
                  const result = response?.result;
                  if (!result || !response) return;
                  const next = response.view;
                  const moved = !!next.item && next.item_number !== before.item_number;
                  if (result.kind === "correct" && moved && before.item) {
                    // ตอบถูกแล้วระบบเลือกข้อใหม่ให้: แสดงว่าถูกก่อน แล้วค่อยพาไปข้อถัดไป
                    const option = before.item.options.find((o) => o.id === answer);
                    setSolved({
                      message: result.message ?? "ถูกต้อง",
                      prompt: before.item.prompt,
                      math: before.item.math,
                      answer: option ? option.text : answer,
                      nextIso: next.item_mode === "isomorphic",
                    });
                    setFeedback(null);
                    return;
                  }
                  setFeedback({ ...result, itemNumber: next.item_number });
                }}
                onUndo={async () => {
                  const response = await act("undo");
                  setFeedback(response?.result ? { ...response.result, itemNumber: response.view.item_number } : null);
                }}
                onRestart={async () => {
                  const response = await act("restart-item");
                  setFeedback(response?.result ? { ...response.result, itemNumber: response.view.item_number } : null);
                }}
                onTimer={refresh}
                onNotes={() => {
                  setNotesOpen(true);
                  act("revisit", { concept: view.target.id });
                }}
                onRest={() => act("rest")}
              />
            ) : (
              <StateScreen view={view} act={act} onTimer={refresh} onBack={() => navigate("/student")} />
            )}
          </div>
          <aside className="stack">
            <HintPanel
              view={view}
              socratic={socratic}
              onHint={async () => {
                const response = await act("hint");
                const result = response?.result;
                if (!result) return;
                if (result.socratic) setSocratic(result.socratic);
                if (result.kind === "wait" || result.kind === "delay" || result.kind === "abuse" || result.kind === "cooldown")
                  setFeedback({ ...result, itemNumber: response.view.item_number });
              }}
              onTimer={refresh}
            />
            <TutorChat
              messages={chat}
              toTeacher={!answering}
              teacherIn={teacherIn}
              onSend={async (message) => {
                setChat((list) => [...list, { from: "me", text: message }]);
                const response = await act("chat", { message });
                if (!response) return;
                if (response.to_teacher) {
                  setChat((list) => list.map((m, i) => (i === list.length - 1 ? { ...m, note: "ส่งถึงครูแล้ว รอครูตอบนะ" } : m)));
                } else if (response.reply) {
                  const reply = response.reply;
                  setChat((list) => [...list, { from: response.source === "safety" ? "system" : "tutor", text: reply }]);
                }
              }}
            />
          </aside>
        </div>
      </main>
      <NotesModal open={notesOpen} onClose={() => setNotesOpen(false)} setId={setId} />
    </>
  );
}

// ---------------------------------------------------------------- จำนวนข้อ

// ระบบปรับลำดับและเพิ่มข้อทบทวนตามผู้เรียน จำนวนข้อจริงจึงไม่ตายตัว แสดงโจทย์หลักที่ผ่านแล้วแทน
function QuestionProgress({ view }: { view: View }) {
  const { main_done, main_total, max_items } = view.progress;
  return (
    <div className="q-progress">
      <ol className="q-dots" aria-label={`ผ่านโจทย์หลักแล้ว ${main_done} จาก ${main_total} ข้อ`}>
        {Array.from({ length: main_total }, (_, i) => (
          <li key={i} className={i < main_done ? "done" : ""} />
        ))}
      </ol>
      <span className="small muted">
        โจทย์หลัก {main_done} จาก {main_total} ข้อ
      </span>
      <span className="xsmall faint">ทำได้ไม่เกิน {max_items} ข้อต่อรอบ รวมข้อทบทวน</span>
    </div>
  );
}

// ---------------------------------------------------------------- ตอบถูกแล้ว ก่อนไปข้อถัดไป

function SolvedCard({ solved, onNext }: { solved: Solved; onNext: () => void }) {
  return (
    <article className="card solved-card fade-in" role="status">
      <span className="celebrate small-celebrate">
        <CircleCheck size={36} />
      </span>
      <h2 className="title-lg">ถูกต้อง!</h2>
      {solved.message.replace(/^ถูกต้อง\s*/, "") && <p className="muted">{solved.message.replace(/^ถูกต้อง\s*/, "")}</p>}
      <div className="solved-recap">
        <span className="small muted">{solved.prompt}</span>
        {solved.math && <span className="solved-math">{solved.math}</span>}
        <span className="solved-answer">
          คำตอบของเรา <strong>{solved.answer}</strong>
        </span>
      </div>
      {solved.nextIso && <p className="small muted">ข้อถัดไปเป็นข้อทดสอบความเข้าใจ ลองทำด้วยตัวเองโดยไม่มีคำใบ้นะ</p>}
      <Button variant="primary" size="lg" icon={<ArrowRight size={18} />} onClick={onNext} autoFocus>
        ไปข้อถัดไป
      </Button>
    </article>
  );
}

// ---------------------------------------------------------------- โจทย์และช่องตอบ

function ProblemCard({
  view,
  feedback,
  onSubmit,
  onUndo,
  onRestart,
  onTimer,
  onNotes,
  onRest,
}: {
  view: View;
  feedback: Result | null;
  onSubmit: (answer: string) => Promise<void>;
  onUndo: () => void;
  onRestart: () => void;
  onTimer: () => void;
  onNotes: () => void;
  onRest: () => void;
}) {
  const item = view.item!;
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const locked = view.position === "RAPID_GUESS_LOCK";
  const lockLeft = useCountdown(view.timers.lock, onTimer);
  const delayLeft = useCountdown(view.timers.delay, onTimer);
  const iso = view.item_mode === "isomorphic";
  const remedial = view.item_mode === "remedial";
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setAnswer("");
    inputRef.current?.focus();
  }, [item.id, view.item_number]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!answer.trim() || locked || busy) return;
    setBusy(true);
    await onSubmit(answer);
    setBusy(false);
  };

  const tone =
    feedback?.kind === "correct" ? "callout-success" : feedback?.kind === "rapid" ? "callout-warning" : "callout-calm";

  return (
    <article className="card problem-card fade-in" key={`${item.id}-${view.item_number}`}>
      <div className="spread">
        <div className="row row-sm">
          <span className="eyebrow">
            ข้อที่ {view.item_number}
            <span className="faint"> / ไม่เกิน {view.progress.max_items}</span>
          </span>
          {iso && <Badge tone="accent">ข้อทดสอบความเข้าใจ · ไม่มีคำใบ้</Badge>}
          {remedial && view.remedial && <Badge tone="calm">ทบทวนพื้นฐาน · {view.remedial.concept_name}</Badge>}
          {!iso && !remedial && view.concept_name && <Badge>{view.concept_name}</Badge>}
        </div>
        <div className="row row-sm">
          <Button variant="ghost" size="sm" icon={<BookOpen size={16} />} onClick={onNotes}>
            ทบทวนเนื้อหา
          </Button>
          <Button variant="ghost" size="sm" icon={<Coffee size={16} />} onClick={onRest}>
            ขอพัก
          </Button>
        </div>
      </div>

      <div className="problem-body">
        <p className="problem-prompt">{item.prompt}</p>
        {item.math && <p className="problem-math">{item.math}</p>}
      </div>

      <form onSubmit={submit} className="stack">
        {item.format === "mcq" ? (
          <div className="options" role="radiogroup">
            {item.options.map((option) => (
              <button
                type="button"
                key={option.id}
                role="radio"
                aria-checked={answer === option.id}
                className="option"
                disabled={locked}
                onClick={() => setAnswer(option.id)}
              >
                <span className="option-letter">{LETTERS[option.id] ?? option.id}</span>
                <span>{option.text}</span>
              </button>
            ))}
          </div>
        ) : (
          <input
            ref={inputRef}
            className="input input-lg answer-input"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            disabled={locked}
            placeholder={item.format === "numeric" ? "พิมพ์คำตอบ เช่น 4 หรือ −2" : "พิมพ์คำตอบสั้น ๆ"}
            inputMode={item.format === "numeric" ? "decimal" : "text"}
            autoComplete="off"
            aria-label="คำตอบ"
          />
        )}

        {locked && (
          <div className="callout callout-warning">
            <Lightbulb size={18} />
            <span>
              ลองอ่านโจทย์ให้ครบอีกครั้งนะ ปุ่มตอบจะกลับมาในอีก <b className="num">{mmss(lockLeft)}</b> วินาที
            </span>
          </div>
        )}
        {view.position === "DELIBERATE_DELAY" && (
          <div className="callout callout-calm">
            <Sparkles size={18} />
            <span>
              ลองตรวจคำตอบด้วยตัวเองก่อนนะ แก้ใหม่ได้เลย ถ้ายังไม่แน่ใจ คำใบ้จะขึ้นในอีก{" "}
              <b className="num">{mmss(delayLeft)}</b> วินาที
            </span>
          </div>
        )}
        {feedback?.message && !locked && (
          <div className={`callout ${tone}`} role="status">
            {feedback.kind === "correct" ? <CircleCheck size={18} color="var(--success)" /> : <MessageCircle size={18} />}
            <span>{feedback.message}</span>
          </div>
        )}

        <div className="spread">
          <div className="row row-sm">
            {view.can_undo && (
              <Button type="button" variant="ghost" size="sm" icon={<Undo2 size={16} />} onClick={onUndo}>
                ยกเลิกคำตอบล่าสุด
              </Button>
            )}
            <Button type="button" variant="ghost" size="sm" icon={<RotateCcw size={16} />} onClick={onRestart}>
              เริ่มข้อนี้ใหม่
            </Button>
          </div>
          <Button variant="primary" size="lg" type="submit" loading={busy} disabled={!answer.trim() || locked}>
            ส่งคำตอบ
          </Button>
        </div>
      </form>
    </article>
  );
}

// ---------------------------------------------------------------- สถานะพิเศษ

function StateScreen({
  view,
  act,
  onTimer,
  onBack,
}: {
  view: View;
  act: (path: string, body?: unknown) => Promise<unknown>;
  onTimer: () => void;
  onBack: () => void;
}) {
  const breakLeft = useCountdown(view.timers.break, onTimer);
  switch (view.position) {
    case "CIRCUIT_BREAKER":
      return (
        <article className="card state-card fade-in">
          <div className="breath" aria-hidden>
            <span />
          </div>
          <h2 className="title-lg">พักสายตาสักครู่นะ</h2>
          <p className="muted prose">
            หายใจเข้าลึก ๆ แล้วหายใจออกช้า ๆ ตามวงกลม ไม่ต้องรีบเลย เดี๋ยวเราจะเริ่มใหม่ด้วยตัวอย่างทีละขั้นด้วยกัน
          </p>
          <p className="faint small num">อีก {mmss(breakLeft)} วินาที</p>
        </article>
      );
    case "WALKTHROUGH":
      return (
        <article className="card state-card state-left fade-in">
          <p className="eyebrow">ตัวอย่างทีละขั้น</p>
          <h2 className="title-lg">{view.walkthrough?.title ?? "ดูตัวอย่างก่อนนะ"}</h2>
          {view.walkthrough && (
            <>
              <p className="problem-math small-math">{view.walkthrough.problem}</p>
              <ol className="steps">
                {view.walkthrough.steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
            </>
          )}
          <Button variant="primary" size="lg" onClick={() => act("walkthrough-done")}>
            อ่านจบแล้ว ไปต่อ
          </Button>
        </article>
      );
    case "IDLE_PAUSE":
      return (
        <article className="card state-card fade-in">
          <Coffee size={36} color="var(--accent)" />
          <h2 className="title-lg">พักอยู่นะ</h2>
          <p className="muted prose">ไม่เป็นไรเลย พักให้พอแล้วค่อยกลับมา เวลาที่พักไม่นับเป็นเวลาคิด</p>
          <Button variant="primary" size="lg" onClick={() => act("resume")}>
            กลับมาทำต่อ
          </Button>
        </article>
      );
    case "CHOOSING_PATH":
      return (
        <article className="card state-card fade-in">
          <h2 className="title-lg">อยากไปต่อแบบไหนดี</h2>
          <p className="muted prose">บางวันก็เหนื่อย เลือกได้ตามที่สบายใจ ระบบเก็บความคืบหน้าไว้ให้แล้ว</p>
          <div className="choice-grid">
            <button className="choice" onClick={() => act("choose", { option: "rest" })}>
              <Coffee size={22} />
              <b>พักก่อน</b>
              <span className="small muted">กลับมาทำต่อเมื่อพร้อม</span>
            </button>
            <button className="choice" onClick={() => act("choose", { option: "easier" })}>
              <Sparkles size={22} />
              <b>ทำต่อแบบง่ายลง</b>
              <span className="small muted">เริ่มจากข้อที่ง่ายกว่าก่อน</span>
            </button>
            <button className="choice" onClick={() => act("choose", { option: "stop" })}>
              <CircleCheck size={22} />
              <b>หยุดวันนี้</b>
              <span className="small muted">กลับมาทำต่อวันหลังได้</span>
            </button>
          </div>
        </article>
      );
    case "SAFETY_STOP":
      return (
        <article className="card state-card fade-in">
          <Phone size={34} color="var(--accent)" />
          <h2 className="title-lg">ขอบคุณที่บอกนะ</h2>
          <p className="muted prose">ครูได้รับแจ้งแล้วและกำลังมาคุยด้วย ระหว่างนี้ถ้าอยากคุยกับผู้เชี่ยวชาญ โทรได้ตลอด 24 ชั่วโมง</p>
          <p className="hotline">
            สายด่วนสุขภาพจิต <b className="num">1323</b>
          </p>
        </article>
      );
    case "STAGNATION_DEADLOCK":
      return (
        <article className="card state-card fade-in">
          <Sparkles size={34} color="var(--accent)" />
          <h2 className="title-lg">ข้อนี้ยากจริง ๆ</h2>
          <p className="muted prose">เราพยายามมาเยอะมากแล้ว ครูกำลังจะมาช่วยอธิบายข้อนี้ด้วยกัน รอสักครู่นะ</p>
        </article>
      );
    case "COMPLETED":
      return (
        <article className="card state-card fade-in">
          <div className="celebrate" aria-hidden>
            <CircleCheck size={44} />
          </div>
          <h2 className="title-lg">ทำชุดนี้สำเร็จแล้ว</h2>
          <p className="muted prose">เข้าใจเรื่องนี้แล้วจริง ๆ ทั้งโจทย์ปกติและข้อที่ไม่มีคำใบ้ เก่งมาก</p>
          <Button variant="primary" size="lg" onClick={onBack}>
            กลับไปเลือกชุดคำถาม
          </Button>
        </article>
      );
    case "SESSION_ENDED":
      return (
        <article className="card state-card fade-in">
          <CircleCheck size={36} color="var(--accent)" />
          <h2 className="title-lg">วันนี้พอแค่นี้ก่อน</h2>
          <p className="muted prose">ระบบบันทึกความคืบหน้าไว้แล้ว กลับมาทำต่อจากเดิมได้ทุกเมื่อ</p>
          <Button variant="primary" size="lg" onClick={onBack}>
            กลับไปหน้าชุดคำถาม
          </Button>
        </article>
      );
    default:
      return (
        <article className="card state-card fade-in">
          <Spinner label="กำลังเตรียมขั้นต่อไป" />
        </article>
      );
  }
}

// ---------------------------------------------------------------- คำใบ้

function HintPanel({
  view,
  socratic,
  onHint,
  onTimer,
}: {
  view: View;
  socratic: string | null;
  onHint: () => void;
  onTimer: () => void;
}) {
  const unlock = useCountdown(view.hint_button.unlock_in > 0 ? view.hint_button.unlock_in : null);
  const cooldown = useCountdown(view.hint_button.cooldown, onTimer);
  const levels = view.hints.length;
  const iso = view.item_mode === "isomorphic";
  const waiting = (unlock ?? 0) > 0.05 || (cooldown ?? 0) > 0.05;

  return (
    <section className="card hint-card">
      <div className="spread">
        <div className="row row-sm">
          <Lightbulb size={18} color="var(--accent)" />
          <h2 className="subtitle">คำใบ้</h2>
        </div>
        <div className="ladder" aria-label={`ได้คำใบ้แล้ว ${levels} จาก 3 ระดับ`}>
          {[1, 2, 3].map((level) => (
            <span key={level} className={level <= levels ? "rung on" : "rung"} title={LEVEL_NAMES[level - 1]} />
          ))}
        </div>
      </div>

      {iso ? (
        <p className="small muted">ข้อนี้เป็นข้อทดสอบความเข้าใจ ลองทำด้วยตัวเองนะ เชื่อว่าทำได้</p>
      ) : levels === 0 ? (
        <p className="small muted">ลองคิดด้วยตัวเองก่อน ถ้าตอบผิด คำใบ้จะค่อย ๆ ขึ้นทีละขั้น และไม่มีขั้นไหนเฉลยคำตอบ</p>
      ) : (
        <ol className="hint-list">
          {view.hints.map((hint) => (
            <li key={hint.level} className="hint fade-in">
              <span className="hint-level">ระดับ {hint.level} · {LEVEL_NAMES[hint.level - 1]}</span>
              {hint.status === "ready" && hint.text ? (
                <p>{hint.text}</p>
              ) : (
                <div className="stack stack-sm" aria-label="ครูผู้ช่วยกำลังเตรียมคำใบ้">
                  <div className="skeleton" style={{ height: 12, width: "92%" }} />
                  <div className="skeleton" style={{ height: 12, width: "70%" }} />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}

      {socratic && (
        <div className="callout callout-accent fade-in">
          <MessageCircle size={18} />
          <span>{socratic}</span>
        </div>
      )}

      {view.hint_button.visible && !iso && (
        <Button variant="soft" block onClick={onHint} disabled={waiting} icon={<Lightbulb size={16} />}>
          {(cooldown ?? 0) > 0.05
            ? `ปุ่มคำใบ้พักอีก ${mmss(cooldown)} วินาที`
            : (unlock ?? 0) > 0.05
              ? `ลองคิดก่อน ขอคำใบ้ได้ในอีก ${mmss(unlock)} วินาที`
              : levels > 0
                ? "ขอคำถามชวนคิดเพิ่ม"
                : "ขอคำใบ้"}
        </Button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- ครูผู้ช่วย

const ROLE: Record<ChatMessage["from"], string | null> = { me: null, tutor: "ครูผู้ช่วย (AI)", teacher: "ครู", system: "ระบบ" };

function TutorChat({
  messages,
  onSend,
  toTeacher,
  teacherIn,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => Promise<void>;
  toTeacher: boolean;
  teacherIn: boolean;
}) {
  const direct = toTeacher || teacherIn;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setText("");
    setBusy(!direct);
    await onSend(message);
    setBusy(false);
  };

  return (
    <section className="card chat-card">
      <div className="spread">
        <div className="row row-sm">
          <MessageCircle size={18} color="var(--accent)" />
          <h2 className="subtitle">{direct ? "คุยกับครู" : "ถามครูผู้ช่วย"}</h2>
        </div>
        {teacherIn && (
          <span className="teacher-in">
            <span className="dot" />
            ครูอยู่ในแชต
          </span>
        )}
      </div>
      {direct && <p className="xsmall muted">ตอนนี้ข้อความจะส่งถึงครูโดยตรง ครูจะตอบกลับในกล่องนี้</p>}
      <div className="chat-list" ref={listRef}>
        {messages.length === 0 && (
          <p className="small faint">พิมพ์บอกได้ว่าติดตรงไหน ครูผู้ช่วยจะถามกลับให้คิดต่อ ไม่บอกคำตอบ</p>
        )}
        {messages.map((m, index) => (
          <div key={index} className={`bubble bubble-${m.from === "me" ? "me" : m.from}`}>
            {ROLE[m.from] && <span className="bubble-from">{ROLE[m.from]}</span>}
            {m.text}
            {m.note && <span className="bubble-note">{m.note}</span>}
          </div>
        ))}
        {busy && (
          <div className="bubble bubble-tutor typing" aria-label="ครูผู้ช่วยกำลังพิมพ์">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>
      <form onSubmit={send} className="chat-form">
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={direct ? "พิมพ์ถึงครู" : "เช่น ไม่แน่ใจว่าต้องย้ายเลข 3 ยังไง"}
          maxLength={600}
          aria-label={direct ? "ข้อความถึงครู" : "ข้อความถึงครูผู้ช่วย"}
        />
        <Button variant="primary" className="btn-icon" type="submit" disabled={!text.trim()} aria-label="ส่ง" icon={<Send size={16} />} />
      </form>
    </section>
  );
}

// ---------------------------------------------------------------- ทบทวนเนื้อหา

function NotesModal({ open, onClose, setId }: { open: boolean; onClose: () => void; setId: string }) {
  const [notes, setNotes] = useState<any[] | null>(null);
  useEffect(() => {
    if (open && !notes) api<any[]>("student", `/api/student/sets/${setId}/notes`).then(setNotes).catch(() => setNotes([]));
  }, [open, notes, setId]);
  return (
    <Modal open={open} onClose={onClose} title="ทบทวนเนื้อหา" wide>
      {!notes ? (
        <Spinner />
      ) : (
        <div className="stack stack-lg">
          {notes.map((note) => (
            <section key={note.id} className="stack stack-sm">
              <div className="row row-sm">
                <h3 className="subtitle">{note.name}</h3>
                <Badge>{note.grade}</Badge>
              </div>
              <p className="muted small">{note.description}</p>
              {note.walkthrough && (
                <div className="card-flat" style={{ padding: "12px 16px" }}>
                  <p className="small" style={{ fontWeight: 600 }}>
                    ตัวอย่าง: {note.walkthrough.problem}
                  </p>
                  <ol className="steps small">
                    {note.walkthrough.steps.map((step: string, index: number) => (
                      <li key={index}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </Modal>
  );
}
