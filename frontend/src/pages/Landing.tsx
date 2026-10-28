import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ArrowRight, GraduationCap, LogOut, Network, UsersRound } from "lucide-react";
import { BrandMark, ThemeToggle } from "../components/Shell";
import { Button, Field, Segmented, Spinner } from "../components/ui";
import { api, clearAuth, getAuth, setAuth, staffLogin, staffLogout } from "../lib/api";

// โหมดเดิม (เซิร์ฟเวอร์ยังไม่มีบัญชีผู้ใช้): เลือกบทบาทแล้วเข้าได้เลย
const ROLES = [
  {
    to: "/student",
    icon: <GraduationCap size={22} />,
    title: "นักเรียน",
    text: "ทำชุดคำถามที่ปรับตามจังหวะของตัวเอง มีคำใบ้ทีละขั้นและครูผู้ช่วยคอยถามนำ",
    action: "เข้าด้วยรหัสนักเรียน",
  },
  {
    to: "/teacher",
    icon: <UsersRound size={22} />,
    title: "ครู",
    text: "ดูแลนักเรียนรายคน รับการแจ้งเตือน สั่งแทรกแซงได้ทุกเมื่อ และจัดการชุดคำถาม",
    action: "เข้าหน้าครู",
  },
  {
    to: "/admin",
    icon: <Network size={22} />,
    title: "ผู้ดูแลระบบ",
    text: "ดูตรรกะของระบบแบบสด นักเรียนแต่ละคนอยู่ตรงไหนในผัง และหลักการเบื้องหลังทุกขั้น",
    action: "เข้าหน้าผู้ดูแลระบบ",
  },
];

// หน้าที่ส่งกลับมาให้ล็อกอินก่อน (เช่น เปิดลิงก์หน้าครูตรง ๆ) รับเฉพาะเส้นทางในเว็บนี้
function nextPath(raw: string | null): string | null {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : null;
}

export default function Landing() {
  const [accounts, setAccounts] = useState<boolean | null>(null);

  useEffect(() => {
    api<{ users?: boolean }>(null, "/api/auth/staff-mode")
      .then((mode) => setAccounts(!!mode.users))
      .catch(() => setAccounts(true));
  }, []);

  return (
    <div className="landing">
      <header className="landing-top">
        <div className="brand">
          <BrandMark />
          <span>Adaptive Tutor</span>
        </div>
        <ThemeToggle />
      </header>
      <main className={accounts ? "landing-main landing-split" : "landing-main"}>
        <section className="landing-hero fade-in">
          <p className="eyebrow">Intelligent Tutoring System</p>
          <h1 className="landing-title">ติวเตอร์ที่รอให้คิดก่อน แล้วค่อยช่วยทีละขั้น</h1>
          <p className="lead">
            ระบบอ่านร่องรอยการเรียนของนักเรียนแต่ละคน ปรับลำดับโจทย์ ความยาก และคำใบ้ให้พอดีกับเขตพัฒนาการ
            โดยไม่เฉลยคำตอบ และให้ครูเป็นผู้ตัดสินใจขั้นสุดท้ายเสมอ
          </p>
        </section>
        {accounts === null ? <Spinner /> : accounts ? <SignIn /> : <RoleCards />}
      </main>
    </div>
  );
}

function RoleCards() {
  return (
    <>
      <section className="role-grid">
        {ROLES.map((role, index) => (
          <Link key={role.to} to={role.to} className="card card-hover role-card fade-in" style={{ animationDelay: `${index * 60}ms` }}>
            <span className="role-icon">{role.icon}</span>
            <h2 className="title">{role.title}</h2>
            <p className="muted small">{role.text}</p>
            <span className="role-action">
              {role.action}
              <ArrowRight size={16} />
            </span>
          </Link>
        ))}
      </section>
      <p className="faint small landing-note">
        เปิดหลายแท็บพร้อมกันได้ ตอนสาธิตให้วางหน้านักเรียนคู่กับหน้าผู้ดูแลระบบ แล้วผังตรรกะจะขยับตามทุกครั้งที่ตอบ
      </p>
    </>
  );
}

// เข้าสู่ระบบอยู่เมื่อมี token ครบทั้งหน้าครูและหน้าผู้ดูแลระบบ (ล็อกอินครั้งเดียวได้ทั้งคู่)
function signedInName(): string | null {
  const teacher = getAuth("teacher");
  return teacher && getAuth("admin") ? teacher.code ?? "" : null;
}

function SignIn() {
  const [params] = useSearchParams();
  const next = nextPath(params.get("next"));
  const [who, setWho] = useState<"staff" | "student">(next?.startsWith("/student") ? "student" : "staff");
  const [name, setName] = useState(signedInName);

  return (
    <section className="card login-card signin-card fade-in" aria-label="เข้าสู่ระบบ">
      {name !== null ? (
        <SignedIn
          name={name}
          onLogout={() => {
            staffLogout();
            setName(null);
          }}
        />
      ) : (
        <div className="stack" style={{ gap: 20 }}>
          <div className="stack stack-sm">
            <h2 className="title-lg">เข้าสู่ระบบ</h2>
            <Segmented
              label="เข้าในฐานะ"
              options={[
                { id: "staff", label: "ครูและผู้ดูแลระบบ" },
                { id: "student", label: "นักเรียน" },
              ]}
              value={who}
              onChange={setWho}
            />
          </div>
          {who === "staff" ? <StaffForm next={next} /> : <StudentForm next={next} />}
        </div>
      )}
    </section>
  );
}

function SignedIn({ name, onLogout }: { name: string; onLogout: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="stack stack-sm">
        <p className="eyebrow">เข้าสู่ระบบอยู่</p>
        <h2 className="title-lg">{name || "บัญชีของคุณ"}</h2>
        <p className="small muted">เห็นเฉพาะ Gem นักเรียน และ API key ของบัญชีนี้</p>
      </div>
      <div className="stack stack-sm">
        <Button variant="primary" size="lg" block icon={<UsersRound size={18} />} onClick={() => navigate("/teacher")}>
          หน้าครู
        </Button>
        <Button size="lg" block icon={<Network size={18} />} onClick={() => navigate("/admin")}>
          หน้าผู้ดูแลระบบ
        </Button>
      </div>
      <Button variant="ghost" block icon={<LogOut size={16} />} onClick={onLogout}>
        ออกจากระบบ / สลับบัญชี
      </Button>
    </div>
  );
}

function StaffForm({ next }: { next: string | null }) {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await staffLogin(username.trim(), password);
      navigate(next && !next.startsWith("/student") ? next : "/teacher");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="stack" style={{ gap: 16 }}>
      <Field label="ชื่อผู้ใช้">
        <input
          className="input input-lg"
          value={username}
          onChange={(e) => setUsername(e.target.value.toLowerCase())}
          autoFocus
          autoComplete="username"
          autoCapitalize="off"
          spellCheck={false}
        />
      </Field>
      <Field label="รหัสผ่าน">
        <input
          className="input input-lg"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          aria-invalid={!!error}
        />
      </Field>
      {error && (
        <p className="small" role="alert" style={{ color: "var(--text-2)" }}>
          {error}
        </p>
      )}
      <Button variant="primary" size="lg" block loading={busy} disabled={!username.trim() || !password} type="submit">
        เข้าสู่ระบบ
      </Button>
      <p className="small muted">
        บัญชีเดียวใช้ได้ทั้งหน้าครูและหน้าผู้ดูแลระบบ เข้าจากเครื่องไหนก็ได้ แต่ละบัญชีเห็นเฉพาะ Gem นักเรียน และ API key ของตัวเอง
      </p>
    </form>
  );
}

function StudentForm({ next }: { next: string | null }) {
  const navigate = useNavigate();
  const [current, setCurrent] = useState(() => getAuth("student")?.code ?? null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const target = next?.startsWith("/student") ? next : "/student";

  if (current) {
    return (
      <div className="stack" style={{ gap: 12 }}>
        <Button variant="primary" size="lg" block icon={<GraduationCap size={18} />} onClick={() => navigate(target)}>
          เรียนต่อด้วยรหัส {current}
        </Button>
        <Button
          variant="ghost"
          block
          onClick={() => {
            clearAuth("student");
            setCurrent(null);
          }}
        >
          ใช้รหัสอื่น
        </Button>
      </div>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ token: string; code: string }>(null, "/api/auth/student", { body: { code } });
      setAuth("student", { token: result.token, code: result.code });
      navigate(target);
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="stack" style={{ gap: 16 }}>
      <Field label="รหัสนักเรียน" hint="ขอรหัสจากครูประจำวิชา ระบบรู้จักเราจากรหัสนี้เท่านั้น ไม่เก็บชื่อจริง">
        <input
          className="input input-lg mono"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="S-01"
          autoFocus
          autoComplete="off"
          aria-invalid={!!error}
        />
      </Field>
      {error && (
        <p className="small" role="alert" style={{ color: "var(--text-2)" }}>
          {error}
        </p>
      )}
      <Button variant="primary" size="lg" block loading={busy} disabled={!code.trim()} type="submit">
        เข้าเรียน
      </Button>
    </form>
  );
}
