import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowLeft, ArrowRight, Database, FileText, Lightbulb, ListOrdered, RotateCcw, Route, Save, SlidersHorizontal, Timer, UsersRound } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { num } from "../../lib/format";
import PrincipleCard, { type Principle } from "../../components/PrincipleCard";
import { Badge, Button, Drawer, Empty, Spinner, useToast } from "../../components/ui";

// แผงข้อมูลของกล่องหนึ่งในผังตรรกะ: คืออะไร ทำงานอย่างไรทีละขั้น มาจากไหนไปไหน ใช้ข้อมูลอะไร และปรับค่าอะไรได้ (ปรับได้ทันทีจากแผงนี้)

interface NodeParam {
  key: string;
  label: string;
  unit: string;
  value: number;
  default: number;
  changed: boolean;
  scaled: boolean;
  effective: number | null;
  effect: string;
  min: number;
  max: number;
  step: number;
}

interface FlowRoute {
  edge: string;
  node: string;
  label: string;
  when: string;
  lane: string | null;
}

interface NodeDetail {
  id: string;
  label: string;
  kind: "position" | "gate" | "step" | "event";
  lane_info: { id: string; name: string; color: string };
  card: Principle | null;
  steps: string[];
  example: string | null;
  incoming: FlowRoute[];
  outgoing: FlowRoute[];
  uses: string[];
  params: NodeParam[];
  content: string | null;
  rules: { id: string; title: string }[];
  students: { code: string; kind: string }[];
  compare: { columns: string[]; rows: string[][] } | null;
}

const KIND: Record<NodeDetail["kind"], { label: string; text: string }> = {
  position: { label: "ตำแหน่ง", text: "นักเรียนอยู่ที่ขั้นนี้ได้ ชิปบนกล่องคือคนที่อยู่ตรงนี้ตอนนี้" },
  gate: { label: "ด่านตัดสินใจ", text: "ระบบเลือกทางแยกจากเงื่อนไข นักเรียนผ่านไปทันที ไม่ได้หยุดอยู่ตรงนี้" },
  step: { label: "ขั้นประมวลผล", text: "ระบบคำนวณหรือปรับข้อมูล แล้วส่งต่อขั้นถัดไปทันที" },
  event: { label: "เหตุการณ์", text: "จุดที่การกระทำของนักเรียนเข้ามาในระบบ" },
};

export default function NodeInspector({
  nodeId,
  onClose,
  version,
  onNavigate,
  onOpenLane,
}: {
  nodeId: string | null;
  onClose: () => void;
  version?: number;
  // กดชื่อกล่องในส่วน "มาจากไหน ไปต่อที่ไหน" เพื่อเปิดกล่องนั้นแทน
  onNavigate?: (id: string) => void;
  onOpenLane?: (lane: string) => void;
}) {
  const toast = useToast();
  const node = useLoad(() => (nodeId ? api<NodeDetail>("admin", `/api/admin/flow/nodes/${nodeId}`) : Promise.resolve(null)), [nodeId, version]);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    document.querySelector(".drawer")?.scrollTo({ top: 0 });
  }, [nodeId]);

  useEffect(() => {
    if (node.data) setDraft(Object.fromEntries(node.data.params.map((p) => [p.key, String(p.value)])));
  }, [node.data]);

  const data = node.data;
  const changed = data ? data.params.filter((p) => draft[p.key] !== undefined && Number(draft[p.key]) !== p.value) : [];
  const outOfRange = (p: NodeParam, raw: string) => raw === "" || Number.isNaN(Number(raw)) || Number(raw) < p.min || Number(raw) > p.max;
  const hasInvalid = changed.some((p) => outOfRange(p, draft[p.key]));

  const save = async (values: Record<string, number>) => {
    setSaving(true);
    try {
      await api("admin", "/api/admin/settings", { method: "PUT", body: { params: values } });
      toast("บันทึกแล้ว มีผลกับการตัดสินครั้งถัดไปทันที", "success");
      node.reload();
    } catch (err) {
      toast(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ", "warning");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      open={!!nodeId}
      onClose={onClose}
      title={
        data ? (
          <div className="stack" style={{ gap: 2 }}>
            <span className="row row-sm">
              <Badge tone={data.kind === "gate" ? "info" : data.kind === "position" ? "accent" : "neutral"}>{KIND[data.kind].label}</Badge>
              <LaneTag lane={data.lane_info} onOpen={onOpenLane} />
              <span className="mono xsmall faint">{data.id}</span>
            </span>
            <span className="subtitle">{data.label}</span>
          </div>
        ) : (
          "กำลังโหลด"
        )
      }
    >
      {node.loading && !data && <Spinner />}
      {node.error && <Empty>{node.error}</Empty>}
      {data && (
        <div className="stack stack-lg inspector">
          <section className="stack stack-sm">
            <h4 className="inspector-title">คืออะไร ทำหน้าที่อะไร</h4>
            <p className="small muted">{KIND[data.kind].text}</p>
            {data.card && <PrincipleCard card={data.card} compact />}
          </section>

          {data.steps.length > 0 && (
            <section className="stack stack-sm">
              <h4 className="inspector-title">
                <ListOrdered size={16} />
                ระบบทำอะไรทีละขั้น
              </h4>
              <ol className="step-list">
                {data.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </section>
          )}

          {data.example && (
            <section className="stack stack-sm">
              <h4 className="inspector-title">
                <Lightbulb size={16} />
                ตัวอย่างจากโจทย์ 2x + 3 = 11
              </h4>
              <p className="example-box small">{data.example}</p>
            </section>
          )}

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <Route size={16} />
              มาจากไหน ไปต่อที่ไหน
            </h4>
            <div className="route-grid">
              <RouteList title="เข้ามาจาก" icon={<ArrowLeft size={14} />} routes={data.incoming} onNavigate={onNavigate} empty="จุดเริ่มต้น" />
              <RouteList
                title="ไปต่อเมื่อ"
                icon={<ArrowRight size={14} />}
                routes={data.outgoing}
                onNavigate={onNavigate}
                empty="ปลายทาง นักเรียนจบที่นี่"
              />
            </div>
          </section>

          {data.compare && (
            <section className="stack stack-sm">
              <h4 className="inspector-title">ต่างจากอีกกล่องอย่างไร</h4>
              <div className="table-wrap card">
                <table className="table compare-table">
                  <thead>
                    <tr>
                      <th />
                      {data.compare.columns.map((c) => (
                        <th key={c} className={c === data.label ? "is-current" : ""}>
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.compare.rows.map(([label, ...cells]) => (
                      <tr key={label}>
                        <td className="small strong nowrap">{label}</td>
                        {cells.map((cell, i) => (
                          <td key={i} className={`small ${data.compare!.columns[i] === data.label ? "is-current" : "muted"}`}>
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <Database size={16} />
              ใช้ข้อมูลอะไรตัดสิน
            </h4>
            <ul className="pill-list uses-list">
              {data.uses.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          </section>

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <SlidersHorizontal size={16} />
              ปรับแต่งได้
            </h4>
            {data.params.length === 0 ? (
              <p className="small muted">ขั้นนี้ไม่มีค่าตัวเลขให้ปรับ การตัดสินเป็นไปตามกฎตายตัว{data.content ? " ส่วนเนื้อหาแก้ได้ตามด้านล่าง" : ""}</p>
            ) : (
              <div className="stack stack-sm">
                {data.params.map((p) => {
                  const value = draft[p.key] ?? String(p.value);
                  const dirty = Number(value) !== p.value;
                  const invalid = outOfRange(p, value);
                  return (
                    <div key={p.key} className={`param-edit ${dirty ? "is-dirty" : ""}`}>
                      <div className="spread">
                        <label className="small strong" htmlFor={`param-${p.key}`}>
                          {p.label}
                        </label>
                        {p.changed && (
                          <Button
                            size="sm"
                            variant="ghost"
                            icon={<RotateCcw size={14} />}
                            disabled={saving}
                            onClick={() => save({ [p.key]: p.default })}
                            title="คืนค่าเริ่มต้น"
                          >
                            ค่าเริ่มต้น {num(p.default, 2)}
                          </Button>
                        )}
                      </div>
                      <div className="param-input">
                        <input
                          id={`param-${p.key}`}
                          type="range"
                          min={p.min}
                          max={p.max}
                          step={p.step}
                          value={invalid ? p.value : Number(value)}
                          onChange={(e) => setDraft({ ...draft, [p.key]: e.target.value })}
                          aria-label={p.label}
                        />
                        <input
                          className="input num"
                          type="number"
                          min={p.min}
                          max={p.max}
                          step={p.step}
                          value={value}
                          aria-invalid={invalid}
                          onChange={(e) => setDraft({ ...draft, [p.key]: e.target.value })}
                        />
                        <span className="small muted">{p.unit}</span>
                      </div>
                      {invalid && <p className="xsmall" style={{ color: "var(--warning)" }}>ค่าต้องอยู่ระหว่าง {num(p.min, 2)} ถึง {num(p.max, 2)}</p>}
                      <p className="xsmall muted">{p.effect}</p>
                      <p className="xsmall faint">
                        ช่วงที่ตั้งได้ {num(p.min, 2)}–{num(p.max, 2)}
                        {p.effective != null && (
                          <span className="row row-sm" style={{ display: "inline-flex", marginLeft: 8 }}>
                            <Timer size={12} />
                            ตอนสาธิตใช้จริง {num(p.effective, 1)}
                          </span>
                        )}
                      </p>
                    </div>
                  );
                })}
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <Button
                    variant="ghost"
                    disabled={!changed.length || saving}
                    onClick={() => setDraft(Object.fromEntries(data.params.map((p) => [p.key, String(p.value)])))}
                  >
                    ยกเลิกการแก้
                  </Button>
                  <Button
                    variant="primary"
                    icon={<Save size={16} />}
                    loading={saving}
                    disabled={!changed.length || hasInvalid}
                    onClick={() => save(Object.fromEntries(changed.map((p) => [p.key, Number(draft[p.key])])))}
                  >
                    บันทึก {changed.length ? `${changed.length} ค่า` : ""}
                  </Button>
                </div>
              </div>
            )}
            {data.content && (
              <div className="callout callout-info">
                <FileText size={16} />
                <span className="small">{data.content}</span>
              </div>
            )}
          </section>

          {data.rules.length > 0 && (
            <section className="stack stack-sm">
              <h4 className="inspector-title">กฎที่เกี่ยวข้อง</h4>
              <div className="pill-list">
                {data.rules.map((r) => (
                  <Link key={r.id} to={`/admin/rules#${r.id}`} className="rule-pill">
                    <span className="mono">{r.id}</span>
                    {r.title}
                  </Link>
                ))}
              </div>
            </section>
          )}

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <UsersRound size={16} />
              นักเรียนที่อยู่ตรงนี้ตอนนี้ ({data.students.length})
            </h4>
            {data.students.length ? (
              <div className="pill-list">
                {data.students.map((s) => (
                  <span key={s.code} className={`chip-toggle chip-kind-${s.kind}`}>
                    <span className="chip-dot" />
                    {s.code}
                  </span>
                ))}
              </div>
            ) : (
              <p className="small faint">{data.kind === "position" ? "ไม่มี" : "ขั้นนี้เป็นทางผ่าน นักเรียนไม่ได้หยุดอยู่ตรงนี้"}</p>
            )}
          </section>
        </div>
      )}
    </Drawer>
  );
}

function LaneTag({ lane, onOpen }: { lane: { id: string; name: string; color: string }; onOpen?: (lane: string) => void }) {
  const content = (
    <>
      <span className="lane-dot" style={{ background: lane.color }} />
      {lane.name}
    </>
  );
  return onOpen ? (
    <button type="button" className="lane-tag" onClick={() => onOpen(lane.id)} title="ดูคำอธิบายของกลุ่มนี้">
      {content}
    </button>
  ) : (
    <span className="lane-tag">{content}</span>
  );
}

function RouteList({
  title,
  icon,
  routes,
  onNavigate,
  empty,
}: {
  title: string;
  icon: ReactNode;
  routes: FlowRoute[];
  onNavigate?: (id: string) => void;
  empty: string;
}) {
  return (
    <div className="stack stack-sm">
      <span className="xsmall strong muted row row-sm">
        {icon}
        {title}
      </span>
      {routes.length ? (
        <ul className="route-list">
          {routes.map((r) => (
            <li key={r.edge}>
              {r.when && <span className="route-when">{r.when}</span>}
              {onNavigate ? (
                <button type="button" className="route-node" onClick={() => onNavigate(r.node)}>
                  {r.label}
                </button>
              ) : (
                <span className="route-node">{r.label}</span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="small faint">{empty}</p>
      )}
    </div>
  );
}
