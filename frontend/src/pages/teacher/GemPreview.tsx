import { useEffect, useRef, useState, type FormEvent } from "react";
import { History, Lightbulb, LoaderCircle, Play, RotateCcw, Send } from "lucide-react";
import { api } from "../../lib/api";
import { useNow } from "../../lib/hooks";
import { ago } from "../../lib/format";
import type { AiLog } from "../../lib/types";
import AiLogCard from "../../components/AiLog";
import { Badge, Button, Modal, useToast } from "../../components/ui";
import FlowWidget, { type WidgetResult, type WidgetView } from "../../components/FlowWidget";
import type { GemDetail, GemVersion } from "./gemTypes";

// แท็บ "ลองเรียน": ครูเรียน Gem ผ่าน engine จริงในบทบาทนักเรียนทดสอบ (ไม่นับเข้าสถิติ ไม่ส่งแจ้งเตือน)
// และเห็น prompt 4 กรอบที่ส่งให้ AI จริงทุกครั้ง

interface PreviewView {
  position: string;
  label: string;
  mastery: number;
  item: { id: string; prompt: string; math: string | null; format: string; options: { id: string; text: string }[] } | null;
  hints: { level: number; text: string | null; status: string }[];
  hint_button: { visible: boolean; cooldown: number; unlock_in: number };
  timers: { delay: number; lock: number; break: number };
  walkthrough: { title: string; problem: string; steps: string[] } | null;
  lesson?: { title: string; text: string; walkthrough: { title: string; problem: string; steps: string[] } | null };
  reflect?: { question: string };
  activity?: { title: string; status: string; text: string | null; question: string | null; response: "none" | "text" };
  break_text?: string | null;
  widget?: WidgetView;
  error_count: number;
  ended: boolean;
  gem: { tools: Record<string, boolean>; starter_prompts: string[] } | null;
}

interface PreviewResponse {
  view: PreviewView | null;
  code: string;
  ai: AiLog | null;
  result?: (WidgetResult & { message: string }) | null;
  reply?: string | null;
  to_teacher?: boolean;
}

interface ChatLine {
  from: "me" | "tutor" | "system";
  text: string;
}

export function PreviewTry({ gem }: { gem: GemDetail }) {
  const toast = useToast();
  const [data, setData] = useState<PreviewResponse | null>(null);
  const [answer, setAnswer] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [busy, setBusy] = useState(false);
  const path = `/api/gems/${gem.id}/preview`;

  const call = async (suffix: string, body?: unknown) => {
    setBusy(true);
    try {
      const response = await api<PreviewResponse>("teacher", path + suffix, body === undefined ? { method: "POST" } : { body });
      setData(response);
      return response;
    } catch (err) {
      toast(err instanceof Error ? err.message : "ทำรายการไม่สำเร็จ", "warning");
      return null;
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    api<PreviewResponse>("teacher", path).then(setData).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gem.id, gem.bank_version]);

  // คำใบ้จาก AI เขียนเสร็จทีหลัง และตัวจับเวลา (หน่วง ล็อก พัก) หมดเอง ดึงสถานะใหม่จนกว่าจะนิ่ง
  const view = data?.view;
  const waiting = !!view && (view.hints.some((h) => h.status === "pending") || view.timers.delay > 0 || view.timers.lock > 0 || view.timers.break > 0
    || (view.position === "FLOW_ACTIVITY" && view.activity?.status === "pending"));
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => api<PreviewResponse>("teacher", path).then(setData).catch(() => {}), 2000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, path]);

  const start = async () => {
    setChat([]);
    setMessage(null);
    setAnswer("");
    await call("/start");
  };

  const submit = async (value: string) => {
    if (!value.trim()) return;
    const response = await call("/answer", { answer: value });
    setMessage(response?.result?.message ?? null);
    setAnswer("");
  };

  const send = async (text: string) => {
    setChat((c) => [...c, { from: "me", text }]);
    const response = await call("/chat", { message: text });
    if (response?.reply) setChat((c) => [...c, { from: "tutor", text: response.reply! }]);
    else if (response?.to_teacher) setChat((c) => [...c, { from: "system", text: "ข้อความนี้จะส่งถึงครู (นักเรียนพักอยู่)" }]);
  };

  if (!view) {
    return (
      <div className="gem-try-empty">
        <p className="small muted">ลองเรียนติวเตอร์นี้เป็นนักเรียนผ่าน engine จริง ไม่นับเข้าสถิติห้องและไม่ส่งแจ้งเตือนถึงครู ทุกครั้งที่ AI ทำงานจะเห็น prompt ที่ส่งไปจริง</p>
        <Button variant="primary" icon={<Play size={16} />} loading={busy} onClick={start}>
          เริ่มลองเรียน
        </Button>
      </div>
    );
  }

  const tools = view.gem?.tools ?? {};
  const item = view.item;
  const locked = view.timers.lock > 0;
  return (
    <div className="stack">
      <div className="spread">
        <span className="row row-sm xsmall muted">
          <span className="mono">{data?.code}</span>· ความชำนาญ {Math.round(view.mastery * 100)}%
        </span>
        <span className="row row-sm">
          <Badge tone="accent">{view.label || view.position}</Badge>
          <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={start} disabled={busy}>
            เริ่มใหม่
          </Button>
        </span>
      </div>

      {view.ended ? (
        <p className="small">จบรอบลองเรียนแล้ว กดเริ่มใหม่เพื่อลองอีกครั้ง</p>
      ) : view.position === "FLOW_LESSON" ? (
        <div className="gem-item">
          <span className="small strong">{view.lesson?.title}</span>
          {view.lesson?.text && <span className="small lesson-text">{view.lesson.text}</span>}
          {view.lesson?.walkthrough && (
            <>
              <span className="gem-item-math">{view.lesson.walkthrough.problem}</span>
              <ol className="small">
                {view.lesson.walkthrough.steps.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ol>
            </>
          )}
          <Button size="sm" variant="primary" disabled={busy} onClick={() => call("/lesson-done")} style={{ alignSelf: "flex-start" }}>
            อ่านจบแล้ว ไปต่อ
          </Button>
        </div>
      ) : view.position === "FLOW_ACTIVITY" ? (
        <div className="gem-item">
          <span className="small strong">{view.activity?.title}</span>
          {!view.activity || view.activity.status === "pending" ? (
            <span className="small muted">AI กำลังสร้างกิจกรรม…</span>
          ) : (
            <span className="small lesson-text">{view.activity.text}</span>
          )}
          {view.activity?.status !== "pending" &&
            (view.activity?.response === "text" ? (
              <TryReflect question={view.activity?.question || "ตอบสั้น ๆ"} busy={busy} onSend={async (text) => setMessage((await call("/reflect", { answer: text }))?.result?.message ?? null)} />
            ) : (
              <Button size="sm" variant="primary" disabled={busy} onClick={() => call("/lesson-done")} style={{ alignSelf: "flex-start" }}>
                ทำเสร็จแล้ว ไปต่อ
              </Button>
            ))}
        </div>
      ) : view.position === "FLOW_WIDGET" && view.widget ? (
        <div className="gem-item">
          <span className="small strong">{view.widget.title}</span>
          {view.widget.prompt && <span className="small">{view.widget.prompt}</span>}
          <FlowWidget key={`${view.widget.title}-${view.widget.type}`} widget={view.widget} onSubmit={async (response) => (await call("/widget", { response }))?.result} />
        </div>
      ) : view.position === "FLOW_REFLECT" ? (
        <TryReflect question={view.reflect?.question ?? ""} busy={busy} onSend={async (text) => setMessage((await call("/reflect", { answer: text }))?.result?.message ?? null)} />
      ) : view.position === "IDLE_PAUSE" ? (
        <div className="gem-item">
          <span className="small">พักอยู่ (Idle Pause)</span>
          <Button size="sm" variant="primary" disabled={busy} onClick={() => call("/resume")} style={{ alignSelf: "flex-start" }}>
            กลับมาทำต่อ
          </Button>
        </div>
      ) : view.position === "STAGNATION_DEADLOCK" || view.position === "SAFETY_STOP" ? (
        <p className="small callout callout-calm">
          นักเรียนจริงจะหยุดรอครูตรงนี้ ครูกดปล่อยต่อได้ในหน้าภาพรวมห้อง (Manual Override) ในพรีวิวกดเริ่มใหม่เพื่อลองต่อ
        </p>
      ) : view.position === "CIRCUIT_BREAKER" ? (
        <p className="small callout callout-calm">
          {view.break_text || "พักสายตา"} · อีก {Math.ceil(view.timers.break)} วินาที
        </p>
      ) : view.walkthrough ? (
        <div className="gem-item">
          <span className="small strong">{view.walkthrough.title}</span>
          <span className="gem-item-math">{view.walkthrough.problem}</span>
          <ol className="small">
            {view.walkthrough.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      ) : (
        item && (
          <div className="gem-item">
            <span className="small">{item.prompt}</span>
            {item.math && <span className="gem-item-math">{item.math}</span>}
            {item.format === "mcq" ? (
              <div className="gem-try-options">
                {item.options.map((o) => (
                  <button key={o.id} type="button" disabled={busy || locked} onClick={() => submit(o.id)}>
                    <span className="mono">{o.id}</span> {o.text}
                  </button>
                ))}
              </div>
            ) : (
              <form
                className="row row-sm row-nowrap"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  submit(answer);
                }}
              >
                <input className="input" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="พิมพ์คำตอบ" disabled={locked} />
                <Button variant="primary" type="submit" disabled={!answer.trim() || busy || locked}>
                  {locked ? `ล็อก ${Math.ceil(view.timers.lock)} วิ` : "ส่ง"}
                </Button>
              </form>
            )}
          </div>
        )
      )}

      {message && <div className="callout callout-info small">{message}</div>}
      {view.timers.delay > 0 && <p className="xsmall muted">Deliberate Delay: คำใบ้จะขึ้นในอีก {Math.ceil(view.timers.delay)} วินาที</p>}

      {tools.hints !== false && (view.hints.length > 0 || view.hint_button.visible) && (
        <div className="stack stack-sm">
          {view.hints.map((h) => (
            <div key={h.level} className="gem-try-hint">
              <span className="xsmall strong">คำใบ้ระดับ {h.level}</span>
              <span className="small">{h.text ?? (h.status === "pending" ? "AI กำลังเขียนคำใบ้…" : "")}</span>
            </div>
          ))}
          {view.hint_button.visible && (
            <Button
              size="sm"
              icon={<Lightbulb size={14} />}
              disabled={busy || view.hint_button.unlock_in > 0 || view.hint_button.cooldown > 0}
              onClick={async () => setMessage((await call("/hint"))?.result?.message ?? null)}
              style={{ alignSelf: "flex-start" }}
            >
              {view.hint_button.unlock_in > 0 ? `ขอคำใบ้ได้ในอีก ${Math.ceil(view.hint_button.unlock_in)} วิ` : "ขอคำใบ้"}
            </Button>
          )}
        </div>
      )}

      {tools.chat !== false && (
        <TryChat lines={chat} starters={view.gem?.starter_prompts ?? []} busy={busy} onSend={send} />
      )}

      {data?.ai && (
        <div className="stack stack-sm">
          <span className="xsmall strong muted">prompt ที่ส่งให้ AI ล่าสุด</span>
          <AiLogCard log={data.ai} />
        </div>
      )}
    </div>
  );
}

function TryChat({ lines, starters, busy, onSend }: { lines: ChatLine[]; starters: string[]; busy: boolean; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [lines]);
  return (
    <div className="gem-try-chat">
      <div className="gem-try-lines" ref={list}>
        {lines.length === 0 &&
          starters.map((s) => (
            <button key={s} type="button" className="starter-chip" onClick={() => onSend(s)} disabled={busy}>
              {s}
            </button>
          ))}
        {lines.map((l, i) => (
          <div key={i} className={`bubble bubble-${l.from}`}>
            {l.text}
          </div>
        ))}
        {busy && lines[lines.length - 1]?.from === "me" && <LoaderCircle size={16} className="spin" />}
      </div>
      <form
        className="row row-sm row-nowrap"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          onSend(text.trim());
          setText("");
        }}
      >
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="ถามครูผู้ช่วย" />
        <Button variant="primary" className="btn-icon" type="submit" disabled={!text.trim() || busy} icon={<Send size={15} />} aria-label="ส่ง" />
      </form>
    </div>
  );
}

// แท็บ "เวอร์ชัน": ทุกครั้งที่บันทึกหรือสร้างคลังใหม่ ย้อนกลับได้
export function Versions({ gem, onRestored }: { gem: GemDetail; onRestored: (g: GemDetail) => void }) {
  const toast = useToast();
  const now = useNow(30000);
  const [target, setTarget] = useState<GemVersion | null>(null);
  const [busy, setBusy] = useState(false);
  const current = gem.versions[0]?.n;

  const restore = async () => {
    if (!target) return;
    setBusy(true);
    try {
      onRestored(await api<GemDetail>("teacher", `/api/gems/${gem.id}/versions/${target.n}/restore`, { method: "POST" }));
      toast(`ย้อนกลับไปเวอร์ชัน ${target.n} แล้ว`, "success");
      setTarget(null);
    } catch (err) {
      toast(err instanceof Error ? err.message : "ย้อนกลับไม่สำเร็จ", "warning");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack stack-sm">
      <p className="xsmall muted">นักเรียนที่เริ่มเรียนไปแล้วใช้คลังโจทย์รุ่นเดิมจนจบรอบ</p>
      <ol className="gem-versions">
        {gem.versions.map((v) => (
          <li key={v.n}>
            <span className="gem-version-n num">{v.n}</span>
            <span className="stack grow" style={{ gap: 1 }}>
              <span className="small">{v.note}</span>
              <span className="xsmall faint">
                {v.actor === "teacher" ? "ครู" : v.actor} · {ago(v.ts, now)}
                {v.bank_version ? ` · คลังรุ่นที่ ${v.bank_version}` : ""}
              </span>
            </span>
            {v.n === current ? (
              <Badge tone="success">ปัจจุบัน</Badge>
            ) : (
              <Button size="sm" variant="ghost" icon={<History size={14} />} onClick={() => setTarget(v)}>
                ย้อนกลับ
              </Button>
            )}
          </li>
        ))}
      </ol>
      <Modal
        open={!!target}
        onClose={() => setTarget(null)}
        title={`ย้อนกลับไปเวอร์ชัน ${target?.n ?? ""}`}
        footer={
          <>
            <Button onClick={() => setTarget(null)}>ยกเลิก</Button>
            <Button variant="primary" loading={busy} onClick={restore}>
              ย้อนกลับ
            </Button>
          </>
        }
      >
        <p className="small">
          ชื่อ คำสั่ง เครื่องมือ และคลังโจทย์จะกลับไปเป็นแบบ "{target?.note}" ระบบจะบันทึกการย้อนกลับเป็นเวอร์ชันใหม่ จึงย้อนกลับมาอีกครั้งได้
        </p>
      </Modal>
    </div>
  );
}

function TryReflect({ question, busy, onSend }: { question: string; busy: boolean; onSend: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  return (
    <div className="gem-item">
      <span className="small strong">{question}</span>
      <textarea className="input reflect-input" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="ลองพิมพ์คำอธิบายแบบนักเรียน" />
      <Button
        size="sm"
        variant="primary"
        disabled={busy || !text.trim()}
        onClick={async () => {
          await onSend(text.trim());
          setText("");
        }}
        style={{ alignSelf: "flex-start" }}
      >
        ส่งคำอธิบาย
      </Button>
    </div>
  );
}
