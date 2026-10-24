import { useMemo, useState } from "react";
import { Link } from "react-router";
import { ArrowUpRight, BookOpen, Code2, FlaskConical, Printer, Quote, Search, Timer, Workflow } from "lucide-react";
import { api, type Role } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { num } from "../../lib/format";
import { Button, Card, Empty, Spinner } from "../../components/ui";

// หน้า "กฎทั้งหมด": ข้อความและค่าตัวเลขมาจาก backend/app/rules.py ซึ่งเติมค่าที่ตั้งไว้ตอนนี้ให้แล้ว

interface RuleParam {
  key: string;
  label: string;
  unit: string;
  value: number;
  default: number;
  changed: boolean;
  scaled: boolean;
  effective: number | null;
}

interface Rule {
  id: string;
  title: string;
  when: string;
  then: string;
  params: RuleParam[];
  principle?: string;
  source?: string;
  code?: string;
  node?: string;
  node_label?: string | null;
  test?: string;
}

interface RuleGroup {
  id: string;
  title: string;
  summary: string;
  rules: Rule[];
}

interface RulesData {
  groups: RuleGroup[];
  total: number;
  demo: { enabled: boolean; time_scale: number };
  time_scale: number;
}

const GROUP_MARKS = ["ก", "ข", "ค", "ง", "จ", "ฉ", "ช", "ซ", "ฌ"];

function matches(rule: Rule, query: string) {
  if (!query) return true;
  const text = [rule.id, rule.title, rule.when, rule.then, rule.principle, rule.source, rule.code, ...rule.params.map((p) => p.label)]
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.includes(word));
}

export default function RulesPage({ role }: { role: Exclude<Role, "student"> }) {
  const rules = useLoad(() => api<RulesData>(role, "/api/rules"));
  const [query, setQuery] = useState("");
  const admin = role === "admin";

  const groups = useMemo(
    () =>
      (rules.data?.groups ?? []).map((group, index) => ({
        ...group,
        mark: GROUP_MARKS[index] ?? String(index + 1),
        visible: group.rules.filter((rule) => matches(rule, query.trim())),
      })),
    [rules.data, query],
  );
  const shown = groups.reduce((sum, g) => sum + g.visible.length, 0);

  if (rules.error) return <Empty>{rules.error}</Empty>;
  if (!rules.data) return <Spinner />;

  return (
    <div className="page stack stack-lg rules-page">
      <header className="topic-head fade-in">
        <div className="stack stack-sm">
          <p className="eyebrow">กฎทั้งหมด</p>
          <h1 className="title-xl">กฎที่ระบบใช้ตัดสินทุกขั้น</h1>
          <p className="lead">
            กฎ {rules.data.total} ข้อ เรียงตามลำดับที่คำตอบหนึ่งครั้งเดินผ่าน ตัวเลขในกฎเป็นค่าที่ใช้อยู่ตอนนี้
            {admin ? " ปรับได้ที่หน้าตั้งค่า แล้วหน้านี้จะเปลี่ยนตาม" : " ผู้ดูแลระบบปรับค่าได้ที่หน้าตั้งค่า"}
          </p>
        </div>
        <div className="row rules-tools">
          <label className="search-box">
            <Search size={16} aria-hidden />
            <input
              className="input"
              type="search"
              placeholder="ค้นกฎ เช่น คำใบ้, Mastery, 15 วินาที"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="ค้นกฎ"
            />
          </label>
          <Button variant="ghost" icon={<Printer size={16} />} onClick={() => window.print()}>
            พิมพ์
          </Button>
        </div>
      </header>

      {rules.data.demo.enabled && (
        <div className="callout callout-warning">
          <Timer size={18} />
          <span>
            Demo Mode เปิดอยู่ เวลารอที่มีเครื่องหมาย ⏱ ถูกย่อ × {rules.data.time_scale} ระหว่างสาธิต ส่วนกฎและลำดับการตัดสินยังเหมือนเดิม
          </span>
        </div>
      )}

      <nav className="rule-toc" aria-label="กลุ่มกฎ">
        {groups.map((group) => (
          <a key={group.id} href={`#rules-${group.id}`} className={group.visible.length ? "" : "is-empty"}>
            <span className="rule-toc-mark">{group.mark}</span>
            {group.title}
            <span className="rule-toc-count">{group.visible.length}</span>
          </a>
        ))}
      </nav>

      {query && (
        <p className="small muted" role="status">
          พบ {shown} จาก {rules.data.total} ข้อ
        </p>
      )}
      {shown === 0 && <Empty>ไม่พบกฎที่ตรงกับคำค้นนี้</Empty>}

      {groups
        .filter((group) => group.visible.length)
        .map((group) => (
          <section key={group.id} id={`rules-${group.id}`} className="topic-section rule-group">
            <div className="topic-section-head">
              <div className="stack" style={{ gap: 4 }}>
                <h2 className="title row row-sm">
                  <span className="section-num">{group.mark}</span>
                  {group.title}
                </h2>
                <p className="small muted prose">{group.summary}</p>
              </div>
            </div>
            <Card>
              <ol className="rule-list-full">
                {group.visible.map((rule) => (
                  <li key={rule.id} className="rule" id={rule.id}>
                    <span className="rule-id mono">{rule.id}</span>
                    <div className="rule-body">
                      <h3 className="rule-title">{rule.title}</h3>
                      <dl className="rule-wt">
                        <dt>เมื่อ</dt>
                        <dd>{rule.when}</dd>
                        <dt>ระบบ</dt>
                        <dd>{rule.then}</dd>
                      </dl>
                      {rule.params.length > 0 && (
                        <ul className="param-chips" aria-label="ค่าที่ใช้อยู่">
                          {rule.params.map((p) => (
                            <li key={p.key} className={p.changed ? "param-chip changed" : "param-chip"}>
                              <span>{p.label}</span>
                              <strong className="num">
                                {num(p.value, 2)}
                                {p.unit ? ` ${p.unit}` : ""}
                              </strong>
                              {p.changed && <span className="param-note">ค่าเริ่มต้น {num(p.default, 2)}</span>}
                              {p.effective != null && (
                                <span className="param-note">
                                  ⏱ ตอนสาธิต {num(p.effective, 1)}
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                      <div className="rule-meta">
                        {rule.principle && (
                          <span>
                            <BookOpen size={13} aria-hidden />
                            {rule.principle}
                          </span>
                        )}
                        {rule.source && (
                          <span>
                            <Quote size={13} aria-hidden />
                            {rule.source}
                          </span>
                        )}
                        {rule.code && (
                          <span className="mono">
                            <Code2 size={13} aria-hidden />
                            {rule.code}
                          </span>
                        )}
                        {rule.node &&
                          (admin ? (
                            <Link to={`/admin/3?node=${rule.node}`} className="topic-link">
                              <Workflow size={13} aria-hidden />
                              ดูในผัง: {rule.node_label}
                              <ArrowUpRight size={13} />
                            </Link>
                          ) : (
                            <span>
                              <Workflow size={13} aria-hidden />
                              ขั้นในผัง: {rule.node_label}
                            </span>
                          ))}
                        {rule.test &&
                          (admin ? (
                            <Link to="/admin/6" className="topic-link">
                              <FlaskConical size={13} aria-hidden />
                              มีชุดทดสอบ
                              <ArrowUpRight size={13} />
                            </Link>
                          ) : (
                            <span>
                              <FlaskConical size={13} aria-hidden />
                              มีชุดทดสอบใน Stress Test
                            </span>
                          ))}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </section>
        ))}
    </div>
  );
}
