import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { api, setAuth, type Role } from "../lib/api";
import { BrandMark, ThemeToggle } from "../components/Shell";
import { Button, Field, Spinner } from "../components/ui";

function LoginFrame({ children }: { children: ReactNode }) {
  return (
    <div className="login-page">
      <header className="landing-top">
        <Link to="/" className="brand">
          <BrandMark />
          <span>Adaptive Tutor</span>
        </Link>
        <ThemeToggle />
      </header>
      <main className="login-main">
        <div className="card login-card fade-in">{children}</div>
        <Link to="/" className="small muted row row-sm" style={{ justifyContent: "center" }}>
          <ArrowLeft size={14} /> กลับไปเลือกบทบาท
        </Link>
      </main>
    </div>
  );
}

export function StudentLogin({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ token: string; code: string }>(null, "/api/auth/student", { body: { code } });
      setAuth("student", { token: result.token, code: result.code });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  };

  return (
    <LoginFrame>
      <form onSubmit={submit} className="stack" style={{ gap: 20 }}>
        <div className="stack stack-sm">
          <p className="eyebrow">นักเรียน</p>
          <h1 className="title-lg">ใส่รหัสนักเรียนของเรา</h1>
          <p className="small muted">ระบบรู้จักเราจากรหัสนี้เท่านั้น ไม่เก็บชื่อจริง</p>
        </div>
        <Field label="รหัสนักเรียน" hint="รหัสตัวอย่างสำหรับสาธิต: S-01 ถึง S-06">
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
        {error && <p className="small" style={{ color: "var(--text-2)" }}>{error}</p>}
        <Button variant="primary" size="lg" block loading={busy} disabled={!code.trim()} type="submit">
          เข้าเรียน
        </Button>
      </form>
    </LoginFrame>
  );
}

// ครูและ Admin: ถ้าเซิร์ฟเวอร์ตั้งรหัสผ่านไว้ (ไฟล์ .env) ให้ใส่รหัสก่อน ไม่ตั้งก็ขอ token แล้วเข้าหน้าเลย
export function StaffEnter({ role, onDone }: { role: Exclude<Role, "student">; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [needsPassword, setNeedsPassword] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const label = role === "teacher" ? "หน้าครู" : "หน้าผู้ดูแลระบบ";

  const enter = async (secret?: string) => {
    const result = await api<{ token: string }>(null, "/api/auth/staff", { body: { role, password: secret } });
    setAuth(role, { token: result.token });
    onDone();
  };

  useEffect(() => {
    let live = true;
    api<Record<string, boolean>>(null, "/api/auth/staff-mode")
      .then(async (mode) => {
        if (!live) return;
        if (mode[role]) {
          setNeedsPassword(true);
          return;
        }
        setNeedsPassword(false);
        await enter();
      })
      .catch((err) => live && setError(err instanceof Error ? err.message : "เข้าระบบไม่สำเร็จ"));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, attempt]);

  if (needsPassword) {
    const submit = async (event: FormEvent) => {
      event.preventDefault();
      setBusy(true);
      setError(null);
      try {
        await enter(password);
      } catch (err) {
        setError(err instanceof Error ? err.message : "เข้าระบบไม่สำเร็จ");
      } finally {
        setBusy(false);
      }
    };
    return (
      <LoginFrame>
        <form onSubmit={submit} className="stack" style={{ gap: 20 }}>
          <div className="stack stack-sm">
            <p className="eyebrow">{role === "teacher" ? "ครู" : "ผู้ดูแลระบบ"}</p>
            <h1 className="title-lg">ใส่รหัสผ่านเพื่อเข้า{label}</h1>
            <p className="small muted">{label}มีข้อมูลนักเรียน จึงต้องใส่รหัสผ่านที่ผู้ดูแลเซิร์ฟเวอร์ตั้งไว้</p>
          </div>
          <Field label="รหัสผ่าน">
            <input
              className="input input-lg"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              autoComplete="current-password"
              aria-invalid={!!error}
            />
          </Field>
          {error && <p className="small" style={{ color: "var(--text-2)" }}>{error}</p>}
          <Button variant="primary" size="lg" block loading={busy} disabled={!password} type="submit">
            เข้า{label}
          </Button>
        </form>
      </LoginFrame>
    );
  }

  if (!error) return <Spinner />;
  return (
    <LoginFrame>
      <div className="stack" style={{ gap: 16 }}>
        <h1 className="title-lg">เข้า{role === "teacher" ? "หน้าครู" : "หน้าผู้ดูแลระบบ"}ไม่สำเร็จ</h1>
        <p className="small muted">{error}</p>
        <Button
          variant="primary"
          size="lg"
          block
          onClick={() => {
            setError(null);
            setAttempt((n) => n + 1);
          }}
        >
          ลองอีกครั้ง
        </Button>
      </div>
    </LoginFrame>
  );
}
