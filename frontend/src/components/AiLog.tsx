import { ChevronDown, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { clock, num } from "../lib/format";
import type { AiLog } from "../lib/types";
import { Badge } from "./ui";

// บันทึกการเรียก AI หนึ่งครั้ง: prompt 4 กรอบ, เอกสารที่ RAG ดึงมา, ข้อความดิบจาก LLM และผลของ Answer-Leak Guard
// ครูใช้ตรวจข้อเท็จจริงย้อนหลังได้ทุกครั้ง (HITL ข้อ 1)

export const PURPOSE_LABEL: Record<string, string> = {
  hint_l1: "คำใบ้ระดับ 1",
  hint_l2: "คำใบ้ระดับ 2",
  hint_l3: "คำใบ้ระดับ 3",
  chat: "แชตกับครูผู้ช่วย",
  suggest_tag: "เสนอแท็ก Bug Library",
};

export const FRAME_LABEL: Record<string, string> = {
  role: "1. Role & Persona",
  context: "2. Context & Environment",
  task: "3. Task & Intent",
  constraints: "4. Constraints & Fallback",
};

export function GuardBadge({ log }: { log: AiLog }) {
  if (log.guard?.trigger) return <Badge tone="warning">ส่ง Circuit Breaker</Badge>;
  if (log.guard?.blocked)
    return (
      <Badge tone="warning">
        <ShieldAlert size={13} />
        Guard บล็อก ใช้ข้อความต้นฉบับแทน
      </Badge>
    );
  if (log.provider === "offline") return <Badge tone="calm">Offline ใช้ข้อความต้นฉบับ</Badge>;
  return (
    <Badge tone="success">
      <ShieldCheck size={13} />
      ผ่าน Guard
    </Badge>
  );
}

export default function AiLogCard({ log, who, open }: { log: AiLog; who?: string | null; open?: boolean }) {
  const raw = log.output && log.output.trim() !== (log.final_text ?? "").trim() ? log.output : null;
  return (
    <details className="ailog" open={open}>
      <summary>
        <div className="ailog-head">
          <span className="row row-sm">
            <span className="strong small">{PURPOSE_LABEL[log.purpose] ?? log.purpose}</span>
            <Badge>{log.provider === "offline" ? "Offline" : `${log.provider}${log.model ? ` · ${log.model}` : ""}`}</Badge>
            <GuardBadge log={log} />
            {log.error && (
              <Badge tone="calm" title={log.error}>
                <TriangleAlert size={13} />
                ใช้สำรอง
              </Badge>
            )}
          </span>
          <span className="xsmall faint num">
            {who ? `${who} · ` : log.code ? `${log.code} · ` : ""}
            {clock(log.ts)}
            {log.latency_ms ? ` · ${num(log.latency_ms)} ms` : ""}
          </span>
        </div>
        <p className="ailog-text">{log.final_text || <span className="faint">(ไม่มีข้อความ)</span>}</p>
        <span className="ailog-more xsmall">
          ดู prompt และที่มา <ChevronDown size={14} />
        </span>
      </summary>
      <div className="ailog-body stack">
        {log.frames && (
          <div className="frames">
            {(["role", "context", "task", "constraints"] as const).map((key) =>
              log.frames?.[key] ? (
                <div key={key} className="frame">
                  <span className="frame-label">{FRAME_LABEL[key]}</span>
                  <pre className="code-block">{log.frames[key]}</pre>
                </div>
              ) : null,
            )}
          </div>
        )}
        {log.retrieved && (log.retrieved.documents?.length || log.retrieved.query_terms?.length) ? (
          <div className="stack stack-sm">
            <span className="frame-label">RAG: คำค้นหลังตัดคำ และย่อหน้าที่ดึงมา</span>
            {!!log.retrieved.query_terms?.length && (
              <div className="pill-list">
                {log.retrieved.query_terms.map((t, i) => (
                  <span key={i} className="token">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {log.retrieved.documents?.map((d, i) => (
              <div key={i} className="retrieved">
                <span className="xsmall faint">
                  {d.filename} · BM25 {num(d.score, 2)}
                </span>
                <p className="small">{d.text?.replace(/^#+\s*/gm, "")}</p>
              </div>
            ))}
          </div>
        ) : null}
        {raw && (
          <div className="stack stack-sm">
            <span className="frame-label">ข้อความดิบจาก LLM {log.guard?.blocked ? "(ถูกบล็อก ไม่ถึงนักเรียน)" : ""}</span>
            <pre className="code-block">{raw}</pre>
            {log.guard?.reason && <p className="xsmall muted">เหตุผลที่บล็อก: {log.guard.reason}</p>}
          </div>
        )}
        {log.error && <p className="xsmall muted">ข้อผิดพลาดจาก Provider: {log.error}</p>}
        {log.tokens_in || log.tokens_out ? (
          <p className="xsmall faint num">
            โทเคนขาเข้า {num(log.tokens_in)} · ขาออก {num(log.tokens_out)}
          </p>
        ) : null}
      </div>
    </details>
  );
}
