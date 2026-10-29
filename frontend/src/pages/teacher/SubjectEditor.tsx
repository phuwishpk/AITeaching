import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ArrowLeft, CircleAlert, CircleCheck, Download, FileText, Plus, Save, Trash2, TriangleAlert, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { useContentScope } from "./contentScope";
import { useLoad } from "../../lib/hooks";
import { ago, num } from "../../lib/format";
import type { BugTag, Concept, Item, QuestionSet, Readiness, Subject, SubjectSummary, Walkthrough } from "../../lib/types";
import KnowledgeMap from "../../components/KnowledgeMap";
import { Badge, Button, Card, CardHead, Empty, Field, Modal, Segmented, Spinner, Tabs, useToast } from "../../components/ui";
import ItemEditor, { blankItem, FORMAT_LABEL, KIND_LABEL } from "./ItemEditor";
import { downloadJson } from "./ContentStudio";

type Tab = "concepts" | "items" | "bugs" | "walk" | "sets" | "docs";

// ข้อคู่ขนานผูกกับโจทย์หลักด้วย iso_of รายการ isomorphs ของโจทย์หลักคำนวณจากตรงนั้นเสมอ
function syncIsomorphs(items: Item[]): Item[] {
  return items.map((it) => (it.kind === "main" ? { ...it, isomorphs: items.filter((x) => x.iso_of === it.id).map((x) => x.id) } : it));
}

export default function SubjectEditor() {
  const { role, base } = useContentScope();
  const [gemParam] = useSearchParams();
  const { subjectId = "" } = useParams();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("concepts");
  const [draft, setDraft] = useState<Subject | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [readiness, setReadiness] = useState<Record<string, Readiness>>({});
  const loaded = useLoad(() => api<Subject>(role, `/api/teacher/subjects/${subjectId}`), [subjectId]);

  useEffect(() => {
    if (loaded.data) {
      setDraft(structuredClone(loaded.data));
      setDirty(false);
    }
  }, [loaded.data]);

  useEffect(() => {
    api<SubjectSummary[]>(role, "/api/teacher/subjects")
      .then((list) => {
        const mine = list.find((s) => s.id === subjectId);
        if (mine) setReadiness(Object.fromEntries(mine.sets.map((qs) => [qs.id, qs.readiness])));
      })
      .catch(() => {});
  }, [subjectId]);

  // เตือนก่อนปิดหน้าถ้ายังไม่ได้บันทึก
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const update = (patch: Partial<Subject>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setDirty(true);
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      const body = { ...draft, items: syncIsomorphs(draft.items) };
      const summary = await api<SubjectSummary>(role, `/api/teacher/subjects/${subjectId}`, { method: "PUT", body });
      setReadiness(Object.fromEntries(summary.sets.map((qs) => [qs.id, qs.readiness])));
      setDraft(body);
      setDirty(false);
      const broken = summary.sets.filter((qs) => !qs.readiness.ok).length;
      toast(broken ? `บันทึกแล้ว มี ${broken} ชุดคำถามที่ยังไม่พร้อม ดูได้ที่แท็บชุดคำถาม` : "บันทึกแล้ว", broken ? "warning" : "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ", "warning");
    } finally {
      setSaving(false);
    }
  };

  if (loaded.error) return <Empty>{loaded.error}</Empty>;
  if (!draft) return <Spinner />;
  const gemId = gemParam.get("gem");

  return (
    <div className="page stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          {/* เปิดมาจากแท็บคลังโจทย์ของ Gem: กลับไปที่ Gem นั้น */}
          <Link to={gemId ? `/teacher/gems/${gemId}` : base} className="row row-sm small muted">
            <ArrowLeft size={14} /> {gemId ? "กลับไปที่ติวเตอร์" : "วิชาทั้งหมด"}
          </Link>
          <h1 className="title-xl">{draft.name}</h1>
          <p className="small muted">
            <span className="mono">{draft.id}</span> · {draft.concepts.length} มโนทัศน์ · {draft.items.length} โจทย์ · {draft.bug_tags.length} รายการใน Bug Library
          </p>
        </div>
        <div className="row">
          <Button icon={<Download size={16} />} onClick={() => downloadJson(`${draft.id}.json`, draft)}>
            ส่งออก JSON
          </Button>
          <Button variant="primary" icon={<Save size={16} />} loading={saving} disabled={!dirty} onClick={save}>
            {dirty ? "บันทึกการแก้ไข" : "บันทึกแล้ว"}
          </Button>
        </div>
      </header>

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { id: "concepts", label: "ข้อมูลวิชาและแผนผังความรู้" },
          { id: "items", label: `โจทย์ (${draft.items.length})` },
          { id: "bugs", label: `Bug Library (${draft.bug_tags.length})` },
          { id: "walk", label: "ตัวอย่างทีละขั้น" },
          { id: "sets", label: `ชุดคำถาม (${draft.question_sets.length})` },
          { id: "docs", label: "เอกสารสำหรับ RAG" },
        ]}
      />

      {tab === "concepts" && <ConceptsTab draft={draft} update={update} />}
      {tab === "items" && <ItemsTab draft={draft} update={update} />}
      {tab === "bugs" && <BugsTab draft={draft} update={update} />}
      {tab === "walk" && <WalkTab draft={draft} update={update} />}
      {tab === "sets" && <SetsTab draft={draft} update={update} readiness={readiness} dirty={dirty} />}
      {tab === "docs" && <DocsTab subjectId={draft.id} />}
    </div>
  );
}

interface TabProps {
  draft: Subject;
  update: (patch: Partial<Subject>) => void;
}

// ---------------------------------------------------------------- มโนทัศน์
function ConceptsTab({ draft, update }: TabProps) {
  const counts = useMemo(
    () => Object.fromEntries(draft.concepts.map((c) => [c.id, draft.items.filter((it) => it.concept === c.id).length])),
    [draft],
  );
  const target = draft.question_sets[0]?.target_concept;

  const setConcept = (index: number, patch: Partial<Concept>) =>
    update({ concepts: draft.concepts.map((c, i) => (i === index ? { ...c, ...patch } : c)) });

  const addConcept = () => {
    let n = draft.concepts.length + 1;
    while (draft.concepts.some((c) => c.id === `C-${n}`)) n++;
    update({ concepts: [...draft.concepts, { id: `C-${n}`, name: "มโนทัศน์ใหม่", grade: draft.grade ?? "", description: "", prerequisites: [] }] });
  };

  const removeConcept = (id: string) => {
    if (counts[id]) return;
    update({
      concepts: draft.concepts.filter((c) => c.id !== id).map((c) => ({ ...c, prerequisites: (c.prerequisites ?? []).filter((p) => p !== id) })),
    });
  };

  return (
    <div className="stack stack-lg">
      <Card>
        <CardHead title="ข้อมูลวิชา" />
        <div className="card-body grid grid-3" style={{ paddingTop: 0 }}>
          <Field label="ชื่อวิชา">
            <input className="input" value={draft.name} onChange={(e) => update({ name: e.target.value })} />
          </Field>
          <Field label="ระดับชั้น">
            <input className="input" value={draft.grade ?? ""} onChange={(e) => update({ grade: e.target.value })} />
          </Field>
          <Field label="คำอธิบาย">
            <input className="input" value={draft.description ?? ""} onChange={(e) => update({ description: e.target.value })} />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHead
          title="แผนผังความรู้ (Knowledge Map)"
          sub="ลูกศรชี้จากความรู้พื้นฐานที่ต้องรู้ก่อน (Prerequisite) ไปยังมโนทัศน์ที่ต้องใช้ ระบบใช้เส้นทางนี้เลือกเรื่องที่จะพาไปทบทวน"
        />
        <div className="card-body" style={{ paddingTop: 0 }}>
          {draft.concepts.length ? <KnowledgeMap concepts={draft.concepts} target={target} counts={counts} /> : <Empty>ยังไม่มีมโนทัศน์</Empty>}
        </div>
      </Card>

      <Card>
        <CardHead
          title="มโนทัศน์"
          actions={
            <Button size="sm" variant="soft" icon={<Plus size={15} />} onClick={addConcept}>
              เพิ่มมโนทัศน์
            </Button>
          }
        />
        <div className="stack" style={{ padding: "0 22px 22px" }}>
          {draft.concepts.map((concept, index) => (
            <div key={index} className="concept-row">
              <div className="grid grid-3">
                <Field label="รหัส">
                  <input className="input mono" value={concept.id} readOnly={!!counts[concept.id]} onChange={(e) => setConcept(index, { id: e.target.value.toUpperCase() })} />
                </Field>
                <Field label="ชื่อ">
                  <input className="input" value={concept.name} onChange={(e) => setConcept(index, { name: e.target.value })} />
                </Field>
                <Field label="ระดับชั้น">
                  <input className="input" value={concept.grade ?? ""} onChange={(e) => setConcept(index, { grade: e.target.value })} />
                </Field>
              </div>
              <Field label="คำอธิบาย (ใช้ในหน้าทบทวนเนื้อหาของนักเรียน)">
                <textarea className="textarea" value={concept.description ?? ""} onChange={(e) => setConcept(index, { description: e.target.value })} />
              </Field>
              <div className="spread">
                <div className="stack stack-sm">
                  <span className="field-label">ต้องรู้ก่อน</span>
                  <div className="pill-list">
                    {draft.concepts
                      .filter((c) => c.id !== concept.id)
                      .map((c) => {
                        const on = (concept.prerequisites ?? []).includes(c.id);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            className={`chip-toggle ${on ? "on" : ""}`}
                            aria-pressed={on}
                            onClick={() =>
                              setConcept(index, {
                                prerequisites: on ? (concept.prerequisites ?? []).filter((p) => p !== c.id) : [...(concept.prerequisites ?? []), c.id],
                              })
                            }
                          >
                            {c.name}
                          </button>
                        );
                      })}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Trash2 size={15} />}
                  disabled={!!counts[concept.id]}
                  title={counts[concept.id] ? "ยังมีโจทย์ใช้มโนทัศน์นี้อยู่" : undefined}
                  onClick={() => removeConcept(concept.id)}
                >
                  ลบ
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- โจทย์
function ItemsTab({ draft, update }: TabProps) {
  const [concept, setConcept] = useState("all");
  const [kind, setKind] = useState<"all" | Item["kind"]>("all");
  const [editing, setEditing] = useState<{ item: Item; isNew: boolean } | null>(null);
  const names = Object.fromEntries(draft.concepts.map((c) => [c.id, c.name]));
  const rows = draft.items.filter((it) => (concept === "all" || it.concept === concept) && (kind === "all" || it.kind === kind));

  const newItem = () => {
    const base = concept !== "all" ? concept : draft.concepts[0]?.id ?? "";
    let n = draft.items.length + 1;
    while (draft.items.some((it) => it.id === `Q-${String(n).padStart(2, "0")}`)) n++;
    setEditing({ item: blankItem(base, `Q-${String(n).padStart(2, "0")}`), isNew: true });
  };

  const saveItem = (item: Item, previousId: string) => {
    const exists = draft.items.some((it) => it.id === previousId);
    let items = exists ? draft.items.map((it) => (it.id === previousId ? item : it)) : [...draft.items, item];
    if (previousId !== item.id) {
      // เปลี่ยนรหัส: ตามไปแก้ที่อ้างถึงทั้งหมด
      items = items.map((it) => (it.iso_of === previousId ? { ...it, iso_of: item.id } : it));
      update({
        items,
        question_sets: draft.question_sets.map((qs) => ({
          ...qs,
          main_items: qs.main_items.map((id) => (id === previousId ? item.id : id)),
          challenge_items: qs.challenge_items.map((id) => (id === previousId ? item.id : id)),
        })),
      });
    } else {
      update({ items });
    }
    setEditing(null);
  };

  const deleteItem = (id: string) => {
    update({
      items: draft.items.filter((it) => it.id !== id).map((it) => (it.iso_of === id ? { ...it, iso_of: null } : it)),
      question_sets: draft.question_sets.map((qs) => ({
        ...qs,
        main_items: qs.main_items.filter((x) => x !== id),
        challenge_items: qs.challenge_items.filter((x) => x !== id),
      })),
    });
    setEditing(null);
  };

  return (
    <Card>
      <div className="card-head">
        <div className="row">
          <select className="select" value={concept} onChange={(e) => setConcept(e.target.value)} style={{ width: "auto" }} aria-label="กรองตามมโนทัศน์">
            <option value="all">ทุกมโนทัศน์</option>
            {draft.concepts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <Segmented
            label="ประเภทโจทย์"
            value={kind}
            onChange={setKind}
            options={[{ id: "all" as const, label: "ทั้งหมด" }, ...Object.entries(KIND_LABEL).map(([id, label]) => ({ id: id as Item["kind"], label }))]}
          />
        </div>
        <Button variant="primary" size="sm" icon={<Plus size={15} />} onClick={newItem} disabled={!draft.concepts.length}>
          เพิ่มโจทย์
        </Button>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>รหัส</th>
              <th>โจทย์</th>
              <th>มโนทัศน์</th>
              <th>ประเภท</th>
              <th>Format</th>
              <th className="num">คำใบ้</th>
              <th className="num">คำตอบผิดที่รู้จัก</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((it) => (
              <tr key={it.id} className="clickable" onClick={() => setEditing({ item: it, isNew: false })}>
                <td className="mono small">
                  {it.id}
                  {it.iso_of && <div className="xsmall faint">คู่ขนานของ {it.iso_of}</div>}
                </td>
                <td>
                  <div className="stack" style={{ gap: 0 }}>
                    {it.math && <span className="mono">{it.math}</span>}
                    <span className="xsmall muted">{it.prompt}</span>
                  </div>
                </td>
                <td className="small">{names[it.concept] ?? it.concept}</td>
                <td className="small">{KIND_LABEL[it.kind]}</td>
                <td className="small">{FORMAT_LABEL[it.format]}</td>
                <td className="num small">{Object.values(it.hints ?? {}).filter((h) => h?.trim()).length}/3</td>
                <td className="num small">{it.bugs?.length ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <Empty>ไม่มีโจทย์ในตัวกรองนี้</Empty>}
      </div>
      <ItemEditor
        item={editing?.item ?? null}
        isNew={!!editing?.isNew}
        concepts={draft.concepts}
        tags={draft.bug_tags}
        mains={draft.items.filter((it) => it.kind === "main")}
        takenIds={draft.items.map((it) => it.id)}
        onSave={saveItem}
        onDelete={deleteItem}
        onClose={() => setEditing(null)}
      />
    </Card>
  );
}

// ---------------------------------------------------------------- Bug Library
function BugsTab({ draft, update }: TabProps) {
  const [editing, setEditing] = useState<{ tag: BugTag; index: number } | null>(null);
  const names = Object.fromEntries(draft.concepts.map((c) => [c.id, c.name]));

  const save = () => {
    if (!editing) return;
    const tags = [...draft.bug_tags];
    if (editing.index < 0) tags.push(editing.tag);
    else tags[editing.index] = editing.tag;
    update({ bug_tags: tags });
    setEditing(null);
  };

  const remove = (index: number) => {
    const id = draft.bug_tags[index].id;
    update({
      bug_tags: draft.bug_tags.filter((_, i) => i !== index),
      items: draft.items.map((it) => ({ ...it, bugs: (it.bugs ?? []).filter((b) => b.tag !== id) })),
    });
    setEditing(null);
  };

  const tag = editing?.tag;
  const setTag = (patch: Partial<BugTag>) => editing && setEditing({ ...editing, tag: { ...editing.tag, ...patch } });

  return (
    <Card>
      <CardHead
        title="คลังข้อผิดพลาด (Bug Library)"
        sub="Misconception เริ่มคำใบ้ที่ระดับ 2 และส่งไปทบทวน Prerequisite ที่ผูกไว้ ส่วน Slip ให้คำใบ้ระดับ 1 สะกิดให้ตรวจทาน"
        actions={
          <Button
            size="sm"
            variant="primary"
            icon={<Plus size={15} />}
            onClick={() => setEditing({ index: -1, tag: { id: `M-${draft.bug_tags.length + 1}`, type: "misconception", name: "", prerequisite: null, description: "", response: "", socratic: "" } })}
          >
            เพิ่มรายการ
          </Button>
        }
      />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>รหัส</th>
              <th>ประเภท</th>
              <th>ชื่อ</th>
              <th>ทบทวนเรื่อง</th>
              <th>การตอบสนองของระบบ</th>
            </tr>
          </thead>
          <tbody>
            {draft.bug_tags.map((t, index) => (
              <tr key={t.id} className="clickable" onClick={() => setEditing({ tag: { ...t }, index })}>
                <td className="mono small">{t.id}</td>
                <td>
                  <Badge tone={t.type === "slip" ? "calm" : "info"}>{t.type === "slip" ? "Slip" : "Misconception"}</Badge>
                </td>
                <td className="small strong">{t.name}</td>
                <td className="small">{t.prerequisite ? names[t.prerequisite] ?? t.prerequisite : <span className="faint">–</span>}</td>
                <td className="small muted">{t.response}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!draft.bug_tags.length && <Empty>ยังไม่มีรายการ</Empty>}
      </div>
      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        wide
        title={editing && editing.index >= 0 ? `แก้ไข ${editing.tag.id}` : "เพิ่มรายการใน Bug Library"}
        footer={
          <>
            {editing && editing.index >= 0 && (
              <Button variant="ghost" icon={<Trash2 size={16} />} onClick={() => remove(editing.index)} style={{ marginRight: "auto" }}>
                ลบรายการ
              </Button>
            )}
            <Button onClick={() => setEditing(null)}>ยกเลิก</Button>
            <Button variant="primary" onClick={save} disabled={!tag?.id.trim() || !tag?.name.trim()}>
              เก็บการแก้ไข
            </Button>
          </>
        }
      >
        {tag && (
          <div className="stack">
            <div className="grid grid-3">
              <Field label="รหัส">
                <input className="input mono" value={tag.id} onChange={(e) => setTag({ id: e.target.value.toUpperCase() })} />
              </Field>
              <Field label="ประเภท">
                <select className="select" value={tag.type} onChange={(e) => setTag({ type: e.target.value as BugTag["type"] })}>
                  <option value="misconception">Misconception (เข้าใจผิดเชิงมโนทัศน์)</option>
                  <option value="slip">Slip (สะเพร่า)</option>
                </select>
              </Field>
              <Field label="พาไปทบทวน">
                <select className="select" value={tag.prerequisite ?? ""} onChange={(e) => setTag({ prerequisite: e.target.value || null })}>
                  <option value="">ไม่ระบุ (ใช้เรื่องที่ Mastery ต่ำสุด)</option>
                  {draft.concepts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="ชื่อ">
              <input className="input" value={tag.name} onChange={(e) => setTag({ name: e.target.value })} />
            </Field>
            <Field label="ลักษณะความผิดพลาด">
              <textarea className="textarea" value={tag.description ?? ""} onChange={(e) => setTag({ description: e.target.value })} />
            </Field>
            <Field label="การตอบสนองของระบบ" hint="ส่งให้ AI Tutor เป็นบริบท (Context Framing ข้อ 2)">
              <textarea className="textarea" value={tag.response ?? ""} onChange={(e) => setTag({ response: e.target.value })} />
            </Field>
            <Field label="คำถามนำแบบ Socratic">
              <input className="input" value={tag.socratic ?? ""} onChange={(e) => setTag({ socratic: e.target.value })} />
            </Field>
          </div>
        )}
      </Modal>
    </Card>
  );
}

// ---------------------------------------------------------------- ตัวอย่างทีละขั้น
function WalkTab({ draft, update }: TabProps) {
  const byConcept = new Map(draft.walkthroughs.map((w) => [w.concept, w]));

  const setWalk = (concept: string, patch: Partial<Walkthrough>) => {
    const current = byConcept.get(concept) ?? { concept, title: "", problem: "", steps: [] };
    const next = { ...current, ...patch };
    const others = draft.walkthroughs.filter((w) => w.concept !== concept);
    update({ walkthroughs: [...others, next] });
  };

  return (
    <div className="stack">
      <p className="small muted prose">
        ตัวอย่างทีละขั้น (Walkthrough Example) ใช้หลัง Circuit Breaker และในหน้าทบทวนเนื้อหา ต้องเป็นโจทย์อื่นที่โครงสร้างเดียวกัน ไม่ใช่เฉลยของข้อที่นักเรียนกำลังทำ
      </p>
      <div className="grid grid-2">
        {draft.concepts.map((concept) => {
          const walk = byConcept.get(concept.id);
          return (
            <Card key={concept.id} className="card-pad stack stack-sm">
              <div className="spread">
                <span className="strong">{concept.name}</span>
                {walk?.steps.length ? <Badge tone="success">มีตัวอย่าง</Badge> : <Badge tone="warning">ยังไม่มี</Badge>}
              </div>
              <div className="grid grid-2">
                <Field label="ชื่อตัวอย่าง">
                  <input className="input" value={walk?.title ?? ""} onChange={(e) => setWalk(concept.id, { title: e.target.value })} />
                </Field>
                <Field label="โจทย์ตัวอย่าง">
                  <input className="input mono" value={walk?.problem ?? ""} onChange={(e) => setWalk(concept.id, { problem: e.target.value })} />
                </Field>
              </div>
              <Field label="ขั้นตอน (บรรทัดละหนึ่งขั้น)">
                <textarea
                  className="textarea"
                  rows={4}
                  value={(walk?.steps ?? []).join("\n")}
                  onChange={(e) => setWalk(concept.id, { steps: e.target.value.split("\n") })}
                  onBlur={(e) => setWalk(concept.id, { steps: e.target.value.split("\n").map((s) => s.trim()).filter(Boolean) })}
                />
              </Field>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- ชุดคำถาม
function SetsTab({ draft, update, readiness, dirty }: TabProps & { readiness: Record<string, Readiness>; dirty: boolean }) {
  const setQs = (index: number, patch: Partial<QuestionSet>) =>
    update({ question_sets: draft.question_sets.map((qs, i) => (i === index ? { ...qs, ...patch } : qs)) });
  const mains = draft.items.filter((it) => it.kind === "main");
  const challenges = draft.items.filter((it) => it.kind === "challenge");

  const addSet = () => {
    let n = draft.question_sets.length + 1;
    const prefix = draft.id.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6) || "QS";
    while (draft.question_sets.some((qs) => qs.id === `${prefix}-${n}`)) n++;
    update({
      question_sets: [
        ...draft.question_sets,
        {
          id: `${prefix}-${n}`,
          name: `ชุดที่ ${n}`,
          description: "",
          target_concept: draft.concepts[0]?.id ?? "",
          main_items: [],
          challenge_items: [],
          max_items: 20,
          published: false,
        },
      ],
    });
  };

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  return (
    <div className="stack">
      {dirty && (
        <div className="callout callout-info">
          <TriangleAlert size={18} />
          ผลการตรวจความพร้อมด้านล่างเป็นของเวอร์ชันที่บันทึกล่าสุด กดบันทึกเพื่อตรวจใหม่
        </div>
      )}
      {draft.question_sets.map((qs, index) => {
        const check = readiness[qs.id];
        return (
          <Card key={index} className="card-pad stack">
            <div className="spread">
              <div className="row row-sm">
                {check ? (
                  check.ok ? (
                    <CircleCheck size={18} color="var(--success)" />
                  ) : (
                    <CircleAlert size={18} color="var(--warning)" />
                  )
                ) : null}
                <span className="subtitle">{qs.name}</span>
                <span className="mono xsmall faint">{qs.id}</span>
              </div>
              <label className="check">
                <input type="checkbox" checked={!!qs.published} onChange={(e) => setQs(index, { published: e.target.checked })} />
                เปิดให้นักเรียนทำ (เมื่อผ่านการตรวจความพร้อม)
              </label>
            </div>
            <div className="grid grid-3">
              <Field label="รหัสชุด">
                <input className="input mono" value={qs.id} onChange={(e) => setQs(index, { id: e.target.value.toUpperCase() })} />
              </Field>
              <Field label="ชื่อชุด">
                <input className="input" value={qs.name} onChange={(e) => setQs(index, { name: e.target.value })} />
              </Field>
              <Field label="Target Concept">
                <select className="select" value={qs.target_concept} onChange={(e) => setQs(index, { target_concept: e.target.value })}>
                  {draft.concepts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="คำอธิบาย">
              <input className="input" value={qs.description ?? ""} onChange={(e) => setQs(index, { description: e.target.value })} />
            </Field>
            <div className="grid grid-2">
              <div className="stack stack-sm">
                <span className="field-label">โจทย์หลัก ({qs.main_items.length})</span>
                <div className="pill-list">
                  {mains.map((it) => (
                    <button
                      key={it.id}
                      type="button"
                      className={`chip-toggle ${qs.main_items.includes(it.id) ? "on" : ""}`}
                      aria-pressed={qs.main_items.includes(it.id)}
                      onClick={() => setQs(index, { main_items: toggle(qs.main_items, it.id) })}
                      title={it.math ?? it.prompt}
                    >
                      {it.id}
                    </button>
                  ))}
                  {!mains.length && <span className="small faint">ยังไม่มีโจทย์หลัก</span>}
                </div>
              </div>
              <div className="stack stack-sm">
                <span className="field-label">โจทย์ท้าทายสำหรับ Fast-Track ({qs.challenge_items.length})</span>
                <div className="pill-list">
                  {challenges.map((it) => (
                    <button
                      key={it.id}
                      type="button"
                      className={`chip-toggle ${qs.challenge_items.includes(it.id) ? "on" : ""}`}
                      aria-pressed={qs.challenge_items.includes(it.id)}
                      onClick={() => setQs(index, { challenge_items: toggle(qs.challenge_items, it.id) })}
                      title={it.math ?? it.prompt}
                    >
                      {it.id}
                    </button>
                  ))}
                  {!challenges.length && <span className="small faint">ยังไม่มีโจทย์ท้าทาย</span>}
                </div>
              </div>
            </div>
            {check && (check.errors.length > 0 || check.warnings.length > 0) && (
              <ul className="check-list">
                {check.errors.map((e, i) => (
                  <li key={`e${i}`} className="is-error">
                    <CircleAlert size={15} />
                    {e}
                  </li>
                ))}
                {check.warnings.map((w, i) => (
                  <li key={`w${i}`}>
                    <TriangleAlert size={15} />
                    {w}
                  </li>
                ))}
              </ul>
            )}
            {check?.ok && !check.warnings.length && <p className="small" style={{ color: "var(--success)" }}>ผ่านการตรวจความพร้อมทุกข้อ</p>}
          </Card>
        );
      })}
      <Button variant="soft" icon={<Plus size={16} />} onClick={addSet} style={{ alignSelf: "flex-start" }} disabled={!draft.concepts.length}>
        เพิ่มชุดคำถาม
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------- เอกสาร
interface DocumentRow {
  id: number;
  filename: string;
  kind: string;
  chars: number;
  chunks: number;
  warning: string | null;
  uploaded_at: number;
  preview: string;
}

function DocsTab({ subjectId }: { subjectId: string }) {
  const { role } = useContentScope();
  const toast = useToast();
  const docs = useLoad(() => api<DocumentRow[]>(role, `/api/teacher/subjects/${subjectId}/documents`), [subjectId]);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<{ warning: string | null; chars: number }>(role, `/api/teacher/subjects/${subjectId}/documents`, { form });
      toast(result.warning ?? `อ่านได้ ${num(result.chars)} ตัวอักษร แบ่งเป็นย่อหน้าให้ RAG ค้นแล้ว`, result.warning ? "warning" : "success");
      docs.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "อัปโหลดไม่สำเร็จ", "warning");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    await api(role, `/api/teacher/documents/${id}`, { method: "DELETE" });
    docs.reload();
  };

  return (
    <Card>
      <CardHead
        title="เอกสารประกอบวิชา"
        sub="PDF, Word, ข้อความ หรือ Markdown ระบบแยกเป็นย่อหน้าแล้วค้นด้วย BM25 ในเครื่องนี้ ไม่ส่งเอกสารไปเทรนโมเดลภายนอก"
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              hidden
              accept=".pdf,.docx,.txt,.md"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) upload(file);
                e.target.value = "";
              }}
            />
            <Button size="sm" variant="primary" icon={<Upload size={15} />} loading={busy} onClick={() => fileRef.current?.click()}>
              อัปโหลดเอกสาร
            </Button>
          </>
        }
      />
      {docs.loading && !docs.data && <Spinner />}
      {docs.data?.length === 0 && <Empty>ยังไม่มีเอกสาร AI Tutor จะอ้างอิงจาก Bug Library และคำใบ้ของครูเท่านั้น</Empty>}
      <ul className="doc-list">
        {docs.data?.map((doc) => (
          <li key={doc.id}>
            <FileText size={20} color="var(--text-3)" />
            <div className="stack grow" style={{ gap: 2 }}>
              <span className="strong small">{doc.filename}</span>
              <span className="xsmall faint">
                {num(doc.chars)} ตัวอักษร · {doc.chunks} ย่อหน้า · {ago(doc.uploaded_at)}
              </span>
              {doc.warning && <span className="xsmall" style={{ color: "var(--warning)" }}>{doc.warning}</span>}
              {doc.preview && <p className="xsmall muted doc-preview">{doc.preview}</p>}
            </div>
            <Button size="sm" variant="ghost" icon={<Trash2 size={15} />} onClick={() => remove(doc.id)} aria-label={`ลบ ${doc.filename}`} />
          </li>
        ))}
      </ul>
    </Card>
  );
}
