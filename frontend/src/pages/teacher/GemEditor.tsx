import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  Check,
  CircleAlert,
  FileText,
  Flag,
  Info,
  LoaderCircle,
  Lock,
  PencilLine,
  Plus,
  Redo2,
  RefreshCw,
  Trash2,
  Undo2,
  WandSparkles,
  X,
} from "lucide-react";
import { api } from "../../lib/api";
import { useNow } from "../../lib/hooks";
import { mmss } from "../../lib/format";
import GemIcon, { GEM_COLORS, GEM_ICONS } from "../../components/GemIcon";
import { Badge, Button, Modal, Spinner, Tabs, useToast } from "../../components/ui";
import { PreviewTry, Versions } from "./GemPreview";
import { STATUS_TEXT, TOOL_LABELS, type BankItem, type GemDetail, type GemTools } from "./gemTypes";

// หน้าสร้างและแก้ Gem แบบ Gemini: ฟอร์มด้านซ้าย พรีวิวด้านขวา กดบันทึกแล้ว AI สร้างคลังโจทย์ให้

interface Form {
  name: string;
  description: string;
  instructions: string;
  icon: string;
  color: string;
  tools: GemTools;
  starter_prompts: string[];
}

const EMPTY: Form = {
  name: "",
  description: "",
  instructions: "",
  icon: "sparkles",
  color: "teal",
  tools: { chat: true, hints: true, isomorphic: true, walkthrough: true, remedial: true },
  starter_prompts: [],
};

const PLACEHOLDER =
  "ตัวอย่าง: คุณเป็นพี่ติวเตอร์ใจดีที่สอนนักเรียน ม.2 เรื่องการแก้สมการเชิงเส้นตัวแปรเดียว ชวนให้คิดทีละขั้นด้วยการเปรียบเทียบกับตาชั่ง " +
  "ใช้ตัวอย่างใกล้ตัว เช่น ค่าขนมหรือเกม ไม่ตัดสินเมื่อนักเรียนตอบผิด และให้กำลังใจเสมอ";

const ACCEPT = ".pdf,.txt,.md,.docx";

function toForm(gem: GemDetail): Form {
  return {
    name: gem.name,
    description: gem.description,
    instructions: gem.instructions,
    icon: gem.icon,
    color: gem.color,
    tools: gem.tools,
    starter_prompts: gem.starter_prompts,
  };
}

export default function GemEditor() {
  const { gemId } = useParams();
  const isNew = !gemId || gemId === "new";
  const navigate = useNavigate();
  const toast = useToast();
  const [gem, setGem] = useState<GemDetail | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [queued, setQueued] = useState<File[]>([]);
  const [knowledgeChanged, setKnowledgeChanged] = useState(false);
  const [saving, setSaving] = useState(false);
  const [askRebuild, setAskRebuild] = useState(false);
  const [loading, setLoading] = useState(!isNew);

  const load = async () => {
    if (isNew) return null;
    const detail = await api<GemDetail>("teacher", `/api/gems/${gemId}`);
    setGem(detail);
    return detail;
  };

  useEffect(() => {
    if (isNew) {
      setGem(null);
      setForm(EMPTY);
      return;
    }
    setLoading(true);
    load()
      .then((detail) => detail && setForm(toForm(detail)))
      .catch((err) => toast(err instanceof Error ? err.message : "โหลด Gem ไม่สำเร็จ", "warning"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gemId]);

  // ระหว่าง AI สร้างคลังโจทย์ ดึงสถานะทุก 2 วินาที
  const building = gem?.build.status === "building";
  useEffect(() => {
    if (!building) return;
    const id = setInterval(() => load().catch(() => {}), 2000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [building, gemId]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));

  const startBuild = async (id: string) => {
    try {
      setGem(await api<GemDetail>("teacher", `/api/gems/${id}/build`, { method: "POST" }));
      setKnowledgeChanged(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : "เริ่มสร้างคลังโจทย์ไม่สำเร็จ", "warning");
    }
  };

  const save = async () => {
    if (!form.name.trim()) return;
    setSaving(true);
    try {
      if (isNew) {
        const created = await api<GemDetail>("teacher", "/api/gems", { body: form });
        for (const file of queued) await uploadFile(created.id, file);
        setQueued([]);
        await startBuild(created.id);
        navigate(`/teacher/gems/${created.id}`, { replace: true });
        return;
      }
      const updated = await api<GemDetail>("teacher", `/api/gems/${gemId}`, { method: "PUT", body: form });
      setGem(updated);
      if (!updated.bank) {
        await startBuild(updated.id);
      } else if (form.instructions !== gem?.instructions || knowledgeChanged) {
        setAskRebuild(true);
      } else {
        toast("บันทึกแล้ว นักเรียนเห็นค่าใหม่ทันที", "success");
      }
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ", "warning");
    } finally {
      setSaving(false);
    }
  };

  const uploadFile = async (id: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const result = await api<{ warning: string | null }>("teacher", `/api/gems/${id}/files`, { form: formData });
    if (result.warning) toast(`${file.name}: ${result.warning}`, "warning");
  };

  const addFiles = async (files: FileList) => {
    const list = Array.from(files);
    if (isNew) {
      setQueued((q) => [...q, ...list]);
      return;
    }
    try {
      for (const file of list) await uploadFile(gemId!, file);
      setKnowledgeChanged(true);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "อัปโหลดไม่สำเร็จ", "warning");
    }
  };

  const removeFile = async (docId: number) => {
    await api("teacher", `/api/gems/${gemId}/files/${docId}`, { method: "DELETE" });
    setKnowledgeChanged(true);
    await load();
  };

  const resolveFlag = async (itemId: string, keep: boolean) => {
    setGem(await api<GemDetail>("teacher", `/api/gems/${gemId}/items/${itemId}/flag`, { body: { keep } }));
    toast(keep ? "ยืนยันเฉลยแล้ว นักเรียนจะได้ข้อนี้" : "ลบข้อนี้ออกจากคลังแล้ว", "success");
  };

  if (loading) return <Spinner />;

  return (
    <div className="gem-editor">
      <header className="gem-editor-head">
        <Button variant="ghost" size="sm" className="btn-icon" icon={<ArrowLeft size={18} />} onClick={() => navigate("/teacher/gems")} aria-label="กลับไปรายการ Gem" />
        <GemIcon icon={form.icon} color={form.color} size={36} />
        <span className="subtitle grow gem-editor-title">{isNew ? "Gem ใหม่" : form.name || "Gem"}</span>
        {gem && <Badge tone={STATUS_TEXT[gem.build.status].tone}>{STATUS_TEXT[gem.build.status].label}</Badge>}
        <Button variant="primary" loading={saving} disabled={!form.name.trim() || building} onClick={save}>
          บันทึก
        </Button>
      </header>

      <div className="gem-editor-body">
        <div className="gem-form stack stack-lg">
          <GemField label="ชื่อ">
            <input
              className="input input-lg"
              placeholder="ตั้งชื่อให้ Gem ของคุณ"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              aria-invalid={!form.name.trim()}
            />
            {!form.name.trim() && <span className="gem-hint-warn">Gem ต้องมีชื่อจึงจะเริ่มการทดสอบได้</span>}
          </GemField>

          <GemField label="คำอธิบาย">
            <textarea
              className="textarea"
              rows={2}
              placeholder="อธิบายลักษณะและสิ่งที่ Gem ของคุณทำได้"
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
            />
          </GemField>

          <Instructions value={form.instructions} onChange={(v) => set("instructions", v)} form={form} locked={gem?.locked_constraints} />

          <GemField label="ไอคอนและสี">
            <div className="gem-pickers">
              <div className="row row-sm" role="group" aria-label="ไอคอน">
                {Object.keys(GEM_ICONS).map((icon) => (
                  <button
                    key={icon}
                    type="button"
                    className={`gem-pick ${form.icon === icon ? "on" : ""}`}
                    onClick={() => set("icon", icon)}
                    aria-pressed={form.icon === icon}
                    aria-label={icon}
                  >
                    <GemIcon icon={icon} color={form.color} size={30} />
                  </button>
                ))}
              </div>
              <div className="row row-sm" role="group" aria-label="สี">
                {Object.entries(GEM_COLORS).map(([color, value]) => (
                  <button
                    key={color}
                    type="button"
                    className={`gem-swatch ${form.color === color ? "on" : ""}`}
                    style={{ background: value }}
                    onClick={() => set("color", color)}
                    aria-pressed={form.color === color}
                    aria-label={color}
                  />
                ))}
              </div>
            </div>
          </GemField>

          <StarterTools form={form} onTools={(tools) => set("tools", tools)} onPrompts={(p) => set("starter_prompts", p)} />

          <GemField label="ความรู้" info="ไฟล์ที่ AI ใช้สร้างโจทย์ และ RAG ใช้ค้นตอนสอน (PDF, DOCX, TXT, MD) AI อ้างอิงเฉพาะเนื้อหาในไฟล์และคำสั่ง">
            <Knowledge
              files={isNew ? queued.map((f, i) => ({ id: -i - 1, filename: f.name, chars: f.size, warning: null })) : (gem?.files ?? [])}
              onAdd={addFiles}
              onRemove={(id) => (isNew ? setQueued((q) => q.filter((_, i) => -i - 1 !== id)) : removeFile(id))}
            />
          </GemField>
        </div>

        <aside className="gem-preview">
          <span className="gem-preview-label">พรีวิว</span>
          <Preview form={form} gem={gem} onRetry={() => gem && startBuild(gem.id)} onFlag={resolveFlag} onChange={setGem} />
        </aside>
      </div>

      <Modal
        open={askRebuild}
        onClose={() => setAskRebuild(false)}
        title="สร้างคลังโจทย์ใหม่ไหม"
        footer={
          <>
            <Button
              onClick={() => {
                setAskRebuild(false);
                setKnowledgeChanged(false);
                toast("บันทึกแล้ว ใช้คลังโจทย์เดิม คำสั่งใหม่มีผลกับครูผู้ช่วยทันที", "success");
              }}
            >
              ใช้คลังเดิม
            </Button>
            <Button
              variant="primary"
              icon={<RefreshCw size={16} />}
              onClick={() => {
                setAskRebuild(false);
                if (gem) startBuild(gem.id);
              }}
            >
              สร้างใหม่
            </Button>
          </>
        }
      >
        <p className="small">
          คำสั่งหรือไฟล์ความรู้เปลี่ยนไป ถ้าสร้างใหม่ AI จะสร้างโจทย์ชุดใหม่ทั้งหมด นักเรียนที่กำลังเรียนอยู่ยังทำคลังเดิมต่อจนจบรอบ
        </p>
      </Modal>
    </div>
  );
}

function GemField({ label, info, children }: { label: string; info?: string; children: ReactNode }) {
  return (
    <section className="gem-field">
      <span className="gem-field-label">
        {label}
        {info && (
          <span className="gem-info" title={info} aria-label={info}>
            <Info size={15} />
          </span>
        )}
      </span>
      {children}
    </section>
  );
}

// ช่องคำสั่ง: ย้อนกลับและทำซ้ำได้หลังให้ AI ช่วยเขียน เหมือนปุ่มไม้กายสิทธิ์ของ Gemini
function Instructions({ value, onChange, form, locked }: { value: string; onChange: (v: string) => void; form: Form; locked?: string }) {
  const toast = useToast();
  const [past, setPast] = useState<string[]>([]);
  const [future, setFuture] = useState<string[]>([]);
  const [refining, setRefining] = useState(false);

  const refine = async () => {
    setRefining(true);
    try {
      const result = await api<{ instructions: string }>("teacher", "/api/gems/refine", {
        body: { name: form.name, description: form.description, instructions: value },
      });
      setPast((p) => [...p, value]);
      setFuture([]);
      onChange(result.instructions);
    } catch (err) {
      toast(err instanceof Error ? err.message : "AI ช่วยเขียนไม่สำเร็จ", "warning");
    } finally {
      setRefining(false);
    }
  };

  return (
    <GemField label="คำสั่ง" info="บอกว่า Gem เป็นใคร สอนใคร สอนเรื่องอะไร และพูดแบบไหน ระบบนำไปใช้เป็นกรอบ Role & Persona ของ prompt">
      <div className="gem-instructions">
        <textarea className="textarea" rows={10} placeholder={PLACEHOLDER} value={value} onChange={(e) => onChange(e.target.value)} />
        <div className="gem-instructions-tools">
          <span className="gem-tool-pair">
            <button
              type="button"
              disabled={!past.length}
              onClick={() => {
                setFuture((f) => [value, ...f]);
                onChange(past[past.length - 1]);
                setPast((p) => p.slice(0, -1));
              }}
              aria-label="ย้อนกลับ"
              title="ย้อนกลับ"
            >
              <Undo2 size={17} />
            </button>
            <button
              type="button"
              disabled={!future.length}
              onClick={() => {
                setPast((p) => [...p, value]);
                onChange(future[0]);
                setFuture((f) => f.slice(1));
              }}
              aria-label="ทำซ้ำ"
              title="ทำซ้ำ"
            >
              <Redo2 size={17} />
            </button>
          </span>
          <button type="button" className="gem-wand" onClick={refine} disabled={refining || !form.name.trim()} title="ให้ AI ช่วยเขียนคำสั่งให้ชัดขึ้น">
            {refining ? <LoaderCircle size={17} className="spin" /> : <WandSparkles size={17} />}
          </button>
        </div>
      </div>
      {locked && (
        <details className="gem-locked">
          <summary>
            <Lock size={14} />
            ข้อห้ามที่ระบบล็อกไว้ แก้ไม่ได้
          </summary>
          <pre className="code-block">{locked}</pre>
        </details>
      )}
    </GemField>
  );
}

function StarterTools({ form, onTools, onPrompts }: { form: Form; onTools: (t: GemTools) => void; onPrompts: (p: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    if (!draft.trim() || form.starter_prompts.length >= 4) return;
    onPrompts([...form.starter_prompts, draft.trim()]);
    setDraft("");
  };
  return (
    <GemField label="เครื่องมือเริ่มต้น" info="เปิดหรือปิดเครื่องมือการสอนของ Gem นี้ และเตรียมคำถามเริ่มต้นให้นักเรียนกดถามได้ทันที">
      <div className="gem-tools">
        {(Object.keys(TOOL_LABELS) as (keyof GemTools)[]).map((key) => (
          <label key={key} className="gem-tool">
            <input type="checkbox" checked={form.tools[key]} onChange={(e) => onTools({ ...form.tools, [key]: e.target.checked })} />
            <span className="stack" style={{ gap: 1 }}>
              <span className="small strong">{TOOL_LABELS[key].label}</span>
              <span className="xsmall muted">{TOOL_LABELS[key].text}</span>
            </span>
          </label>
        ))}
      </div>
      <div className="stack stack-sm">
        <span className="small muted">คำถามเริ่มต้น (ไม่เกิน 4)</span>
        <div className="pill-list">
          {form.starter_prompts.map((p, i) => (
            <span key={i} className="gem-starter">
              {p}
              <button type="button" onClick={() => onPrompts(form.starter_prompts.filter((_, j) => j !== i))} aria-label={`ลบ ${p}`}>
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        {form.starter_prompts.length < 4 && (
          <div className="row row-sm row-nowrap">
            <input
              className="input"
              placeholder="เช่น ช่วยอธิบายการย้ายข้างหน่อย"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  add();
                }
              }}
            />
            <Button icon={<Plus size={16} />} onClick={add} disabled={!draft.trim()}>
              เพิ่ม
            </Button>
          </div>
        )}
      </div>
    </GemField>
  );
}

function Knowledge({
  files,
  onAdd,
  onRemove,
}: {
  files: { id: number; filename: string; chars: number; warning: string | null }[];
  onAdd: (files: FileList) => void;
  onRemove: (id: number) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="stack stack-sm">
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files?.length) onAdd(e.target.files);
          e.target.value = "";
        }}
      />
      <button type="button" className="gem-add-file" onClick={() => input.current?.click()}>
        <span>เพิ่มไฟล์ให้ Gem ใช้อ้างอิง</span>
        <Plus size={20} />
      </button>
      {files.map((f) => (
        <div key={f.id} className="gem-file">
          <FileText size={16} />
          <span className="stack grow" style={{ gap: 0, minWidth: 0 }}>
            <span className="small strong gem-file-name">{f.filename}</span>
            {f.warning && <span className="xsmall" style={{ color: "var(--warning)" }}>{f.warning}</span>}
          </span>
          <Button variant="ghost" size="sm" className="btn-icon" icon={<Trash2 size={15} />} onClick={() => onRemove(f.id)} aria-label={`ลบ ${f.filename}`} />
        </div>
      ))}
    </div>
  );
}

// พรีวิวด้านขวา: ตามสถานะของ Gem ตั้งแต่ยังไม่ตั้งชื่อ กำลังสร้าง จนคลังโจทย์พร้อม
function Preview({
  form,
  gem,
  onRetry,
  onFlag,
  onChange,
}: {
  form: Form;
  gem: GemDetail | null;
  onRetry: () => void;
  onFlag: (itemId: string, keep: boolean) => void;
  onChange: (gem: GemDetail) => void;
}) {
  const now = useNow(1000);
  const [tab, setTab] = useState<"bank" | "try" | "versions">("bank");
  if (!form.name.trim()) {
    return (
      <div className="gem-preview-empty">
        <GemIcon icon={form.icon} color={form.color} size={64} />
        <span>หากจะดูตัวอย่าง Gem ให้ตั้งชื่อก่อน</span>
      </div>
    );
  }
  const build = gem?.build;
  return (
    <div className="stack stack-lg">
      <div className="gem-student-card">
        <span className="xsmall faint">นักเรียนจะเห็น</span>
        <div className="row" style={{ alignItems: "flex-start" }}>
          <GemIcon icon={form.icon} color={form.color} size={44} />
          <span className="stack" style={{ gap: 4, minWidth: 0 }}>
            <span className="subtitle">{form.name}</span>
            <span className="small muted">{form.description || "ยังไม่มีคำอธิบาย"}</span>
          </span>
        </div>
        {form.starter_prompts.length > 0 && (
          <div className="pill-list">
            {form.starter_prompts.map((p) => (
              <span key={p} className="gem-starter gem-starter-view">
                {p}
              </span>
            ))}
          </div>
        )}
      </div>

      {(!build || build.status === "idle") && (
        <p className="small muted">กดบันทึก แล้ว AI จะสร้างแผนผังความรู้ โจทย์ คำใบ้ 3 ระดับ และคลังข้อผิดพลาดจากคำสั่งและไฟล์ความรู้ ใช้เวลาประมาณ 1 นาที</p>
      )}

      {build && build.status === "building" && (
        <div className="stack stack-sm">
          <span className="small strong">
            AI กำลังสร้างคลังโจทย์ · {elapsed(now - (build.started_at ?? now))}
          </span>
          <BuildSteps steps={build.steps ?? []} />
        </div>
      )}

      {build && build.status === "error" && (
        <div className="stack stack-sm">
          <BuildSteps steps={build.steps ?? []} />
          <div className="callout callout-warning">
            <CircleAlert size={16} />
            <span className="small">{build.error}</span>
          </div>
          <Button variant="primary" icon={<RefreshCw size={16} />} onClick={onRetry} style={{ alignSelf: "flex-start" }}>
            ลองอีกครั้ง (ทำต่อจากขั้นที่ค้าง)
          </Button>
        </div>
      )}

      {gem?.bank && build?.status !== "building" && (
        <>
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { id: "bank", label: "คลังโจทย์" },
              { id: "try", label: "ลองเรียน" },
              { id: "versions", label: `เวอร์ชัน (${gem.versions.length})` },
            ]}
          />
          {tab === "bank" && <Bank gem={gem} onFlag={onFlag} onRebuild={onRetry} />}
          {tab === "try" && <PreviewTry gem={gem} />}
          {tab === "versions" && <Versions gem={gem} onRestored={onChange} />}
        </>
      )}
    </div>
  );
}

function elapsed(seconds: number) {
  return seconds < 60 ? `${Math.max(0, Math.round(seconds))} วินาที` : `${mmss(seconds)} นาที`;
}

function BuildSteps({ steps }: { steps: { id: string; label: string; status: string }[] }) {
  return (
    <ol className="gem-steps">
      {steps.map((s) => (
        <li key={s.id} className={`gem-step is-${s.status}`}>
          <span className="gem-step-mark">
            {s.status === "done" ? (
              <Check size={14} />
            ) : s.status === "running" ? (
              <LoaderCircle size={14} className="spin" />
            ) : s.status === "error" ? (
              <X size={14} />
            ) : null}
          </span>
          <span className="small">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

function Bank({ gem, onFlag, onRebuild }: { gem: GemDetail; onFlag: (id: string, keep: boolean) => void; onRebuild: () => void }) {
  const navigate = useNavigate();
  const bank = gem.bank!;
  const target = bank.concepts.find((c) => c.name === bank.target);
  // พื้นฐานที่ต้องรู้ก่อนเป้าหมาย (ไล่ย้อนตามเส้น Prerequisite) อยู่หน้าเป้าหมาย เรื่องที่ต่อยอดอยู่หลัง
  const byId = new Map(bank.concepts.map((c) => [c.id, c]));
  const before = new Set<string>();
  const walk = (id: string) =>
    byId.get(id)?.prerequisites.forEach((p) => {
      if (!before.has(p)) {
        before.add(p);
        walk(p);
      }
    });
  if (target) walk(target.id);
  const prereqs = bank.concepts.filter((c) => before.has(c.id));
  const beyond = bank.concepts.filter((c) => c.id !== target?.id && !before.has(c.id));
  const notes = [...(gem.build.errors ?? []), ...(gem.build.warnings ?? []).filter((w) => !w.startsWith("ติดธง"))];
  return (
    <div className="stack stack-lg">
      <div className="stack stack-sm">
        <span className="spread">
          <span className="small strong">คลังโจทย์รุ่นที่ {gem.bank_version}</span>
          <span className="row row-sm">
            {/* หน้าแก้เนื้อหาแบบเดิม ใช้ตรวจและแก้สิ่งที่ AI สร้าง (Q17) */}
            <Button variant="ghost" size="sm" icon={<PencilLine size={14} />} onClick={() => navigate(`/teacher/content/${bank.subject_id}?gem=${gem.id}`)}>
              แก้คลังโจทย์
            </Button>
            <Button variant="ghost" size="sm" icon={<RefreshCw size={14} />} onClick={onRebuild}>
              สร้างใหม่
            </Button>
          </span>
        </span>
        <div className="gem-stats">
          <Stat value={bank.stats.main} label="โจทย์หลัก" />
          <Stat value={bank.stats.isomorphic} label="ข้อคู่ขนาน" />
          <Stat value={bank.stats.remedial} label="ทบทวนพื้นฐาน" />
          <Stat value={bank.stats.challenge} label="โจทย์ท้าทาย" />
          <Stat value={bank.bugs.filter((b) => !GENERIC_SLIPS.has(b.id)).length} label="ข้อผิดพลาดที่รู้จัก" />
        </div>
      </div>

      <div className="stack stack-sm">
        <span className="small strong">แผนผังความรู้</span>
        <ol className="gem-map">
          {prereqs.map((c) => (
            <li key={c.id}>{c.name}</li>
          ))}
          <li className="is-target">{bank.target}</li>
          {beyond.map((c) => (
            <li key={c.id} className="is-beyond">
              {c.name}
            </li>
          ))}
        </ol>
      </div>

      {bank.flagged.length > 0 && (
        <div className="stack stack-sm">
          <span className="small strong row row-sm" style={{ color: "var(--warning)" }}>
            <Flag size={15} />
            เฉลยติดธง {bank.flagged.length} ข้อ ซ่อนจากนักเรียนจนกว่าครูตรวจ
          </span>
          {bank.flagged.map((item) => (
            <ItemCard key={item.id} item={item}>
              <ul className="gem-flag-reasons">
                {item.flag?.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <div className="row row-sm" style={{ justifyContent: "flex-end" }}>
                <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={() => onFlag(item.id, false)}>
                  ลบข้อนี้
                </Button>
                <Button size="sm" variant="soft" icon={<Check size={14} />} onClick={() => onFlag(item.id, true)}>
                  เฉลยถูกแล้ว
                </Button>
              </div>
            </ItemCard>
          ))}
        </div>
      )}

      {bank.samples.length > 0 && (
        <div className="stack stack-sm">
          <span className="small strong">ตัวอย่างโจทย์</span>
          {bank.samples.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {notes.length > 0 && (
        <details className="gem-notes">
          <summary className="small">ข้อสังเกตจากการตรวจความพร้อม ({notes.length})</summary>
          <ul className="small muted">
            {notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="gem-stat">
      <span className="gem-stat-value num">{value}</span>
      <span className="xsmall muted">{label}</span>
    </div>
  );
}

// Slip ทั่วไปที่ทุก Gem มีเหมือนกัน (backend/app/gems/builder.py GENERIC_SLIPS) ไม่นับเป็นข้อผิดพลาดที่ AI หาเจอ
const GENERIC_SLIPS = new Set(["S-ARITH", "S-SIGNFLIP"]);

const FORMAT_LABEL: Record<string, string> = { numeric: "ตัวเลข", mcq: "ปรนัย", short: "คำตอบสั้น" };

function ItemCard({ item, children }: { item: BankItem; children?: ReactNode }) {
  return (
    <div className="gem-item">
      <span className="row row-sm xsmall faint">
        <span className="mono">{item.id}</span>· {FORMAT_LABEL[item.format] ?? item.format}
        {item.concept && <>· {item.concept}</>}
      </span>
      <span className="small">{item.prompt}</span>
      {item.math && <span className="gem-item-math">{item.math}</span>}
      {item.options && (
        <span className="xsmall muted">{item.options.map((o) => `(${o.id}) ${o.text}`).join("  ")}</span>
      )}
      <span className="xsmall">
        เฉลย: <span className="strong">{item.answer}</span>
      </span>
      {children}
    </div>
  );
}
