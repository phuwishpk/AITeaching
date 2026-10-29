import { useEffect, useState } from "react";
import { CircleCheck, KeyRound, PlugZap, Save, Trash2, TriangleAlert } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { num } from "../../lib/format";
import { Badge, Button, Card, CardHead, Field, Segmented, Spinner, useToast } from "../../components/ui";

interface KeyInfo {
  configured: boolean;
  source: "env" | "file" | "none";
  last4: string | null;
}

interface SettingsData {
  ai: { active: "claude" | "gemini" | "offline"; order: string[]; claude_model: string; gemini_model: string; gemini_design_model: string };
  // โมเดล Gemini ที่ใช้จริงล่าสุดแยกตามงาน และเหตุผลถ้าไม่ใช่ตัวที่ตั้งไว้
  usage: Partial<Record<"chat" | "design", { model: string; ts: number; fallback: string | null }>>;
  keys: Record<"claude" | "gemini", KeyInfo>;
  params: Record<string, number>;
  param_labels: Record<string, string>;
  demo: { enabled: boolean; time_scale: number };
  // นักเรียนจำลองของบัญชีนี้: ปิดแล้วลบทิ้งและระบบไม่สร้างให้อีก
  cohort: { enabled: boolean; students: number };
  // บัญชีที่ค่าในหน้านี้เป็นของ (null = เซิร์ฟเวอร์ยังไม่มีบัญชีผู้ใช้ ค่าใช้ร่วมกันทั้งระบบ)
  account: { username: string; name: string } | null;
}

// Gemini เป็นผู้ให้บริการหลัก (Q26) Claude เป็นตัวสำรองที่พับไว้
const PROVIDERS = [
  { id: "gemini" as const, name: "Gemini (Google)", env: "GEMINI_API_KEY", placeholder: "AIza…", console: "aistudio.google.com" },
  { id: "claude" as const, name: "Claude (Anthropic)", env: "ANTHROPIC_API_KEY", placeholder: "sk-ant-…", console: "console.anthropic.com" },
];

// กลุ่มพารามิเตอร์ตามขั้นในผัง ให้ปรับได้โดยรู้ว่ากระทบส่วนไหน
const PARAM_GROUPS = [
  { title: "ด่าน 2 และ Anti-Gaming", keys: ["rapid_guess_threshold", "rapid_guess_lock", "hint_unlock_wait", "hint_abuse_presses", "hint_abuse_window", "hint_abuse_cooldown"] },
  { title: "ด่าน 3 และบันไดคำใบ้", keys: ["deliberate_delay", "impasse_threshold", "iso_attempts", "remedial_pass_streak", "remedial_max_rounds"] },
  { title: "Mastery และเส้นทาง", keys: ["mastery_window", "fast_track_mastery", "standard_mastery", "slip_mastery", "finish_mastery", "finish_min_items", "max_items"] },
  { title: "Data Cleaning และการดูแล", keys: ["rt_cap", "duplicate_window", "idle_timeout", "undo_window", "circuit_breaker_break", "burnout_idle", "burnout_rapid_streak", "burnout_risk"] },
];

export default function Settings() {
  const toast = useToast();
  const settings = useLoad(() => api<SettingsData>("admin", "/api/admin/settings"));
  const [params, setParams] = useState<Record<string, number>>({});
  const [paramsDirty, setParamsDirty] = useState(false);

  useEffect(() => {
    if (settings.data) {
      setParams(settings.data.params);
      setParamsDirty(false);
    }
  }, [settings.data]);

  if (!settings.data) return <Spinner />;
  const s = settings.data;

  const saveAi = async (patch: Partial<SettingsData["ai"]>) => {
    const result = await api<SettingsData>("admin", "/api/admin/settings", { method: "PUT", body: { ai: patch } });
    settings.setData(result);
    toast("บันทึกการตั้งค่า AI แล้ว", "success");
  };

  const saveParams = async () => {
    const result = await api<SettingsData>("admin", "/api/admin/settings", { method: "PUT", body: { params } });
    settings.setData(result);
    toast("บันทึกพารามิเตอร์แล้ว มีผลกับการตัดสินครั้งถัดไปทันที", "success");
  };

  const saveDemo = async (patch: Partial<SettingsData["demo"]>) => {
    const result = await api<SettingsData>("admin", "/api/admin/settings", { method: "PUT", body: { demo: patch } });
    settings.setData(result);
  };

  const saveCohort = async (enabled: boolean) => {
    const result = await api<SettingsData>("admin", "/api/admin/settings", { method: "PUT", body: { cohort: { enabled } } });
    settings.setData(result);
    toast(enabled ? `เปิดนักเรียนจำลองแล้ว (${result.cohort.students} คน)` : "ลบนักเรียนจำลองทั้งหมดแล้ว ระบบจะไม่สร้างให้อีก", "success");
  };

  return (
    <div className="page page-narrow stack stack-lg">
      <header className="stack stack-sm fade-in">
        <p className="eyebrow">ตั้งค่า</p>
        <h1 className="title-xl">ผู้ให้บริการ AI และพารามิเตอร์ของระบบ</h1>
        <p className="lead">
          ใส่ Gemini API key ที่นี่ ครูต้องใช้ AI สร้างคลังโจทย์ของ Gem ครูผู้ช่วยตอบแชต และสร้างโจทย์สด Claude เป็นตัวสำรองเมื่อ Gemini ล่มหรือติดโควตา
        </p>
        {s.account && (
          <p className="small muted">
            ทุกค่าในหน้านี้ (API key, โมเดล, พารามิเตอร์, Demo Mode และนักเรียนจำลอง) เป็นของบัญชี <strong>{s.account.name}</strong> เท่านั้น
            ใช้กับ Gem และนักเรียนของบัญชีนี้ บัญชีอื่นไม่เห็นและไม่ได้รับผลกระทบ
          </p>
        )}
      </header>

      <Card>
        <CardHead title="ผู้ให้บริการที่ใช้" sub="ถ้าตัวแรกเรียกไม่สำเร็จ ระบบลองตัวถัดไป ถ้าไม่สำเร็จทั้งหมดจะใช้คำใบ้ต้นฉบับของครู" />
        <div className="card-body stack" style={{ paddingTop: 0 }}>
          <Segmented
            label="ผู้ให้บริการหลัก"
            value={s.ai.active}
            onChange={(active) => saveAi({ active, order: active === "offline" ? s.ai.order : [active, ...s.ai.order.filter((p) => p !== active)] })}
            options={[
              { id: "gemini", label: "Gemini" },
              { id: "claude", label: "Claude" },
              { id: "offline", label: "Offline (ไม่เรียก AI)" },
            ]}
          />
          <p className="xsmall muted">
            ลำดับตอนนี้: {s.ai.active === "offline" ? "ไม่เรียก AI" : s.ai.order.join(" → ")} → คำใบ้ต้นฉบับของครู
          </p>
        </div>
      </Card>

      <ProviderCard
        provider={PROVIDERS[0]}
        info={s.keys.gemini}
        model={s.ai.gemini_model}
        onModel={(model) => saveAi({ gemini_model: model })}
        modelLabel="โมเดลสำหรับแชตและคำใบ้ (ตอนนักเรียนเรียน เรียกบ่อย ควรเร็ว)"
        second={{
          label: "โมเดลสำหรับสร้างบทเรียน (อ่านเอกสาร สร้างคลังโจทย์ ออกแบบและตรวจ Flow เรียกไม่กี่ครั้ง ใช้ตัวฉลาดได้)",
          model: s.ai.gemini_design_model,
          onModel: (model) => saveAi({ gemini_design_model: model }),
        }}
        usage={s.usage}
        onKeyChange={settings.reload}
      />

      <details className="provider-backup" open={s.ai.active === "claude" || undefined}>
        <summary>
          ตัวสำรอง: Claude (Anthropic)
          <span className="xsmall muted">{s.keys.claude?.configured ? "ใส่ key แล้ว" : "ยังไม่ได้ใส่ key"}</span>
        </summary>
        <ProviderCard
          provider={PROVIDERS[1]}
          info={s.keys.claude}
          model={s.ai.claude_model}
          onModel={(model) => saveAi({ claude_model: model })}
          onKeyChange={settings.reload}
        />
      </details>

      <Card>
        <CardHead title="Demo Mode" sub="ย่อเวลาที่ต้องรอ (Deliberate Delay, ล็อก, พักสายตา, Idle) ให้สาธิตในเวลาสั้นได้ กฎเหมือนเดิมทุกอย่าง" />
        <div className="card-body row" style={{ paddingTop: 0 }}>
          <label className="check">
            <input type="checkbox" checked={s.demo.enabled} onChange={(e) => saveDemo({ enabled: e.target.checked })} />
            เปิด Demo Mode
          </label>
          <Field label={`คูณเวลา × ${s.demo.time_scale}`}>
            <input
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              value={s.demo.time_scale}
              disabled={!s.demo.enabled}
              onChange={(e) => saveDemo({ time_scale: Number(e.target.value) })}
            />
          </Field>
          <span className="xsmall muted">เช่น × 0.2 ทำให้ Deliberate Delay 15 วินาทีเหลือ {num(15 * s.demo.time_scale, 0)} วินาที</span>
        </div>
      </Card>

      <Card>
        <CardHead
          title="นักเรียนจำลอง (Simulated Cohort)"
          sub="นักเรียนสมมติที่ระบบสร้างให้ ใช้ทำสถิติห้องและจัดกลุ่ม K-Means ตอนสาธิต ปิดแล้วลบทิ้งทั้งหมดพร้อมข้อมูล และระบบจะไม่สร้างให้อีก นักเรียนจริงไม่กระทบ"
        />
        <div className="card-body row" style={{ paddingTop: 0 }}>
          <label className="check">
            <input type="checkbox" checked={s.cohort.enabled} onChange={(e) => saveCohort(e.target.checked)} />
            ใช้นักเรียนจำลอง
          </label>
          <span className="xsmall muted">ตอนนี้มี {s.cohort.students} คน</span>
        </div>
      </Card>

      <Card>
        <CardHead
          title="พารามิเตอร์ของกลไก"
          sub="ค่าเริ่มต้นตามที่ออกแบบไว้ใน docs/decisions.md ปรับได้เพื่อทดลอง"
          actions={
            <Button variant="primary" size="sm" icon={<Save size={15} />} disabled={!paramsDirty} onClick={saveParams}>
              บันทึก
            </Button>
          }
        />
        <div className="card-body stack" style={{ paddingTop: 0 }}>
          {PARAM_GROUPS.map((group) => (
            <fieldset key={group.title} className="fieldset">
              <legend>{group.title}</legend>
              <div className="param-grid">
                {group.keys
                  .filter((key) => key in params)
                  .map((key) => (
                    <Field key={key} label={s.param_labels[key] ?? key}>
                      <input
                        className="input num"
                        type="number"
                        step="any"
                        value={params[key]}
                        onChange={(e) => {
                          setParams({ ...params, [key]: Number(e.target.value) });
                          setParamsDirty(true);
                        }}
                      />
                    </Field>
                  ))}
              </div>
            </fieldset>
          ))}
        </div>
      </Card>

    </div>
  );
}

function ProviderCard({
  provider,
  info,
  model,
  onModel,
  onKeyChange,
  modelLabel = "โมเดล",
  second,
  usage,
}: {
  provider: (typeof PROVIDERS)[number];
  info: KeyInfo;
  model: string;
  onModel: (model: string) => void;
  onKeyChange: () => void;
  modelLabel?: string;
  second?: { label: string; model: string; onModel: (model: string) => void };
  usage?: SettingsData["usage"];
}) {
  const toast = useToast();
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [test, setTest] = useState<{ ok: boolean; error?: string; latency_ms?: number; models?: string[] } | null>(null);
  const [modelDraft, setModelDraft] = useState(model);
  useEffect(() => setModelDraft(model), [model]);

  const save = async (value: string | null) => {
    setBusy(value ? "save" : "remove");
    try {
      await api("admin", "/api/admin/secrets", { method: "PUT", body: { provider: provider.id, key: value } });
      setKey("");
      setTest(null);
      toast(value ? `บันทึก API key ของ ${provider.name} แล้ว` : `ลบ API key ของ ${provider.name} แล้ว`, "success");
      onKeyChange();
    } finally {
      setBusy(null);
    }
  };

  const runTest = async () => {
    setBusy("test");
    try {
      setTest(await api("admin", `/api/admin/providers/${provider.id}/test`, { method: "POST" }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardHead
        title={
          <span className="row row-sm">
            <KeyRound size={17} />
            {provider.name}
          </span>
        }
        sub={`ขอ key ได้ที่ ${provider.console} · key เก็บในไฟล์ runtime/secrets.json บนเครื่องนี้เท่านั้น ไม่ขึ้น git`}
        actions={
          info.configured ? (
            <Badge tone="success">
              <CircleCheck size={13} />
              ใส่แล้ว ••••{info.last4}
              {info.source === "env" ? " (จาก environment)" : ""}
            </Badge>
          ) : (
            <Badge>ยังไม่ได้ใส่</Badge>
          )
        }
      />
      <div className="card-body stack" style={{ paddingTop: 0 }}>
        {info.source === "env" ? (
          <p className="small muted">ใช้ค่าจากตัวแปร {provider.env} ที่ตั้งไว้ตอนเปิดเซิร์ฟเวอร์ ถ้าจะเปลี่ยนให้แก้ตัวแปรนั้น</p>
        ) : (
          <div className="key-row">
            <input
              className="input mono"
              type="password"
              autoComplete="off"
              placeholder={info.configured ? "ใส่ key ใหม่เพื่อแทนที่" : provider.placeholder}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              aria-label={`API key ของ ${provider.name}`}
            />
            <Button variant="primary" loading={busy === "save"} disabled={!key.trim()} onClick={() => save(key.trim())}>
              บันทึก key
            </Button>
            {info.configured && (
              <Button variant="ghost" icon={<Trash2 size={15} />} loading={busy === "remove"} onClick={() => save(null)}>
                ลบ
              </Button>
            )}
          </div>
        )}
        <div className="key-row">
          <Field label={modelLabel}>
            <input className="input mono" list={`${provider.id}-models`} value={modelDraft} onChange={(e) => setModelDraft(e.target.value)} />
          </Field>
          <datalist id={`${provider.id}-models`}>
            {test?.models?.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <Button disabled={modelDraft === model || !modelDraft.trim()} onClick={() => onModel(modelDraft.trim())}>
            ใช้โมเดลนี้
          </Button>
          <Button variant="soft" icon={<PlugZap size={15} />} loading={busy === "test"} disabled={!info.configured} onClick={runTest}>
            ทดสอบการเชื่อมต่อ
          </Button>
        </div>
        {second && <ModelField provider={provider.id} {...second} />}
        {usage && (Object.keys(usage) as ("chat" | "design")[]).map((task) => {
          const u = usage[task]!;
          const wanted = task === "chat" ? model : second?.model;
          return (
            <div key={task} className={`callout ${u.model === wanted ? "callout-calm" : "callout-warning"}`}>
              {u.model === wanted ? <CircleCheck size={18} /> : <TriangleAlert size={18} color="var(--warning)" />}
              <span className="small">
                ล่าสุดงาน{task === "chat" ? "แชตและคำใบ้" : "สร้างบทเรียน"}ใช้ <span className="mono">{u.model}</span>
                {u.model !== wanted && ` ไม่ใช่ ${wanted} ที่ตั้งไว้`}
                {u.fallback && ` · เหตุผล: ${u.fallback}`}
              </span>
            </div>
          );
        })}
        {test &&
          (test.ok ? (
            <div className="callout callout-success">
              <CircleCheck size={18} color="var(--success)" />
              <span className="small">
                เชื่อมต่อได้ ({num(test.latency_ms)} ms) พบ {test.models?.length ?? 0} โมเดล เลือกจากช่องโมเดลได้
                {test.models && !test.models.includes(model) && " · โมเดลที่ตั้งไว้ไม่อยู่ในรายการ ควรเลือกใหม่"}
              </span>
            </div>
          ) : (
            <div className="callout callout-warning">
              <TriangleAlert size={18} color="var(--warning)" />
              <span className="small">{test.error}</span>
            </div>
          ))}
      </div>
    </Card>
  );
}

// ช่องโมเดลที่สอง (งานสร้างบทเรียน) ใช้รายการโมเดลจากการทดสอบการเชื่อมต่อชุดเดียวกัน
function ModelField({ provider, label, model, onModel }: { provider: string; label: string; model: string; onModel: (model: string) => void }) {
  const [draft, setDraft] = useState(model);
  useEffect(() => setDraft(model), [model]);
  return (
    <div className="key-row">
      <Field label={label}>
        <input className="input mono" list={`${provider}-models`} value={draft} onChange={(e) => setDraft(e.target.value)} />
      </Field>
      <Button disabled={draft === model || !draft.trim()} onClick={() => onModel(draft.trim())}>
        ใช้โมเดลนี้
      </Button>
    </div>
  );
}
