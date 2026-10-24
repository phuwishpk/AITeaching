import { useEffect } from "react";
import { ArrowRight, BookOpen, Lightbulb, LogIn, LogOut, UsersRound } from "lucide-react";
import { api } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { Badge, Drawer, Empty, Spinner } from "../../components/ui";

// แผงข้อมูลของกลุ่มกล่องในผัง (สีเดียวกันบนผัง): ดูแลเรื่องอะไร เข้าและออกทางไหน และมีขั้นอะไรบ้างตามลำดับ

interface LaneNode {
  id: string;
  label: string;
  kind: "position" | "gate" | "step" | "event";
  text: string;
  students: number;
}

interface LaneDetail {
  id: string;
  name: string;
  color: string;
  question: string;
  summary: string;
  enter: string[];
  exit: string[];
  principles: string[];
  example: string;
  nodes: LaneNode[];
  students: number;
}

const KIND_LABEL: Record<LaneNode["kind"], string> = {
  position: "ตำแหน่ง",
  gate: "ด่านตัดสินใจ",
  step: "ขั้นประมวลผล",
  event: "เหตุการณ์",
};

export default function LaneInspector({
  laneId,
  onClose,
  onOpenNode,
}: {
  laneId: string | null;
  onClose: () => void;
  onOpenNode: (id: string) => void;
}) {
  const lane = useLoad(() => (laneId ? api<LaneDetail>("admin", `/api/admin/flow/lanes/${laneId}`) : Promise.resolve(null)), [laneId]);
  const data = lane.data;

  useEffect(() => {
    document.querySelector(".drawer")?.scrollTo({ top: 0 });
  }, [laneId]);

  return (
    <Drawer
      open={!!laneId}
      onClose={onClose}
      title={
        data ? (
          <div className="stack" style={{ gap: 2 }}>
            <span className="row row-sm">
              <Badge>กลุ่มในผัง</Badge>
              <span className="xsmall faint">{data.nodes.length} ขั้น · นักเรียนอยู่ในกลุ่มนี้ {data.students} คน</span>
            </span>
            <span className="subtitle row row-sm">
              <span className="lane-dot lane-dot-lg" style={{ background: data.color }} />
              {data.name}
            </span>
          </div>
        ) : (
          "กำลังโหลด"
        )
      }
    >
      {lane.loading && !data && <Spinner />}
      {lane.error && <Empty>{lane.error}</Empty>}
      {data && (
        <div className="stack stack-lg inspector">
          <section className="lane-question" style={{ borderColor: data.color }}>
            <span className="xsmall muted">คำถามที่กลุ่มนี้ตอบ</span>
            <p className="title">{data.question}</p>
            <p className="small muted">{data.summary}</p>
          </section>

          <div className="route-grid">
            <section className="stack stack-sm">
              <h4 className="inspector-title">
                <LogIn size={16} />
                นักเรียนเข้ามาเมื่อ
              </h4>
              <ul className="bullet-list small">
                {data.enter.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </section>
            <section className="stack stack-sm">
              <h4 className="inspector-title">
                <LogOut size={16} />
                ออกจากกลุ่มไปทาง
              </h4>
              <ul className="bullet-list small">
                {data.exit.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </section>
          </div>

          <section className="stack stack-sm">
            <h4 className="inspector-title">ขั้นในกลุ่มนี้ตามลำดับ</h4>
            <p className="xsmall faint">กดแต่ละขั้นเพื่อดูว่าทำอะไรทีละขั้น มาจากไหนไปไหน และปรับค่าอะไรได้</p>
            <ol className="lane-steps">
              {data.nodes.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => onOpenNode(n.id)}>
                    <span className="spread">
                      <span className="row row-sm">
                        <span className="strong small">{n.label}</span>
                        <Badge tone={n.kind === "gate" ? "info" : n.kind === "position" ? "accent" : "neutral"}>{KIND_LABEL[n.kind]}</Badge>
                      </span>
                      <span className="row row-sm xsmall faint">
                        {n.students > 0 && (
                          <>
                            <UsersRound size={13} />
                            {n.students}
                          </>
                        )}
                        <ArrowRight size={14} />
                      </span>
                    </span>
                    {n.text && <span className="xsmall muted">{n.text}</span>}
                  </button>
                </li>
              ))}
            </ol>
          </section>

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <Lightbulb size={16} />
              ตัวอย่างสถานการณ์
            </h4>
            <p className="example-box small">{data.example}</p>
          </section>

          <section className="stack stack-sm">
            <h4 className="inspector-title">
              <BookOpen size={16} />
              หลักการที่ใช้
            </h4>
            <ul className="pill-list uses-list">
              {data.principles.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Drawer>
  );
}
