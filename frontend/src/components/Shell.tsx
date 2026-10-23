import type { ReactNode } from "react";
import { Link } from "react-router";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemeMode } from "../lib/hooks";
import { Button } from "./ui";

export function BrandMark({ size = 16 }: { size?: number }) {
  return (
    <span className="brand-mark" aria-hidden>
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <path d="M4 17l5-10 4 7 2.2-3.4L20 17" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function ThemeToggle() {
  const [mode, setMode] = useTheme();
  const next: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
  const icon = mode === "light" ? <Sun size={18} /> : mode === "dark" ? <Moon size={18} /> : <Monitor size={18} />;
  const label = mode === "light" ? "ธีมสว่าง" : mode === "dark" ? "ธีมมืด" : "ตามระบบ";
  return (
    <Button
      variant="ghost"
      size="sm"
      className="btn-icon"
      onClick={() => setMode(next[mode])}
      aria-label={`เปลี่ยนธีม (ตอนนี้: ${label})`}
      title={label}
      icon={icon}
    />
  );
}

export function TopBar({
  role,
  children,
  onLogout,
  right,
  narrow,
}: {
  role?: string;
  children?: ReactNode;
  onLogout?: () => void;
  right?: ReactNode;
  narrow?: boolean;
}) {
  return (
    <header className="topbar">
      <div className={narrow ? "topbar-inner topbar-narrow" : "topbar-inner"}>
        <Link to="/" className="brand">
          <BrandMark />
          <span>Adaptive Tutor</span>
        </Link>
        {role && <span className="role-chip">{role}</span>}
        <div className="grow row" style={{ gap: 8 }}>
          {children}
        </div>
        {right}
        <ThemeToggle />
        {onLogout && (
          <Button variant="ghost" size="sm" icon={<LogOut size={16} />} onClick={onLogout} aria-label="ออกจากระบบ">
            <span className="btn-label">ออกจากระบบ</span>
          </Button>
        )}
      </div>
    </header>
  );
}
