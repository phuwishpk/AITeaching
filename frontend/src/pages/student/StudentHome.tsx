import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowRight, BookOpen, CircleCheck, RotateCcw } from "lucide-react";
import { api, clearAuth, getAuth } from "../../lib/api";
import { useLoad } from "../../lib/hooks";
import { TopBar } from "../../components/Shell";
import { Badge, Button, Empty, Spinner, useToast } from "../../components/ui";
import { StudentLogin } from "../Login";
import GemIcon from "../../components/GemIcon";

interface SetInfo {
  id: string;
  name: string;
  description: string;
  subject: string;
  grade: string;
  target: string;
  status: "new" | "in_progress" | "paused" | "completed";
  gem: { icon: string; color: string } | null;
}

const STATUS = {
  new: { label: "ยังไม่เริ่ม", tone: "neutral" as const, action: "เริ่มทำ" },
  in_progress: { label: "กำลังทำ", tone: "accent" as const, action: "ทำต่อ" },
  paused: { label: "พักไว้", tone: "calm" as const, action: "ทำต่อจากเดิม" },
  completed: { label: "ทำจบแล้ว", tone: "success" as const, action: "ทำอีกครั้ง" },
};

export default function StudentHome() {
  const [auth, setAuthState] = useState(() => getAuth("student"));
  if (!auth) return <StudentLogin onDone={() => setAuthState(getAuth("student"))} />;
  return <Home code={auth.code ?? ""} onLogout={() => { clearAuth("student"); setAuthState(null); }} />;
}

function Home({ code, onLogout }: { code: string; onLogout: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const { data, loading, error } = useLoad(() => api<SetInfo[]>("student", "/api/student/sets"));
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    const expired = () => onLogout();
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, [onLogout]);

  const open = async (set: SetInfo) => {
    setBusy(set.id);
    try {
      await api("student", `/api/student/sets/${set.id}/start`, { body: { restart: set.status === "completed" } });
      navigate(`/student/${set.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "เปิดชุดคำถามไม่สำเร็จ", "warning");
      setBusy(null);
    }
  };

  return (
    <>
      <TopBar role={`นักเรียน · ${code}`} onLogout={onLogout} narrow />
      <main className="page page-student stack stack-lg">
        <section className="stack stack-sm fade-in">
          <p className="eyebrow">ยินดีต้อนรับ</p>
          <h1 className="title-xl">วันนี้อยากฝึกเรื่องไหนดี</h1>
          <p className="lead">เลือกชุดคำถามได้เลย ระบบจะปรับโจทย์ให้พอดีกับจังหวะของเรา ถ้าติดตรงไหนมีคำใบ้ทีละขั้นคอยช่วย</p>
        </section>
        {loading && <Spinner />}
        {error && <Empty>{error}</Empty>}
        {data && data.length === 0 && <Empty>ยังไม่มีชุดคำถามที่เปิดให้ทำ</Empty>}
        <section className="set-grid">
          {data?.map((set) => {
            const status = STATUS[set.status];
            return (
              <article key={set.id} className="card card-hover set-card fade-in">
                <div className="spread">
                  {/* Gem ตั้งชื่อวิชาเป็นชื่อเดียวกับ Gem จึงแสดงระดับชั้นแทน */}
                  <span className="eyebrow">{set.gem ? set.grade || "Gem" : set.subject}</span>
                  <Badge tone={status.tone} dot>
                    {status.label}
                  </Badge>
                </div>
                <div className="row" style={{ alignItems: "center" }}>
                  {set.gem && <GemIcon icon={set.gem.icon} color={set.gem.color} size={38} />}
                  <h2 className="title">{set.name}</h2>
                </div>
                <p className="small muted">{set.description}</p>
                <div className="row row-sm row-nowrap small faint" style={{ alignItems: "flex-start" }}>
                  <BookOpen size={15} style={{ flex: "none", marginTop: 3 }} />
                  <span>เป้าหมาย: {set.target}</span>
                </div>
                <div className="set-card-foot">
                  <Button
                    variant={set.status === "completed" ? "secondary" : "primary"}
                    loading={busy === set.id}
                    onClick={() => open(set)}
                    icon={set.status === "completed" ? <RotateCcw size={16} /> : set.status === "new" ? <ArrowRight size={16} /> : <CircleCheck size={16} />}
                  >
                    {status.action}
                  </Button>
                </div>
              </article>
            );
          })}
        </section>
      </main>
    </>
  );
}
