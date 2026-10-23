import { useState } from "react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import type { AiLog } from "../../lib/types";
import AiLogCard from "../../components/AiLog";
import { Card, Empty, Segmented, Spinner } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

export default function AiReview() {
  const { liveVersion, nameOf } = useTeacher();
  const [filter, setFilter] = useState<"all" | "blocked" | "chat">("all");
  const logs = useLoad(() => api<AiLog[]>("teacher", "/api/teacher/ai-logs"), [Math.floor(liveVersion / 8)]);
  const rows = (logs.data ?? []).filter((log) =>
    filter === "blocked" ? log.guard?.blocked || log.guard?.trigger : filter === "chat" ? log.purpose === "chat" : true,
  );

  return (
    <div className="page page-narrow stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">ตรวจคำตอบของ AI</p>
          <h1 className="title-xl">ทุกข้อความที่ AI สร้าง เปิดดูย้อนหลังได้</h1>
          <p className="lead">
            อย่าหลงเชื่อภาษาที่สละสลวยของ AI ทุกบันทึกแสดง prompt ทั้ง 4 กรอบ เอกสารที่ RAG ดึงมา และผลการตรวจของ Answer-Leak Guard
            ให้ครูตรวจข้อเท็จจริงได้เอง
          </p>
        </div>
        <Segmented
          label="ตัวกรอง"
          value={filter}
          onChange={setFilter}
          options={[
            { id: "all", label: "ทั้งหมด" },
            { id: "blocked", label: "ถูก Guard บล็อก" },
            { id: "chat", label: "แชต" },
          ]}
        />
      </header>
      {logs.loading && !logs.data && <Spinner />}
      {logs.data && rows.length === 0 && (
        <Card>
          <Empty>ยังไม่มีบันทึก ถ้ายังไม่ได้ใส่ API key ระบบใช้คำใบ้ต้นฉบับของครูเสมอ (Offline Mode)</Empty>
        </Card>
      )}
      <div className="stack stack-sm">
        {rows.map((log) => (
          <AiLogCard key={log.id} log={log} who={log.code ? nameOf(log.code) ?? log.code : null} />
        ))}
      </div>
    </div>
  );
}
