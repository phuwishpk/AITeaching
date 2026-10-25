import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Check, FileText, Minus } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad, useNow } from "../../lib/hooks";
import { ago } from "../../lib/format";
import GemIcon from "../../components/GemIcon";
import { FRAME_LABEL } from "../../components/AiLog";
import { Badge, Button, Card, CardHead, Empty, Spinner, useToast } from "../../components/ui";
import { STATUS_TEXT, TOOL_LABELS, type GemDetail, type GemSummary } from "../teacher/gemTypes";
import { FeatureList } from "../teacher/GemEditor";
import { useAdmin } from "./AdminApp";
import { GemFlowMap, SpecStepDrawer, type GemFlow } from "./gemFlow";
import NodeInspector from "./NodeInspector";

// Flow ที่ครูออกแบบใน Gem (Q24): ผังตรรกะจริงที่ปรับตามเครื่องมือและ Alert Rule ของ Gem ที่เลือก
// Admin ดูได้อย่างเดียว การแก้ทำที่หน้าครู

interface GemDesign extends Omit<GemDetail, "locked_constraints" | "options"> {
  // สถานการณ์แจ้งเตือนเฉพาะที่ Flow ของ Gem นี้เกิดได้จริง
  flow: GemFlow;
  frames: Record<"role" | "context" | "task" | "constraints", string>;
  students: string[];
  situations: { key: string; label: string; locked: boolean }[];
  live_cap: number;
  version: number | null;
}

const LEVEL_TEXT: Record<string, string> = { urgent: "ด่วน", normal: "ปกติ", silent: "เงียบ" };

export default function AdminGems() {
  const { flow } = useAdmin();
  const [params, setParams] = useSearchParams();
  const gems = useLoad(() => api<GemSummary[]>("admin", "/api/gems"));
  const selected = params.get("gem") ?? gems.data?.[0]?.id ?? null;
  const design = useLoad(() => (selected ? api<GemDesign>("admin", `/api/gems/${selected}/design`) : Promise.resolve(null)), [selected]);
  const [inspect, setInspect] = useState<string | null>(null);
  const now = useNow(30000);
  const toast = useToast();
  const demoGem = useLoad(() => api<{ gem_id: string | null }>("admin", "/api/admin/demo-gem"));
  const [switching, setSwitching] = useState(false);

  // Gem ที่ใช้สาธิตหัวข้อ 2–6 และนักเรียนจำลอง เป็นการตั้งค่าระบบ Admin เลือกได้
  const chooseForDemo = async (gemId: string) => {
    setSwitching(true);
    try {
      const result = await api<{ students: number }>("admin", "/api/admin/demo-gem", { method: "PUT", body: { gem_id: gemId } });
      toast(`ใช้ Gem นี้สาธิตหัวข้อ 2–6 แล้ว สร้างนักเรียนจำลองใหม่ ${result.students} คน`, "success");
      demoGem.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "เปลี่ยน Gem ที่ใช้สาธิตไม่สำเร็จ", "warning");
    } finally {
      setSwitching(false);
    }
  };

  useEffect(() => {
    if (!params.get("gem") && gems.data?.[0]) setParams({ gem: gems.data[0].id }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gems.data]);

  if (!flow || (gems.loading && !gems.data)) return <Spinner />;
  const d = design.data;

  return (
    <div className="page page-wide topic stack stack-lg">
      <header className="stack stack-sm fade-in">
        <p className="eyebrow">สิ่งที่ครูออกแบบ</p>
        <h1 className="title-xl">Flow ที่ครูออกแบบใน Gem</h1>
        <p className="lead">
          ผังไม่ตายตัว: ถ้าคำสั่งของครูกำหนดลำดับการสอน AI จะออกแบบ Flow ของ Gem นั้นเอง (ขั้น เส้น เงื่อนไข และตัวเลข) ไม่อย่างนั้นใช้ผังมาตรฐาน
          ที่ตัดขั้นของเครื่องมือที่ครูปิดออก Admin ดูได้อย่างเดียว ครูตรวจและแก้ได้ที่แท็บ Flow ของ Gem
        </p>
      </header>

      {gems.data?.length === 0 && <Empty>ครูยังไม่ได้สร้าง Gem</Empty>}
      <div className="gem-picker" role="tablist" aria-label="เลือก Gem">
        {gems.data?.map((g) => (
          <button
            key={g.id}
            role="tab"
            aria-selected={g.id === selected}
            className={`gem-picker-item ${g.id === selected ? "on" : ""}`}
            onClick={() => setParams({ gem: g.id }, { replace: true })}
          >
            <GemIcon icon={g.icon} color={g.color} size={32} />
            <span className="stack" style={{ gap: 0, minWidth: 0 }}>
              <span className="small strong gem-picker-name">{g.name}</span>
              <span className="xsmall faint">{STATUS_TEXT[g.status].label}</span>
            </span>
          </button>
        ))}
      </div>

      {design.loading && !d && <Spinner />}
      {d && (
        <>
          <Card className="flow-card">
            <div className="flow-toolbar">
              <span className="row row-sm">
                <GemIcon icon={d.icon} color={d.color} size={28} />
                <span className="strong">{d.name}</span>
                <Badge>เวอร์ชัน {d.version ?? "–"}</Badge>
                {d.bank && <Badge tone="info">คลังรุ่นที่ {d.bank_version}</Badge>}
                {demoGem.data?.gem_id === d.id ? (
                  <Badge tone="success">ใช้สาธิตหัวข้อ 2–6 อยู่</Badge>
                ) : (
                  d.bank && (
                    <Button size="sm" variant="soft" loading={switching} onClick={() => chooseForDemo(d.id)}>
                      ใช้ Gem นี้สาธิตหัวข้อ 2–6
                    </Button>
                  )
                )}
              </span>
              <ul className="flow-legend xsmall muted">
                {d.flow.custom ? <li>↻ วนที่ขั้นเดิม · เส้นประด้านล่างคือกลไกที่ล็อกไว้</li> : (
                  <>
                    <li>🔔 แจ้งครู</li>
                    <li>✋ หยุดรอครูอนุมัติ</li>
                  </>
                )}
                <li className="strong">กดกล่องเพื่อดูรายละเอียด</li>
              </ul>
            </div>
            {!d.flow.custom && (
              <p className="small callout callout-warning">
                Gem นี้ยังไม่มี Flow ที่ออกแบบจากคำสั่ง นักเรียนยังเรียนไม่ได้ ผังด้านล่างเป็นแม่แบบอ้างอิงเท่านั้น
              </p>
            )}
            <GemFlowMap
              flow={d.flow}
              allNodes={flow.nodes}
              positions={flow.positions.filter((p) => d.students.includes(p.code))}
              onSelectNode={setInspect}
            />
          </Card>

          <div className="grid grid-2 admin-gem-grid">
            <Card>
              <CardHead title="คำสั่งของครู → prompt 4 กรอบ" sub="Role & Persona มาจากคำสั่งของครู Constraints ล็อกไว้ อีกสองกรอบเติมตอนสอน" />
              <div className="card-body frames">
                {(["role", "context", "task", "constraints"] as const).map((key) => (
                  <div key={key} className="frame">
                    <span className="frame-label">{FRAME_LABEL[key]}</span>
                    <pre className="code-block">{d.frames[key]}</pre>
                  </div>
                ))}
              </div>
            </Card>

            <div className="stack">
              <Card>
                <CardHead title="เครื่องมือของ Gem" sub="ฟีเจอร์การสอนมาจาก Flow ที่ AI ออกแบบตามคำสั่งของครู" />
                <div className="card-body stack stack-sm">
                  <ul className="tool-state">
                    <li className={d.tools?.chat !== false ? "" : "is-off"}>
                      {d.tools?.chat !== false ? <Check size={15} /> : <Minus size={15} />}
                      <span className="small">{TOOL_LABELS.chat.label}</span>
                      {d.tools?.chat === false && <span className="xsmall faint">ครูปิดไว้</span>}
                    </li>
                  </ul>
                  <FeatureList features={d.features} />
                </div>
                {d.tools?.chat !== false && d.starter_prompts.length > 0 && (
                  <div className="card-body pill-list" style={{ paddingTop: 0 }}>
                    {d.starter_prompts.map((p) => (
                      <span key={p} className="gem-starter gem-starter-view">
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </Card>

              <Card>
                <CardHead title="การแจ้งเตือนครู" sub="ระดับและสิ่งที่ระบบทำเมื่อเกิดแต่ละสถานการณ์" />
                <div className="table-wrap">
                  <table className="table">
                    <tbody>
                      {d.situations.map((s) => {
                        const rule = d.alert_rules[s.key];
                        return (
                          <tr key={s.key} className={rule?.enabled ? "" : "faint"}>
                            <td className="small">{s.label}</td>
                            <td className="small nowrap">{rule?.enabled ? LEVEL_TEXT[rule.level] : "ปิด"}</td>
                            <td className="small nowrap">{rule?.enabled ? (rule.mode === "pause" ? "✋ หยุดรอครู" : "🔔 แจ้งอย่างเดียว") : "–"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            <Card>
              <CardHead title={d.bank ? `คลังโจทย์รุ่นที่ ${d.bank_version}` : "คลังโจทย์"} sub={`AI สร้างจากคำสั่งและไฟล์ความรู้ สร้างสดเพิ่มได้ ${d.live_cap} ข้อต่อ Session`} />
              <div className="card-body stack">
                {d.bank ? (
                  <>
                    <div className="gem-stats">
                      {[
                        [d.bank.stats.main, "โจทย์หลัก"],
                        [d.bank.stats.isomorphic, "ข้อคู่ขนาน"],
                        [d.bank.stats.remedial, "ทบทวนพื้นฐาน"],
                        [d.bank.stats.challenge, "โจทย์ท้าทาย"],
                        [d.bank.stats.flagged, "เฉลยติดธง"],
                      ].map(([value, label]) => (
                        <div key={label} className="gem-stat">
                          <span className="gem-stat-value num">{value}</span>
                          <span className="xsmall muted">{label}</span>
                        </div>
                      ))}
                    </div>
                    <ol className="gem-map">
                      {d.bank.concepts
                        .filter((c) => c.name !== d.bank!.target)
                        .map((c) => (
                          <li key={c.id}>{c.name}</li>
                        ))}
                      <li className="is-target">{d.bank.target}</li>
                    </ol>
                  </>
                ) : (
                  <Empty>ยังไม่ได้สร้างคลังโจทย์</Empty>
                )}
                <div className="stack stack-sm">
                  <span className="small strong">Knowledge File ({d.files.length})</span>
                  {d.files.length === 0 && <span className="small faint">ไม่มีไฟล์ AI ใช้คำสั่งของครูอย่างเดียว</span>}
                  {d.files.map((f) => (
                    <span key={f.id} className="row row-sm small">
                      <FileText size={14} />
                      {f.filename}
                      <span className="xsmall faint">{f.chunks} ย่อหน้า</span>
                    </span>
                  ))}
                </div>
              </div>
            </Card>

            <div className="stack">
              <Card>
                <CardHead title={`ประวัติเวอร์ชัน (${d.versions.length})`} />
                <ol className="card-body gem-versions" style={{ paddingTop: 0 }}>
                  {d.versions.map((v) => (
                    <li key={v.n}>
                      <span className="gem-version-n num">{v.n}</span>
                      <span className="stack grow" style={{ gap: 1 }}>
                        <span className="small">{v.note}</span>
                        <span className="xsmall faint">
                          {v.actor === "teacher" ? "ครู" : v.actor} · {ago(v.ts, now)}
                          {v.bank_version ? ` · คลังรุ่นที่ ${v.bank_version}` : ""}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              </Card>
              <Card>
                <CardHead title={`นักเรียนที่เรียน Gem นี้ (${d.students.length})`} sub="ดูไทม์ไลน์ของครูและนักเรียนรายคนได้ที่หน้ากิจกรรมสด โหมดรายคน" />
                <div className="card-body pill-list" style={{ paddingTop: 0 }}>
                  {d.students.map((code) => (
                    <span key={code} className="mono small gem-student-code">
                      {code}
                    </span>
                  ))}
                  {!d.students.length && <span className="small faint">ยังไม่มี</span>}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
      {d?.flow.custom ? (
        <SpecStepDrawer flow={d.flow} nodeId={inspect} onClose={() => setInspect(null)} />
      ) : (
        <NodeInspector nodeId={inspect} onClose={() => setInspect(null)} onNavigate={setInspect} />
      )}
    </div>
  );
}
