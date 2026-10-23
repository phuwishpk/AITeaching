import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { BugTag, Concept, Item } from "../../lib/types";
import { Button, Field, Modal } from "../../components/ui";

export const KIND_LABEL: Record<Item["kind"], string> = {
  main: "โจทย์หลัก",
  isomorphic: "ข้อคู่ขนาน",
  challenge: "โจทย์ท้าทาย",
  remedial: "โจทย์ทบทวน",
};

export const FORMAT_LABEL: Record<Item["format"], string> = {
  numeric: "ตัวเลข",
  mcq: "ปรนัย",
  short: "ข้อความสั้น",
};

const LETTERS = ["a", "b", "c", "d"];

export function blankItem(concept: string, id: string): Item {
  return {
    id,
    concept,
    kind: "main",
    format: "numeric",
    prompt: "จงหาค่าของ x จากสมการ",
    math: "",
    difficulty: 0.5,
    min_read_time: 3,
    expected_time: 45,
    hints: { "1": "", "2": "", "3": "" },
    socratic: [],
    answer: { value: "" },
    bugs: [],
    isomorphs: [],
    iso_of: null,
  };
}

// ตัวแก้ไขโจทย์หนึ่งข้อ: คำตอบตาม Answer Format, คำตอบผิดที่รู้จัก (Bug Library) และคำใบ้ 3 ระดับที่ครูเขียนเอง
export default function ItemEditor({
  item,
  isNew,
  concepts,
  tags,
  mains,
  takenIds,
  onSave,
  onDelete,
  onClose,
}: {
  item: Item | null;
  isNew: boolean;
  concepts: Concept[];
  tags: BugTag[];
  mains: Item[];
  takenIds: string[];
  onSave: (item: Item, previousId: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Item | null>(item);
  useEffect(() => setDraft(item ? structuredClone(item) : null), [item]);
  if (!draft || !item) return null;

  const set = <K extends keyof Item>(key: K, value: Item[K]) => setDraft({ ...draft, [key]: value });
  const idTaken = draft.id !== item.id && takenIds.includes(draft.id);
  const options = draft.options ?? [];
  const accepted = (draft.answer.accepted ?? []).join("\n");

  const changeFormat = (format: Item["format"]) => {
    if (format === "mcq") {
      setDraft({
        ...draft,
        format,
        options: draft.options?.length ? draft.options : LETTERS.map((id) => ({ id, text: "" })),
        answer: { option: draft.answer.option ?? "a" },
        bugs: [],
      });
    } else if (format === "short") {
      setDraft({ ...draft, format, options: undefined, answer: { accepted: draft.answer.accepted ?? [] }, bugs: [] });
    } else {
      setDraft({ ...draft, format, options: undefined, answer: { value: draft.answer.value ?? "" }, bugs: [] });
    }
  };

  const save = () => {
    const clean: Item = { ...draft, id: draft.id.trim().toUpperCase() };
    if (clean.format === "numeric") {
      const value = String(clean.answer.value ?? "").trim();
      clean.answer = { value: /^-?\d+(\.\d+)?$/.test(value) ? Number(value) : value };
      clean.bugs = (clean.bugs ?? [])
        .filter((b) => String(b.answer).trim() && b.tag)
        .map((b) => ({ ...b, answer: /^-?\d+(\.\d+)?$/.test(String(b.answer).trim()) ? Number(b.answer) : String(b.answer).trim() }));
    }
    if (clean.kind !== "isomorphic") clean.iso_of = null;
    clean.socratic = (clean.socratic ?? []).map((s) => s.trim()).filter(Boolean);
    onSave(clean, item.id);
  };

  return (
    <Modal
      open
      wide
      onClose={onClose}
      title={isNew ? "เพิ่มโจทย์" : `แก้ไขโจทย์ ${item.id}`}
      footer={
        <>
          {!isNew && (
            <Button variant="ghost" icon={<Trash2 size={16} />} onClick={() => onDelete(item.id)} style={{ marginRight: "auto" }}>
              ลบโจทย์
            </Button>
          )}
          <Button onClick={onClose}>ยกเลิก</Button>
          <Button variant="primary" onClick={save} disabled={!draft.id.trim() || idTaken || !draft.prompt.trim()}>
            เก็บการแก้ไข
          </Button>
        </>
      }
    >
      <div className="stack">
        <div className="grid grid-4">
          <Field label="รหัสโจทย์" hint={idTaken ? "รหัสนี้มีอยู่แล้ว" : undefined}>
            <input className="input mono" value={draft.id} onChange={(e) => set("id", e.target.value)} aria-invalid={idTaken} />
          </Field>
          <Field label="มโนทัศน์">
            <select className="select" value={draft.concept} onChange={(e) => set("concept", e.target.value)}>
              {concepts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="ประเภท">
            <select className="select" value={draft.kind} onChange={(e) => set("kind", e.target.value as Item["kind"])}>
              {Object.entries(KIND_LABEL).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Answer Format">
            <select className="select" value={draft.format} onChange={(e) => changeFormat(e.target.value as Item["format"])}>
              {Object.entries(FORMAT_LABEL).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {draft.kind === "isomorphic" && (
          <Field label="เป็นข้อคู่ขนานของ" hint="โครงสร้างเดียวกับโจทย์หลักแต่เปลี่ยนตัวเลข ระบบใช้ทดสอบหลังผ่านด้วยคำใบ้ โดยปิดคำใบ้ทั้งหมด">
            <select className="select" value={draft.iso_of ?? ""} onChange={(e) => set("iso_of", e.target.value || null)}>
              <option value="">เลือกโจทย์หลัก</option>
              {mains.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id} · {m.math || m.prompt}
                </option>
              ))}
            </select>
          </Field>
        )}

        <div className="grid grid-2">
          <Field label="คำสั่งโจทย์">
            <textarea className="textarea" value={draft.prompt} onChange={(e) => set("prompt", e.target.value)} />
          </Field>
          <Field label="สมการหรือนิพจน์ (ไม่บังคับ)" hint="แสดงตัวใหญ่กลางกรอบ เช่น 2x + 3 = 11">
            <input className="input mono" value={draft.math ?? ""} onChange={(e) => set("math", e.target.value)} />
          </Field>
        </div>

        <fieldset className="fieldset">
          <legend>คำตอบที่ถูก</legend>
          {draft.format === "numeric" && (
            <Field label="ค่าที่ถูก" hint="รับเลขไทย เศษส่วน และทศนิยมที่เท่ากันได้">
              <input
                className="input mono"
                value={String(draft.answer.value ?? "")}
                onChange={(e) => set("answer", { value: e.target.value })}
                style={{ maxWidth: 200 }}
              />
            </Field>
          )}
          {draft.format === "mcq" && (
            <div className="stack stack-sm">
              {options.map((option, index) => (
                <div key={option.id} className="row row-sm">
                  <label className="check" title="ตัวเลือกที่ถูก">
                    <input
                      type="radio"
                      name="correct"
                      checked={draft.answer.option === option.id}
                      onChange={() => set("answer", { option: option.id })}
                    />
                    <span className="mono">{["ก", "ข", "ค", "ง"][index] ?? option.id}</span>
                  </label>
                  <input
                    className="input grow"
                    value={option.text}
                    onChange={(e) => set("options", options.map((o) => (o.id === option.id ? { ...o, text: e.target.value } : o)))}
                  />
                </div>
              ))}
              <p className="xsmall faint">เลือกปุ่มหน้าตัวเลือกที่ถูก ตัวเลือกผิดผูกกับ Bug Library ได้ในส่วนถัดไป</p>
            </div>
          )}
          {draft.format === "short" && (
            <Field label="คำตอบที่ยอมรับ (บรรทัดละหนึ่งคำตอบ)" hint="ระบบตรวจแบบตรงคำหลังตัดช่องว่าง ไม่ใช้ LLM ตัดสินถูกผิด">
              <textarea
                className="textarea"
                value={accepted}
                onChange={(e) => set("answer", { accepted: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })}
              />
            </Field>
          )}
        </fieldset>

        {draft.format !== "short" && (
          <fieldset className="fieldset">
            <legend>คำตอบผิดที่รู้จัก (Bug Library)</legend>
            <div className="stack stack-sm">
              {(draft.bugs ?? []).map((bug, index) => (
                <div key={index} className="row row-sm">
                  {draft.format === "mcq" ? (
                    <select
                      className="select"
                      style={{ maxWidth: 140 }}
                      value={String(bug.answer)}
                      onChange={(e) => set("bugs", (draft.bugs ?? []).map((b, i) => (i === index ? { ...b, answer: e.target.value } : b)))}
                    >
                      {options
                        .filter((o) => o.id !== draft.answer.option)
                        .map((o) => (
                          <option key={o.id} value={o.id}>
                            ตัวเลือก {["ก", "ข", "ค", "ง"][LETTERS.indexOf(o.id)] ?? o.id}
                          </option>
                        ))}
                    </select>
                  ) : (
                    <input
                      className="input mono"
                      style={{ maxWidth: 140 }}
                      placeholder="คำตอบผิด"
                      value={String(bug.answer)}
                      onChange={(e) => set("bugs", (draft.bugs ?? []).map((b, i) => (i === index ? { ...b, answer: e.target.value } : b)))}
                    />
                  )}
                  <select
                    className="select grow"
                    value={bug.tag}
                    onChange={(e) => set("bugs", (draft.bugs ?? []).map((b, i) => (i === index ? { ...b, tag: e.target.value } : b)))}
                  >
                    {tags.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.type === "slip" ? "Slip" : "Misconception"} · {t.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<Trash2 size={15} />}
                    aria-label="ลบคำตอบผิดนี้"
                    onClick={() => set("bugs", (draft.bugs ?? []).filter((_, i) => i !== index))}
                  />
                </div>
              ))}
              <Button
                size="sm"
                variant="soft"
                icon={<Plus size={15} />}
                disabled={!tags.length}
                onClick={() =>
                  set("bugs", [
                    ...(draft.bugs ?? []),
                    { answer: draft.format === "mcq" ? options.find((o) => o.id !== draft.answer.option)?.id ?? "a" : "", tag: tags[0]?.id ?? "" },
                  ])
                }
                style={{ alignSelf: "flex-start" }}
              >
                เพิ่มคำตอบผิด
              </Button>
              {!tags.length && <p className="xsmall faint">ยังไม่มีรายการใน Bug Library ของวิชานี้ เพิ่มได้ที่แท็บ Bug Library</p>}
            </div>
          </fieldset>
        )}

        <fieldset className="fieldset">
          <legend>บันไดคำใบ้ 3 ระดับ</legend>
          <p className="xsmall muted">
            AI จะปรับถ้อยคำจากคำใบ้เหล่านี้ ถ้า AI ใช้ไม่ได้หรือหลุดเฉลย ระบบจะแสดงคำใบ้ที่ครูเขียนแทน จึงห้ามมีคำตอบสุดท้ายอยู่ในคำใบ้
          </p>
          {(["1", "2", "3"] as const).map((level) => (
            <Field
              key={level}
              label={level === "1" ? "ระดับ 1 สะกิดความคิด" : level === "2" ? "ระดับ 2 อธิบายกฎ" : "ระดับ 3 ชี้นำขั้นแรก (ไม่ใช่เฉลย)"}
            >
              <textarea
                className="textarea"
                value={draft.hints?.[level] ?? ""}
                onChange={(e) => set("hints", { ...(draft.hints ?? {}), [level]: e.target.value })}
              />
            </Field>
          ))}
          <Field label="คำถามนำแบบ Socratic (บรรทัดละหนึ่งคำถาม)">
            <textarea className="textarea" value={(draft.socratic ?? []).join("\n")} onChange={(e) => set("socratic", e.target.value.split("\n"))} />
          </Field>
        </fieldset>

        <div className="grid grid-3">
          <Field label="ความยาก (0–1)" hint="Fuzzy ใช้เลือกข้อถัดไปให้อยู่ใน ZPD">
            <input
              className="input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={draft.difficulty ?? 0.5}
              onChange={(e) => set("difficulty", Number(e.target.value))}
            />
          </Field>
          <Field label="เวลาอ่านขั้นต่ำ (วินาที)" hint="ตอบผิดเร็วกว่านี้ถือเป็น Rapid Guess">
            <input className="input" type="number" min={1} value={draft.min_read_time ?? 3} onChange={(e) => set("min_read_time", Number(e.target.value))} />
          </Field>
          <Field label="เวลาที่คาด (วินาที)" hint="ใช้เทียบว่าคิดช้าหรือเร็ว">
            <input className="input" type="number" min={5} value={draft.expected_time ?? 45} onChange={(e) => set("expected_time", Number(e.target.value))} />
          </Field>
        </div>
      </div>
    </Modal>
  );
}
