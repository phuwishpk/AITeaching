import { useEffect, useMemo, useState } from "react";
import { Bot, MessageCircle, Search, UserRound } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago, POSITION_LABELS } from "../../lib/format";
import AnswerSheet from "../../components/AnswerSheet";
import { Badge, Card, Empty, Spinner } from "../../components/ui";
import ChatPanel from "./ChatPanel";
import { useTeacher } from "./TeacherApp";

// แชตกับนักเรียน: ทุกบทสนทนาในที่เดียว ตอบคำถามและตรวจกิจกรรมของนักเรียนคนนั้นข้าง ๆ กัน

interface InboxRow {
  code: string;
  name: string | null;
  last: { sender: string; text: string; ts: number };
  drafts: number;
  mode: "ai" | "teacher";
}

const LAST_FROM: Record<string, string> = { student: "", tutor: "AI: ", teacher: "ครู: ", system: "ระบบ: " };

export default function Inbox() {
  const { data, lastEvent, unread, markRead } = useTeacher();
  const inbox = useLoad(() => api<InboxRow[]>("teacher", "/api/teacher/inbox"));
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const now = useNow(15000);

  useEffect(() => {
    if (!lastEvent) return;
    const id = setTimeout(inbox.reload, 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  // คนที่มีบทสนทนาขึ้นก่อน ตามด้วยนักเรียนในห้องที่ยังไม่เคยคุย (ครูเริ่มทักได้)
  const rows = useMemo(() => {
    const talked = inbox.data ?? [];
    const seen = new Set(talked.map((r) => r.code));
    const others = (data?.students ?? [])
      .filter((s) => s.kind !== "sim" && !seen.has(s.code))
      .map((s) => ({ code: s.code, name: s.name ?? null, last: null, drafts: 0, mode: "ai" as const }));
    const all = [...talked, ...others];
    const q = query.trim().toLowerCase();
    return q ? all.filter((r) => `${r.code} ${r.name ?? ""}`.toLowerCase().includes(q)) : all;
  }, [inbox.data, data?.students, query]);

  useEffect(() => {
    if (!selected && rows.length) setSelected(rows[0].code);
  }, [rows, selected]);

  const student = data?.students.find((s) => s.code === selected);
  const name = student?.name ?? selected ?? "";

  // บทสนทนาที่เปิดอยู่ถือว่าอ่านแล้ว รวมถึงข้อความที่เพิ่งเข้ามาขณะเปิด
  useEffect(() => {
    if (selected && unread[selected]) markRead(selected);
  }, [selected, unread, markRead]);

  return (
    <div className="page stack stack-lg">
      <header className="stack stack-sm fade-in">
        <p className="eyebrow">แชตกับนักเรียน</p>
        <h1 className="title-xl">ตอบคำถามและดูว่านักเรียนทำอะไรอยู่</h1>
        <p className="lead">
          ครูอ่านทุกบทสนทนาได้ พิมพ์ตอบในฐานะครูได้ทุกเมื่อ หรือกด "เข้าร่วมแชต" ให้ AI ร่างคำตอบมาให้ตรวจก่อนถึงนักเรียน
        </p>
      </header>

      <div className="inbox-grid">
        <Card className="inbox-list-card">
          <label className="search-box inbox-search">
            <Search size={16} aria-hidden />
            <input className="input" type="search" placeholder="ค้นชื่อหรือรหัส" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          {inbox.loading && !inbox.data && <Spinner />}
          <ol className="inbox-list">
            {rows.map((r) => (
              <li key={r.code}>
                <button className={r.code === selected ? "is-on" : ""} onClick={() => setSelected(r.code)}>
                  <span className="inbox-avatar">{r.mode === "teacher" ? <UserRound size={16} /> : <Bot size={16} />}</span>
                  <span className="stack grow" style={{ gap: 1, minWidth: 0 }}>
                    <span className="row row-sm row-nowrap">
                      <span className="strong small nowrap">{r.name ?? r.code}</span>
                      <span className="xsmall faint mono">{r.code}</span>
                    </span>
                    <span className="xsmall muted inbox-last">
                      {r.last ? `${LAST_FROM[r.last.sender] ?? ""}${r.last.text}` : "ยังไม่เคยคุย"}
                    </span>
                  </span>
                  <span className="stack" style={{ gap: 3, alignItems: "flex-end" }}>
                    {r.last && <span className="xsmall faint nowrap">{ago(r.last.ts, now, true)}</span>}
                    {!!unread[r.code] && (
                      <span className="unread-pill">
                        <MessageCircle size={11} />
                        {unread[r.code]}
                      </span>
                    )}
                    {r.drafts > 0 && <Badge tone="info">ร่าง {r.drafts}</Badge>}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          {!rows.length && <Empty>ไม่พบนักเรียน</Empty>}
        </Card>

        <div className="stack">
          {selected ? (
            <>
              <Card className="card-pad stack">
                <div className="spread">
                  <div className="stack" style={{ gap: 2 }}>
                    <span className="subtitle">{name}</span>
                    <span className="xsmall faint mono">{selected}</span>
                  </div>
                  {student?.position && <Badge tone="accent">{POSITION_LABELS[student.position] ?? student.position}</Badge>}
                </div>
                <ChatPanel code={selected} name={name} position={student?.position ?? null} />
              </Card>
              <AnswerSheet code={selected} role="teacher" lastEvent={lastEvent} compact title="กิจกรรมของนักเรียน: โจทย์ที่กำลังทำและคำตอบ" />
            </>
          ) : (
            <Card className="card-pad">
              <Empty>เลือกนักเรียนจากรายการ</Empty>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
