import { useMemo, useState } from "react";
import { Activity, ArrowRight, BellRing, Check, HeartHandshake, Lightbulb, LifeBuoy, MessageCircle } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago, ALERT_LABEL, ALERT_TONE, clock, CLUSTER_COLORS, CLUSTER_NAMES, CLUSTER_SHORT, PATH_LABELS, pct, POSITION_LABELS, POSITION_TONE } from "../../lib/format";
import type { StaffView } from "../../lib/types";
import { BarList, CLUSTER_SHAPES, ClusterScatter, shapePath, type Centroid, type ClusterPoint } from "../../components/charts";
import { Badge, Button, Card, CardHead, Empty, Segmented, Spinner, Stat } from "../../components/ui";
import { useTeacher } from "./TeacherApp";

// ตำแหน่งที่ต้องให้ครูเข้าไปดู เรียงจากด่วนที่สุด
const NEEDS_TEACHER = ["SAFETY_STOP", "STAGNATION_DEADLOCK", "CHOOSING_PATH"];
const STRUGGLING = ["IMPASSE", "REMEDIAL", "CIRCUIT_BREAKER", "WALKTHROUGH"];

export function riskLevel(score?: number | null) {
  if (score == null) return { label: "–", tone: "neutral" as const };
  if (score >= 60) return { label: "สูง", tone: "danger" as const };
  if (score >= 35) return { label: "กลาง", tone: "warning" as const };
  return { label: "ต่ำ", tone: "calm" as const };
}

function priority(s: StaffView) {
  const urgent = s.position ? NEEDS_TEACHER.indexOf(s.position) : -1;
  if (urgent >= 0) return 1000 - urgent * 10;
  if (s.position && STRUGGLING.includes(s.position)) return 500 + (s.risk?.score ?? 0);
  if (!s.position) return -100;
  return s.risk?.score ?? 0;
}

export function ClusterMark({ cluster, short }: { cluster?: { key: string; name: string } | null; short?: boolean }) {
  if (!cluster) return <span className="faint">–</span>;
  return (
    <span className="row row-sm row-nowrap nowrap">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
        <path d={shapePath(CLUSTER_SHAPES[cluster.key] ?? "circle", 6, 6, 0.8)} fill={CLUSTER_COLORS[cluster.key]} />
      </svg>
      <span title={CLUSTER_NAMES[cluster.key]}>{(short ? CLUSTER_SHORT : CLUSTER_NAMES)[cluster.key] ?? cluster.name}</span>
    </span>
  );
}

export default function Overview() {
  const { data, error, feed, openStudent, nameOf, ackAlert, liveVersion, unread } = useTeacher();
  const [scope, setScope] = useState<"class" | "all">("class");
  const now = useNow(15000);
  const clusters = useLoad(
    () => api<{ points: ClusterPoint[]; centroids: Centroid[] }>("teacher", "/api/teacher/clusters"),
    [Math.floor(liveVersion / 25)],
  );

  const students = useMemo(() => {
    const list = (data?.students ?? []).filter((s) => scope === "all" || s.kind !== "sim");
    return [...list].sort((a, b) => priority(b) - priority(a));
  }, [data?.students, scope]);

  if (error && !data) return <Empty>{error}</Empty>;
  if (!data) return <Spinner />;

  const active = students.filter((s) => s.position && !["COMPLETED", "SESSION_ENDED"].includes(s.position));
  const needTeacher = students.filter((s) => s.position && NEEDS_TEACHER.includes(s.position));
  const urgent = students.filter((s) => s.position === "SAFETY_STOP");
  const t = data.telemetry;
  const openAlerts = data.alerts.filter((a) => !a.acknowledged).slice(0, 6);
  const visibleFeed = feed.filter((f) => scope === "all" || !f.code.startsWith("SIM-")).slice(0, 14);

  return (
    <div className="page stack stack-lg">
      <header className="spread fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">ภาพรวมห้องเรียน</p>
          <h1 className="title-xl">วันนี้นักเรียนเป็นอย่างไรบ้าง</h1>
        </div>
        <Segmented
          label="ขอบเขตนักเรียน"
          value={scope}
          onChange={setScope}
          options={[
            { id: "class", label: "ห้องเรียนจริง" },
            { id: "all", label: "รวมนักเรียนจำลอง" },
          ]}
        />
      </header>

      <section className="grid grid-4">
        <Stat label={<span className="row row-sm"><Activity size={15} />กำลังเรียนอยู่</span>} value={active.length} sub={`จากทั้งหมด ${students.length} คน`} />
        <Stat
          label={<span className="row row-sm"><LifeBuoy size={15} />รอครูช่วย</span>}
          value={needTeacher.length}
          sub={urgent.length ? `ด่วน ${urgent.length} คน` : "ไม่มีกรณีด่วน"}
          tone={urgent.length ? "var(--danger)" : undefined}
        />
        <Stat
          label={<span className="row row-sm"><HeartHandshake size={15} />Average Remediation Success</span>}
          value={pct(t.remediation_success)}
          sub={`ซ่อมเสริมผ่าน ${t.remediation_counts.passed} จาก ${t.remediation_counts.started} รอบ`}
        />
        <Stat
          label={<span className="row row-sm"><Lightbulb size={15} />Hint Utility Rate</span>}
          value={pct(t.hint_utility)}
          sub={`คำใบ้ที่ตามด้วยการตอบถูก ${t.hint_counts.useful}/${t.hint_counts.shown}`}
        />
      </section>

      <section className="ov-grid">
        <Card>
          <CardHead title="นักเรียนรายคน" sub="เรียงจากคนที่ควรดูก่อน กดที่แถวเพื่อดูรายละเอียดและสั่ง Manual Override" />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>นักเรียน</th>
                  <th style={{ minWidth: 150 }}>ตอนนี้</th>
                  <th>เส้นทาง</th>
                  <th>Mastery เป้าหมาย</th>
                  <th>Risk Score</th>
                  <th>กลุ่ม</th>
                  <th>ล่าสุด</th>
                </tr>
              </thead>
              <tbody>
                {students.map((s) => {
                  const mastery = s.target ? s.mastery?.[s.target] : null;
                  const risk = riskLevel(s.risk?.score);
                  return (
                    <tr key={s.code} className="clickable" onClick={() => openStudent(s.code)}>
                      <td>
                        <div className="stack" style={{ gap: 0 }}>
                          <span className="row row-sm row-nowrap">
                            <span className="strong nowrap">{s.name ?? s.code}</span>
                            {!!unread[s.code] && (
                              <button
                                className="unread-pill"
                                title="มีข้อความใหม่จากนักเรียน"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openStudent(s.code, "messages");
                                }}
                              >
                                <MessageCircle size={12} />
                                {unread[s.code]}
                              </button>
                            )}
                          </span>
                          <span className="xsmall faint mono">
                            {s.code}
                            {s.kind === "sim" ? " · จำลอง" : s.kind === "demo" ? " · สาธิต" : ""}
                          </span>
                        </div>
                      </td>
                      <td>
                        {s.position ? (
                          <Badge tone={POSITION_TONE[s.position] ?? "neutral"} dot title={POSITION_LABELS[s.position]}>
                            {s.teacher_text}
                          </Badge>
                        ) : (
                          <span className="faint small">ยังไม่เริ่มเรียน</span>
                        )}
                      </td>
                      <td className="small nowrap">{s.path ? PATH_LABELS[s.path] ?? s.path : "–"}</td>
                      <td style={{ minWidth: 120 }}>
                        {mastery != null ? (
                          <div className="row row-sm row-nowrap">
                            <div className="meter grow" style={{ minWidth: 60 }}>
                              <span style={{ width: `${mastery * 100}%`, background: "var(--accent)" }} />
                            </div>
                            <span className="small num">{pct(mastery)}</span>
                          </div>
                        ) : (
                          <span className="faint">–</span>
                        )}
                      </td>
                      <td>
                        {s.risk ? (
                          <span className="row row-sm row-nowrap">
                            <span className="num strong">{Math.round(s.risk.score)}</span>
                            <Badge tone={risk.tone}>{risk.label}</Badge>
                          </span>
                        ) : (
                          <span className="faint">–</span>
                        )}
                      </td>
                      <td className="small">
                        <ClusterMark cluster={s.cluster} short />
                      </td>
                      <td className="small faint nowrap">{ago(s.last_activity, now, true)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!students.length && <Empty>ยังไม่มีนักเรียน เพิ่มรายชื่อได้ที่เมนูรายชื่อนักเรียน</Empty>}
          </div>
        </Card>

        <div className="stack">
          <Card>
            <CardHead
              title={<span className="row row-sm"><BellRing size={17} />การแจ้งเตือนที่ยังไม่รับทราบ</span>}
              sub="ระบบส่งเรื่องที่ต้องใช้ดุลยพินิจของครู"
            />
            <div className="card-body stack stack-sm" style={{ paddingTop: 0 }}>
              {openAlerts.length === 0 && <p className="small faint">ไม่มีเรื่องค้างอยู่</p>}
              {openAlerts.map((a) => (
                <div key={a.id} className={`alert-row alert-${a.level}`}>
                  <button className="alert-main" onClick={() => openStudent(a.code)}>
                    <span className="row row-sm">
                      <Badge tone={ALERT_TONE[a.level]}>{ALERT_LABEL[a.level]}</Badge>
                      <span className="strong small">{nameOf(a.code) ?? a.code}</span>
                      <span className="xsmall faint">{ago(a.ts, now)}</span>
                    </span>
                    <span className="small muted">{a.message}</span>
                  </button>
                  <span className="stack" style={{ gap: 2 }}>
                    <Button size="sm" variant="ghost" icon={<MessageCircle size={15} />} onClick={() => openStudent(a.code, "messages")}>
                      ตอบกลับ
                    </Button>
                    <Button size="sm" variant="ghost" icon={<Check size={15} />} onClick={() => ackAlert(a.id)} aria-label="รับทราบ">
                      รับทราบ
                    </Button>
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHead title="ความเคลื่อนไหวล่าสุด" sub="การตัดสินใจของระบบแบบสด (Decision Trace)" />
            <ol className="feed">
              {visibleFeed.length === 0 && <li className="small faint">รอความเคลื่อนไหวจากนักเรียน</li>}
              {visibleFeed.map((f) => (
                <li key={f.key}>
                  <button onClick={() => openStudent(f.code)}>
                    <span className="row row-sm xsmall">
                      <span className="strong">{nameOf(f.code) ?? f.code}</span>
                      <span className="faint num">{clock(f.ts)}</span>
                    </span>
                    <span className="small">{f.rule}</span>
                    {f.from !== f.to && (
                      <span className="row row-sm xsmall faint">
                        {POSITION_LABELS[f.from] ?? f.from}
                        <ArrowRight size={12} />
                        {POSITION_LABELS[f.to] ?? f.to}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </section>

      <section className="ov-grid ov-grid-even">
        <Card>
          <CardHead
            title="กลุ่มพฤติกรรมผู้เรียน (K-Means)"
            sub="จัดกลุ่มจากเวลาคิดเฉลี่ย สัดส่วนตอบถูก และความยาว Session ชื่อกลุ่มแสดงเฉพาะฝั่งครู"
          />
          <div className="card-body" style={{ paddingTop: 0 }}>
            {clusters.data?.points.length ? (
              <ClusterScatter points={clusters.data.points} centroids={clusters.data.centroids} onSelect={openStudent} />
            ) : clusters.loading ? (
              <Spinner />
            ) : (
              <Empty>ต้องมีนักเรียนที่ตอบอย่างน้อย 3 ครั้งอย่างน้อย 4 คนก่อนจึงจัดกลุ่มได้</Empty>
            )}
          </div>
        </Card>
        <Card>
          <CardHead title="Platform Telemetry" sub="ตัวชี้วัดประสิทธิภาพของระบบ ไม่ใช่คะแนนของนักเรียน" />
          <div className="card-body stack" style={{ paddingTop: 0 }}>
            <div className="stack stack-sm">
              <p className="small strong">Drop-off Rate ต่อชุดคำถาม</p>
              <BarList
                rows={Object.entries(t.drop_off).map(([setId, entry]) => ({
                  key: setId,
                  label: setId,
                  sub: `${entry.sessions} Session · จบ ${entry.completed}`,
                  value: entry.drop_off_rate,
                  valueText: pct(entry.drop_off_rate),
                }))}
                max={1}
              />
              {!Object.keys(t.drop_off).length && <p className="small faint">ยังไม่มี Session</p>}
            </div>
            <hr className="divider" />
            <dl className="defs">
              <div>
                <dt>Drop-off Rate</dt>
                <dd>สัดส่วน Session ที่นักเรียนเลือกหยุดเองหรือหายไปเกิน 6 ชั่วโมงก่อนจบชุด</dd>
              </div>
              <div>
                <dt>Average Remediation Success</dt>
                <dd>รอบซ่อมเสริมที่ทำผ่านแล้วได้กลับไปข้อเดิม เทียบกับรอบที่เริ่มทั้งหมด</dd>
              </div>
              <div>
                <dt>Hint Utility Rate</dt>
                <dd>คำใบ้ที่นักเรียนเห็นแล้วตอบถูกในครั้งถัดไป เทียบกับคำใบ้ทั้งหมดที่แสดง</dd>
              </div>
            </dl>
          </div>
        </Card>
      </section>
    </div>
  );
}
