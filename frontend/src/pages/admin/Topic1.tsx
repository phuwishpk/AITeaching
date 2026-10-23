import type { ReactNode } from "react";
import { BookOpenCheck, Brain, School } from "lucide-react";
import { Card, Spinner } from "../../components/ui";
import { TopicHeader } from "./AdminApp";
import { Section, TopicLink, useTopics } from "./shared";

// ปัญหาแต่ละข้อ ระบบตอบด้วยกลไกอะไร และดูได้ที่แท็บไหน
const ANSWERS: Record<string, { mechanism: string; tab: string }[]> = {
  ด้านผู้เรียน: [
    { mechanism: "Remedial Loop พาไปทบทวน Prerequisite ที่ผูกกับความเข้าใจผิด", tab: "3" },
    { mechanism: "ด่าน 2 จับ Rapid Guess แล้วพักปุ่มตอบ", tab: "6" },
    { mechanism: "Fuzzy ดูแนวโน้มเวลาคิดเพื่อตัดสิน Impasse", tab: "4" },
  ],
  ด้านเนื้อหา: [
    { mechanism: "บันไดคำใบ้ 3 ระดับ ไม่เฉลยคำตอบ", tab: "3" },
    { mechanism: "Fuzzy เลือกความยากข้อถัดไปให้อยู่ใน ZPD", tab: "4" },
  ],
  ด้านระบบและครู: [
    { mechanism: "แจ้งเตือนครูเฉพาะเรื่องที่ต้องใช้ดุลยพินิจ พร้อม Manual Override", tab: "7" },
    { mechanism: "จัดกลุ่มผู้เรียนด้วย K-Means ให้ครูเห็นภาพทั้งห้อง", tab: "4" },
  ],
};

// สิ่งที่ Static CAI ทำ เทียบกับสิ่งที่ระบบนี้ทำแทน
const SHIFTS = [
  { from: "เรียงหน้าเหมือนกันทุกคน", to: "เลือกข้อถัดไปตาม Mastery และเวลาคิด", tab: "3" },
  { from: "ผิดแล้วแจกเฉลย", to: "รอให้คิด 15 วินาที แล้วช่วยทีละขั้น", tab: "3" },
  { from: "ถูกเพราะดูเฉลย", to: "พิสูจน์ด้วยข้อคู่ขนานที่ปิดคำใบ้", tab: "3" },
  { from: "ครูไม่รู้ว่าใครติด", to: "แจ้งครูเฉพาะเรื่องที่ต้องตัดสินใจ", tab: "7" },
];

const SIDE_ICON: Record<string, ReactNode> = {
  ด้านผู้เรียน: <Brain size={20} />,
  ด้านเนื้อหา: <BookOpenCheck size={20} />,
  ด้านระบบและครู: <School size={20} />,
};

export default function Topic1() {
  const data = useTopics();
  if (!data) return <Spinner />;
  const t = data.topics["1"];

  return (
    <div className="page topic stack stack-lg">
      <TopicHeader id="1" lead="บทเรียนคอมพิวเตอร์แบบเดิมสอนทุกคนเหมือนกัน และช่วยด้วยการเฉลย ระบบนี้ออกแบบมาเพื่อแก้สองเรื่องนั้น" />

      <Section num="1.1" title="ปัญหาจริง (Pain Point)">
        <div className="grid grid-2">
          <Card className="card-pad stack">
            <ul className="point-list">
              {t.pain_points.map((p: string, i: number) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
            <div className="answer-box">
              <span className="eyebrow">ระบบนี้เปลี่ยนเป็น</span>
              {SHIFTS.map((item) => (
                <div key={item.from} className="answer-item">
                  <span className="small">
                    <span className="faint">{item.from}</span> → <span className="strong">{item.to}</span>
                  </span>
                  <TopicLink to={item.tab}>แท็บ {item.tab}</TopicLink>
                </div>
              ))}
            </div>
          </Card>
          <Card className="card-pad stack">
            <figure className="figure">
              <StaticVsAdaptive />
              <figcaption className="xsmall muted">
                บน: Static CAI เดินเส้นเดียวและจบที่เฉลย ล่าง: ระบบนี้รอให้คิดก่อน ช่วยทีละขั้น และพาไปทบทวนพื้นฐานเมื่อติด
              </figcaption>
            </figure>
          </Card>
        </div>
      </Section>

      <Section num="1.2" title="การจำแนกปัญหา (Decomposition)" sub="แต่ละด้านจับคู่กับกลไกในระบบ กดลิงก์เพื่อดูกลไกนั้นทำงานจริง">
        <div className="grid grid-3">
          {t.decomposition.map((d: { side: string; points: string[] }) => (
            <Card key={d.side} className="card-pad stack">
              <div className="row row-sm">
                <span className="role-icon role-icon-sm">{SIDE_ICON[d.side]}</span>
                <h3 className="subtitle">{d.side}</h3>
              </div>
              <ul className="point-list">
                {d.points.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
              <div className="answer-box">
                <span className="eyebrow">ระบบตอบด้วย</span>
                {(ANSWERS[d.side] ?? []).map((a, i) => (
                  <div key={i} className="answer-item">
                    <span className="small">{a.mechanism}</span>
                    <TopicLink to={a.tab}>แท็บ {a.tab}</TopicLink>
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </Section>

      <Section num="1.3" title="กลุ่มเป้าหมาย (Target Learners)">
        <Card className="card-pad stack">
          <p className="lead" style={{ maxWidth: "none" }}>
            {t.target}
          </p>
          <ol className="chain">
            <li>
              <span className="chain-grade">ม.1</span>บวกลบจำนวนเต็ม
            </li>
            <li>
              <span className="chain-grade">ม.1</span>สมบัติการเท่ากัน
            </li>
            <li>
              <span className="chain-grade">ม.1</span>สมการขั้นเดียว
            </li>
            <li className="is-target">
              <span className="chain-grade">ม.2</span>สมการสองขั้น (เป้าหมาย)
            </li>
            <li>
              <span className="chain-grade">ม.2</span>ตัวแปรสองข้าง (Fast-Track)
            </li>
          </ol>
          <p className="xsmall muted">
            จะแก้สมการ ม.2 ได้ ต้องบวกลบจำนวนติดลบของ ม.1 ให้คล่องก่อน ช่องโหว่ตรงนี้คือ Learning Gap ที่ระบบพาย้อนไปซ่อม (ดูแผนผังเต็มที่ <TopicLink to="2">แท็บ 2</TopicLink>)
          </p>
        </Card>
      </Section>
    </div>
  );
}

function Box({ x, y, w, label, accent }: { x: number; y: number; w: number; label: string; accent?: boolean }) {
  return (
    <g className={accent ? "dg-box dg-accent" : "dg-box"}>
      <rect x={x} y={y} width={w} height={34} rx={9} />
      <text x={x + w / 2} y={y + 21.5} textAnchor="middle">
        {label}
      </text>
    </g>
  );
}

function Arrow({ d, label, lx, ly, accent }: { d: string; label?: string; lx?: number; ly?: number; accent?: boolean }) {
  return (
    <g className={accent ? "dg-arrow dg-accent" : "dg-arrow"}>
      <path d={d} markerEnd={accent ? "url(#dg-head-accent)" : "url(#dg-head)"} />
      {label && (
        <text x={lx} y={ly} textAnchor="middle" className="dg-label">
          {label}
        </text>
      )}
    </g>
  );
}

function StaticVsAdaptive() {
  return (
    <svg viewBox="0 0 560 330" className="diagram" role="img" aria-label="เปรียบเทียบ Static CAI ที่เดินเส้นเดียวแล้วเฉลย กับระบบนี้ที่หน่วงเวลา ให้คำใบ้ทีละขั้น และพาไปทบทวนพื้นฐาน">
      <defs>
        <marker id="dg-head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
        <marker id="dg-head-accent" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
        </marker>
      </defs>
      <text x={0} y={14} className="dg-title">
        Static CAI
      </text>
      <Box x={0} y={28} w={110} label="หน้า 1" />
      <Box x={150} y={28} w={110} label="หน้า 2" />
      <Box x={300} y={28} w={110} label="หน้า 3" />
      <Arrow d="M110,45 L148,45" label="ทุกคน" lx={129} ly={38} />
      <Arrow d="M260,45 L298,45" label="ทุกคน" lx={279} ly={38} />
      <Arrow d="M205,62 L205,96" label="ตอบผิด" lx={232} ly={84} />
      <Box x={130} y={98} w={150} label="บอกว่าผิด / แจกเฉลย" />
      <text x={292} y={119} className="dg-note">
        สมองลัดวงจร · คิดว่าเข้าใจแล้ว
      </text>

      <line x1={0} y1={152} x2={560} y2={152} className="dg-divider" />

      <text x={0} y={178} className="dg-title dg-accent-text">
        Adaptive Tutor
      </text>
      <Box x={0} y={192} w={96} label="โจทย์" accent />
      <Box x={140} y={192} w={110} label="รอคิดเอง 15 วิ" accent />
      <Box x={290} y={192} w={120} label="คำใบ้ L1 → L3" accent />
      <Box x={446} y={192} w={114} label="ข้อคู่ขนาน" accent />
      <Arrow d="M96,209 L138,209" label="ตอบผิด" lx={117} ly={202} accent />
      <Arrow d="M250,209 L288,209" label="ยังผิด" lx={269} ly={202} accent />
      <Arrow d="M410,209 L444,209" label="ผ่าน" lx={427} ly={202} accent />
      <Arrow d="M350,226 L350,268" label="ติด Impasse" lx={392} ly={252} accent />
      <Box x={280} y={270} w={140} label="ทบทวนพื้นฐาน" accent />
      <Arrow d="M280,287 L48,287 L48,228" label="ถูก 2 ข้อติดกัน กลับข้อเดิม" lx={160} ly={280} accent />
      <text x={446} y={244} className="dg-note">
        ปิดคำใบ้ พิสูจน์ว่าเข้าใจจริง
      </text>
    </svg>
  );
}
