import { useEffect, useMemo, useState } from "react";
import { Check, Flag, PencilLine, Plus, Sparkles, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { Badge, Button, Field, Modal, Segmented, Spinner, useToast } from "../../components/ui";

// คลังโจทย์ของ Gem: ครูตรวจ อนุมัติ แก้ เพิ่ม และลบโจทย์ทีละข้อ (Human-in-the-Loop)
// ข้อที่ครูบันทึกถือว่าครูตรวจแล้ว ข้อที่ AI สร้างจากปุ่มสร้างเพิ่มรออนุมัติก่อนถึงนักเรียน

type Status = "active" | "flagged" | "pending" | "check";

interface BankRow {
  id: string;
  kind: string;
  format: "numeric" | "mcq" | "short";
  prompt: string;
  math: string | null;
  options: { id: string; text: string }[] | null;
  answer: { value?: number; option?: string; accepted?: string[] };
  hints: Record<string, string>;
  difficulty: number;
  concept: string;
  concept_name: string | null;
  iso_of: string | null;
  isomorphs: string[];
  flag: { reasons: string[] } | null;
  live: boolean | null;
  status: Status;
  answer_text: string;
}

interface Listing {
  items: BankRow[];
  concepts: { id: string; name: string }[];
  target: string;
  warning?: string | null;
}

const STATUS: Record<Status, { label: string; tone: "success" | "warning" | "info" | "calm" }> = {
  active: { label: "ใช้งานอยู่", tone: "success" },
  flagged: { label: "เฉลยติดธง", tone: "warning" },
  pending: { label: "รอครูอนุมัติ", tone: "info" },
  check: { label: "สร้างสด รอตรวจ", tone: "calm" },
};

const KIND: Record<string, string> = { main: "โจทย์หลัก", isomorphic: "ข้อคู่ขนาน", remedial: "ทบทวนพื้นฐาน", challenge: "โจทย์ท้าทาย" };
const FORMAT: Record<string, string> = { numeric: "ตัวเลข", mcq: "ปรนัย", short: "คำตอบสั้น" };

type Filter = "review" | "all" | Status;

export default function GemItems({ gemId, onChanged }: { gemId: string; onChanged: () => void }) {
  const toast = useToast();
  const [data, setData] = useState<Listing | null>(null);
  const [filter, setFilter] = useState<Filter>("review");
  const [editing, setEditing] = useState<BankRow | "new" | null>(null);
  const [removing, setRemoving] = useState<BankRow | null>(null);
  const [generating, setGenerating] = useState(false);
  const base = `/api/gems/${gemId}`;

  const load = () => api<Listing>("teacher", `${base}/items`).then(setData).catch(() => {});
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gemId]);

  const apply = (next: Listing, message: string) => {
    setData(next);
    onChanged();
    if (next.warning) toast(`บันทึกแล้ว แต่ ${next.warning}`, "warning");
    else toast(message, "success");
  };

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: data?.items.length ?? 0, review: 0 };
    for (const it of data?.items ?? []) {
      c[it.status] = (c[it.status] ?? 0) + 1;
      if (it.status !== "active") c.review += 1;
    }
    return c;
  }, [data]);

  // มีข้อต้องตรวจ เปิดที่รายการนั้นก่อน ถ้าไม่มีแสดงทั้งหมด
  const shown = filter === "review" && !counts.review ? "all" : filter;
  const rows = (data?.items ?? []).filter((it) => (shown === "all" ? true : shown === "review" ? it.status !== "active" : it.status === shown));

  const generate = async (count: number) => {
    setGenerating(true);
    try {
      apply(await api<Listing>("teacher", `${base}/generate`, { body: { count } }), `AI สร้างโจทย์เพิ่ม ${count} ข้อ รอครูอนุมัติก่อนถึงนักเรียน`);
      setFilter("pending");
    } catch (err) {
      toast(err instanceof Error ? err.message : "AI สร้างโจทย์ไม่สำเร็จ", "warning");
    } finally {
      setGenerating(false);
    }
  };

  if (!data) return <Spinner />;

  return (
    <div className="stack">
      <div className="spread">
        <span className="small strong">โจทย์ทั้งหมด {counts.all} ข้อ</span>
        <span className="row row-sm">
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditing("new")}>
            เพิ่มเอง
          </Button>
          <Button size="sm" variant="soft" icon={<Sparkles size={14} />} loading={generating} onClick={() => generate(2)}>
            AI สร้างเพิ่ม 2 ข้อ
          </Button>
        </span>
      </div>
      <div className="pill-list" role="group" aria-label="กรองตามสถานะ">
        {(
          [
            ["review", `ต้องตรวจ ${counts.review}`],
            ["all", `ทั้งหมด ${counts.all}`],
            ["flagged", `ติดธง ${counts.flagged ?? 0}`],
            ["pending", `รออนุมัติ ${counts.pending ?? 0}`],
            ["check", `สร้างสดรอตรวจ ${counts.check ?? 0}`],
          ] as [Filter, string][]
        ).map(([key, label]) => (
          <button key={key} type="button" className={`chip-toggle ${shown === key ? "on" : ""}`} aria-pressed={shown === key} onClick={() => setFilter(key)}>
            {label}
          </button>
        ))}
      </div>
      {shown === "review" && <p className="xsmall muted">ติดธงและรออนุมัติยังไม่ถึงนักเรียน ส่วนโจทย์สดนักเรียนใช้ไปแล้ว ตรวจแล้วแก้หรือลบได้</p>}

      <ul className="bank-list">
        {rows.map((it) => (
          <li key={it.id} className={`bank-row status-${it.status}`}>
            <div className="spread">
              <span className="row row-sm xsmall">
                <span className="mono strong">{it.id}</span>
                <Badge tone={STATUS[it.status].tone}>{STATUS[it.status].label}</Badge>
                <span className="faint">
                  {KIND[it.kind] ?? it.kind}
                  {it.iso_of ? ` ของ ${it.iso_of}` : ""} · {FORMAT[it.format]} · {it.concept_name}
                </span>
              </span>
              <span className="row row-sm row-nowrap">
                {it.status !== "active" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<Check size={14} />}
                    onClick={async () => apply(await api<Listing>("teacher", `${base}/items/${it.id}/approve`, { method: "POST" }), `อนุมัติ ${it.id} แล้ว`)}
                  >
                    อนุมัติ
                  </Button>
                )}
                <Button size="sm" variant="ghost" className="btn-icon" icon={<PencilLine size={14} />} onClick={() => setEditing(it)} aria-label={`แก้ ${it.id}`} />
                <Button size="sm" variant="ghost" className="btn-icon" icon={<Trash2 size={14} />} onClick={() => setRemoving(it)} aria-label={`ลบ ${it.id}`} />
              </span>
            </div>
            <span className="small">{it.prompt}</span>
            {it.math && <span className="gem-item-math">{it.math}</span>}
            {it.options && it.options.length > 0 && <span className="xsmall muted">{it.options.map((o) => `(${o.id}) ${o.text}`).join("  ")}</span>}
            <span className="xsmall">
              เฉลย: <span className="strong">{it.answer_text}</span>
            </span>
            {it.flag && (
              <ul className="gem-flag-reasons">
                {it.flag.reasons.map((r) => (
                  <li key={r}>
                    <Flag size={11} /> {r}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
        {rows.length === 0 && <li className="small faint">ไม่มีโจทย์ในกลุ่มนี้</li>}
      </ul>

      {editing && (
        <ItemModal
          item={editing === "new" ? null : editing}
          data={data}
          onClose={() => setEditing(null)}
          onSave={async (body) => {
            const path = editing === "new" ? `${base}/items` : `${base}/items/${editing.id}`;
            const next = await api<Listing & { saved: string }>("teacher", path, { method: editing === "new" ? "POST" : "PUT", body });
            apply(next, editing === "new" ? `เพิ่มโจทย์ ${next.saved} แล้ว นักเรียนได้ข้อนี้ทันที` : `บันทึก ${next.saved} แล้ว`);
            setEditing(null);
          }}
        />
      )}
      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title={`ลบโจทย์ ${removing?.id ?? ""}`}
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>ยกเลิก</Button>
            <Button
              variant="danger"
              onClick={async () => {
                apply(await api<Listing>("teacher", `${base}/items/${removing!.id}`, { method: "DELETE" }), `ลบ ${removing!.id} แล้ว`);
                setRemoving(null);
              }}
            >
              ลบ
            </Button>
          </>
        }
      >
        <p className="small">
          {removing?.kind === "main" && removing.isomorphs.length ? `ข้อคู่ขนาน ${removing.isomorphs.join(", ")} จะถูกลบด้วย ` : ""}
          นักเรียนที่กำลังทำข้อนี้อยู่จะได้ข้อถัดไปแทน
        </p>
      </Modal>
    </div>
  );
}

// หน้าต่างเพิ่มหรือแก้โจทย์หนึ่งข้อ ช่องเฉลยเปลี่ยนตามรูปแบบคำตอบ
function ItemModal({ item, data, onClose, onSave }: { item: BankRow | null; data: Listing; onClose: () => void; onSave: (body: unknown) => Promise<void> }) {
  const toast = useToast();
  const [kind, setKind] = useState(item?.kind ?? "main");
  const [isoOf, setIsoOf] = useState("");
  const [concept, setConcept] = useState(item?.concept ?? data.target);
  const [prompt, setPrompt] = useState(item?.prompt ?? "จงหาค่าของ x จากสมการ");
  const [math, setMath] = useState(item?.math ?? "");
  const [format, setFormat] = useState<BankRow["format"]>(item?.format ?? "numeric");
  const [value, setValue] = useState(item?.answer.value != null ? String(item.answer.value) : "");
  const [options, setOptions] = useState<string[]>(item?.options?.length ? item.options.map((o) => o.text) : ["", "", "", ""]);
  const [correct, setCorrect] = useState(item?.answer.option ?? "a");
  const [accepted, setAccepted] = useState((item?.answer.accepted ?? []).join("\n"));
  const [hints, setHints] = useState<Record<string, string>>(item?.hints ?? { "1": "", "2": "", "3": "" });
  const [difficulty, setDifficulty] = useState(item?.difficulty ?? 0.5);
  const [busy, setBusy] = useState(false);
  const mains = data.items.filter((it) => it.kind === "main");

  const save = async () => {
    setBusy(true);
    try {
      await onSave({
        kind,
        iso_of: kind === "isomorphic" ? isoOf : null,
        concept,
        prompt,
        math,
        format,
        difficulty,
        hints,
        options: options.map((text) => ({ text })),
        answer: format === "numeric" ? { value } : format === "mcq" ? { option: correct } : { accepted: accepted.split(/\n|,/) },
      });
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ", "warning");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={item ? `แก้โจทย์ ${item.id}` : "เพิ่มโจทย์เอง"}
      footer={
        <>
          <Button onClick={onClose}>ยกเลิก</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {item && item.status !== "active" ? "บันทึกและอนุมัติ" : "บันทึก"}
          </Button>
        </>
      }
    >
      <div className="stack">
        {!item && (
          <div className="grid grid-2">
            <Field label="ประเภท">
              <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(KIND).map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            {kind === "isomorphic" ? (
              <Field label="คู่ขนานของโจทย์หลัก">
                <select className="select" value={isoOf} onChange={(e) => setIsoOf(e.target.value)}>
                  <option value="">เลือกโจทย์หลัก</option>
                  {mains.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.id} · {m.math ?? m.prompt.slice(0, 30)}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <Field label="มโนทัศน์">
                <select className="select" value={concept} onChange={(e) => setConcept(e.target.value)}>
                  {data.concepts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>
        )}
        <Field label="คำสั่งโจทย์">
          <textarea className="textarea" rows={2} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </Field>
        <Field label="สมการหรือนิพจน์" hint="ข้อความธรรมดา ใช้ / แทนเศษส่วน ระบบตรวจเฉลยด้วย sympy ให้อีกชั้น">
          <input className="input mono" value={math} onChange={(e) => setMath(e.target.value)} placeholder="2x + 3 = 11" />
        </Field>
        <Segmented
          label="รูปแบบคำตอบ"
          value={format}
          onChange={setFormat}
          options={[
            { id: "numeric", label: "ตัวเลข" },
            { id: "mcq", label: "ปรนัย" },
            { id: "short", label: "คำตอบสั้น" },
          ]}
        />
        {format === "numeric" && (
          <Field label="เฉลย" hint="ตัวเลข ทศนิยม หรือเศษส่วน เช่น 4, -2.5, 3/4">
            <input className="input mono" value={value} onChange={(e) => setValue(e.target.value)} />
          </Field>
        )}
        {format === "mcq" && (
          <div className="stack stack-sm">
            <span className="small strong">ตัวเลือก (เลือกข้อที่ถูก)</span>
            {options.map((text, i) => {
              const id = "abcdefgh"[i];
              return (
                <label key={i} className="row row-sm row-nowrap">
                  <input type="radio" name="correct" checked={correct === id} onChange={() => setCorrect(id)} />
                  <span className="mono small">{id}</span>
                  <input className="input" value={text} onChange={(e) => setOptions(options.map((o, j) => (j === i ? e.target.value : o)))} />
                </label>
              );
            })}
            {options.length < 8 && (
              <Button size="sm" variant="ghost" icon={<Plus size={14} />} onClick={() => setOptions([...options, ""])} style={{ alignSelf: "flex-start" }}>
                เพิ่มตัวเลือก
              </Button>
            )}
          </div>
        )}
        {format === "short" && (
          <Field label="คำตอบที่ยอมรับ" hint="บรรทัดละหนึ่งคำตอบ ระบบไม่สนช่องว่าง">
            <textarea className="textarea" rows={3} value={accepted} onChange={(e) => setAccepted(e.target.value)} />
          </Field>
        )}
        {(["1", "2", "3"] as const).map((level) => (
          <Field key={level} label={`คำใบ้ระดับ ${level}`} hint={level === "3" ? "แสดงเฉพาะขั้นแรก ห้ามบอกคำตอบสุดท้าย" : undefined}>
            <textarea className="textarea" rows={2} value={hints[level] ?? ""} onChange={(e) => setHints({ ...hints, [level]: e.target.value })} />
          </Field>
        ))}
        <Field label={`ความยาก ${Math.round(difficulty * 100)}`}>
          <input type="range" min={0} max={1} step={0.05} value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))} />
        </Field>
      </div>
    </Modal>
  );
}
