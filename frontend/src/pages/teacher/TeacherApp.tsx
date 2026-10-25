import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Route, Routes, useNavigate } from "react-router";
import { Bell, BellOff, BellRing, Bot, Gem, LayoutDashboard, ListChecks, MessagesSquare, Sparkles, UsersRound } from "lucide-react";
import { api, clearAuth, getAuth } from "../../lib/api";
import { useLive } from "../../lib/hooks";
import { notifyAlert, notifyEnabled, setNotify } from "../../lib/notify";
import { Button } from "../../components/ui";
import type { Alert, Decision, StaffView, Telemetry } from "../../lib/types";
import type { Centroid } from "../../components/charts";
import { TopBar } from "../../components/Shell";
import SideNav from "../../components/SideNav";
import { StaffEnter } from "../Login";
import Overview from "./Overview";
import AlertsPage from "./Alerts";
import ContentStudio from "./ContentStudio";
import SubjectEditor from "./SubjectEditor";
import Roster from "./Roster";
import TagReview from "./TagReview";
import AiReview from "./AiReview";
import Inbox from "./Inbox";
import GemList from "./GemList";
import GemFlowPage from "./GemFlow";
import GemEditor from "./GemEditor";
import StudentDrawer, { type DrawerTab } from "./StudentDrawer";
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
  openStudent: (code: string, tab?: DrawerTab) => void;
  unread: Record<string, number>;
  markRead: (code: string) => void;
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
  const navigate = useNavigate();
  if (!auth) return <StaffEnter role="teacher" onDone={() => setAuthState(getAuth("teacher"))} />;
  return (
    <TeacherShell
      onLogout={() => {
        // ไม่มี PIN แล้ว อยู่หน้าเดิมจะเข้าใหม่ทันที จึงพากลับหน้าเลือกบทบาท
        api("teacher", "/api/auth/logout", { method: "POST" }).catch(() => {});
        clearAuth("teacher");
        navigate("/");
      }}
      onExpired={() => {
        // token หมดอายุ (เช่น server เริ่มใหม่): ขอ token ใหม่แล้วอยู่หน้าเดิม
        clearAuth("teacher");
        setAuthState(null);
      }}
    />
  );
}

function TeacherShell({ onLogout, onExpired }: { onLogout: () => void; onExpired: () => void }) {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feed, setFeed] = useState<FeedEntry[]>([]);
  const [student, setStudent] = useState<{ code: string; tab: DrawerTab } | null>(null);
  // ข้อความจากนักเรียนที่ครูยังไม่ได้เปิดอ่าน
  const [unread, setUnread] = useState<Record<string, number>>({});
  const openTab = useRef<{ code: string; tab: DrawerTab } | null>(null);
  const markRead = useCallback((code: string) => setUnread((u) => (u[code] ? { ...u, [code]: 0 } : u)), []);
  openTab.current = student;
  const [liveVersion, setLiveVersion] = useState(0);
  const [lastEvent, setLastEvent] = useState<{ code: string; n: number } | null>(null);
  const expire = useRef(onExpired);
  expire.current = onExpired;
  const namesRef = useRef(new Map<string, string | null>());
  const [sound, setSound] = useState(notifyEnabled);

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
    const expired = () => expire.current();
    window.addEventListener("auth-expired", expired);
    return () => {
      clearInterval(id);
      window.removeEventListener("auth-expired", expired);
    };
  }, [reload]);

  useLive("teacher", (message) => {
    if (message.code) setLastEvent((e) => ({ code: message.code, n: (e?.n ?? 0) + 1 }));
    if (message.type === "message" && message.message?.sender === "student") {
      const reading = openTab.current?.code === message.code && openTab.current?.tab === "messages";
      if (!reading) setUnread((u) => ({ ...u, [message.code]: (u[message.code] ?? 0) + 1 }));
    }
    if (message.type === "update") {
      const view = message.view as StaffView;
      setData((current) => {
        if (!current) return current;
        const index = current.students.findIndex((s) => s.code === view.code);
        const previous = index >= 0 ? current.students[index] : null;
        const merged = { ...previous, ...view, name: previous?.name ?? null, cluster: previous?.cluster ?? null, persona: previous?.persona };
        const students = index >= 0 ? current.students.map((s, i) => (i === index ? merged : s)) : [...current.students, merged];
        const fresh = view.kind === "sim" ? [] : ((message.alerts ?? []) as Alert[]);
        fresh.forEach((a) => notifyAlert(a, namesRef.current.get(a.code) ?? a.code));
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
  namesRef.current = names;

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
    openStudent: (code, tab = "now") => setStudent({ code, tab }),
    unread,
    markRead,
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
          role={getAuth("teacher")?.code ? `ครู · ${getAuth("teacher")?.code}` : "ครู"}
          onLogout={onLogout}
          right={
            <Button
              variant="ghost"
              size="sm"
              icon={sound ? <BellRing size={16} /> : <BellOff size={16} />}
              onClick={async () => setSound(await setNotify(!sound))}
              title={sound ? "ปิดเสียงและการแจ้งเตือนของเบราว์เซอร์" : "เปิดเสียงและการแจ้งเตือนของเบราว์เซอร์ เด้งแม้ไม่ได้เปิดหน้านี้อยู่"}
            >
              <span className="btn-label">{sound ? "แจ้งเตือนเปิด" : "แจ้งเตือนปิด"}</span>
            </Button>
          }
        />
        <div className="side-layout">
          <SideNav
            label="เมนูครู"
            sections={[
              {
                title: "สร้างบทเรียน",
                items: [{ to: "/teacher/gems", label: "Gem ของฉัน", icon: <Gem size={17} /> }],
              },
              {
                title: "ติดตามนักเรียน",
                items: [
                  { to: "/teacher", end: true, label: "ภาพรวมห้องเรียน", icon: <LayoutDashboard size={17} /> },
                  { to: "/teacher/alerts", label: "การแจ้งเตือน", icon: <Bell size={17} />, count: openAlerts },
                  {
                    to: "/teacher/inbox",
                    label: "แชตกับนักเรียน",
                    icon: <MessagesSquare size={17} />,
                    count: Object.values(unread).reduce((a, b) => a + b, 0),
                    tone: "calm",
                  },
                ],
              },
              {
                title: "ตรวจงานของ AI",
                items: [
                  { to: "/teacher/tags", label: "แท็กที่ AI เสนอ", icon: <Sparkles size={17} />, count: data?.pending_tags ?? 0, tone: "calm" },
                  { to: "/teacher/ai", label: "คำตอบของ AI", icon: <Bot size={17} /> },
                ],
              },
              {
                title: "จัดการชั้นเรียน",
                items: [
                  { to: "/teacher/roster", label: "รายชื่อนักเรียน", icon: <UsersRound size={17} /> },
                ],
              },
              {
                title: "คู่มือ",
                items: [{ to: "/teacher/rules", label: "กฎของระบบ", icon: <ListChecks size={17} /> }],
              },
            ]}
            footer="ครูเห็นชื่อจริงและ Risk Score ได้คนเดียว ฝั่งนักเรียนเห็นเพียงแถบความก้าวหน้า"
          />
          <main className="side-main">
            <Routes>
              <Route index element={<Overview />} />
              <Route path="gems" element={<GemList />} />
              <Route path="gems/new" element={<GemEditor />} />
              <Route path="gems/:gemId" element={<GemEditor />} />
              <Route path="gems/:gemId/flow" element={<GemFlowPage />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="inbox" element={<Inbox />} />
              <Route path="content" element={<ContentStudio />} />
              <Route path="content/:subjectId" element={<SubjectEditor />} />
              <Route path="roster" element={<Roster />} />
              <Route path="tags" element={<TagReview />} />
              <Route path="ai" element={<AiReview />} />
              <Route path="rules" element={<RulesPage role="teacher" />} />
            </Routes>
          </main>
        </div>
        <StudentDrawer
          code={student?.code ?? null}
          tab={student?.tab ?? "now"}
          onTab={(tab) => {
            setStudent((s) => (s ? { ...s, tab } : s));
            if (tab === "messages" && student) setUnread((u) => ({ ...u, [student.code]: 0 }));
          }}
          onClose={() => setStudent(null)}
        />
      </div>
    </TeacherContext.Provider>
  );
}
