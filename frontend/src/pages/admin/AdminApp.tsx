import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router";
import { Activity as ActivityIcon, ListChecks, Presentation, Settings as SettingsIcon } from "lucide-react";
import { api, clearAuth, getAuth } from "../../lib/api";
import { useLive } from "../../lib/hooks";
import type { StaffView } from "../../lib/types";
import type { FlowEdge, FlowNode, FlowPosition } from "../../components/FlowMap";
import type { Principle } from "../../components/PrincipleCard";
import { TopBar } from "../../components/Shell";
import { Button } from "../../components/ui";
import { StaffLogin } from "../Login";
import Topic1 from "./Topic1";
import Topic2 from "./Topic2";
import Topic3 from "./Topic3";
import Topic4 from "./Topic4";
import Topic5 from "./Topic5";
import Topic6 from "./Topic6";
import Topic7 from "./Topic7";
import Settings from "./Settings";
import RulesPage from "../shared/RulesPage";
import Activity from "./Activity";

export interface FlowData {
  nodes: FlowNode[];
  edges: FlowEdge[];
  labels: Record<string, string>;
  cards: Record<string, Principle>;
  positions: (FlowPosition & { set_id: string; hint_level: number; remedial_round: number | null; since: number })[];
  now: number;
}

export interface ScenarioEvent {
  name: string;
  step: number;
  total: number;
  action: string;
  position: string;
  rules: string[];
  code: string;
  ts: number;
}

interface AdminContextValue {
  flow: FlowData | null;
  reloadFlow: () => Promise<void>;
  scenarios: ScenarioEvent[];
  present: boolean;
  liveVersion: number;
  lastEvent: { code: string; n: number } | null;
}

const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin() {
  const value = useContext(AdminContext);
  if (!value) throw new Error("useAdmin ต้องอยู่ภายใน AdminApp");
  return value;
}

export const TOPICS = [
  { id: "1", short: "ปัญหา", title: "ที่มาและสภาพปัญหาในสถานศึกษา" },
  { id: "2", short: "สถาปัตยกรรม", title: "สถาปัตยกรรม 4 แบบจำลอง" },
  { id: "3", short: "ผังตรรกะ", title: "พิมพ์เขียวตรรกะระบบและการไหลของข้อมูล" },
  { id: "4", short: "AI", title: "เครื่องมือและการบูรณาการ AI" },
  { id: "5", short: "สาธิต", title: "สาธิตการทำงานของต้นแบบ" },
  { id: "6", short: "Stress Test", title: "การทดสอบจุดบอดและกรณีข้อยกเว้น" },
  { id: "7", short: "HITL · จริยธรรม", title: "การควบคุมโดยมนุษย์ จริยธรรม และความเป็นส่วนตัว" },
];

const PRESENT_KEY = "adaptive-tutor:present";

export default function AdminApp() {
  const [auth, setAuthState] = useState(() => getAuth("admin"));
  if (!auth) return <StaffLogin role="admin" onDone={() => setAuthState(getAuth("admin"))} />;
  return (
    <AdminShell
      onLogout={() => {
        api("admin", "/api/auth/logout", { method: "POST" }).catch(() => {});
        clearAuth("admin");
        setAuthState(null);
      }}
    />
  );
}

function AdminShell({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [flow, setFlow] = useState<FlowData | null>(null);
  const [scenarios, setScenarios] = useState<ScenarioEvent[]>([]);
  const [liveVersion, setLiveVersion] = useState(0);
  const [lastEvent, setLastEvent] = useState<{ code: string; n: number } | null>(null);
  const [present, setPresent] = useState(() => {
    try {
      return localStorage.getItem(PRESENT_KEY) === "1";
    } catch {
      return false;
    }
  });
  const logout = useRef(onLogout);
  logout.current = onLogout;

  const reloadFlow = useCallback(async () => {
    try {
      setFlow(await api<FlowData>("admin", "/api/admin/flow"));
    } catch {
      /* หน้าแต่ละแท็บแสดงสถานะเอง */
    }
  }, []);

  useEffect(() => {
    reloadFlow();
    const expired = () => logout.current();
    window.addEventListener("auth-expired", expired);
    return () => window.removeEventListener("auth-expired", expired);
  }, [reloadFlow]);

  useEffect(() => {
    try {
      localStorage.setItem(PRESENT_KEY, present ? "1" : "0");
    } catch {
      /* ไม่จำก็ได้ */
    }
  }, [present]);

  // Presentation View: ใช้ลูกศรซ้ายขวาเปลี่ยนหัวข้อ
  useEffect(() => {
    if (!present) return;
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const current = TOPICS.findIndex((t) => location.pathname.endsWith(`/admin/${t.id}`));
      if (current < 0) return;
      if (event.key === "ArrowRight" && current < TOPICS.length - 1) navigate(`/admin/${TOPICS[current + 1].id}`);
      if (event.key === "ArrowLeft" && current > 0) navigate(`/admin/${TOPICS[current - 1].id}`);
      if (event.key === "Escape") setPresent(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [present, location.pathname, navigate]);

  const connected = useLive("admin", (message) => {
    if (message.code) setLastEvent((e) => ({ code: message.code, n: (e?.n ?? 0) + 1 }));
    if (message.type === "update") {
      const view = message.view as StaffView;
      setFlow((current) => {
        if (!current) return current;
        const entry = {
          code: view.code,
          kind: view.kind,
          set_id: view.set_id ?? "",
          position: view.position ?? "",
          path: view.path ?? "",
          item: view.item?.id ?? null,
          hint_level: view.item?.hint_level ?? 0,
          remedial_round: view.remedial?.round ?? null,
          last_edges: view.last_decision?.edges ?? [],
          last_rule: view.last_decision?.rule ?? null,
          since: view.position_since ?? Date.now() / 1000,
        };
        const exists = current.positions.some((p) => p.code === view.code);
        return {
          ...current,
          positions: exists ? current.positions.map((p) => (p.code === view.code ? entry : p)) : [...current.positions, entry],
        };
      });
      setLiveVersion((v) => v + 1);
    } else if (message.type === "scenario") {
      setScenarios((list) => [{ ...(message as ScenarioEvent), ts: Date.now() / 1000 }, ...list].slice(0, 80));
    } else {
      setLiveVersion((v) => v + 1);
    }
  });

  return (
    <AdminContext.Provider value={{ flow, reloadFlow, scenarios, present, liveVersion, lastEvent }}>
      <div className={present ? "admin present" : "admin"}>
        <TopBar
          role="ผู้ดูแลระบบ"
          onLogout={onLogout}
          right={
            <>
              <span className={`live-dot ${connected ? "on" : ""}`} title={connected ? "รับข้อมูลสดอยู่" : "กำลังเชื่อมต่อใหม่"}>
                <span className="btn-label">{connected ? "สด" : "ออฟไลน์"}</span>
              </span>
              <Button
                variant={present ? "soft" : "ghost"}
                size="sm"
                className="hide-mobile"
                icon={<Presentation size={16} />}
                onClick={() => setPresent((v) => !v)}
                aria-pressed={present}
                title="ขยายตัวอักษรสำหรับฉายบนจอ ใช้ลูกศรซ้ายขวาเปลี่ยนหัวข้อ"
              >
                Presentation View
              </Button>
              <NavLink
                to="/admin/settings"
                aria-label="ตั้งค่า"
                className={({ isActive }) => `btn btn-ghost btn-sm ${isActive ? "is-active" : ""}`}
              >
                <SettingsIcon size={16} />
                <span className="btn-label">ตั้งค่า</span>
              </NavLink>
            </>
          }
        />
        <nav className="topic-nav" aria-label="หัวข้อการนำเสนอ">
          <div className="topic-nav-inner">
            {TOPICS.map((topic) => (
              <NavLink key={topic.id} to={`/admin/${topic.id}`} className={({ isActive }) => `topic-tab ${isActive ? "active" : ""}`} title={topic.title}>
                <span className="topic-num">{topic.id}</span>
                <span>{topic.short}</span>
              </NavLink>
            ))}
            <span className="topic-sep" aria-hidden />
            <NavLink to="/admin/activity" className={({ isActive }) => `topic-tab ${isActive ? "active" : ""}`} title="นักเรียนทำอะไร และการกระทำเข้าไปตรงไหนในผัง">
              <span className="topic-num">
                <ActivityIcon size={14} />
              </span>
              <span>กิจกรรมสด</span>
            </NavLink>
            <NavLink to="/admin/rules" className={({ isActive }) => `topic-tab ${isActive ? "active" : ""}`} title="กฎทั้งหมดที่ระบบใช้ตัดสิน">
              <span className="topic-num">
                <ListChecks size={14} />
              </span>
              <span>กฎทั้งหมด</span>
            </NavLink>
          </div>
        </nav>
        <main>
          <Routes>
            <Route index element={<Navigate to="3" replace />} />
            <Route path="1" element={<Topic1 />} />
            <Route path="2" element={<Topic2 />} />
            <Route path="3" element={<Topic3 />} />
            <Route path="4" element={<Topic4 />} />
            <Route path="5" element={<Topic5 />} />
            <Route path="6" element={<Topic6 />} />
            <Route path="7" element={<Topic7 />} />
            <Route path="settings" element={<Settings />} />
            <Route path="rules" element={<RulesPage role="admin" />} />
            <Route path="activity" element={<Activity />} />
            <Route path="*" element={<Navigate to="3" replace />} />
          </Routes>
        </main>
      </div>
    </AdminContext.Provider>
  );
}

export function TopicHeader({ id, lead, children }: { id: string; lead?: string; children?: ReactNode }) {
  const topic = TOPICS.find((t) => t.id === id)!;
  return (
    <header className="topic-head fade-in">
      <div className="stack stack-sm">
        <p className="eyebrow">หัวข้อที่ {id}</p>
        <h1 className="title-xl">{topic.title}</h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {children}
    </header>
  );
}
