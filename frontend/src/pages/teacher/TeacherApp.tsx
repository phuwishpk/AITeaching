import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, Route, Routes } from "react-router";
import { Bell, BookMarked, Bot, LayoutDashboard, ListChecks, Sparkles, UsersRound } from "lucide-react";
import { api, clearAuth, getAuth } from "../../lib/api";
import { useLive } from "../../lib/hooks";
import type { Alert, Decision, StaffView, Telemetry } from "../../lib/types";
import type { Centroid } from "../../components/charts";
import { TopBar } from "../../components/Shell";
import { StaffLogin } from "../Login";
import Overview from "./Overview";
import AlertsPage from "./Alerts";
import ContentStudio from "./ContentStudio";
import SubjectEditor from "./SubjectEditor";
import Roster from "./Roster";
import TagReview from "./TagReview";
import AiReview from "./AiReview";
import StudentDrawer from "./StudentDrawer";
import RulesPage from "../shared/RulesPage";

export interface OverviewData {
  students: StaffView[];
  alerts: Alert[];
  telemetry: Telemetry;
  clusters: Centroid[];
  pending_tags: number;
  now: number;
}

export interface FeedEntry extends Decision {
  code: string;
  key: string;
}

interface TeacherContextValue {
  data: OverviewData | null;
  error: string | null;
  feed: FeedEntry[];
  reload: () => Promise<void>;
  openStudent: (code: string) => void;
  nameOf: (code: string) => string | null;
  ackAlert: (id: number) => Promise<void>;
  liveVersion: number;
  lastEvent: { code: string; n: number } | null;
}

const TeacherContext = createContext<TeacherContextValue | null>(null);

export function useTeacher() {
  const value = useContext(TeacherContext);
  if (!value) throw new Error("useTeacher ต้องอยู่ภายใน TeacherApp");
  return value;
}

export default function TeacherApp() {
  const [auth, setAuthState] = useState(() => getAuth("teacher"));
  if (!auth) return <StaffLogin role="teacher" onDone={() => setAuthState(getAuth("teacher"))} />;
  return (
    <TeacherShell
      onLogout={() => {
        api("teacher", "/api/auth/logout", { method: "POST" }).catch(() => {});
        clearAuth("teacher");
        setAuthState(null);
      }}
    />
  );
}

function TeacherShell({ onLogout }: { onLogout: () => void }) {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [student, setStudent] = useState<string | null>(null);
  const [liveVersion, setLiveVersion] = useState(0);
  const [lastEvent, setLastEvent] = useState<{ code: string; n: number } | null>(null);
  const logout = useRef(onLogout);
  logout.current = onLogout;

  const reload = useCallback(async () => {
    try {
      setData(await api<OverviewData>("teacher", "/api/teacher/overview"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    }
  }, []);

  useEffect(() => {
    reload();
    // ตัวชี้วัดรวม (Telemetry, กลุ่มผู้เรียน) คำนวณใหม่เป็นระยะ ส่วนสถานะรายคนมาทาง WebSocket
    const id = setInterval(reload, 30000);
    const expired = () => logout.current();
    window.addEventListener("auth-expired", expired);
    return () => {
      clearInterval(id);
      window.removeEventListener("auth-expired", expired);
    };
  }, [reload]);

  const connected = useLive("teacher", (message) => {
    if (message.code) setLastEvent((e) => ({ code: message.code, n: (e?.n ?? 0) + 1 }));
    if (message.type === "update") {
      const view = message.view as StaffView;
      setData((current) => {
        if (!current) return current;
        const index = current.students.findIndex((s) => s.code === view.code);
        const previous = index >= 0 ? current.students[index] : null;
        const merged = { ...previous, ...view, name: previous?.name ?? null, cluster: previous?.cluster ?? null, persona: previous?.persona };
        const students = index >= 0 ? current.students.map((s, i) => (i === index ? merged : s)) : [...current.students, merged];
        const fresh = view.kind === "sim" ? [] : ((message.alerts ?? []) as Alert[]);
        const alerts = fresh.length ? [...fresh, ...current.alerts] : current.alerts;
        return { ...current, students, alerts };
      });
      if (message.decisions?.length) {
        const entries = (message.decisions as Decision[]).map((d, i) => ({ ...d, code: view.code, key: `${view.code}-${d.ts}-${i}-${Math.random()}` }));
        setFeed((list) => [...entries.reverse(), ...list].slice(0, 60));
      }
      setLiveVersion((v) => v + 1);
    } else if (message.type === "suggested_tag") {
      setData((current) => (current ? { ...current, pending_tags: current.pending_tags + 1 } : current));
    } else if (message.type === "ai_log" || message.type === "chat" || message.type === "override") {
      setLiveVersion((v) => v + 1);
    }
  });

  const names = useMemo(() => new Map((data?.students ?? []).map((s) => [s.code, s.name ?? null])), [data?.students]);

  const ackAlert = useCallback(async (id: number) => {
    await api("teacher", `/api/teacher/alerts/${id}/ack`, { method: "POST" });
    setData((current) =>
      current ? { ...current, alerts: current.alerts.map((a) => (a.id === id ? { ...a, acknowledged: 1 } : a)) } : current,
    );
  }, []);

  const value: TeacherContextValue = {
    data,
    error,
    feed,
    reload,
    openStudent: setStudent,
    nameOf: (code) => names.get(code) ?? null,
    ackAlert,
    liveVersion,
    lastEvent,
  };

  const openAlerts = data?.alerts.filter((a) => !a.acknowledged && a.level !== "silent").length ?? 0;

  return (
    <TeacherContext.Provider value={value}>
      <div className="teacher">
        <TopBar
          role="ครู"
          onLogout={onLogout}
          right={
            <span className={`live-dot ${connected ? "on" : ""}`} title={connected ? "รับข้อมูลสดอยู่" : "กำลังเชื่อมต่อใหม่"}>
              <span className="btn-label">{connected ? "สด" : "ออฟไลน์"}</span>
            </span>
          }
        />
        <div className="side-layout">
          <nav className="sidebar" aria-label="เมนูครู">
            <NavItem to="/teacher" end icon={<LayoutDashboard size={17} />}>
              ภาพรวมห้องเรียน
            </NavItem>
            <NavItem to="/teacher/alerts" icon={<Bell size={17} />} count={openAlerts}>
              การแจ้งเตือน
            </NavItem>
            <NavItem to="/teacher/content" icon={<BookMarked size={17} />}>
              วิชาและชุดคำถาม
            </NavItem>
            <NavItem to="/teacher/roster" icon={<UsersRound size={17} />}>
              รายชื่อนักเรียน
            </NavItem>
            <NavItem to="/teacher/tags" icon={<Sparkles size={17} />} count={data?.pending_tags ?? 0} tone="calm">
              แท็กที่ AI เสนอ
            </NavItem>
            <NavItem to="/teacher/ai" icon={<Bot size={17} />}>
              ตรวจคำตอบของ AI
            </NavItem>
            <NavItem to="/teacher/rules" icon={<ListChecks size={17} />}>
              กฎของระบบ
            </NavItem>
            <div className="sidebar-foot xsmall faint">
              ครูเห็นชื่อจริงและ Risk Score ได้คนเดียว ฝั่งนักเรียนเห็นเพียงแถบความก้าวหน้า
            </div>
          </nav>
          <main className="side-main">
            <Routes>
              <Route index element={<Overview />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="content" element={<ContentStudio />} />
              <Route path="content/:subjectId" element={<SubjectEditor />} />
              <Route path="roster" element={<Roster />} />
              <Route path="tags" element={<TagReview />} />
              <Route path="ai" element={<AiReview />} />
              <Route path="rules" element={<RulesPage role="teacher" />} />
            </Routes>
          </main>
        </div>
        <StudentDrawer code={student} onClose={() => setStudent(null)} />
      </div>
    </TeacherContext.Provider>
  );
}

function NavItem({
  to,
  end,
  icon,
  count,
  tone,
  children,
}: {
  to: string;
  end?: boolean;
  icon: ReactNode;
  count?: number;
  tone?: "calm";
  children: ReactNode;
}) {
  return (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
      {icon}
      <span>{children}</span>
      {!!count && <span className={`nav-count ${tone === "calm" ? "nav-count-calm" : ""}`}>{count}</span>}
    </NavLink>
  );
}
