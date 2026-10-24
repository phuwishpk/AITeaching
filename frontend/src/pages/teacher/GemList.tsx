import { useState } from "react";
import { useNavigate } from "react-router";
import { FileText, Plus, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago } from "../../lib/format";
import GemIcon from "../../components/GemIcon";
import { Badge, Button, Empty, Modal, Spinner, useToast } from "../../components/ui";
import { STATUS_TEXT, type GemSummary } from "./gemTypes";

// รายการ Gem ของครู เหมือนหน้า "Gem ของคุณ" ใน Gemini กดการ์ดเพื่อแก้ กด Gem ใหม่เพื่อสร้าง

export default function GemList() {
  const navigate = useNavigate();
  const toast = useToast();
  const gems = useLoad(() => api<GemSummary[]>("teacher", "/api/gems"));
  const [removing, setRemoving] = useState<GemSummary | null>(null);
  const now = useNow(30000);

  const remove = async () => {
    if (!removing) return;
    await api("teacher", `/api/gems/${removing.id}`, { method: "DELETE" });
    toast(`ลบ Gem ${removing.name} แล้ว`, "success");
    setRemoving(null);
    gems.reload();
  };

  return (
    <div className="page stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <h1 className="title-xl">Gem ของฉัน</h1>
          <p className="lead">สร้างติวเตอร์ให้นักเรียนด้วยคำสั่งและไฟล์ความรู้ AI จะสร้างโจทย์ คำใบ้ และคลังข้อผิดพลาดให้ทั้งหมด</p>
        </div>
        <Button variant="primary" icon={<Plus size={18} />} onClick={() => navigate("/teacher/gems/new")}>
          Gem ใหม่
        </Button>
      </header>

      {gems.loading && !gems.data && <Spinner />}
      {gems.data?.length === 0 && (
        <button className="gem-empty" onClick={() => navigate("/teacher/gems/new")}>
          <GemIcon size={56} />
          <span className="subtitle">สร้าง Gem แรก</span>
          <span className="small muted">ตั้งชื่อ เขียนคำสั่ง แนบไฟล์ แล้วกดบันทึก</span>
        </button>
      )}
      <div className="gem-grid">
        {gems.data?.map((gem) => {
          const status = STATUS_TEXT[gem.status];
          return (
            <article key={gem.id} className="gem-card fade-in">
              <button className="gem-card-main" onClick={() => navigate(`/teacher/gems/${gem.id}`)}>
                <GemIcon icon={gem.icon} color={gem.color} size={44} />
                <span className="stack" style={{ gap: 4, minWidth: 0 }}>
                  <span className="subtitle gem-card-name">{gem.name}</span>
                  <span className="small muted gem-card-text">{gem.description || "ยังไม่มีคำอธิบาย"}</span>
                </span>
              </button>
              <div className="gem-card-foot">
                <Badge tone={status.tone} dot>
                  {status.label}
                </Badge>
                {gem.stats && (
                  <span className="xsmall muted">
                    {gem.stats.main} โจทย์หลัก
                    {gem.stats.flagged + gem.stats.pending + gem.stats.check > 0 && (
                      <span className="gem-flag-count"> · รอตรวจ {gem.stats.flagged + gem.stats.pending + gem.stats.check}</span>
                    )}
                  </span>
                )}
                {gem.files > 0 && (
                  <span className="xsmall faint row row-sm">
                    <FileText size={12} />
                    {gem.files}
                  </span>
                )}
                <span className="xsmall faint grow" style={{ textAlign: "right" }}>
                  {ago(gem.updated_at, now, true)}
                </span>
                <Button variant="ghost" size="sm" icon={<Trash2 size={15} />} onClick={() => setRemoving(gem)} aria-label={`ลบ ${gem.name}`} />
              </div>
            </article>
          );
        })}
      </div>
      {gems.data && gems.data.length > 0 && <Empty>นักเรียนเห็น Gem ที่สร้างคลังโจทย์เสร็จแล้วเป็นการ์ดในหน้าเลือกบทเรียน</Empty>}

      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        title={`ลบ Gem ${removing?.name ?? ""}`}
        footer={
          <>
            <Button onClick={() => setRemoving(null)}>ยกเลิก</Button>
            <Button variant="danger" onClick={remove}>
              ลบ Gem
            </Button>
          </>
        }
      >
        <p className="small">ลบ Gem คลังโจทย์ทุกรุ่น และไฟล์ความรู้ นักเรียนที่กำลังเรียนกับ Gem นี้จะเรียนต่อไม่ได้</p>
      </Modal>
    </div>
  );
}
