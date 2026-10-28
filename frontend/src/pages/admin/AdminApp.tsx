import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";
import { Activity as ActivityIcon, ArrowLeft, ArrowRight, Gem, ListChecks, Presentation, Settings as SettingsIcon, UsersRound } from "lucide-react";
import { api, clearAuth, getAuth, staffLogout } from "../../lib/api";
import { useLive } from "../../lib/hooks";
import type { StaffView } from "../../lib/types";
import type { FlowEdge, FlowNode, FlowPosition } from "../../components/FlowMap";
import type { Principle } from "../../components/PrincipleCard";
import { TopBar } from "../../components/Shell";
import SideNav from "../../components/SideNav";
import { Button } from "../../components/ui";
import { StaffEnter } from "../Login";
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
import AdminGems from "./AdminGems";

export interface FlowLane {
  id: string;
  name: string;
  color: string;
  count: number;
}

export interface FlowData {
  nodes: FlowNode[];
  edges: FlowEdge[];
  labels: Record<string, string>;
  cards: Record<string, Principle>;
  lanes: FlowLane[];
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
  { id: "1", menu: "ปัญหาและความต้องการ", title: "ที่มาและสภาพปัญหาในสถานศึกษา" },
  { id: "2", menu: "สถาปัตยกรรม 4 แบบจำลอง", title: "สถาปัตยกรรม 4 แบบจำลอง" },
  { id: "3", menu: "ผังตรรกะสด", title: "พิมพ์เขียวตรรกะระบบและการไหลของข้อมูล" },
  { id: "4", menu: "เครื่องมือ AI", title: "เครื่องมือและการบูรณาการ AI" },
  { id: "5", menu: "สาธิตต้นแบบ", title: "สาธิตการทำงานของต้นแบบ" },
  { id: "6", menu: "ทดสอบกรณีพิเศษ", title: "การทดสอบจุดบอดและกรณีข้อยกเว้น" },
  { id: "7", menu: "มนุษย์กำกับ · จริยธรรม", title: "การควบคุมโดยมนุษย์ จริยธรรม และความเป็นส่วนตัว" },
];

const PRESENT_KEY = "adaptive-tutor:present";

export default function AdminApp() {
  const [auth, setAuthState] = useState(() => getAuth("admin"));
  const navigate = useNavigate();
  if (!auth) return <StaffEnter role="admin" onDone={() => setAuthState(getAuth("admin"))} />;
  return (
    <AdminShell
      onLogout={() => {
        // ออกจากบัญชีทั้งหน้าครูและหน้าผู้ดูแลระบบ แล้วกลับหน้าแรก (ล็อกอินบัญชีอื่นได้)
        staffLogout();
        navigate("/");
      }}
      onExpired={() => {
        // token หมดอายุ: โหมดเดิมขอ token ใหม่แล้วอยู่หน้าเดิม มีบัญชีผู้ใช้กลับไปล็อกอินที่หน้าแรกแล้วพากลับมาหน้านี้
        clearAuth("admin");
        setAuthState(null);
      }}
    />
  );
}

function AdminShell({ onLogout, onExpired }: { onLogout: () => void; onExpired: () => void }) {
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
  const expire = useRef(onExpired);
  expire.current = onExpired;

  const reloadFlow = useCallback(async () => {
    try {
      setFlow(await api<FlowData>("admin", "/api/admin/flow"));
    } catch {
      /* หน้าแต่ละแท็บแสดงสถานะเอง */
    }
  }, []);

  useEffect(() => {
    reloadFlow();
    const expired = () => expire.current();
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

  useLive("admin", (message) => {
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
          role={getAuth("admin")?.code ? `ผู้ดูแลระบบ · ${getAuth("admin")?.code}` : "ผู้ดูแลระบบ"}
          onLogout={onLogout}
          right={
            <>
              {/* บัญชีเดียวเข้าได้ทั้งสองหน้า สลับได้โดยไม่ต้องล็อกอินใหม่ */}
              {getAuth("teacher") && (
                <Link to="/teacher" className="btn btn-ghost btn-sm hide-mobile">
                  <UsersRound size={16} />
                  หน้าครู
                </Link>
              )}
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
            </>
          }
        />
        <div className="side-layout">
          <SideNav
            label="เมนูผู้ดูแลระบบ"
            sections={[
              {
                title: "นำเสนอตามลำดับสไลด์",
                items: TOPICS.map((topic) => ({
                  to: `/admin/${topic.id}`,
                  label: topic.menu,
                  icon: <span className="nav-num">{topic.id}</span>,
                })),
              },
              {
                title: "ดูระบบทำงานจริง",
                items: [
                  { to: "/admin/activity", label: "กิจกรรมสดของนักเรียน", icon: <ActivityIcon size={17} /> },
                  { to: "/admin/rules", label: "กฎทั้งหมด", icon: <ListChecks size={17} /> },
                ],
              },
              {
                title: "สิ่งที่ครูออกแบบ",
                items: [{ to: "/admin/gems", label: "Gem ที่ครูออกแบบ", icon: <Gem size={17} /> }],
              },
              {
                title: "ระบบ",
                items: [{ to: "/admin/settings", label: "ตั้งค่า (API key)", icon: <SettingsIcon size={17} /> }],
              },
            ]}
            footer="หน้านี้เห็นนักเรียนเป็นรหัสเท่านั้น ใช้ Presentation View ตอนฉายจอ"
          />
          <main className="side-main">
            <Routes>
              <Route index element={<Navigate to="1" replace />} />
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
              <Route path="gems" element={<AdminGems />} />
              <Route path="*" element={<Navigate to="1" replace />} />
            </Routes>
            <TopicPager />
          </main>
        </div>
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

// ท้ายหน้าของแต่ละหัวข้อ: ไปหัวข้อก่อนหน้าหรือถัดไปตามลำดับสไลด์
function TopicPager() {
  const location = useLocation();
  const index = TOPICS.findIndex((t) => location.pathname.endsWith(`/admin/${t.id}`));
  if (index < 0) return null;
  const prev = TOPICS[index - 1];
  const next = TOPICS[index + 1];
  return (
    <nav className="topic-pager" aria-label="เปลี่ยนหัวข้อ">
      {prev ? (
        <Link to={`/admin/${prev.id}`} className="pager-link">
          <ArrowLeft size={16} />
          <span className="stack" style={{ gap: 0 }}>
            <span className="xsmall faint">หัวข้อที่ {prev.id}</span>
            <span>{prev.menu}</span>
          </span>
        </Link>
      ) : (
        <span />
      )}
      <span className="xsmall faint">
        หัวข้อ {index + 1} จาก {TOPICS.length}
      </span>
      {next ? (
        <Link to={`/admin/${next.id}`} className="pager-link pager-next">
          <span className="stack" style={{ gap: 0 }}>
            <span className="xsmall faint">หัวข้อที่ {next.id}</span>
            <span>{next.menu}</span>
          </span>
          <ArrowRight size={16} />
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}

