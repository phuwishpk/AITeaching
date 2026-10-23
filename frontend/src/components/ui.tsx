import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CircleCheck, Info, LoaderCircle, TriangleAlert, X } from "lucide-react";
import type { Tone } from "../lib/format";

type ButtonVariant = "primary" | "secondary" | "soft" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size,
  icon,
  loading,
  block,
  className = "",
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "lg";
  icon?: ReactNode;
  loading?: boolean;
  block?: boolean;
}) {
  const classes = ["btn", `btn-${variant}`, size ? `btn-${size}` : "", block ? "btn-block" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={classes} disabled={loading || rest.disabled} {...rest}>
      {loading ? <LoaderCircle size={16} className="spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function Card({ className = "", children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={`card ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function CardHead({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="card-head">
      <div className="stack stack-sm" style={{ gap: 2 }}>
        <h3 className="subtitle">{title}</h3>
        {sub && <p className="small muted">{sub}</p>}
      </div>
      {actions && <div className="row row-sm">{actions}</div>}
    </div>
  );
}

export function Badge({ tone = "neutral", dot, children, title }: { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  const cls = tone === "neutral" ? "badge" : `badge badge-${tone}`;
  return (
    <span className={cls} title={title}>
      {dot && <span className="dot" aria-hidden />}
      {children}
    </span>
  );
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
}: {
  items: { id: T; label: ReactNode; num?: ReactNode; icon?: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          className="tab"
          aria-selected={item.id === value}
          onClick={() => onChange(item.id)}
        >
          {item.num != null && <span className="tab-num">{item.num}</span>}
          {item.icon}
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { id: T; label: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
  label?: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.id} aria-pressed={option.id === value} onClick={() => onChange(option.id)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, hint, children }: { label: ReactNode; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Modal({
  open,
  onClose,
  title,
  wide,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  wide?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="overlay overlay-center" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? "modal-wide" : ""}`} role="dialog" aria-modal="true">
        <div className="card-head">
          <h3 className="subtitle">{title}</h3>
          <Button variant="ghost" size="sm" className="btn-icon" onClick={onClose} aria-label="ปิด" icon={<X size={18} />} />
        </div>
        <div className="card-body">{children}</div>
        {footer && (
          <div className="row" style={{ justifyContent: "flex-end", padding: "0 22px 20px" }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEscape(open, onClose);
  if (!open) return null;
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="drawer-head">
          <div className="grow">{title}</div>
          <Button variant="ghost" size="sm" className="btn-icon" onClick={onClose} aria-label="ปิด" icon={<X size={18} />} />
        </div>
        <div style={{ padding: "18px 22px 32px" }}>{children}</div>
      </aside>
    </div>
  );
}

function useEscape(active: boolean, onClose: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!active) return;
    const handler = (event: KeyboardEvent) => event.key === "Escape" && close.current();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active]);
}

export function Spinner({ label = "กำลังโหลด" }: { label?: string }) {
  return (
    <div className="row muted small" style={{ padding: 20, justifyContent: "center" }}>
      <LoaderCircle size={18} className="spin" aria-hidden />
      {label}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Stat({ label, value, sub, tone }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className="card stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

// ---------- แจ้งเตือนชั่วคราว ----------
type ToastTone = "info" | "success" | "warning";
interface ToastItem {
  id: number;
  tone: ToastTone;
  text: ReactNode;
}

const ToastContext = createContext<(text: ReactNode, tone?: ToastTone) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((text: ReactNode, tone: ToastTone = "info") => {
    const id = Date.now() + Math.random();
    setItems((list) => [...list.slice(-3), { id, tone, text }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), 4200);
  }, []);
  const icons = {
    info: <Info size={18} color="var(--info)" />,
    success: <CircleCheck size={18} color="var(--success)" />,
    warning: <TriangleAlert size={18} color="var(--warning)" />,
  };
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => (
          <div className="toast" key={t.id}>
            {icons[t.tone]}
            <div>{t.text}</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
