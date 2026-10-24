import { useEffect } from "react";
import { Check, X } from "lucide-react";
import { api } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { clock, num } from "../lib/format";
import { Badge, Card, CardHead, Empty, Spinner } from "./ui";

// โจทย์ที่นักเรียนกำลังทำ และคำตอบที่ส่งมาแต่ละครั้ง เทียบกับคำตอบที่ถูก (ใช้ในผังตรรกะและหน้าสาธิต)

export interface ItemBrief {
  id: string;
  prompt: string;
  math: string | null;
  format: "numeric" | "mcq" | "short";
  kind: string;
  options: { id: string; text: string }[];
  correct: string;
  correct_option: string | null;
}

interface SheetAnswer {
  ts: number;
  item: ItemBrief | null;
  raw: string;
  correct?: boolean;
  rapid: boolean;
  invalid: boolean;
  rt?: number;
  isomorphic: boolean;
  diagnosis?: { class?: string; tag_name?: string | null } | null;
}

interface Sheet {
  current: (ItemBrief & { mode: string; error_count: number; hint_level: number; attempts: { raw: string; kind: string; rt?: number }[] }) | null;
  answers: SheetAnswer[];
  position: string | null;
}

const MODE: Record<string, string> = {
  main: "โจทย์หลัก",
  isomorphic: "ข้อคู่ขนาน ไม่มีคำใบ้",
  challenge: "โจทย์ท้าทาย",
  remedial: "โจทย์ทบทวน",
  extra: "โจทย์ฝึกเพิ่ม",
};

const LETTERS = ["ก", "ข", "ค", "ง"];

// คำตอบปรนัยเก็บเป็นรหัสตัวเลือก แปลงเป็น "ข. x = 5" ให้อ่านง่าย
export function answerText(item: ItemBrief | null | undefined, raw: string) {
  if (!item || item.format !== "mcq") return raw;
  const index = item.options.findIndex((o) => o.id === raw);
  return index >= 0 ? `${LETTERS[index]}. ${item.options[index].text}` : raw;
}

export function ResultBadge({ answer }: { answer: { correct?: boolean; rapid?: boolean; invalid?: boolean; kind?: string } }) {
  if (answer.invalid || answer.kind === "invalid") return <Badge>ผิดรูปแบบ</Badge>;
  if (answer.kind === "undone") return <Badge>ยกเลิกแล้ว</Badge>;
  if (answer.correct || answer.kind === "correct")
    return (
      <Badge tone="success">
        <Check size={13} />
        ถูก
      </Badge>
    );
  if (answer.rapid || answer.kind === "rapid") return <Badge tone="warning">เร็วเกิน (โมฆะ)</Badge>;
  return (
    <Badge tone="calm">
      <X size={13} />
      ผิด
    </Badge>
  );
}

export function ItemView({ item, chosen }: { item: ItemBrief; chosen?: string[] }) {
  return (
    <div className="item-view">
      <p className="small muted">{item.prompt}</p>
      {item.math && <div className="problem-math small-math">{item.math}</div>}
      {item.format === "mcq" ? (
        <ol className="item-options">
          {item.options.map((o, i) => (
            <li key={o.id} className={[o.id === item.correct_option ? "is-correct" : "", chosen?.includes(o.id) ? "is-chosen" : ""].join(" ")}>
              <span className="option-letter">{LETTERS[i]}</span>
              <span className="grow">{o.text}</span>
              {o.id === item.correct_option && <span className="xsmall strong">คำตอบที่ถูก</span>}
              {chosen?.includes(o.id) && o.id !== item.correct_option && <span className="xsmall">นักเรียนเลือก</span>}
            </li>
          ))}
        </ol>
      ) : (
        <p className="small">
          คำตอบที่ถูก: <span className="strong mono">{item.correct}</span>
        </p>
      )}
    </div>
  );
}

export default function AnswerSheet({
  code,
  title,
  role = "admin",
  lastEvent,
  compact,
}: {
  code: string | null;
  title?: string;
  role?: "admin" | "teacher";
  lastEvent?: { code: string; n: number } | null;
  compact?: boolean;
}) {
  const path = role === "admin" ? `/api/admin/students/${code}/answers` : `/api/teacher/students/${code}/answers`;
  const sheet = useLoad(() => (code ? api<Sheet>(role, path) : Promise.resolve(null)), [code]);

  // นักเรียนคนนี้ตอบหรือเปลี่ยนสถานะ: โหลดใหม่
  useEffect(() => {
    if (!code || lastEvent?.code !== code) return;
    const id = setTimeout(sheet.reload, 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  const current = sheet.data?.current;
  return (
    <Card>
      <CardHead title={title ?? `โจทย์และคำตอบของ ${code ?? "–"}`} sub="คำตอบที่ถูกแสดงเฉพาะฝั่งครูและผู้ดูแลระบบ นักเรียนไม่เห็น" />
      <div className="card-body stack" style={{ paddingTop: 0 }}>
        {!code && <Empty>เลือกนักเรียนก่อน</Empty>}
        {code && sheet.loading && !sheet.data && <Spinner />}
        {sheet.data && (
          <div className={compact ? "answer-sheet answer-sheet-compact" : "answer-sheet"}>
            <section className="stack stack-sm">
              <span className="row row-sm">
                <span className="small strong">กำลังทำ</span>
                {current && (
                  <>
                    <span className="mono xsmall faint">{current.id}</span>
                    <Badge tone="accent">{MODE[current.mode] ?? current.mode}</Badge>
                  </>
                )}
              </span>
              {current ? (
                <>
                  <ItemView item={current} chosen={current.attempts.map((a) => a.raw)} />
                  <div className="stack stack-sm">
                    <span className="xsmall faint">
                      คำตอบในข้อนี้ · ผิด {current.error_count} ครั้ง · คำใบ้ถึงระดับ {current.hint_level}
                    </span>
                    <div className="pill-list">
                      {current.attempts.length === 0 && <span className="small faint">ยังไม่ได้ตอบ</span>}
                      {current.attempts.map((a, i) => (
                        <span key={i} className={`attempt attempt-${a.kind}`}>
                          <span className="mono">{answerText(current, a.raw)}</span>
                          <ResultBadge answer={{ kind: a.kind }} />
                        </span>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="small faint">ตอนนี้ไม่มีโจทย์ (จบชุดหรือยังไม่เริ่ม)</p>
              )}
            </section>

            <section className="stack stack-sm">
              <span className="small strong">คำตอบที่ผ่านมา (ใหม่สุดอยู่บน)</span>
              {sheet.data.answers.length === 0 ? (
                <p className="small faint">ยังไม่มีคำตอบ</p>
              ) : (
                <div className="table-wrap" style={{ maxHeight: 420 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>เวลา</th>
                        <th>โจทย์</th>
                        <th>นักเรียนตอบ</th>
                        <th>ที่ถูก</th>
                        <th>ผล</th>
                        <th className="num">เวลาคิด</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sheet.data.answers.map((a, i) => (
                        <tr key={i}>
                          <td className="xsmall faint num nowrap">{clock(a.ts)}</td>
                          <td>
                            <div className="stack" style={{ gap: 0 }}>
                              <span className="mono small">{a.item?.math ?? a.item?.prompt ?? "–"}</span>
                              <span className="xsmall faint">
                                {a.item?.id}
                                {a.isomorphic ? " · ข้อคู่ขนาน" : ""}
                              </span>
                            </div>
                          </td>
                          <td className="mono small">{answerText(a.item, a.raw)}</td>
                          <td className="mono small">{a.item?.correct ?? "–"}</td>
                          <td>
                            <div className="stack" style={{ gap: 2 }}>
                              <ResultBadge answer={a} />
                              {a.diagnosis?.tag_name && <span className="xsmall faint">{a.diagnosis.tag_name}</span>}
                            </div>
                          </td>
                          <td className="num small nowrap">{a.rt != null ? `${num(a.rt, 1)} วิ` : "–"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </Card>
  );
}
