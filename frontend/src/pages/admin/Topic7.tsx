import { useState } from "react";
import { Eraser, HeartHandshake, Lock, ShieldCheck, UserCheck } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { ago, ALERT_LABEL, ALERT_TONE, clock } from "../../lib/format";
import { Badge, Button, Card, CardHead, Empty, Field, Spinner } from "../../components/ui";
import PrincipleCard from "../../components/PrincipleCard";
import { TopicHeader, useAdmin } from "./AdminApp";
import { AntiLabeling, useStudentPicker } from "./Topic2";
import { CodePicker, Section, TopicLink, useTopics } from "./shared";

const ESCALATION = [
  { signal: "ข้อความสื่อถึงการทำร้ายตนเอง", response: "หยุดทันที แสดงสายด่วนสุขภาพจิต 1323 AI ไม่คุยเรื่องนั้นต่อ", level: "urgent" },
  { signal: "ข้อความเครียดหรือท้อแท้", response: "Circuit Breaker พักสายตา 1 นาที แล้วเริ่มจากตัวอย่างทีละขั้น", level: "normal" },
  { signal: "บอกว่าไม่อยากเรียนต่อ", response: "ให้เลือกเอง: พัก ทำต่อแบบง่ายลง หรือหยุดวันนี้", level: "normal" },
  { signal: "ซ่อมเสริมครบ 2 รอบแล้วยังติด", response: "Stagnation Deadlock หยุดลูปและรอครู", level: "normal" },
  { signal: "Burnout Signal (ตอบเร็วผิดปกติ พักบ่อย Risk สูง)", response: "แจ้งครูแบบเงียบเท่านั้น ไม่หยุดกิจกรรมของนักเรียน", level: "silent" },
] as const;

const OVERRIDE_LABEL: Record<string, string> = {
  release: "ปลดล็อก",
  reset_item: "เริ่มข้อใหม่",
  resume: "เปิดให้เรียนต่อ",
  set_item: "เปลี่ยนโจทย์",
  set_path: "ตั้งเส้นทาง",
  set_mastery: "แก้ Mastery",
  end_session: "จบ Session",
};

export default function Topic7() {
  const data = useTopics();
  const { flow, liveVersion } = useAdmin();
  const { students, code, setCode, detail } = useStudentPicker();
  const logs = useLoad(() => api<{ overrides: any[]; alerts: any[] }>("admin", "/api/admin/logs"), [Math.floor(liveVersion / 10)]);
  const privacy = useLoad(() => (code ? api<any>("admin", `/api/admin/privacy/${code}`) : Promise.resolve(null)), [code, detail.data]);
  const labeling = useLoad(
    () => (code ? api<any>("admin", `/api/admin/anti-labeling/${code}`).catch(() => null) : Promise.resolve(null)),
    [code, detail.data],
  );

  if (!data || !flow) return <Spinner />;
  const t = data.topics["7"];
  const cards = data.cards;

  return (
    <div className="page topic stack stack-lg">
      <TopicHeader id="7" lead="ระบบช่วยคัดกรอง แต่ครูเป็นผู้ตัดสินใจขั้นสุดท้ายเสมอ และข้อมูลของนักเรียนต้องไม่กลายเป็นป้ายที่ตัดสินตัวเขา">
        <CodePicker codes={students} value={code} onChange={setCode} label="ตรวจข้อมูลของ" />
      </TopicHeader>

      <Section num="7.1" title="การตัดวงจรและการส่งต่อให้ครู" sub="กลไกอัตโนมัติมีแป้นเบรกให้มนุษย์เหยียบได้เสมอ เหมือนระบบเบรกอัตโนมัติในรถยนต์">
        <div className="grid grid-3">
          <PrincipleCard card={cards.CIRCUIT_BREAKER} compact />
          <PrincipleCard card={cards.STAGNATION_DEADLOCK} compact />
          <PrincipleCard
            compact
            card={{
              title: "Manual Override",
              theory: "Human-in-the-Loop",
              principle: "ครูสั่งปลดล็อก เริ่มข้อใหม่ เปลี่ยนโจทย์ ตั้งเส้นทาง แก้ Mastery หรือจบ Session ได้ทุกเมื่อจากหน้าครู ทุกคำสั่งบันทึกพร้อมเหตุผล",
              source: "สเปก 7.1",
              code: "backend/app/engine/core.py › override()",
            }}
          />
        </div>
        <Card>
          <CardHead title="ระดับการส่งต่อ" sub="เลือกระดับให้เหมาะกับความเสี่ยง ไม่ใช่ทุกสัญญาณต้องหยุดนักเรียน" />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>สัญญาณ</th>
                  <th>ระบบทำอะไร</th>
                  <th>แจ้งครู</th>
                </tr>
              </thead>
              <tbody>
                {ESCALATION.map((row) => (
                  <tr key={row.signal}>
                    <td className="small strong">{row.signal}</td>
                    <td className="small muted">{row.response}</td>
                    <td>
                      <Badge tone={ALERT_TONE[row.level]}>{ALERT_LABEL[row.level]}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </Section>

      <Section num="HITL" title="กฎ 4 ข้อของครู (Human-in-the-Loop)">
        <div className="grid grid-4">
          {t.teacher_rules.map((rule: string, i: number) => (
            <Card key={i} className="card-pad stack stack-sm">
              <span className="role-icon role-icon-sm">{[<ShieldCheck size={18} key="a" />, <HeartHandshake size={18} key="b" />, <UserCheck size={18} key="c" />, <HeartHandshake size={18} key="d" />][i]}</span>
              <span className="eyebrow">ข้อ {i + 1}</span>
              <p className="small">{rule}</p>
            </Card>
          ))}
        </div>
        <Card>
          <CardHead title="ประวัติ Manual Override" sub="ทุกครั้งที่ครูแทรกแซง ระบบเก็บว่าใครสั่งอะไรกับนักเรียนรหัสไหน และเพราะอะไร" />
          {logs.data?.overrides.length ? (
            <div className="table-wrap" style={{ maxHeight: 280 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>เวลา</th>
                    <th>ผู้สั่ง</th>
                    <th>นักเรียน</th>
                    <th>คำสั่ง</th>
                    <th>เหตุผล</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.data.overrides.map((o) => (
                    <tr key={o.id}>
                      <td className="xsmall faint num">{clock(o.ts)}</td>
                      <td className="small">{o.actor === "teacher" ? "ครู" : o.actor}</td>
                      <td className="mono small">{o.code}</td>
                      <td className="small">{OVERRIDE_LABEL[o.action] ?? o.action}</td>
                      <td className="small muted">{o.reason || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>ยังไม่มีการแทรกแซง ลองสั่งจากหน้าครูแล้วกลับมาดูที่นี่</Empty>
          )}
        </Card>
      </Section>

      <Section num="7.2" title="ความเป็นส่วนตัว (PDPA)">
        <div className="grid grid-2">
          <Card className="card-pad stack">
            <ul className="point-list">
              {t.privacy.map((p: string, i: number) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
            <hr className="divider" />
            <ScrubDemo />
          </Card>
          <Card>
            <CardHead
              title={
                <span className="row row-sm">
                  <Lock size={16} />
                  ข้อมูลที่ระบบเก็บของ {code ?? "–"}
                </span>
              }
              sub="มุมมองของ Admin: เห็นเฉพาะรหัส ไม่มีชื่อจริง"
            />
            <div className="card-body stack" style={{ paddingTop: 0 }}>
              {privacy.data ? (
                <>
                  <dl className="kv">
                    {Object.entries(privacy.data.counts as Record<string, number>).map(([table, n]) => (
                      <div key={table}>
                        <dt className="mono">{table}</dt>
                        <dd className="num">{n} แถว</dd>
                      </div>
                    ))}
                    <div>
                      <dt>ชื่อจริง</dt>
                      <dd>{privacy.data.name_visible ? "เห็น" : "ไม่เห็น"}</dd>
                    </div>
                  </dl>
                  <p className="xsmall muted">{privacy.data.roster_note}</p>
                  <div className="stack stack-sm">
                    <span className="xsmall strong">บริบทที่ส่งให้ AI Provider ล่าสุด (Context Framing ข้อ 2)</span>
                    {privacy.data.last_prompt_context ? (
                      <pre className="code-block">{privacy.data.last_prompt_context}</pre>
                    ) : (
                      <span className="small faint">ยังไม่เคยส่งข้อมูลของนักเรียนคนนี้ให้ Provider</span>
                    )}
                  </div>
                </>
              ) : (
                <Empty>เลือกนักเรียนด้านบน</Empty>
              )}
            </div>
          </Card>
        </div>
      </Section>

      <Section num="7.2" title="ป้องกันอคติทางสถิติและการตีตราผู้เรียน">
        <div className="grid grid-3">
          {t.bias.map((b: { name: string; example: string }) => (
            <Card key={b.name} className="card-pad stack stack-sm">
              <h3 className="subtitle">{b.name}</h3>
              <p className="small muted">{b.example}</p>
            </Card>
          ))}
        </div>
        {labeling.data && <AntiLabeling data={labeling.data} linkToEthics={false} />}
      </Section>

      <Card>
        <CardHead title="การแจ้งเตือนทั้งหมดในระบบ" sub={<>ครูรับทราบได้ที่หน้าครู ส่วนนี้เป็นบันทึกสำหรับตรวจสอบย้อนหลัง (<TopicLink to="3">ดูตำแหน่งในผัง</TopicLink>)</>} />
        {logs.data?.alerts.length ? (
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>ระดับ</th>
                  <th>นักเรียน</th>
                  <th>ข้อความ</th>
                  <th>สถานะ</th>
                  <th>เวลา</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.alerts.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Badge tone={ALERT_TONE[a.level]}>{ALERT_LABEL[a.level]}</Badge>
                    </td>
                    <td className="mono small">{a.code}</td>
                    <td className="small">{a.message}</td>
                    <td className="small faint">{a.acknowledged ? "ครูรับทราบแล้ว" : "รอครู"}</td>
                    <td className="xsmall faint nowrap">{ago(a.ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>ยังไม่มีการแจ้งเตือน</Empty>
        )}
      </Card>
    </div>
  );
}

// ลองลบข้อมูลส่วนตัวด้วยกฎเดียวกับที่ใช้ก่อนส่งข้อความแชตให้ Provider
function ScrubDemo() {
  const [text, setText] = useState("ผมชื่อภูมิ ใจดี เบอร์ 081-234-5678 อีเมล bhumi@example.com ช่วยเฉลยข้อนี้ให้หน่อย");
  const [result, setResult] = useState<{ text: string; found: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      setResult(await api("admin", "/api/admin/privacy/scrub", { body: { text } }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack stack-sm">
      <span className="small strong">ลองดูข้อความที่ Provider จะได้รับ</span>
      <Field label="ข้อความที่นักเรียนพิมพ์" hint="ตัวอย่างนี้ใช้ชื่อสมมติของนักเรียนสาธิต S-01 ถึง S-06">
        <textarea className="textarea" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Button icon={<Eraser size={16} />} loading={busy} onClick={run} style={{ alignSelf: "flex-start" }}>
        ลบข้อมูลส่วนตัว
      </Button>
      {result && (
        <div className="retrieved">
          <span className="xsmall faint">สิ่งที่ส่งออกไป {result.found.length ? `· แทนที่ ${result.found.join(" ")}` : "· ไม่พบข้อมูลส่วนตัว"}</span>
          <p className="small">{result.text}</p>
        </div>
      )}
    </div>
  );
}
