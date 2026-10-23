import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowUpRight } from "lucide-react";
import { api } from "../../lib/api";
import type { Principle } from "../../components/PrincipleCard";

// ข้อความประกอบ 7 หัวข้อมาจาก backend/app/principles.py (ทีมแก้ข้อความที่ไฟล์นั้นได้ที่เดียว)
export interface TopicsData {
  topics: Record<string, any>;
  cards: Record<string, Principle>;
}

let cache: TopicsData | null = null;

export function useTopics() {
  const [data, setData] = useState<TopicsData | null>(cache);
  useEffect(() => {
    if (cache) return;
    api<TopicsData>("admin", "/api/admin/topics")
      .then((result) => {
        cache = result;
        setData(result);
      })
      .catch(() => {});
  }, []);
  return data;
}

export function Section({
  num,
  title,
  sub,
  actions,
  children,
}: {
  num?: string;
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="topic-section">
      <div className="topic-section-head">
        <div className="stack" style={{ gap: 4 }}>
          <h2 className="title row row-sm">
            {num && <span className="section-num">{num}</span>}
            {title}
          </h2>
          {sub && <p className="small muted prose">{sub}</p>}
        </div>
        {actions && <div className="row row-sm">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

export function TopicLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={`/admin/${to}`} className="topic-link">
      {children}
      <ArrowUpRight size={13} />
    </Link>
  );
}

// ตัวเลือกนักเรียนแบบรหัส (Admin ไม่เห็นชื่อจริง)
export function CodePicker({
  codes,
  value,
  onChange,
  label = "นักเรียน",
}: {
  codes: { code: string; kind: string }[];
  value: string | null;
  onChange: (code: string) => void;
  label?: string;
}) {
  const groups: Record<string, string> = { real: "นักเรียนจริง", demo: "นักเรียนสาธิต", sim: "นักเรียนจำลอง" };
  return (
    <label className="row row-sm small">
      <span className="muted">{label}</span>
      <select className="select select-sm" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>
          เลือกรหัส
        </option>
        {Object.entries(groups).map(([kind, name]) => {
          const list = codes.filter((c) => c.kind === kind);
          return list.length ? (
            <optgroup key={kind} label={name}>
              {list.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.code}
                </option>
              ))}
            </optgroup>
          ) : null;
        })}
      </select>
    </label>
  );
}
