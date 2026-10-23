import { useState, type FormEvent } from "react";
import { Copy, Lock, Trash2, UserPlus } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { Button, Card, CardHead, Empty, Field, Modal, Spinner, useToast } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

interface Entry {
  code: string;
  name: string | null;
  created_at: number;
}

export default function Roster() {
  const toast = useToast();
  const { reload: reloadOverview } = useTeacher();
  const roster = useLoad(() => api<Entry[]>("teacher", "/api/teacher/roster"));
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<Entry | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api<{ code: string; name: string }>("teacher", "/api/teacher/roster", {
        body: { name, code: code.trim() || null },
      });
      toast(`เพิ่ม ${result.name} แล้ว รหัสนักเรียนคือ ${result.code}`, "success");
      setName("");
      setCode("");
      roster.reload();
      reloadOverview();
    } catch (err) {
      toast(err instanceof Error ? err.message : "เพิ่มไม่สำเร็จ", "warning");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!removing) return;
    await api("teacher", `/api/teacher/roster/${removing.code}`, { method: "DELETE" });
    toast(`ลบชื่อของ ${removing.code} ออกจาก Roster แล้ว`, "success");
    setRemoving(null);
    roster.reload();
    reloadOverview();
  };

  return (
    <div className="page page-narrow stack stack-lg">
      <header className="stack stack-sm fade-in">
        <p className="eyebrow">รายชื่อนักเรียน (Roster)</p>
        <h1 className="title-xl">จับคู่รหัสนักเรียนกับชื่อจริง</h1>
        <p className="lead">
          ข้อมูลการเรียนทุกส่วนเก็บด้วยรหัสนักเรียนเท่านั้น ชื่อจริงอยู่ในตารางนี้ตารางเดียว เปิดได้เฉพาะครู หน้าผู้ดูแลระบบและ AI ไม่เห็นชื่อ
        </p>
      </header>

      <Card>
        <CardHead title="เพิ่มนักเรียน" sub="เว้นรหัสว่างไว้ ระบบจะออกรหัสถัดไปให้ (S-07, S-08, …)" />
        <form className="card-body roster-form" onSubmit={add} style={{ paddingTop: 0 }}>
          <Field label="ชื่อ-นามสกุล">
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="ชื่อนักเรียน" required />
          </Field>
          <Field label="รหัสนักเรียน (ไม่บังคับ)">
            <input className="input mono" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="อัตโนมัติ" />
          </Field>
          <Button variant="primary" type="submit" loading={busy} disabled={!name.trim()} icon={<UserPlus size={16} />}>
            เพิ่ม
          </Button>
        </form>
      </Card>

      <Card>
        <CardHead title="นักเรียนในห้อง" sub="ให้นักเรียนใช้รหัสนี้เข้าเรียน" actions={<Lock size={16} color="var(--text-3)" aria-label="ข้อมูลส่วนบุคคล" />} />
        {roster.loading && <Spinner />}
        {roster.data && roster.data.length === 0 && <Empty>ยังไม่มีนักเรียน</Empty>}
        {roster.data && roster.data.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>รหัสนักเรียน</th>
                  <th>ชื่อ</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {roster.data.map((entry) => (
                  <tr key={entry.code}>
                    <td className="mono">{entry.code}</td>
                    <td>{entry.name ?? <span className="faint">ไม่มีชื่อใน Roster</span>}</td>
                    <td style={{ textAlign: "right" }}>
                      <span className="row row-sm" style={{ justifyContent: "flex-end" }}>
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Copy size={15} />}
                          onClick={() => navigator.clipboard?.writeText(entry.code).then(() => toast("คัดลอกรหัสแล้ว"))}
                        >
                          คัดลอกรหัส
                        </Button>
                        {entry.name && (
                          <Button size="sm" variant="ghost" icon={<Trash2 size={15} />} onClick={() => setRemoving(entry)} aria-label={`ลบชื่อของ ${entry.code}`} />
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title="ลบชื่อออกจาก Roster"
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>ยกเลิก</Button>
            <Button variant="danger" onClick={remove}>
              ลบชื่อ
            </Button>
          </>
        }
      >
        <p className="small">
          ลบชื่อของ <span className="mono">{removing?.code}</span> ออกจาก Roster ข้อมูลการเรียนยังอยู่ครบภายใต้รหัสเดิม แต่ครูจะไม่เห็นชื่อจริงอีก
        </p>
      </Modal>
    </div>
  );
}
