import { useCallback, useEffect, useState } from "react";
import { CircleCheck, CircleX, Play, RotateCcw } from "lucide-react";
import { api } from "../../lib/api";
import { Badge, Button, Card, Spinner } from "../../components/ui";
import { TopicHeader } from "./AdminApp";
import { Section } from "./shared";

interface StressResult {
  id: string;
  title: string;
  input: string;
  expected: string;
  actual: string;
  passed: boolean;
  rules: string[];
}

const GROUPS = [
  {
    num: "6.1",
    title: "การดักจับพฤติกรรมผิดปกติ (Anti-Gaming และ Impasse)",
    cases: ["rapid_guess", "hint_spam", "idle", "cross_format"],
  },
  {
    num: "6.2",
    title: "ข้อมูลวิกฤตและข้อจำกัดทางเทคนิค",
    cases: ["double_submit", "disconnect", "malformed", "undo", "prompt_injection"],
  },
  {
    num: "7.1",
    title: "กลไกความปลอดภัยที่ส่งต่อให้ครู",
    cases: ["distress", "deadlock"],
  },
];

export default function Topic6() {
  const [results, setResults] = useState<Record<string, StressResult>>({});
  const [running, setRunning] = useState<string | null>(null);

  const runOne = useCallback(async (id: string) => {
    setRunning(id);
    try {
      const result = await api<StressResult>("admin", `/api/admin/stress/${id}`, { method: "POST" });
      setResults((current) => ({ ...current, [id]: result }));
    } finally {
      setRunning(null);
    }
  }, []);

  const runAll = useCallback(async () => {
    for (const group of GROUPS) for (const id of group.cases) await runOne(id);
  }, [runOne]);

  useEffect(() => {
    runAll();
  }, [runAll]);

  const all = Object.values(results);
  const passed = all.filter((r) => r.passed).length;

  return (
    <div className="page topic stack stack-lg">
      <TopicHeader id="6" lead="ทุกกรณีรันกับ engine ตัวจริงด้วยนาฬิกาจำลอง ไม่แตะข้อมูลนักเรียน กดรันซ้ำได้ระหว่างนำเสนอ">
        <div className="row">
          {all.length > 0 && (
            <Badge tone={passed === all.length ? "success" : "warning"}>
              ผ่าน {passed} จาก {all.length} กรณี
            </Badge>
          )}
          <Button variant="primary" icon={<RotateCcw size={16} />} loading={!!running} onClick={runAll}>
            รันทั้งหมดอีกครั้ง
          </Button>
        </div>
      </TopicHeader>

      {GROUPS.map((group) => (
        <Section key={group.num} num={group.num} title={group.title}>
          <div className="grid grid-2">
            {group.cases.map((id) => {
              const r = results[id];
              return (
                <Card key={id} className="card-pad stack stress-card">
                  <div className="spread">
                    <h3 className="subtitle">{r?.title ?? id}</h3>
                    {r ? (
                      r.passed ? (
                        <Badge tone="success">
                          <CircleCheck size={14} />
                          ผ่าน
                        </Badge>
                      ) : (
                        <Badge tone="danger">
                          <CircleX size={14} />
                          ไม่ผ่าน
                        </Badge>
                      )
                    ) : (
                      <Spinner label="" />
                    )}
                  </div>
                  {r && (
                    <dl className="stress-rows">
                      <div>
                        <dt>ข้อมูลที่ป้อน</dt>
                        <dd>{r.input}</dd>
                      </div>
                      <div>
                        <dt>สิ่งที่ควรเกิด</dt>
                        <dd>{r.expected}</dd>
                      </div>
                      <div>
                        <dt>สิ่งที่เกิดจริง</dt>
                        <dd className="strong">{r.actual}</dd>
                      </div>
                      {r.rules.length > 0 && (
                        <div>
                          <dt>กฎที่ทำงาน</dt>
                          <dd>
                            <ol className="rule-list">
                              {r.rules.map((rule, i) => (
                                <li key={i}>{rule}</li>
                              ))}
                            </ol>
                          </dd>
                        </div>
                      )}
                    </dl>
                  )}
                  <Button size="sm" variant="ghost" icon={<Play size={15} />} loading={running === id} onClick={() => runOne(id)} style={{ alignSelf: "flex-end", marginTop: "auto" }}>
                    รันกรณีนี้
                  </Button>
                </Card>
              );
            })}
          </div>
        </Section>
      ))}
    </div>
  );
}
