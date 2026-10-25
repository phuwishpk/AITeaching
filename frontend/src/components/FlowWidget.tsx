import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Check, RotateCcw, Undo2 } from "lucide-react";
import { Button } from "./ui";

// Widget ในขั้น "widget" ของ Flow ที่ครูออกแบบ (backend/app/engine/widgets.py)
// หน้านี้ได้แค่ข้อมูลที่ไม่มีเฉลย ถูกผิดตัดสินที่เซิร์ฟเวอร์ด้วยกฎ ส่วน custom เป็นหน้าเว็บที่ AI เขียน รันใน iframe แยก

export interface WidgetView {
  type: string;
  title: string;
  prompt: string;
  graded: boolean;
  tries: number;
  data: Record<string, unknown>;
}

export interface WidgetResult {
  kind: string;
  marks?: boolean[] | null;
  message?: string;
}

type Submit = (response: Record<string, unknown>) => Promise<WidgetResult | null | undefined>;

export const WIDGET_NAMES: Record<string, string> = {
  order: "ลากเรียงลำดับ",
  match: "จับคู่",
  balance: "ตาชั่งสมการ",
  fraction: "แบบจำลองเศษส่วน",
  numberline: "เส้นจำนวน",
  blank: "เติมคำในช่องว่าง",
  custom: "Widget ที่ AI เขียนเอง",
};

export default function FlowWidget({ widget, onSubmit, preview }: { widget: WidgetView; onSubmit: Submit; preview?: boolean }) {
  const [result, setResult] = useState<WidgetResult | null>(null);
  const [busy, setBusy] = useState(false);
  const send = async (response: Record<string, unknown>) => {
    if (busy) return;
    setBusy(true);
    const answer = await onSubmit(response);
    setBusy(false);
    setResult(answer ?? null);
  };
  const marks = result?.kind === "wrong" ? (result.marks ?? null) : null;
  const props = { data: widget.data, marks, busy, preview, onSend: send };
  return (
    <div className="stack">
      {widget.type === "order" && <OrderWidget {...props} />}
      {widget.type === "match" && <MatchWidget {...props} />}
      {widget.type === "balance" && <BalanceWidget {...props} />}
      {widget.type === "fraction" && <FractionWidget {...props} />}
      {widget.type === "numberline" && <NumberLineWidget {...props} />}
      {widget.type === "blank" && <BlankWidget {...props} />}
      {widget.type === "custom" && <CustomWidget {...props} />}
      {result?.message && (
        <p className={`callout ${result.kind === "correct" ? "callout-success" : "callout-calm"} small`} role="status">
          {result.message}
        </p>
      )}
    </div>
  );
}

interface PartProps {
  data: Record<string, unknown>;
  marks: boolean[] | null;
  busy: boolean;
  preview?: boolean;
  onSend: (response: Record<string, unknown>) => void;
}

function SendButton({ busy, preview, disabled, onClick, children = "ส่งคำตอบ" }: {
  busy: boolean;
  preview?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children?: string;
}) {
  return (
    <Button variant="primary" size="lg" icon={<Check size={18} />} loading={busy} disabled={disabled || preview} onClick={onClick} style={{ alignSelf: "flex-start" }}>
      {children}
    </Button>
  );
}

const markClass = (marks: boolean[] | null, i: number) => (marks ? (marks[i] ? "is-right" : "is-wrong") : "");

// ---------------------------------------------------------------- ลากเรียงลำดับ

function OrderWidget({ data, marks, busy, preview, onSend }: PartProps) {
  const [items, setItems] = useState<string[]>(() => [...((data.items as string[]) ?? [])]);
  const drag = useRef<number | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setItems(next);
  };
  return (
    <>
      <ol className="widget-order">
        {items.map((item, i) => (
          <li
            key={item}
            className={`widget-order-item ${markClass(marks, i)}`}
            draggable
            onDragStart={() => (drag.current = i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => drag.current !== null && move(drag.current, i)}
          >
            <span className="widget-order-n num">{i + 1}</span>
            <span className="widget-order-text">{item}</span>
            <span className="row row-sm row-nowrap">
              <button type="button" className="icon-btn" onClick={() => move(i, i - 1)} disabled={i === 0} aria-label={`เลื่อน ${item} ขึ้น`}>
                <ArrowUp size={16} />
              </button>
              <button type="button" className="icon-btn" onClick={() => move(i, i + 1)} disabled={i === items.length - 1} aria-label={`เลื่อน ${item} ลง`}>
                <ArrowDown size={16} />
              </button>
            </span>
          </li>
        ))}
      </ol>
      <SendButton busy={busy} preview={preview} onClick={() => onSend({ order: items })} />
    </>
  );
}

// ---------------------------------------------------------------- จับคู่

function MatchWidget({ data, marks, busy, preview, onSend }: PartProps) {
  const lefts = (data.lefts as string[]) ?? [];
  const rights = (data.rights as string[]) ?? [];
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const complete = lefts.every((l) => chosen[l]);
  return (
    <>
      <div className="widget-match">
        {lefts.map((left, i) => (
          <label key={left} className={`widget-match-row ${markClass(marks, i)}`}>
            <span className="widget-match-left">{left}</span>
            <span className="faint" aria-hidden>↔</span>
            <select className="input" value={chosen[left] ?? ""} onChange={(e) => setChosen({ ...chosen, [left]: e.target.value })} aria-label={`คู่ของ ${left}`}>
              <option value="">เลือกคู่</option>
              {rights.map((right) => (
                <option key={right} value={right}>
                  {right}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <SendButton busy={busy} preview={preview} disabled={!complete} onClick={() => onSend({ pairs: chosen })} />
    </>
  );
}

// ---------------------------------------------------------------- เศษส่วนแบบง่าย (หน้าเว็บคำนวณภาพ เซิร์ฟเวอร์ตรวจคำตอบ)

interface Frac {
  n: number;
  d: number;
}

const gcd = (a: number, b: number): number => (b ? gcd(b, a % b) : Math.abs(a) || 1);
const frac = (n: number, d = 1): Frac => {
  const g = gcd(n, d) * (d < 0 ? -1 : 1);
  return { n: n / g, d: d / g };
};
const parseFrac = (text: unknown): Frac => {
  const [n, d] = String(text ?? "0").split("/").map(Number);
  return frac(n || 0, d || 1);
};
const add = (a: Frac, b: Frac) => frac(a.n * b.d + b.n * a.d, a.d * b.d);
const mul = (a: Frac, b: Frac) => frac(a.n * b.n, a.d * b.d);
const div = (a: Frac, b: Frac) => frac(a.n * b.d, a.d * b.n);
const value = (a: Frac) => a.n / a.d;
const show = (a: Frac) => (a.d === 1 ? String(a.n) : `${a.n}/${a.d}`);

// ---------------------------------------------------------------- ตาชั่งสมการ

function parseEquation(text: string): [number, number, number] {
  const m = text.replace(/\s/g, "").match(/^(\d*)x([+-]\d+)?=([+-]?\d+)$/);
  return m ? [Number(m[1] || 1), Number(m[2] || 0), Number(m[3])] : [1, 0, 0];
}

interface Move {
  op: "+" | "-" | "/";
  n: number;
  side: "both" | "left" | "right";
}

function sideText(a: Frac, b: Frac) {
  const x = a.n === a.d ? "x" : `${show(a)}x`;
  if (b.n === 0) return x;
  return `${x} ${b.n > 0 ? "+" : "−"} ${show(frac(Math.abs(b.n), b.d))}`;
}

function BalanceWidget({ data, busy, preview, onSend }: PartProps) {
  const [a0, b0, c0] = useMemo(() => parseEquation(String(data.equation ?? "")), [data.equation]);
  const solution = frac(c0 - b0, a0);
  const [moves, setMoves] = useState<Move[]>([]);
  const [n, setN] = useState(1);
  const [side, setSide] = useState<Move["side"]>("both");
  let la = frac(a0), lb = frac(b0), r = frac(c0);
  for (const m of moves) {
    const k = frac(m.n);
    if (m.side !== "right") {
      if (m.op === "+") lb = add(lb, k);
      else if (m.op === "-") lb = add(lb, frac(-m.n));
      else [la, lb] = [div(la, k), div(lb, k)];
    }
    if (m.side !== "left") r = m.op === "+" ? add(r, k) : m.op === "-" ? add(r, frac(-m.n)) : div(r, k);
  }
  const leftValue = value(add(mul(la, solution), lb));
  const diff = leftValue - value(r);
  const tilt = Math.max(-12, Math.min(12, diff * 3));
  const isolated = la.n === la.d && lb.n === 0;
  const xs = Math.min(Math.round(value(la)), 9);
  const units = (k: number) => Math.min(Math.abs(Math.round(k)), 12);

  return (
    <>
      <p className="problem-math">
        {sideText(la, lb)} = {show(r)}
      </p>
      <svg viewBox="0 0 320 170" className="widget-balance" role="img" aria-label={diff === 0 ? "ตาชั่งสมดุล" : "ตาชั่งเอียง สองข้างไม่เท่ากัน"}>
        <polygon points="160,150 145,170 175,170" fill="currentColor" opacity="0.5" />
        <line x1="160" y1="60" x2="160" y2="150" stroke="currentColor" strokeWidth="3" opacity="0.5" />
        <g transform={`rotate(${tilt} 160 60)`} style={{ transition: "transform 0.4s" }}>
          <line x1="40" y1="60" x2="280" y2="60" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          <Pan x={70} xs={xs} units={units(value(lb))} negative={lb.n < 0} />
          <Pan x={250} xs={0} units={units(value(r))} negative={r.n < 0} />
        </g>
      </svg>
      <p className={`small ${diff === 0 ? "success-text" : "warning-text"}`}>
        {diff === 0 ? "ตาชั่งสมดุล สองข้างเท่ากัน" : "ตาชั่งเอียงแล้ว สองข้างไม่เท่ากันแล้วนะ ลองย้อนขั้นดู"}
      </p>
      {!preview && (
        <div className="row row-sm widget-balance-controls">
          <select className="input widget-small" value={side} onChange={(e) => setSide(e.target.value as Move["side"])} aria-label="ทำกับข้างไหน">
            <option value="both">ทั้งสองข้าง</option>
            <option value="left">ข้างซ้ายอย่างเดียว</option>
            <option value="right">ข้างขวาอย่างเดียว</option>
          </select>
          <input className="input widget-small" type="number" min={1} max={30} value={n} onChange={(e) => setN(Math.max(1, Math.min(30, Number(e.target.value) || 1)))} aria-label="จำนวน" style={{ width: 72 }} />
          {(["+", "-", "/"] as const).map((op) => (
            <Button key={op} size="sm" onClick={() => setMoves([...moves, { op, n, side }])} disabled={moves.length >= 20}>
              {op === "+" ? `บวก ${n}` : op === "-" ? `ลบ ${n}` : `หารด้วย ${n}`}
            </Button>
          ))}
          <Button size="sm" variant="ghost" icon={<Undo2 size={14} />} onClick={() => setMoves(moves.slice(0, -1))} disabled={!moves.length}>
            ย้อน
          </Button>
          <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={() => setMoves([])} disabled={!moves.length}>
            เริ่มใหม่
          </Button>
        </div>
      )}
      <SendButton busy={busy} preview={preview} disabled={!isolated} onClick={() => onSend({ steps: moves })}>
        {isolated ? `ส่งคำตอบ x = ${show(r)}` : "ทำให้เหลือ x ข้างเดียวก่อน"}
      </SendButton>
    </>
  );
}

function Pan({ x, xs, units, negative }: { x: number; xs: number; units: number; negative: boolean }) {
  const blocks = [...Array(xs).fill("x"), ...Array(units).fill(negative ? "-" : "1")];
  return (
    <g>
      <line x1={x} y1="60" x2={x} y2="80" stroke="currentColor" strokeWidth="2" />
      <path d={`M${x - 50},80 L${x + 50},80 L${x + 40},92 L${x - 40},92 Z`} fill="currentColor" opacity="0.18" />
      {blocks.map((b, i) => {
        const col = i % 7;
        const row = Math.floor(i / 7);
        const bx = x - 42 + col * 12;
        const by = 66 - row * 13;
        return b === "x" ? (
          <g key={i}>
            <rect x={bx} y={by} width="11" height="12" rx="2" fill="var(--accent)" />
            <text x={bx + 5.5} y={by + 9.5} fontSize="9" textAnchor="middle" fill="var(--on-accent)">x</text>
          </g>
        ) : (
          <circle key={i} cx={bx + 5.5} cy={by + 6} r="5" fill={b === "-" ? "var(--danger)" : "var(--warning)"} />
        );
      })}
    </g>
  );
}

// ---------------------------------------------------------------- แบบจำลองเศษส่วน

function FractionWidget({ data, busy, preview, onSend }: PartProps) {
  const parts = Math.max(1, Math.min(24, Math.round(Number(data.parts) || 4)));
  const [on, setOn] = useState<boolean[]>(() => Array(parts).fill(false));
  const shaded = on.filter(Boolean).length;
  const toggle = (i: number) => setOn(on.map((v, j) => (j === i ? !v : v)));
  const fill = (i: number) => (on[i] ? "var(--accent)" : "var(--surface-2)");
  return (
    <>
      <p className="small">
        ระบายให้ได้ <strong className="num">{String(data.target)}</strong> ของรูป · ระบายแล้ว <span className="num">{shaded}/{parts}</span>
      </p>
      {data.shape === "bar" ? (
        <svg viewBox={`0 0 ${parts * 40} 60`} className="widget-fraction" role="group" aria-label={`แถบแบ่ง ${parts} ส่วน`}>
          {on.map((_, i) => (
            <rect key={i} x={i * 40 + 1} y="1" width="38" height="58" fill={fill(i)} stroke="currentColor" strokeWidth="1.5" onClick={() => toggle(i)} role="button" aria-pressed={on[i]} aria-label={`ส่วนที่ ${i + 1}`} style={{ cursor: "pointer" }} />
          ))}
        </svg>
      ) : (
        <svg viewBox="0 0 200 200" className="widget-fraction widget-fraction-circle" role="group" aria-label={`วงกลมแบ่ง ${parts} ส่วน`}>
          {on.map((_, i) => {
            const a1 = (i / parts) * 2 * Math.PI - Math.PI / 2;
            const a2 = ((i + 1) / parts) * 2 * Math.PI - Math.PI / 2;
            const large = a2 - a1 > Math.PI ? 1 : 0;
            const d = `M100,100 L${100 + 95 * Math.cos(a1)},${100 + 95 * Math.sin(a1)} A95,95 0 ${large} 1 ${100 + 95 * Math.cos(a2)},${100 + 95 * Math.sin(a2)} Z`;
            return <path key={i} d={d} fill={fill(i)} stroke="currentColor" strokeWidth="1.5" onClick={() => toggle(i)} role="button" aria-pressed={on[i]} aria-label={`ชิ้นที่ ${i + 1}`} style={{ cursor: "pointer" }} />;
          })}
        </svg>
      )}
      <SendButton busy={busy} preview={preview} disabled={!shaded} onClick={() => onSend({ shaded })} />
    </>
  );
}

// ---------------------------------------------------------------- เส้นจำนวน

function NumberLineWidget({ data, busy, preview, onSend }: PartProps) {
  const low = parseFrac(data.min);
  const high = parseFrac(data.max);
  const step = parseFrac(data.step);
  const count = Math.round(value(div(add(high, frac(-low.n, low.d)), step)));
  const [picked, setPicked] = useState<number | null>(null);
  const at = (i: number) => add(low, mul(step, frac(i)));
  const width = 600;
  const x = (i: number) => 30 + (i / count) * (width - 60);
  return (
    <>
      <p className="small">
        แตะขีดบนเส้นจำนวนตรงตำแหน่งของ <strong className="num">{String(data.target)}</strong>
        {picked !== null && <> · เลือกไว้ที่ <span className="num">{show(at(picked))}</span></>}
      </p>
      <svg viewBox={`0 0 ${width} 80`} className="widget-numberline" role="group" aria-label="เส้นจำนวน">
        <line x1="20" y1="40" x2={width - 20} y2="40" stroke="currentColor" strokeWidth="2" />
        {Array.from({ length: count + 1 }, (_, i) => {
          const v = at(i);
          const whole = v.d === 1;
          return (
            <g key={i} onClick={() => setPicked(i)} role="button" aria-label={`ขีดที่ ${i + 1}`} style={{ cursor: "pointer" }}>
              <rect x={x(i) - 8} y="20" width="16" height="44" fill="transparent" />
              <line x1={x(i)} y1={whole ? 30 : 34} x2={x(i)} y2={whole ? 50 : 46} stroke="currentColor" strokeWidth={whole ? 2 : 1} />
              {(whole || count <= 12) && (
                <text x={x(i)} y="70" fontSize="12" textAnchor="middle" fill="currentColor">
                  {show(v)}
                </text>
              )}
            </g>
          );
        })}
        {picked !== null && <circle cx={x(picked)} cy="40" r="8" fill="var(--accent)" />}
      </svg>
      <SendButton busy={busy} preview={preview} disabled={picked === null} onClick={() => picked !== null && onSend({ value: show(at(picked)) })} />
    </>
  );
}

// ---------------------------------------------------------------- เติมคำในช่องว่าง

function BlankWidget({ data, marks, busy, preview, onSend }: PartProps) {
  const parts = (data.parts as string[]) ?? [""];
  const [blanks, setBlanks] = useState<string[]>(() => Array(Math.max(parts.length - 1, 0)).fill(""));
  return (
    <>
      <p className="widget-blank prose">
        {parts.map((part, i) => (
          <span key={i}>
            {part}
            {i < parts.length - 1 && (
              <input
                className={`input widget-blank-input ${markClass(marks, i)}`}
                value={blanks[i]}
                maxLength={60}
                onChange={(e) => setBlanks(blanks.map((b, j) => (j === i ? e.target.value : b)))}
                aria-label={`ช่องที่ ${i + 1}`}
              />
            )}
          </span>
        ))}
      </p>
      <SendButton busy={busy} preview={preview} disabled={blanks.some((b) => !b.trim())} onClick={() => onSend({ blanks })} />
    </>
  );
}

// ---------------------------------------------------------------- Widget ที่ AI เขียนเอง

// ห้ามเน็ตทุกชนิด (รูปแบบ data: ได้) และรันแบบไม่มี origin ของเว็บ (sandbox ไม่มี allow-same-origin) จึงอ่าน cookie หรือ token ไม่ได้
const CSP = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:">`;

export function CustomFrame({ html, onDone }: { html: string; onDone?: (result: string) => void }) {
  const frame = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const listen = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.data?.type !== "widget-done") return;
      onDone?.(String(event.data.result ?? "").slice(0, 300));
    };
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [onDone]);
  return <iframe ref={frame} className="widget-frame" title="Widget" sandbox="allow-scripts" srcDoc={CSP + html} />;
}

function CustomWidget({ data, busy, preview, onSend }: PartProps) {
  const [result, setResult] = useState<string | null>(null);
  return (
    <>
      <CustomFrame html={String(data.html ?? "")} onDone={(r) => setResult(r || "ทำเสร็จแล้ว")} />
      <SendButton busy={busy} preview={preview} onClick={() => onSend({ done: true, result: result ?? "" })}>
        {result ? "ทำเสร็จแล้ว ไปต่อ" : "ไปต่อ"}
      </SendButton>
    </>
  );
}
