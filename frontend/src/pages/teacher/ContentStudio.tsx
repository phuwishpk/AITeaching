import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { CircleAlert, CircleCheck, Download, FilePlus2, PencilLine, Trash2, Upload } from "lucide-react";
import { api } from "../../lib/api";
import { useContentScope } from "./contentScope";
import { useLoad } from "../../lib/hooks";
import type { Subject, SubjectSummary } from "../../lib/types";
import { Badge, Button, Card, Empty, Field, Modal, Spinner, useToast } from "../../components/ui";

export function downloadJson(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ContentStudio() {
  const { role, base } = useContentScope();
  const toast = useToast();
  const navigate = useNavigate();
  const subjects = useLoad(() => api<SubjectSummary[]>(role, "/api/teacher/subjects"));
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState<SubjectSummary | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const exportSubject = async (id: string) => {
    const subject = await api<Subject>(role, `/api/teacher/subjects/${id}`);
    downloadJson(`${id}.json`, subject);
  };

  const importFile = async (file: File) => {
    try {
      const subject = JSON.parse(await file.text()) as Subject;
      if (!subject.id || !subject.name) throw new Error("ไฟล์ต้องมี id และ name ของวิชา");
      const exists = subjects.data?.some((s) => s.id === subject.id);
      await api(role, exists ? `/api/teacher/subjects/${subject.id}` : "/api/teacher/subjects", {
        method: exists ? "PUT" : "POST",
        body: subject,
      });
      toast(exists ? `แทนที่วิชา ${subject.name} ด้วยไฟล์ที่นำเข้าแล้ว` : `นำเข้าวิชา ${subject.name} แล้ว`, "success");
      subjects.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "อ่านไฟล์ไม่สำเร็จ", "warning");
    }
  };

  const remove = async () => {
    if (!removing) return;
    await api(role, `/api/teacher/subjects/${removing.id}`, { method: "DELETE" });
    toast(`ลบวิชา ${removing.name} แล้ว`, "success");
    setRemoving(null);
    subjects.reload();
  };

  return (
    <div className="page stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">วิชาและชุดคำถาม</p>
          <h1 className="title-xl">เนื้อหาที่ระบบใช้สอน</h1>
          <p className="lead">
            วิชาหนึ่งมีแผนผังความรู้ โจทย์ คลังข้อผิดพลาด ตัวอย่างทีละขั้น และเอกสารให้ RAG ค้น ชุดคำถามจะเปิดให้นักเรียนเมื่อผ่านการตรวจความพร้อม
          </p>
        </div>
        <div className="row">
          <input
            ref={fileRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importFile(file);
              e.target.value = "";
            }}
          />
          <Button icon={<Upload size={16} />} onClick={() => fileRef.current?.click()}>
            นำเข้า JSON
          </Button>
          <Button variant="primary" icon={<FilePlus2 size={16} />} onClick={() => setCreating(true)}>
            สร้างวิชาใหม่
          </Button>
        </div>
      </header>

      {subjects.loading && !subjects.data && <Spinner />}
      {subjects.data?.length === 0 && (
        <Card>
          <Empty>ยังไม่มีวิชา เริ่มจากสร้างวิชาใหม่หรือนำเข้าไฟล์ JSON</Empty>
        </Card>
      )}
      <div className="subject-grid">
        {subjects.data?.map((subject) => (
          <Card key={subject.id} className="card-pad stack fade-in">
            <div className="spread">
              <div className="stack" style={{ gap: 2 }}>
                <span className="eyebrow">{subject.grade || "ไม่ระบุชั้น"}</span>
                <h2 className="title">{subject.name}</h2>
              </div>
              <span className="mono xsmall faint">{subject.id}</span>
            </div>
            {subject.description && <p className="small muted">{subject.description}</p>}
            <div className="row small muted">
              <span>{subject.concepts} มโนทัศน์</span>·<span>{subject.items} โจทย์</span>·<span>{subject.bug_tags} รายการใน Bug Library</span>
            </div>
            <ul className="set-status">
              {subject.sets.map((qs) => (
                <li key={qs.id}>
                  {qs.readiness.ok ? <CircleCheck size={16} color="var(--success)" /> : <CircleAlert size={16} color="var(--warning)" />}
                  <span className="grow small">{qs.name}</span>
                  {qs.readiness.ok ? (
                    <Badge tone={qs.published ? "success" : "neutral"}>{qs.published ? "เปิดให้นักเรียนแล้ว" : "พร้อม ยังไม่เปิด"}</Badge>
                  ) : (
                    <Badge tone="warning">ยังไม่พร้อม {qs.readiness.errors.length} จุด</Badge>
                  )}
                </li>
              ))}
              {!subject.sets.length && <li className="small faint">ยังไม่มีชุดคำถาม</li>}
            </ul>
            <div className="row" style={{ justifyContent: "flex-end", marginTop: "auto" }}>
              <Button variant="ghost" size="sm" icon={<Trash2 size={15} />} onClick={() => setRemoving(subject)} aria-label={`ลบวิชา ${subject.name}`} />
              <Button variant="ghost" size="sm" icon={<Download size={15} />} onClick={() => exportSubject(subject.id)}>
                ส่งออก JSON
              </Button>
              <Button variant="primary" size="sm" icon={<PencilLine size={15} />} onClick={() => navigate(`${base}/${subject.id}`)}>
                แก้ไขเนื้อหา
              </Button>
            </div>
          </Card>
        ))}
      </div>

      <CreateSubject
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(id) => {
          setCreating(false);
          navigate(`${base}/${id}`);
        }}
      />
      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title={`ลบวิชา ${removing?.name ?? ""}`}
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>ยกเลิก</Button>
            <Button variant="danger" onClick={remove}>
              ลบวิชาและเอกสาร
            </Button>
          </>
        }
      >
        <p className="small">ลบวิชา ชุดคำถาม และเอกสารทั้งหมดของวิชานี้ ถ้าต้องการเก็บไว้ ให้ส่งออก JSON ก่อน</p>
      </Modal>
    </div>
  );
}

function CreateSubject({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: string) => void }) {
  const { role } = useContentScope();
  const toast = useToast();
  const [form, setForm] = useState({ id: "", name: "", grade: "", description: "" });
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const id = form.id.trim().toLowerCase().replace(/\s+/g, "-");
      await api(role, "/api/teacher/subjects", {
        body: { ...form, id, concepts: [], items: [], bug_tags: [], walkthroughs: [], question_sets: [] },
      });
      setForm({ id: "", name: "", grade: "", description: "" });
      onCreated(id);
    } catch (err) {
      toast(err instanceof Error ? err.message : "สร้างวิชาไม่สำเร็จ", "warning");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="สร้างวิชาใหม่">
      <form className="stack" onSubmit={submit}>
        <div className="grid grid-2">
          <Field label="รหัสวิชา" hint="ภาษาอังกฤษ ไม่มีช่องว่าง เช่น math-m1">
            <input className="input mono" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} required />
          </Field>
          <Field label="ระดับชั้น">
            <input className="input" value={form.grade} onChange={(e) => setForm({ ...form, grade: e.target.value })} placeholder="ม.1" />
          </Field>
        </div>
        <Field label="ชื่อวิชา">
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="คำอธิบาย">
          <textarea className="textarea" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </Field>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <Button onClick={onClose} type="button">
            ยกเลิก
          </Button>
          <Button variant="primary" type="submit" loading={busy} disabled={!form.id.trim() || !form.name.trim()}>
            สร้างแล้วเริ่มใส่เนื้อหา
          </Button>
        </div>
      </form>
    </Modal>
  );
}
