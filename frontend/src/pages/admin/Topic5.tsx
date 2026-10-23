import { useEffect, useMemo, useState } from "react";
import { ExternalLink, FastForward, Pause, Play, RotateCcw, Shuffle, Timer } from "lucide-react";
import { api, setAuth } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import FlowMap from "../../components/FlowMap";
import { Badge, Button, Card, CardHead, Empty, Spinner, useToast } from "../../components/ui";
import { TopicHeader, useAdmin, type ScenarioEvent } from "./AdminApp";
import { Section } from "./shared";

interface Scenario {
  id: string;
  title: string;
  description: string;
  code: string;
  steps: number;
}

export default function Topic5() {
  const toast = useToast();
  const { flow, scenarios: events } = useAdmin();
  const list = useLoad(() => api<Scenario[]>("admin", "/api/admin/scenarios"));
  const settings = useLoad(() => api<any>("admin", "/api/admin/settings"));
  const [focus, setFocus] = useState<string>("hints");
  const [auto, setAuto] = useState(false);
  const [ticking, setTicking] = useState(false);

  const scenario = list.data?.find((s) => s.id === focus);
  const runs = useMemo(() => {
    const out: Record<string, ScenarioEvent[]> = {};
    for (const e of events) (out[e.name] ??= []).push(e);
    return out;
  }, [events]);

  // เดินนักเรียนจำลองอัตโนมัติ ให้ผังในหน้านี้และแท็บ 3 เคลื่อนไหว
  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => {
      api("admin", "/api/admin/cohort/tick", { body: { students: 6 } }).catch(() => setAuto(false));
    }, 2500);
    return () => clearInterval(id);
  }, [auto]);

  const run = async (s: Scenario) => {
    setFocus(s.id);
    try {
      await api("admin", `/api/admin/scenario/${s.id}`, { method: "POST" });
    } catch (err) {
      toast(err instanceof Error ? err.message : "เริ่มสถานการณ์ไม่สำเร็จ", "warning");
    }
  };

  const openStudent = async (code: string) => {
    try {
      const result = await api<{ token: string; code: string }>(null, "/api/auth/student", { body: { code } });
      setAuth("student", { token: result.token, code: result.code });
      const setId = flow?.positions.find((p) => p.code === code)?.set_id || "QS-1";
      window.open(`/student/${setId}`, "_blank", "noopener");
    } catch (err) {
      toast(err instanceof Error ? err.message : "เปิดหน้านักเรียนไม่สำเร็จ", "warning");
    }
  };

  const tick = async () => {
    setTicking(true);
    try {
      const result = await api<{ moved: number }>("admin", "/api/admin/cohort/tick", { body: { students: 10 } });
      toast(`ขยับนักเรียนจำลอง ${result.moved} คน`);
    } finally {
      setTicking(false);
    }
  };

  const reset = async () => {
    const result = await api<{ students: number }>("admin", "/api/admin/cohort/reset", { method: "POST" });
    toast(`สร้างห้องเรียนจำลองใหม่ ${result.students} คน`, "success");
  };

  const demo = settings.data?.demo;
  const toggleDemo = async () => {
    await api("admin", "/api/admin/settings", { method: "PUT", body: { demo: { enabled: !demo?.enabled } } });
    settings.reload();
  };

  if (!list.data || !flow) return <Spinner />;
  const focusEvents = runs[focus] ?? [];
  const latest = focusEvents[0];
  const code = scenario?.code ?? "DEMO-1";

  return (
    <div className="page page-wide topic stack stack-lg">
      <TopicHeader id="5" lead="กดเริ่มสถานการณ์ แล้วดูนักเรียนสาธิตเดินผ่านผังตรรกะทีละก้าว เปิดหน้านักเรียนในอีกแท็บเพื่อให้เห็นทั้งสองฝั่งพร้อมกัน">
        <div className="row">
          <Button variant={demo?.enabled ? "soft" : "ghost"} size="sm" icon={<Timer size={16} />} onClick={toggleDemo} aria-pressed={!!demo?.enabled}>
            Demo Mode {demo?.enabled ? `เปิด (เวลา × ${demo.time_scale})` : "ปิด"}
          </Button>
        </div>
      </TopicHeader>

      <div className="grid grid-3">
        {list.data.map((s, index) => {
          const own = runs[s.id] ?? [];
          const last = own[0];
          const running = last && last.step < last.total;
          return (
            <Card key={s.id} className={`card-pad stack scenario-card ${focus === s.id ? "is-focus" : ""}`} onClick={() => setFocus(s.id)}>
              <div className="spread">
                <span className="eyebrow">สถานการณ์ที่ {index + 1}</span>
                <span className="mono xsmall faint">{s.code}</span>
              </div>
              <h3 className="subtitle">{s.title}</h3>
              <p className="small muted grow">{s.description}</p>
              {last && (
                <div className="stack stack-sm">
                  <div className="meter">
                    <span style={{ width: `${(last.step / last.total) * 100}%`, background: "var(--accent)" }} />
                  </div>
                  <span className="xsmall faint">
                    ก้าวที่ {last.step} จาก {last.total} · {flow.labels[last.position] ?? last.position}
                  </span>
                </div>
              )}
              <div className="row" style={{ justifyContent: "flex-end" }}>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<ExternalLink size={15} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    openStudent(s.code);
                  }}
                  title="เปิดหน้านักเรียนของรหัสนี้ในแท็บใหม่ (แทนที่การเข้าระบบนักเรียนในเบราว์เซอร์นี้)"
                >
                  หน้านักเรียน
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  icon={running ? <Pause size={15} /> : last ? <RotateCcw size={15} /> : <Play size={15} />}
                  disabled={!!running}
                  onClick={(e) => {
                    e.stopPropagation();
                    run(s);
                  }}
                >
                  {running ? "กำลังเล่น" : last ? "เล่นอีกครั้ง" : "เริ่มสาธิต"}
                </Button>
              </div>
            </Card>
          );
        })}
      </div>

      <Card className="flow-card">
        <CardHead
          title={`ติดตาม ${code}: ${scenario?.title ?? ""}`}
          sub="ผังเดียวกับแท็บ 3 แต่แสดงเฉพาะนักเรียนสาธิตคนนี้ เส้นสีเข้มคือเส้นทางของก้าวล่าสุด"
          actions={latest && <Badge tone="accent">{flow.labels[latest.position] ?? latest.position}</Badge>}
        />
        <FlowMap
          nodes={flow.nodes}
          edges={flow.edges}
          positions={flow.positions.filter((p) => p.code === code)}
          selectedStudent={code}
          selectedNode={latest?.position}
        />
      </Card>

      <div className="grid grid-2">
        <Card>
          <CardHead title="บันทึกทีละก้าว" sub="การกระทำของนักเรียนสาธิต และกฎที่ engine ใช้ตัดสินในก้าวนั้น" />
          {focusEvents.length === 0 ? (
            <Empty>กดเริ่มสาธิตเพื่อดูบันทึก</Empty>
          ) : (
            <ol className="timeline" style={{ padding: "0 22px 22px" }}>
              {[...focusEvents].reverse().map((e, i) => (
                <li key={i}>
                  <span className="timeline-time num">
                    {e.step}/{e.total}
                  </span>
                  <div className="stack" style={{ gap: 2 }}>
                    <span className="small strong">{e.action}</span>
                    {e.rules.map((r, j) => (
                      <span key={j} className="small muted">
                        {r}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
        <Section title="ห้องเรียนจำลอง (Simulated Cohort)" sub="นักเรียนจำลอง 32 คน 4 บุคลิก ทำให้ K-Means และผังตรรกะมีข้อมูลพอจะเห็นภาพ โดยไม่ต้องใช้ข้อมูลนักเรียนจริง">
          <Card className="card-pad stack">
            <div className="row">
              <Button icon={<FastForward size={16} />} loading={ticking} onClick={tick}>
                ขยับหนึ่งก้าว
              </Button>
              <Button variant={auto ? "soft" : "secondary"} icon={auto ? <Pause size={16} /> : <Play size={16} />} onClick={() => setAuto((v) => !v)} aria-pressed={auto}>
                {auto ? "หยุดเดินอัตโนมัติ" : "เดินอัตโนมัติ"}
              </Button>
              <Button variant="ghost" icon={<Shuffle size={16} />} onClick={reset}>
                สุ่มห้องใหม่
              </Button>
            </div>
            <p className="xsmall muted">
              นักเรียนจำลองไม่เรียก AI Provider และการแจ้งเตือนของนักเรียนจำลองไม่ขึ้นในหน้าครู ใช้ประกอบการสาธิตเท่านั้น ชิปสีเทาในผังคือนักเรียนจำลอง
            </p>
          </Card>
        </Section>
      </div>
    </div>
  );
}
