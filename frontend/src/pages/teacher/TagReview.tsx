import { useState } from "react";
import { Check, Sparkles, X } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { ago } from "../../lib/format";
import { Badge, Button, Card, Empty, Segmented, Spinner, useToast } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

interface Suggestion {
  id: number;
  ts: number;
  code: string;
  item_id: string;
  item_text: string;
  answer: string;
  tag: string;
  tag_name: string;
  rationale: string;
  status: "pending" | "confirmed" | "rejected";
}

const STATUS = {
  pending: { label: "รอครูตัดสิน", tone: "info" as const },
  confirmed: { label: "ยืนยันแล้ว", tone: "success" as const },
  rejected: { label: "ไม่ใช้", tone: "calm" as const },
};

export default function TagReview() {
  const toast = useToast();
  const { reload: reloadOverview, liveVersion } = useTeacher();
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const tags = useLoad(() => api<Suggestion[]>("teacher", "/api/teacher/tags"), [Math.floor(liveVersion / 10)]);
  const [busy, setBusy] = useState<number | null>(null);

  const decide = async (row: Suggestion, decision: "confirm" | "reject") => {
    setBusy(row.id);
    try {
      await api("teacher", `/api/teacher/tags/${row.id}`, { body: { decision } });
      toast(decision === "confirm" ? `เพิ่มคำตอบ ${row.answer} เข้า Bug Library ของข้อ ${row.item_id} แล้ว` : "ไม่ใช้แท็กนี้", "success");
      tags.reload();
      reloadOverview();
    } finally {
      setBusy(null);
    }
  };

  const rows = (tags.data ?? []).filter((r) => filter === "all" || r.status === "pending");

  return (
    <div className="page page-narrow stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">แท็กที่ AI เสนอ</p>
          <h1 className="title-xl">คำตอบผิดแบบใหม่ที่ยังไม่อยู่ใน Bug Library</h1>
          <p className="lead">
            เมื่อนักเรียนตอบผิดแบบที่ระบบไม่รู้จัก AI จะเดาว่าน่าจะเป็นความเข้าใจผิดแบบไหน แต่ยังไม่ใช้กับนักเรียนจนกว่าครูจะยืนยัน
          </p>
        </div>
        <Segmented
          label="ตัวกรอง"
          value={filter}
          onChange={setFilter}
          options={[
            { id: "pending", label: "รอตัดสิน" },
            { id: "all", label: "ทั้งหมด" },
          ]}
        />
      </header>
      {tags.loading && !tags.data && <Spinner />}
      {tags.data && rows.length === 0 && (
        <Card>
          <Empty>
            <Sparkles size={20} />
            <br />
            ไม่มีแท็กที่รอตัดสิน ต้องเปิดใช้ AI Provider ในหน้าผู้ดูแลระบบก่อน ระบบจึงจะเสนอแท็กได้
          </Empty>
        </Card>
      )}
      <div className="stack">
        {rows.map((row) => (
          <Card key={row.id} className="card-pad stack stack-sm">
            <div className="spread">
              <span className="row row-sm">
                <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                <span className="xsmall faint">
                  {row.code} · {ago(row.ts)}
                </span>
              </span>
              <span className="mono small">{row.item_id}</span>
            </div>
            <p className="small muted">{row.item_text}</p>
            <div className="tag-proposal">
              <div>
                <span className="xsmall faint">คำตอบของนักเรียน</span>
                <span className="mono strong">{row.answer}</span>
              </div>
              <div>
                <span className="xsmall faint">AI เสนอว่าเป็น</span>
                <span className="strong">
                  {row.tag_name} <span className="mono xsmall faint">{row.tag}</span>
                </span>
              </div>
            </div>
            {row.rationale && <p className="small">เหตุผลของ AI: {row.rationale}</p>}
            {row.status === "pending" && (
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button variant="ghost" icon={<X size={16} />} loading={busy === row.id} onClick={() => decide(row, "reject")}>
                  ไม่ใช้
                </Button>
                <Button variant="primary" icon={<Check size={16} />} loading={busy === row.id} onClick={() => decide(row, "confirm")}>
                  ยืนยันเข้า Bug Library
                </Button>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
