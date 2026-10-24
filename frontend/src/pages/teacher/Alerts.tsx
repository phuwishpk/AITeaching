import { useState } from "react";
import { Check, MessageCircle } from "lucide-react";
import { useNow } from "../../lib/hooks";
import { ago, ALERT_LABEL, ALERT_TONE, clock } from "../../lib/format";
import { Badge, Button, Card, Empty, Segmented, Spinner } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

const KIND_LABEL: Record<string, string> = {
  self_harm: "ข้อความเสี่ยงทำร้ายตนเอง",
  stress: "ความเครียด",
  quit: "อยากเลิกเรียน",
  burnout_rapid: "Burnout Signal: ตอบเร็วผิดปกติ",
  burnout_idle: "Burnout Signal: พักบ่อย",
  burnout_risk: "Burnout Signal: Risk Score สูง",
  hint_abuse: "Gaming the System",
  deadlock: "Stagnation Deadlock",
  cap: "ครบเพดาน 20 ข้อ",
};

export default function AlertsPage() {
  const { data, ackAlert, openStudent, nameOf } = useTeacher();
  const [filter, setFilter] = useState<"open" | "all" | "silent">("open");
  const now = useNow(15000);
  if (!data) return <Spinner />;

  const alerts = data.alerts.filter((a) =>
    filter === "open" ? !a.acknowledged && a.level !== "silent" : filter === "silent" ? a.level === "silent" : true,
  );

  return (
    <div className="page page-narrow stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">การแจ้งเตือน</p>
          <h1 className="title-xl">เรื่องที่ระบบส่งต่อให้ครู</h1>
          <p className="lead">
            แจ้งเตือนแบบด่วนใช้กับข้อความที่เสี่ยงต่อความปลอดภัย แบบปกติใช้เมื่อระบบช่วยต่อเองไม่ได้ ส่วนแบบเงียบเป็นสัญญาณให้ครูสังเกต
            ระบบไม่หยุดกิจกรรมของนักเรียนเพียงเพราะตัวเลขบอกว่าเสี่ยง
          </p>
        </div>
        <Segmented
          label="ตัวกรอง"
          value={filter}
          onChange={setFilter}
          options={[
            { id: "open", label: "ยังไม่รับทราบ" },
            { id: "silent", label: "แจ้งเตือนเงียบ" },
            { id: "all", label: "ทั้งหมด" },
          ]}
        />
      </header>
      <Card>
        {alerts.length === 0 && <Empty>ไม่มีรายการในตัวกรองนี้</Empty>}
        <ul className="alert-list">
          {alerts.map((a) => (
            <li key={a.id} className={`alert-row alert-${a.level} ${a.acknowledged ? "is-done" : ""}`}>
              <button className="alert-main" onClick={() => openStudent(a.code)}>
                <span className="row row-sm">
                  <Badge tone={ALERT_TONE[a.level]}>{ALERT_LABEL[a.level]}</Badge>
                  <span className="strong">{nameOf(a.code) ?? a.code}</span>
                  <span className="xsmall faint mono">{a.code}</span>
                  <span className="xsmall faint">{KIND_LABEL[a.kind] ?? a.kind}</span>
                </span>
                <span className="small muted">{a.message}</span>
                <span className="xsmall faint num">
                  {clock(a.ts)} · {ago(a.ts, now)}
                </span>
              </button>
              <Button size="sm" variant="ghost" icon={<MessageCircle size={15} />} onClick={() => openStudent(a.code, "messages")}>
                ตอบกลับ
              </Button>
              {a.acknowledged ? (
                <span className="xsmall faint row row-sm">
                  <Check size={14} />
                  รับทราบแล้ว
                </span>
              ) : (
                <Button size="sm" variant="secondary" icon={<Check size={15} />} onClick={() => ackAlert(a.id)}>
                  รับทราบ
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
