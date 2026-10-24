import { useEffect, useRef, useState } from "react";
import { RefreshCw, Scissors, Send } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { num, pct } from "../../lib/format";
import type { AiLog, BugTag, FuzzyResult } from "../../lib/types";
import AiLogCard from "../../components/AiLog";
import {
  BarList,
  ClusterScatter,
  ElbowChart,
  MembershipChart,
  OutputChart,
  type Centroid,
  type ClusterPoint,
  type FuzzyVarDef,
} from "../../components/charts";
import { Badge, Button, Card, CardHead, Empty, Field, Segmented, Spinner } from "../../components/ui";
import { CLUSTER_NAMES } from "../../lib/format";
import { TopicHeader } from "./AdminApp";
import { Section, useTopics } from "./shared";

export default function Topic4() {
  const data = useTopics();
  if (!data) return <Spinner />;
  const t = data.topics["4"];
  return (
    <div className="page topic stack stack-lg">
      <TopicHeader
        id="4"
        lead="AI ในระบบมี 4 บทบาท กฎกับ Fuzzy ตัดสินเส้นทาง K-Means ช่วยครูเห็นภาพทั้งห้อง ส่วน LLM ทำหน้าที่แค่ปรับถ้อยคำภายใต้กรอบที่ควบคุมไว้"
      />

      <Section num="4.1" title="บทบาทของ AI ภายในระบบ">
        <div className="grid grid-4">
          {t.roles.map((r: { name: string; chapter: string; job: string }) => (
            <Card key={r.name} className="card-pad stack stack-sm">
              <h3 className="subtitle">{r.name}</h3>
              <span className="xsmall faint">{r.chapter}</span>
              <p className="small muted">{r.job}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section num="A" title="Fuzzy Logic (ใบงานที่ 5)" sub="Fuzzification แปลงค่าเป็นระดับความเป็นสมาชิก μ → ประเมินกฎด้วย min/max → Defuzzification ด้วยจุดศูนย์ถ่วง (Center of Gravity)">
        <FuzzyExplorer />
      </Section>

      <Section num="B" title="K-Means Clustering (บทที่ 6)" sub="Unsupervised Learning จัดนักเรียนเป็น 4 กลุ่มด้วยระยะ Euclidean บนตัวแปรที่ปรับสเกลแล้ว K-Means ไม่รู้ชื่อกลุ่ม ชื่อมาจากกฎที่เขียนไว้ชัด">
        <KMeansPanel />
      </Section>

      <Section num="C" title="LLM Tutor + RAG และ Context Framing 4 กรอบ" sub="ลองประกอบ prompt จริงกับโจทย์ในระบบ ดูว่า RAG ดึงอะไรมา LLM ตอบอะไร และ Guard ตัดสินอย่างไร">
        <PromptInspector />
      </Section>

      <Section num="4.2" title="ข้อจำกัดของเครื่องมือ">
        <div className="grid grid-2">
          <Card className="card-pad stack">
            <ul className="point-list">
              {t.llm_limits.map((l: string, i: number) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </Card>
          <TokenizeDemo />
        </div>
      </Section>

      <Section num="RL" title="ศัพท์ Reinforcement Learning เทียบกับระบบนี้" sub={t.rl_note}>
        <Card>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>องค์ประกอบ</th>
                  <th>ในระบบนี้</th>
                </tr>
              </thead>
              <tbody>
                {t.rl_mapping.map((r: { part: string; system: string }) => (
                  <tr key={r.part}>
                    <td className="strong small">{r.part}</td>
                    <td className="small">{r.system}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------- Fuzzy
interface FuzzyDescribe {
  name: string;
  inputs: FuzzyVarDef[];
  output: FuzzyVarDef;
  rules: string[];
}

const SYSTEM_INFO: Record<string, { title: string; meaning: (v: number) => string; defaults: Record<string, number> }> = {
  impasse: {
    title: "ตัดสิน Impasse (ผิดครั้งที่ 3)",
    meaning: (v) => (v >= 55 ? `${num(v, 1)} ≥ 55 ถือว่าเกิด Impasse พักข้อนี้แล้วไปทบทวนพื้นฐาน` : `${num(v, 1)} < 55 ยังคิดต่อได้ ให้คำใบ้ระดับ 3`),
    defaults: { trend: 0.4, slowness: 1.3 },
  },
  difficulty: {
    title: "ความยากของข้อถัดไป",
    meaning: (v) => `เลือกโจทย์ที่ความยากใกล้ ${num(v, 0)}% มากที่สุดจากโจทย์ที่ยังไม่ได้ทำ`,
    defaults: { mastery: 0.62, slowness: 0.9 },
  },
  risk: {
    title: "Risk Score (โอกาส Drop-out)",
    meaning: (v) => `Risk Score ${num(v, 0)} แสดงเฉพาะครู ถ้าถึงเกณฑ์จะส่งแจ้งเตือนแบบเงียบ ไม่หยุดกิจกรรมของนักเรียน`,
    defaults: { error_rate: 0.55, disengagement: 0.4, slowness: 1.2 },
  },
};

function FuzzyExplorer() {
  const systems = useLoad(() => api<Record<string, FuzzyDescribe>>("admin", "/api/admin/fuzzy"));
  const [name, setName] = useState("impasse");
  const [inputs, setInputs] = useState<Record<string, number>>(SYSTEM_INFO.impasse.defaults);
  const [result, setResult] = useState<FuzzyResult | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      api<FuzzyResult>("admin", "/api/admin/fuzzy/evaluate", { body: { system: name, inputs } })
        .then(setResult)
        .catch(() => {});
    }, 120);
    return () => clearTimeout(timer.current);
  }, [name, inputs]);

  const system = systems.data?.[name];
  if (!system) return <Spinner />;

  const choose = (next: string) => {
    setName(next);
    setInputs(SYSTEM_INFO[next].defaults);
    setResult(null);
  };

  return (
    <div className="stack">
      <Segmented
        label="ระบบ Fuzzy"
        value={name}
        onChange={choose}
        options={Object.keys(systems.data ?? {}).map((id) => ({ id, label: SYSTEM_INFO[id]?.title ?? id }))}
      />
      <div className="fuzzy-grid">
        <Card className="card-pad stack">
          <span className="eyebrow">1 · Fuzzification</span>
          {system.inputs.map((v) => (
            <div key={v.name} className="stack stack-sm">
              <div className="spread">
                <span className="small strong">{v.label}</span>
                <span className="num small">{num(inputs[v.name], 2)}</span>
              </div>
              <input
                type="range"
                min={v.low}
                max={v.high}
                step={(v.high - v.low) / 100}
                value={inputs[v.name] ?? v.low}
                onChange={(e) => setInputs({ ...inputs, [v.name]: Number(e.target.value) })}
                aria-label={v.label}
              />
              <MembershipChart variable={v} value={inputs[v.name]} />
            </div>
          ))}
        </Card>
        <div className="stack">
          <Card className="card-pad stack">
            <span className="eyebrow">2 · Rule Evaluation (AND = min, รวมด้วย max)</span>
            {result ? (
              <BarList
                max={1}
                rows={result.rules.map((r, i) => ({
                  key: String(i),
                  label: r.text,
                  value: r.strength,
                  valueText: num(r.strength, 2),
                  color: r.strength > 0 ? "var(--series-1)" : "var(--surface-3)",
                }))}
              />
            ) : (
              <Spinner />
            )}
          </Card>
          <Card className="card-pad stack">
            <span className="eyebrow">3 · Defuzzification (Center of Gravity)</span>
            {result?.curve && <OutputChart variable={system.output} curve={result.curve} crisp={result.output} />}
            {result && (
              <div className="callout callout-accent">
                <span className="small">{SYSTEM_INFO[name]?.meaning(result.output)}</span>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- K-Means
interface ClusterModel {
  k: number;
  points: ClusterPoint[];
  centroids: Centroid[];
  elbow: { k: number; inertia: number }[];
  rules: string[];
  iterations: number;
  inertia?: number;
}

function KMeansPanel() {
  const [force, setForce] = useState(0);
  const model = useLoad(() => api<ClusterModel>("admin", `/api/admin/clusters${force ? "?force=true" : ""}`), [force]);
  const m = model.data;
  if (model.loading && !m) return <Spinner />;
  if (!m || !m.points.length) return <Empty>ต้องมีนักเรียนที่ตอบอย่างน้อย 3 ครั้งอย่างน้อย 4 คนก่อน</Empty>;

  return (
    <div className="stack">
      <div className="kmeans-grid">
        <Card>
          <CardHead
            title="ผลการจัดกลุ่ม"
            sub={`${m.points.length} คน · ${m.iterations} รอบจนลู่เข้า${m.inertia != null ? ` · inertia ${num(m.inertia, 1)}` : ""}`}
            actions={
              <Button size="sm" variant="ghost" icon={<RefreshCw size={15} />} loading={model.loading} onClick={() => setForce((v) => v + 1)}>
                คำนวณใหม่
              </Button>
            }
          />
          <div className="card-body" style={{ paddingTop: 0 }}>
            <ClusterScatter points={m.points} centroids={m.centroids} />
          </div>
        </Card>
        <div className="stack">
          <Card>
            <CardHead title="Elbow Method" sub="inertia ลดลงช้าลงชัดหลัง k = 4 จึงเลือก 4 กลุ่ม" />
            <div className="card-body" style={{ paddingTop: 0 }}>
              <ElbowChart data={m.elbow} chosen={m.k} />
            </div>
          </Card>
          <Card className="card-pad stack stack-sm">
            <span className="small strong">กฎตั้งชื่อกลุ่มจาก centroid</span>
            <ol className="steps small">
              {m.rules.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
      <Card>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>กลุ่ม</th>
                <th>ลักษณะ</th>
                <th className="num">จำนวน</th>
                <th className="num">เวลาคิดเฉลี่ย</th>
                <th className="num">ตอบถูก</th>
                <th className="num">Session เฉลี่ย</th>
              </tr>
            </thead>
            <tbody>
              {m.centroids.map((c) => (
                <tr key={c.cluster}>
                  <td className="small strong nowrap">{CLUSTER_NAMES[c.cluster] ?? c.cluster_name}</td>
                  <td className="small muted">{c.description}</td>
                  <td className="num small">{c.size}</td>
                  <td className="num small">{num(c.avg_rt, 1)} วิ</td>
                  <td className="num small">{pct(c.accuracy)}</td>
                  <td className="num small">{num(c.session_min, 1)} นาที</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- Prompt
interface SampleData {
  items: { id: string; concept: string; kind: string; format: string; prompt: string; math: string | null }[];
  bug_tags: BugTag[];
}

interface PreviewResult {
  text: string;
  source: string;
  model?: string;
  guard: { blocked: boolean } | null;
  errors?: string[];
  log: AiLog | null;
}

function PromptInspector() {
  const sample = useLoad(() => api<SampleData>("admin", "/api/admin/sample"));
  const stats = useLoad(() => api<any>("admin", "/api/admin/ai/stats"));
  const [itemId, setItemId] = useState("");
  const [level, setLevel] = useState("1");
  const [tag, setTag] = useState("");

  // ค่าเริ่มต้นจากคลังของ Gem ที่ใช้สาธิต: โจทย์หลักข้อแรก และ Misconception ข้อแรก
  useEffect(() => {
    if (!sample.data) return;
    setItemId((current) => current || sample.data!.items.find((it) => it.kind === "main")?.id || "");
    setTag((current) => current || sample.data!.bug_tags.find((t) => t.type === "misconception")?.id || "");
  }, [sample.data]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PreviewResult | null>(null);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await api<PreviewResult>("admin", "/api/admin/ai/preview", { body: { item_id: itemId, level: Number(level), tag: tag || null } }));
      stats.reload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <Card className="card-pad">
        <div className="prompt-form">
          <Field label="โจทย์">
            <select className="select" value={itemId} onChange={(e) => setItemId(e.target.value)}>
              {(sample.data?.items ?? [])
                .filter((it) => it.kind !== "isomorphic")
                .map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.id} · {it.math ?? it.prompt.slice(0, 30)}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="ระดับคำใบ้">
            <Segmented
              label="ระดับคำใบ้"
              value={level}
              onChange={setLevel}
              options={[
                { id: "1", label: "L1" },
                { id: "2", label: "L2" },
                { id: "3", label: "L3" },
              ]}
            />
          </Field>
          <Field label="Misconception ที่พบ (จาก Bug Library)">
            <select className="select" value={tag} onChange={(e) => setTag(e.target.value)}>
              <option value="">ไม่มี</option>
              {(sample.data?.bug_tags ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} · {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Button variant="primary" icon={<Send size={16} />} loading={busy} onClick={run}>
            ประกอบ prompt และเรียก AI
          </Button>
        </div>
        {stats.data && (
          <p className="xsmall faint" style={{ marginTop: 12 }}>
            {(stats.data.providers ?? []).map((p: any) => `${p.provider}: ${p.calls} ครั้ง`).join(" · ") || "ยังไม่มีการเรียก AI"} · Guard บล็อกไปแล้ว{" "}
            {stats.data.guard_blocked} ครั้ง
          </p>
        )}
      </Card>
      {result && (
        <div className="stack stack-sm">
          <div className="row row-sm">
            <span className="small strong">ผลลัพธ์ที่นักเรียนจะเห็น</span>
            <Badge tone={result.source === "authored" ? "calm" : "success"}>
              {result.source === "authored" ? "คำใบ้ต้นฉบับของครู" : `${result.source}${result.model ? ` · ${result.model}` : ""}`}
            </Badge>
            {result.errors?.length ? <span className="xsmall faint">{result.errors.join(" · ")}</span> : null}
          </div>
          {result.log ? <AiLogCard log={result.log} open /> : <p className="small">{result.text}</p>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- ตัดคำภาษาไทย
function TokenizeDemo() {
  const [text, setText] = useState("ฉันชอบไปตากลมที่ชายทะเล แต่น้องคนนี้ตากลมโตน่ารัก");
  const [query, setQuery] = useState("ย้ายข้างสมการต้องเปลี่ยนเครื่องหมายไหม");
  const [result, setResult] = useState<{ tokens: string[]; query_terms: string[]; results: { filename: string; text: string; score: number }[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await api("admin", "/api/admin/ai/tokenize", { body: { text, query } }));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Card className="card-pad stack">
      <span className="eyebrow">ตัดคำภาษาไทยด้วย PyThaiNLP (newmm)</span>
      <Field label="ประโยค">
        <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} rows={2} />
      </Field>
      {result && (
        <div className="pill-list">
          {result.tokens.map((t, i) => (
            <span key={i} className="token">
              {t}
            </span>
          ))}
        </div>
      )}
      <p className="xsmall muted">คำว่า "ตากลม" ตัดได้สองแบบ (ตาก + ลม หรือ ตา + กลม) ตัวตัดคำเลือกแบบเดียวเสมอ ความหมายจึงอาจคลาดได้</p>
      <Field label="ลองค้นเอกสารวิชาด้วย BM25">
        <input className="input" value={query} onChange={(e) => setQuery(e.target.value)} />
      </Field>
      <Button icon={<Scissors size={16} />} loading={busy} onClick={run} style={{ alignSelf: "flex-start" }}>
        ตัดคำและค้น
      </Button>
      {result && result.query_terms.length > 0 && (
        <div className="stack stack-sm">
          <span className="xsmall faint">คำค้นหลังตัดคำและตัดคำหยุด: {result.query_terms.join(" · ")}</span>
          {result.results.map((r, i) => (
            <div key={i} className="retrieved">
              <span className="xsmall faint">
                {r.filename} · BM25 {num(r.score, 2)}
              </span>
              <p className="small">{r.text.replace(/^#+\s*/gm, "")}</p>
            </div>
          ))}
          {!result.results.length && <span className="small faint">ไม่พบย่อหน้าที่เกี่ยวข้อง</span>}
        </div>
      )}
    </Card>
  );
}
