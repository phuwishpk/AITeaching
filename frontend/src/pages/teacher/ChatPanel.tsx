import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Bot, Check, History, Lightbulb, LogIn, LogOut, PencilLine, Send, Trash2, UserRound } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { clock } from "../../lib/format";
import { Badge, Button, Spinner, useToast } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

// บทสนทนากับนักเรียนหนึ่งคน: ครูตอบเองได้ และเข้าร่วมแชตเพื่อตรวจร่างคำตอบของ AI ก่อนถึงนักเรียน (Human-in-the-Loop)

// ประวัติที่นักเรียนคุยกับ AI และกับครู รวมคำใบ้ที่ AI ให้ (hint) ย้อนหลังได้ทีละหน้า
interface Message {
  id: string;
  ts: number;
  sender: "student" | "tutor" | "teacher" | "system" | "draft" | "hint";
  text: string;
  draft_id?: number | null;
  set_name?: string | null;
  level?: number;
  authored?: boolean;
}

interface Page {
  messages: Message[];
  has_more: boolean;
  mode: "ai" | "teacher";
}

const SENDER: Record<Message["sender"], string> = {
  student: "นักเรียน",
  tutor: "ครูผู้ช่วย (AI)",
  system: "ระบบ",
  teacher: "ครู",
  draft: "ร่างจาก AI · รอครูตรวจ",
  hint: "คำใบ้",
};

const QUICK_REPLIES = [
  "ครูเห็นข้อความแล้ว กำลังมาช่วยนะ",
  "ไม่เป็นไรนะ พักสักครู่แล้วค่อยลองใหม่ด้วยกัน",
  "ลองอ่านตัวอย่างทีละขั้นก่อน แล้วค่อยกลับมาข้อนี้",
  "เก่งมาก ทำต่อได้เลย",
];

export default function ChatPanel({ code, name, position }: { code: string; name: string; position: string | null }) {
  const toast = useToast();
  const { lastEvent } = useTeacher();
  const [hints, setHints] = useState(true);
  const thread = useLoad(() => api<Page>("teacher", `/api/teacher/students/${code}/messages?hints=${hints}`), [code, hints]);
  // หน้าที่โหลดย้อนหลังเพิ่ม เก็บแยกจากหน้าล่าสุดที่โหลดใหม่ทุกครั้งที่มีข้อความเข้า
  const [older, setOlder] = useState<{ messages: Message[]; has_more: boolean } | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const keepScroll = useRef<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const mode = thread.data?.mode ?? "ai";

  useEffect(() => {
    if (lastEvent?.code !== code) return;
    const id = setTimeout(thread.reload, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  useEffect(() => setOlder(null), [code, hints]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [thread.data]);

  // โหลดหน้าเก่าแล้วคงตำแหน่งที่อ่านอยู่ ไม่กระโดดไปบนสุด
  useLayoutEffect(() => {
    const list = listRef.current;
    if (list && keepScroll.current != null) {
      list.scrollTop = list.scrollHeight - keepScroll.current;
      keepScroll.current = null;
    }
  }, [older]);

  const latest = thread.data?.messages ?? [];
  const messages = [...(older?.messages ?? []), ...latest.filter((m) => !(older?.messages ?? []).some((o) => o.id === m.id))];
  const hasMore = older ? older.has_more : (thread.data?.has_more ?? false);

  const loadOlder = async () => {
    if (!messages.length) return;
    setLoadingOlder(true);
    try {
      const page = await api<Page>("teacher", `/api/teacher/students/${code}/messages?hints=${hints}&before=${messages[0].ts}`);
      keepScroll.current = (listRef.current?.scrollHeight ?? 0) - (listRef.current?.scrollTop ?? 0);
      setOlder({ messages: [...page.messages, ...(older?.messages ?? [])], has_more: page.has_more });
    } finally {
      setLoadingOlder(false);
    }
  };

  const run = async (key: string, job: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await job();
      thread.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "ทำรายการไม่สำเร็จ", "warning");
    } finally {
      setBusy(null);
    }
  };

  const send = (message: string) =>
    message.trim() &&
    run("send", async () => {
      await api("teacher", `/api/teacher/students/${code}/messages`, { body: { text: message.trim() } });
      setText("");
    });

  const setMode = (next: "ai" | "teacher") =>
    run("mode", () => api("teacher", `/api/teacher/students/${code}/chat-mode`, { body: { mode: next } }));

  const waiting = position === "SAFETY_STOP" || position === "STAGNATION_DEADLOCK";
  const drafts = latest.filter((m) => m.sender === "draft").length;

  return (
    <div className="stack chat-panel">
      <div className={`chat-mode ${mode === "teacher" ? "on" : ""}`}>
        <span className="chat-mode-icon">{mode === "teacher" ? <UserRound size={18} /> : <Bot size={18} />}</span>
        <div className="stack grow" style={{ gap: 2 }}>
          <span className="small strong">{mode === "teacher" ? "ครูอยู่ในแชต" : "ครูผู้ช่วย (AI) ตอบเอง"}</span>
          <span className="xsmall muted">
            {mode === "teacher"
              ? "AI ไม่ตอบนักเรียนเอง แต่ร่างคำตอบให้ครูตรวจ แก้ หรือทิ้งก่อนส่ง"
              : "ครูอ่านทุกข้อความได้และพิมพ์แทรกได้ทุกเมื่อ กดเข้าร่วมแชตเพื่อตรวจคำตอบของ AI ก่อนถึงนักเรียน"}
          </span>
        </div>
        {mode === "teacher" ? (
          <Button size="sm" variant="ghost" icon={<LogOut size={15} />} loading={busy === "mode"} onClick={() => setMode("ai")}>
            ให้ AI ตอบต่อ
          </Button>
        ) : (
          <Button size="sm" variant="primary" icon={<LogIn size={15} />} loading={busy === "mode"} onClick={() => setMode("teacher")}>
            เข้าร่วมแชต
          </Button>
        )}
      </div>

      {waiting && (
        <div className="callout callout-warning">
          <span className="small">
            ระบบหยุดรอครูอยู่ ข้อความที่นักเรียนพิมพ์ส่งถึงครูโดยตรง AI ไม่ตอบ คุยเสร็จแล้วกดปลดล็อกในแผงของนักเรียน แท็บ "ตอนนี้และ Override"
          </span>
        </div>
      )}
      {drafts > 0 && <Badge tone="info">ร่างจาก AI รอครูตรวจ {drafts} ข้อความ</Badge>}

      <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}>
        <span className="xsmall muted row row-sm">
          <History size={13} />
          ประวัติทั้งหมดกับ AI และครู
        </span>
        <label className="check xsmall">
          <input type="checkbox" checked={hints} onChange={(e) => setHints(e.target.checked)} />
          แสดงคำใบ้จาก AI
        </label>
      </div>
      <div className="teacher-thread" ref={listRef}>
        {thread.loading && !thread.data && <Spinner />}
        {hasMore && (
          <Button size="sm" variant="ghost" className="thread-older" loading={loadingOlder} onClick={loadOlder}>
            ดูข้อความเก่ากว่านี้
          </Button>
        )}
        {thread.data && messages.length === 0 && <p className="small faint">ยังไม่มีข้อความ ครูเริ่มทักนักเรียนได้เลย</p>}
        {messages.map((m, i) => [
          divider(m, messages[i - 1]),
          m.sender === "hint" ? (
            <div key={m.id} className="tmsg tmsg-hint">
              <span className="tmsg-meta xsmall row row-sm">
                <Lightbulb size={12} />
                คำใบ้ระดับ {m.level} {m.authored ? "(ข้อความต้นฉบับ AI ไม่ได้ปรับ)" : "จาก AI"} · {clock(m.ts)}
              </span>
              <span className="tmsg-text">{m.text}</span>
            </div>
          ) : m.sender === "draft" ? (
            <div key={m.id} className="tmsg tmsg-draft">
              <span className="tmsg-meta xsmall">
                {SENDER.draft} · {clock(m.ts)}
              </span>
              {editing?.id === m.id ? (
                <textarea
                  className="textarea"
                  rows={3}
                  value={editing.text}
                  onChange={(e) => setEditing({ id: m.id, text: e.target.value })}
                  aria-label="แก้ร่างก่อนส่ง"
                  autoFocus
                />
              ) : (
                <span className="tmsg-text">{m.text}</span>
              )}
              <span className="row row-sm draft-actions">
                {editing?.id === m.id ? (
                  <Button
                    size="sm"
                    variant="primary"
                    icon={<Send size={14} />}
                    loading={busy === `d${m.id}`}
                    disabled={!editing.text.trim()}
                    onClick={() =>
                      run(`d${m.id}`, async () => {
                        await api("teacher", `/api/teacher/drafts/${m.draft_id}/send`, { body: { text: editing.text } });
                        setEditing(null);
                      })
                    }
                  >
                    ส่งฉบับที่แก้
                  </Button>
                ) : (
                  <>
                    <Button
                      size="sm"
                      variant="primary"
                      icon={<Check size={14} />}
                      loading={busy === `d${m.id}`}
                      onClick={() => run(`d${m.id}`, () => api("teacher", `/api/teacher/drafts/${m.draft_id}/send`, { body: {} }))}
                    >
                      ส่งตามนี้
                    </Button>
                    <Button size="sm" variant="secondary" icon={<PencilLine size={14} />} onClick={() => setEditing({ id: m.id, text: m.text })}>
                      แก้แล้วส่ง
                    </Button>
                  </>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={14} />}
                  onClick={() => run(`x${m.id}`, () => api("teacher", `/api/teacher/drafts/${m.draft_id}`, { method: "DELETE" }))}
                >
                  ทิ้ง
                </Button>
              </span>
            </div>
          ) : (
            <div key={m.id} className={`tmsg tmsg-${m.sender}`}>
              <span className="tmsg-meta xsmall">
                {m.sender === "student" ? name : SENDER[m.sender]} · {clock(m.ts)}
              </span>
              <span className="tmsg-text">{m.text}</span>
            </div>
          ),
        ])}
      </div>
      <div className="pill-list">
        {QUICK_REPLIES.map((q) => (
          <button key={q} type="button" className="chip-toggle" onClick={() => setText(q)}>
            {q}
          </button>
        ))}
      </div>
      <form
        className="teacher-compose"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <textarea
          className="textarea"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
          placeholder={`พิมพ์ถึง${name} ในฐานะครู (Enter ส่ง · Shift+Enter ขึ้นบรรทัดใหม่)`}
          maxLength={1000}
          aria-label="ข้อความถึงนักเรียน"
        />
        <Button variant="primary" type="submit" loading={busy === "send"} disabled={!text.trim()} icon={<Send size={16} />}>
          ส่ง
        </Button>
      </form>
      <p className="xsmall faint">ข้อความของนักเรียนที่แสดงเป็นฉบับที่ลบข้อมูลส่วนตัวแล้ว ข้อความของครูขึ้นในกล่องแชตของนักเรียนทันทีพร้อมป้าย "ครู"</p>
    </div>
  );
}

// เส้นคั่นเมื่อขึ้นวันใหม่หรือเปลี่ยน Gem: ครูเห็นว่าแต่ละช่วงคุยกันตอนไหน เรื่องอะไร
function divider(m: Message, prev: Message | undefined) {
  const day = (ts: number) => new Date(ts * 1000).toLocaleDateString("th-TH", { dateStyle: "medium" });
  const setOf = (x: Message | undefined) => x?.set_name ?? null;
  const newDay = !prev || day(prev.ts) !== day(m.ts);
  const newSet = m.set_name && setOf(prev) !== m.set_name;
  if (!newDay && !newSet) return null;
  return (
    <div key={`d-${m.id}`} className="thread-divider xsmall">
      <span>
        {day(m.ts)}
        {m.set_name ? ` · ${m.set_name}` : ""}
      </span>
    </div>
  );
}
