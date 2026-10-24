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

// ครูและ Admin เข้าได้ทันทีโดยไม่ใช้ PIN: ขอ token ของบทบาทนั้นแล้วเข้าหน้าเลย
export function StaffEnter({ role, onDone }: { role: Exclude<Role, "student">; onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    api<{ token: string }>(null, "/api/auth/staff", { body: { role } })
      .then((result) => {
        if (!live) return;
        setAuth(role, { token: result.token });
        onDone();
      })
      .catch((err) => live && setError(err instanceof Error ? err.message : "เข้าระบบไม่สำเร็จ"));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, attempt]);

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
