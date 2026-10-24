import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Activity, BarChart3, Check, CircleCheckBig, Flag, LifeBuoy, MessageCircle, Trophy } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago, ALERT_LABEL, ALERT_TONE, CLUSTER_COLORS, CLUSTER_NAMES, CLUSTER_SHORT, pct, POSITION_TONE } from "../../lib/format";
import type { Alert, StaffView, Telemetry } from "../../lib/types";
import { BarList, CLUSTER_SHAPES, ClusterScatter, shapePath, type Centroid, type ClusterPoint } from "../../components/charts";
import { Badge, Button, Card, CardHead, Empty, Segmented, Spinner, Stat } from "../../components/ui";
import { useTeacher } from "./TeacherApp";
import type { GemSummary } from "./gemTypes";

// ภาพรวมห้องเรียน: บนสุดคือเรื่องที่ครูต้องทำตอนนี้ ถัดมาคือนักเรียนทุกคน สถิติเชิงวิเคราะห์พับเก็บไว้ล่างสุด

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

interface Attention {
  code: string;
  level: Alert["level"] | "waiting";
  message: string;
  ts: number;
  alerts: Alert[];
}

export default function Overview() {
  const { data, error, openStudent, nameOf, ackAlert, liveVersion, unread } = useTeacher();
  const [scope, setScope] = useState<"class" | "all">("class");
  const [statsOpen, setStatsOpen] = useState(false);
  const now = useNow(15000);
  const navigate = useNavigate();
  const gems = useLoad(() => api<GemSummary[]>("teacher", "/api/gems"), [Math.floor(liveVersion / 20)]);
  // โจทย์ที่รอครูตรวจ: เฉลยติดธง AI สร้างเพิ่มรออนุมัติ และโจทย์สดที่นักเรียนใช้ไปแล้ว
  const review = (g: GemSummary) => (g.stats?.flagged ?? 0) + (g.stats?.pending ?? 0) + (g.stats?.check ?? 0);
  const flaggedGems = (gems.data ?? []).filter((g) => review(g) > 0);

  const students = useMemo(() => {
    const list = (data?.students ?? []).filter((s) => scope === "all" || s.kind !== "sim");
    return [...list].sort((a, b) => priority(b) - priority(a));
  }, [data?.students, scope]);

  // เรื่องที่ต้องดูตอนนี้: การแจ้งเตือนที่ยังไม่รับทราบรวมเป็นรายคน (ไม่นับแบบเงียบ) และคนที่ระบบหยุดรอครู
  const attention = useMemo(() => {
    const byCode = new Map<string, Attention>();
    for (const a of data?.alerts ?? []) {
      if (a.acknowledged || a.level === "silent") continue;
      const entry = byCode.get(a.code);
      if (!entry) byCode.set(a.code, { code: a.code, level: a.level, message: a.message, ts: a.ts, alerts: [a] });
      else {
        entry.alerts.push(a);
        if (a.level === "urgent") entry.level = "urgent";
      }
    }
    for (const s of students) {
      if (s.position && NEEDS_TEACHER.includes(s.position) && !byCode.has(s.code)) {
        byCode.set(s.code, { code: s.code, level: "waiting", message: s.teacher_text, ts: s.position_since ?? 0, alerts: [] });
      }
    }
    const rank = (a: Attention) => (a.level === "urgent" ? 0 : 1);
    return [...byCode.values()].sort((a, b) => rank(a) - rank(b) || b.ts - a.ts);
  }, [data?.alerts, students]);

  if (error && !data) return <Empty>{error}</Empty>;
  if (!data) return <Spinner />;

  const active = students.filter((s) => s.position && !["COMPLETED", "SESSION_ENDED"].includes(s.position));
  const needTeacher = students.filter((s) => s.position && NEEDS_TEACHER.includes(s.position));
  const done = students.filter((s) => s.position === "COMPLETED");

  return (
    <div className="page stack stack-lg">
      <header className="spread fade-in">
        <h1 className="title-xl">ภาพรวมห้องเรียน</h1>
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

      {attention.length ? (
        <Card className="attention-card">
          <CardHead
            title={
              <span className="row row-sm">
                <LifeBuoy size={18} />
                ต้องดูตอนนี้ ({attention.length})
              </span>
            }
          />
          <ul className="attention-list">
            {attention.map((a) => (
              <li key={a.code} className={`attention attention-${a.level}`}>
                <div className="stack grow" style={{ gap: 2 }}>
                  <span className="row row-sm">
                    <span className="strong">{nameOf(a.code) ?? a.code}</span>
                    {a.level === "waiting" ? <Badge tone="warning">รอครู</Badge> : <Badge tone={ALERT_TONE[a.level]}>{ALERT_LABEL[a.level]}</Badge>}
                    <span className="xsmall faint">{ago(a.ts, now)}</span>
                  </span>
                  <span className="small muted">{a.message}</span>
                </div>
                <div className="row row-sm row-nowrap">
                  <Button size="sm" variant="primary" onClick={() => openStudent(a.code)}>
                    เปิดดู
                  </Button>
                  <Button size="sm" variant="secondary" icon={<MessageCircle size={15} />} onClick={() => openStudent(a.code, "messages")}>
                    ทัก
                  </Button>
                  {a.alerts.length > 0 && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="btn-icon"
                      icon={<Check size={16} />}
                      title="รับทราบแล้ว"
                      aria-label="รับทราบแล้ว"
                      onClick={() => a.alerts.forEach((x) => ackAlert(x.id))}
                    />
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <div className="calm-banner fade-in">
          <CircleCheckBig size={20} />
          ไม่มีเรื่องที่ต้องรีบดู นักเรียนเรียนได้ตามปกติ
        </div>
      )}

      {/* เฉลยที่ AI เขียนแล้วตรวจไม่ผ่าน ซ่อนจากนักเรียนจนครูตรวจ (ADR-0003) */}
      {flaggedGems.map((g) => (
        <div key={g.id} className="flag-banner fade-in">
          <Flag size={18} />
          <span className="grow small">
            Gem <span className="strong">{g.name}</span> มีโจทย์รอครูตรวจ {review(g)} ข้อ
            <span className="muted">
              {" "}
              (ติดธง {g.stats!.flagged} · รออนุมัติ {g.stats!.pending} · สร้างสดระหว่างเรียน {g.stats!.check})
            </span>
          </span>
          <Button size="sm" variant="secondary" onClick={() => navigate(`/teacher/gems/${g.id}`)}>
            ตรวจโจทย์
          </Button>
        </div>
      ))}

      <section className="grid grid-3 overview-stats">
        <Stat
          label={
            <span className="row row-sm">
              <Activity size={15} />
              กำลังเรียนอยู่
            </span>
          }
          value={active.length}
          sub={`จากทั้งหมด ${students.length} คน`}
        />
        <Stat
          label={
            <span className="row row-sm">
              <LifeBuoy size={15} />
              รอครูช่วย
            </span>
          }
          value={needTeacher.length}
          sub={needTeacher.length ? "ดูได้ที่กล่องด้านบน" : "ไม่มี"}
          tone={needTeacher.length ? "var(--danger)" : undefined}
        />
        <Stat
          label={
            <span className="row row-sm">
              <Trophy size={15} />
              ทำชุดจบแล้ว
            </span>
          }
          value={done.length}
          sub="ผ่านเกณฑ์ความชำนาญ"
        />
      </section>

      <Card>
        <CardHead title="นักเรียน" sub="คนที่ควรดูก่อนอยู่บน กดที่แถวเพื่อดูรายละเอียด ทักนักเรียน หรือสั่ง Manual Override" />
        <div className="table-wrap">
          <table className="table class-table">
            <thead>
              <tr>
                <th>นักเรียน</th>
                <th>ตอนนี้</th>
                <th>ความชำนาญ</th>
                <th>ความเสี่ยง</th>
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
                        <span className={`status-text tone-${POSITION_TONE[s.position] ?? "neutral"}`}>{s.teacher_text}</span>
                      ) : (
                        <span className="faint small">ยังไม่เริ่ม</span>
                      )}
                    </td>
                    <td style={{ minWidth: 140 }}>
                      {mastery != null ? (
                        <div className="row row-sm row-nowrap">
                          <div className="meter grow" style={{ minWidth: 70 }}>
                            <span style={{ width: `${mastery * 100}%`, background: "var(--accent)" }} />
                          </div>
                          <span className="small num">{pct(mastery)}</span>
                        </div>
                      ) : (
                        <span className="faint">–</span>
                      )}
                    </td>
                    <td className="nowrap">
                      {s.risk ? (
                        <span className={`risk-text tone-${risk.tone}`} title={`Risk Score ${Math.round(s.risk.score)} จาก 100 (Fuzzy Logic) แสดงเฉพาะครู`}>
                          {risk.label}
                        </span>
                      ) : (
                        <span className="faint">–</span>
                      )}
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

      <section>
        <button className="stats-toggle" onClick={() => setStatsOpen((v) => !v)} aria-expanded={statsOpen}>
          <BarChart3 size={18} />
          <span className="grow">สถิติห้องเรียน: กลุ่มผู้เรียน (K-Means) และตัวชี้วัดของระบบ</span>
          <span className="small muted">{statsOpen ? "ซ่อน" : "แสดง"}</span>
        </button>
        {statsOpen && <ClassStats liveVersion={liveVersion} onSelect={openStudent} telemetry={data.telemetry} />}
      </section>
    </div>
  );
}

function ClassStats({ liveVersion, onSelect, telemetry: t }: { liveVersion: number; onSelect: (code: string) => void; telemetry: Telemetry }) {
  const clusters = useLoad(
    () => api<{ points: ClusterPoint[]; centroids: Centroid[] }>("teacher", "/api/teacher/clusters"),
    [Math.floor(liveVersion / 25)],
  );
  return (
    <div className="stack fade-in" style={{ marginTop: 14 }}>
      <div className="grid grid-2">
        <Stat
          label="Average Remediation Success"
          value={pct(t.remediation_success)}
          sub={`ซ่อมเสริมผ่าน ${t.remediation_counts.passed} จาก ${t.remediation_counts.started} รอบ`}
        />
        <Stat label="Hint Utility Rate" value={pct(t.hint_utility)} sub={`คำใบ้ที่ตามด้วยการตอบถูก ${t.hint_counts.useful}/${t.hint_counts.shown}`} />
      </div>
      <div className="ov-grid ov-grid-even">
        <Card>
          <CardHead title="กลุ่มพฤติกรรมผู้เรียน (K-Means)" sub="จัดกลุ่มจากเวลาคิดเฉลี่ย สัดส่วนตอบถูก และความยาว Session ชื่อกลุ่มแสดงเฉพาะฝั่งครู" />
          <div className="card-body" style={{ paddingTop: 0 }}>
            {clusters.data?.points.length ? (
              <ClusterScatter points={clusters.data.points} centroids={clusters.data.centroids} onSelect={onSelect} />
            ) : clusters.loading ? (
              <Spinner />
            ) : (
              <Empty>ต้องมีนักเรียนที่ตอบอย่างน้อย 3 ครั้งอย่างน้อย 4 คนก่อนจึงจัดกลุ่มได้</Empty>
            )}
          </div>
        </Card>
        <Card>
          <CardHead title="Drop-off Rate ต่อชุดคำถาม" sub="สัดส่วน Session ที่นักเรียนหยุดเองหรือหายไปก่อนจบชุด" />
          <div className="card-body" style={{ paddingTop: 0 }}>
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
        </Card>
      </div>
    </div>
  );
}
