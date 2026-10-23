import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowLeft, KeyRound } from "lucide-react";
import { api, setAuth, type Role } from "../lib/api";
import { BrandMark, ThemeToggle } from "../components/Shell";
import { Button, Field } from "../components/ui";

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

export function StaffLogin({ role, onDone }: { role: Exclude<Role, "student">; onDone: () => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [defaults, setDefaults] = useState<Record<string, boolean>>({});
  const label = role === "teacher" ? "ครู" : "ผู้ดูแลระบบ";
  const defaultPin = role === "teacher" ? "1234" : "4321";

  useEffect(() => {
    api<Record<string, boolean>>(null, "/api/auth/pin-hints").then(setDefaults).catch(() => {});
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ token: string }>(null, "/api/auth/staff", { body: { role, pin } });
      setAuth(role, { token: result.token });
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
          <p className="eyebrow">{label}</p>
          <h1 className="title-lg">ใส่ PIN {label}</h1>
          <p className="small muted">
            {role === "teacher"
              ? "หน้าครูเห็นชื่อจริงของนักเรียน คะแนนความเสี่ยง และการแจ้งเตือน"
              : "หน้าผู้ดูแลระบบเห็นการทำงานภายในของระบบ แต่เห็นนักเรียนเป็นรหัสเท่านั้น"}
          </p>
        </div>
        <Field
          label="PIN"
          hint={defaults[role] ? `ยังใช้ PIN เริ่มต้นสำหรับสาธิตอยู่: ${defaultPin} (เปลี่ยนได้ในหน้าตั้งค่า)` : undefined}
        >
          <input
            className="input input-lg mono"
            type="password"
            inputMode="numeric"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            autoFocus
            aria-invalid={!!error}
          />
        </Field>
        {error && <p className="small" style={{ color: "var(--danger)" }}>{error}</p>}
        <Button variant="primary" size="lg" block loading={busy} disabled={!pin} type="submit" icon={<KeyRound size={18} />}>
          เข้าสู่ระบบ
        </Button>
      </form>
    </LoginFrame>
  );
}
