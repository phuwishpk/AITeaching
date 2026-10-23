import { useMemo, useRef, useState, type ReactNode } from "react";
import { Table2, ChartScatter } from "lucide-react";
import { CLUSTER_COLORS, CLUSTER_NAMES, num, pct } from "../lib/format";
import { Button } from "./ui";

/*
 * กราฟทั้งหมดของหน้าครูและ Admin
 * สีกลุ่ม (--cluster-*) และสีชุดข้อมูล (--series-1..3) ผ่าน validate_palette.js ทั้งโหมดสว่างและมืดแล้ว
 * สีกลุ่มบางคู่อยู่ในช่วงที่ต้องมีการเข้ารหัสซ้ำ จึงใช้รูปทรงต่างกันทุกกลุ่ม + legend + ป้ายชื่อตรงจุด
 * ตัวหนังสือในกราฟใช้สีตัวอักษรเสมอ สีของชุดข้อมูลใช้กับเส้นและจุดเท่านั้น
 */

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

export type Shape = "circle" | "square" | "triangle" | "diamond";

export const CLUSTER_SHAPES: Record<string, Shape> = {
  fast: "circle",
  struggling: "square",
  guesser: "triangle",
  bite: "diamond",
};

const CLUSTER_ORDER = ["fast", "struggling", "guesser", "bite"];

// รูปทรงพื้นที่ใกล้เคียงกัน ให้ไม่มีกลุ่มไหนดูเด่นกว่าเพราะขนาด
export function shapePath(shape: Shape, cx: number, cy: number, scale = 1) {
  if (shape === "square") {
    const h = 4.6 * scale;
    return `M${cx - h},${cy - h}h${2 * h}v${2 * h}h${-2 * h}z`;
  }
  if (shape === "triangle") {
    const s = 6.2 * scale;
    return `M${cx},${cy - s}L${cx + s * 0.95},${cy + s * 0.65}L${cx - s * 0.95},${cy + s * 0.65}z`;
  }
  if (shape === "diamond") {
    const d = 6.4 * scale;
    return `M${cx},${cy - d}L${cx + d},${cy}L${cx},${cy + d}L${cx - d},${cy}z`;
  }
  const r = 5.2 * scale;
  return `M${cx - r},${cy}a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0`;
}

function niceStep(raw: number) {
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / power;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * power;
}

export function niceTicks(max: number, count = 5) {
  const step = niceStep(max / count);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Number(v.toFixed(6)));
  return ticks;
}

// ---------- กล่องข้อความเมื่อชี้ (ค่าเด่น ชื่อรอง) ----------
export interface TipRow {
  value: ReactNode;
  label: ReactNode;
  color?: string;
}

interface TipState {
  x: number;
  y: number;
  flip?: boolean;
  title?: ReactNode;
  rows: TipRow[];
}

function useTip() {
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<TipState | null>(null);
  const show = (event: { clientX: number; clientY: number }, content: Omit<TipState, "x" | "y">) => {
    const box = wrap.current?.getBoundingClientRect();
    if (!box) return;
    const x = event.clientX - box.left;
    setTip({ ...content, x, y: event.clientY - box.top, flip: x > box.width * 0.6 });
  };
  // ตำแหน่งจากจุดบน SVG (ใช้ตอน focus ด้วยคีย์บอร์ด)
  const showAt = (svg: SVGSVGElement | null, vbWidth: number, x: number, y: number, content: Omit<TipState, "x" | "y">) => {
    const box = wrap.current?.getBoundingClientRect();
    const rect = svg?.getBoundingClientRect();
    if (!box || !rect) return;
    const scale = rect.width / vbWidth;
    const left = rect.left - box.left + x * scale;
    setTip({ ...content, x: left, y: rect.top - box.top + y * scale, flip: left > box.width * 0.6 });
  };
  const hide = () => setTip(null);
  const node = tip && (
    <div className={`chart-tip ${tip.flip ? "flip" : ""}`} style={{ left: tip.x, top: tip.y }} role="status">
      {tip.title && <div className="chart-tip-title">{tip.title}</div>}
      {tip.rows.map((row, i) => (
        <div className="chart-tip-row" key={i}>
          {row.color && <span className="tip-key" style={{ background: row.color }} />}
          <strong className="num">{row.value}</strong>
          <span>{row.label}</span>
        </div>
      ))}
    </div>
  );
  return { wrap, show, showAt, hide, node };
}

// แปลงตำแหน่งเมาส์เป็นพิกัดใน viewBox
function svgX(svg: SVGSVGElement | null, vbWidth: number, clientX: number) {
  const rect = svg?.getBoundingClientRect();
  if (!rect) return 0;
  return ((clientX - rect.left) / rect.width) * vbWidth;
}

// ---------- คำอธิบายสัญลักษณ์ ----------
export interface LegendItem {
  label: ReactNode;
  color?: string;
  mark?: Shape | "line" | "dash" | "rect" | "ring";
  value?: ReactNode;
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="legend">
      {items.map((item, i) => (
        <li key={i}>
          <svg width="16" height="12" viewBox="0 0 16 12" aria-hidden>
            {item.mark === "line" && <line x1="1" y1="6" x2="15" y2="6" stroke={item.color} strokeWidth="2.5" strokeLinecap="round" />}
            {item.mark === "dash" && (
              <line x1="1" y1="6" x2="15" y2="6" stroke={item.color} strokeWidth="2" strokeDasharray="3 2.5" />
            )}
            {item.mark === "rect" && <rect x="2" y="1" width="12" height="10" rx="3" fill={item.color} />}
            {item.mark === "ring" && <circle cx="8" cy="6" r="4.6" fill="none" stroke="var(--text-2)" strokeWidth="1.6" />}
            {item.mark && !["line", "dash", "rect", "ring"].includes(item.mark) && (
              <path d={shapePath(item.mark as Shape, 8, 6, 0.85)} fill={item.color} />
            )}
          </svg>
          <span>{item.label}</span>
          {item.value != null && <span className="legend-value num">{item.value}</span>}
        </li>
      ))}
    </ul>
  );
}

// ---------- กราฟการจัดกลุ่มผู้เรียน (K-Means) ----------
export interface ClusterPoint {
  code: string;
  name?: string | null;
  simulated?: boolean;
  cluster: string;
  cluster_name: string;
  avg_rt: number;
  accuracy: number;
  session_min: number;
  distance?: number;
}

export interface Centroid {
  cluster: string;
  cluster_name: string;
  description?: string;
  avg_rt: number;
  accuracy: number;
  session_min: number;
  size: number;
}

const SC = { w: 660, h: 360, l: 52, r: 18, t: 16, b: 44 };

export function ClusterScatter({
  points,
  centroids,
  selected,
  onSelect,
}: {
  points: ClusterPoint[];
  centroids: Centroid[];
  selected?: string | null;
  onSelect?: (code: string) => void;
}) {
  const [table, setTable] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const { wrap, show, showAt, hide, node } = useTip();

  const xTicks = useMemo(() => niceTicks(Math.max(10, ...points.map((p) => p.avg_rt), ...centroids.map((c) => c.avg_rt)) * 1.04), [points, centroids]);
  const xMax = xTicks[xTicks.length - 1];
  const sx = (v: number) => SC.l + (v / xMax) * (SC.w - SC.l - SC.r);
  const sy = (v: number) => SC.t + (1 - v) * (SC.h - SC.t - SC.b);

  // ป้ายชื่อกลุ่มที่ centroid: เลื่อนลงไม่ให้ทับกัน
  const labels = useMemo(() => {
    const placed = centroids
      .map((c) => ({ ...c, lx: sx(c.avg_rt) + 13, ly: sy(c.accuracy) + 4 }))
      .sort((a, b) => a.ly - b.ly);
    for (let i = 1; i < placed.length; i++) {
      const prev = placed[i - 1];
      if (Math.abs(placed[i].lx - prev.lx) < 150 && placed[i].ly - prev.ly < 16) placed[i].ly = prev.ly + 16;
    }
    for (const p of placed) if (p.lx > SC.w - 150) p.lx = sx(p.avg_rt) - 13;
    return placed;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centroids, xMax]);

  const counts = Object.fromEntries(CLUSTER_ORDER.map((k) => [k, points.filter((p) => p.cluster === k).length]));
  const hasReal = points.some((p) => !p.simulated);

  const tipFor = (p: ClusterPoint) => ({
    title: p.name ? `${p.name} · ${p.code}` : p.code,
    rows: [
      { value: CLUSTER_NAMES[p.cluster] ?? p.cluster_name, label: "กลุ่ม", color: CLUSTER_COLORS[p.cluster] },
      { value: `${num(p.avg_rt, 1)} วิ`, label: "เวลาคิดเฉลี่ย" },
      { value: pct(p.accuracy), label: "ตอบถูก" },
      { value: `${num(p.session_min, 1)} นาที`, label: "Session เฉลี่ย" },
    ],
  });

  return (
    <div className="chart" ref={wrap}>
      <div className="chart-bar">
        <Legend
          items={[
            ...CLUSTER_ORDER.map((k) => ({
              label: CLUSTER_NAMES[k],
              color: CLUSTER_COLORS[k],
              mark: CLUSTER_SHAPES[k],
              value: counts[k],
            })),
            ...(hasReal ? [{ label: "นักเรียนจริง", mark: "ring" as const }] : []),
          ]}
        />
        <Button
          variant="ghost"
          size="sm"
          icon={table ? <ChartScatter size={15} /> : <Table2 size={15} />}
          onClick={() => setTable((v) => !v)}
          aria-pressed={table}
        >
          {table ? "กราฟ" : "ตาราง"}
        </Button>
      </div>

      {table ? (
        <div className="table-wrap chart-table">
          <table className="table">
            <thead>
              <tr>
                <th>นักเรียน</th>
                <th>กลุ่ม</th>
                <th className="num">เวลาคิดเฉลี่ย (วิ)</th>
                <th className="num">ตอบถูก</th>
                <th className="num">Session (นาที)</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.code} className={onSelect ? "clickable" : ""} onClick={() => onSelect?.(p.code)}>
                  <td>
                    {p.name ? `${p.name} · ` : ""}
                    <span className="mono">{p.code}</span>
                  </td>
                  <td>{CLUSTER_NAMES[p.cluster]}</td>
                  <td className="num">{num(p.avg_rt, 1)}</td>
                  <td className="num">{pct(p.accuracy)}</td>
                  <td className="num">{num(p.session_min, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <svg ref={svgRef} viewBox={`0 0 ${SC.w} ${SC.h}`} className="chart-svg" role="img" aria-label="กราฟการกระจายของนักเรียน แกนนอนเวลาคิดเฉลี่ย แกนตั้งสัดส่วนตอบถูก">
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line x1={SC.l} x2={SC.w - SC.r} y1={sy(v)} y2={sy(v)} className={v === 0 ? "axis-line" : "grid-line"} />
              <text x={SC.l - 8} y={sy(v) + 4} textAnchor="end" className="ax-label">
                {Math.round(v * 100)}%
              </text>
            </g>
          ))}
          {xTicks.map((v) => (
            <text key={v} x={sx(v)} y={SC.h - SC.b + 18} textAnchor="middle" className="ax-label">
              {v}
            </text>
          ))}
          <text x={(SC.l + SC.w - SC.r) / 2} y={SC.h - 6} textAnchor="middle" className="ax-title">
            เวลาคิดเฉลี่ยต่อข้อ (วินาที)
          </text>
          <text transform={`translate(13 ${(SC.t + SC.h - SC.b) / 2}) rotate(-90)`} textAnchor="middle" className="ax-title">
            สัดส่วนตอบถูก
          </text>

          {points.map((p) => {
            const x = sx(p.avg_rt);
            const y = sy(p.accuracy);
            const shape = CLUSTER_SHAPES[p.cluster] ?? "circle";
            return (
              <g
                key={p.code}
                className={`scatter-point ${p.code === selected ? "is-selected" : ""}`}
                tabIndex={0}
                role="button"
                aria-label={`${p.name ?? p.code} กลุ่ม ${CLUSTER_NAMES[p.cluster]} เวลาคิด ${num(p.avg_rt, 1)} วินาที ตอบถูก ${pct(p.accuracy)}`}
                onPointerMove={(e) => show(e, tipFor(p))}
                onPointerLeave={hide}
                onFocus={() => showAt(svgRef.current, SC.w, x, y, tipFor(p))}
                onBlur={hide}
                onClick={() => onSelect?.(p.code)}
                onKeyDown={(e) => e.key === "Enter" && onSelect?.(p.code)}
              >
                {!p.simulated && <circle cx={x} cy={y} r={9.5} className="real-ring" />}
                {p.code === selected && <circle cx={x} cy={y} r={12.5} className="select-ring" />}
                <path d={shapePath(shape, x, y)} fill={CLUSTER_COLORS[p.cluster]} className="mark" />
                <circle cx={x} cy={y} r={12} className="hit" />
              </g>
            );
          })}

          {centroids.map((c) => (
            <path
              key={c.cluster}
              d={shapePath(CLUSTER_SHAPES[c.cluster] ?? "circle", sx(c.avg_rt), sy(c.accuracy), 1.65)}
              className="centroid"
              stroke={CLUSTER_COLORS[c.cluster]}
            >
              <title>{`จุดศูนย์กลางกลุ่ม ${CLUSTER_NAMES[c.cluster]} (${c.size} คน)`}</title>
            </path>
          ))}
          {labels.map((c) => (
            <text key={c.cluster} x={c.lx} y={c.ly} textAnchor={c.lx < sx(c.avg_rt) ? "end" : "start"} className="dl-label">
              {CLUSTER_NAMES[c.cluster]}
            </text>
          ))}
        </svg>
      )}
      {node}
    </div>
  );
}

// ---------- Elbow (inertia ต่อจำนวนกลุ่ม) ----------
const EB = { w: 420, h: 220, l: 50, r: 16, t: 18, b: 38 };

export function ElbowChart({ data, chosen = 4 }: { data: { k: number; inertia: number }[]; chosen?: number }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { wrap, show, hide, node } = useTip();
  const [hover, setHover] = useState<number | null>(null);
  if (!data.length) return null;
  const ticks = niceTicks(Math.max(...data.map((d) => d.inertia)));
  const top = ticks[ticks.length - 1];
  const ks = data.map((d) => d.k);
  const sx = (k: number) => EB.l + ((k - ks[0]) / Math.max(1, ks[ks.length - 1] - ks[0])) * (EB.w - EB.l - EB.r);
  const sy = (v: number) => EB.t + (1 - v / top) * (EB.h - EB.t - EB.b);
  const line = data.map((d, i) => `${i ? "L" : "M"}${sx(d.k)},${sy(d.inertia)}`).join("");

  const move = (e: React.PointerEvent) => {
    const x = svgX(svgRef.current, EB.w, e.clientX);
    const nearest = data.reduce((best, d) => (Math.abs(sx(d.k) - x) < Math.abs(sx(best.k) - x) ? d : best), data[0]);
    setHover(nearest.k);
    show(e, { title: `k = ${nearest.k}`, rows: [{ value: num(nearest.inertia, 1), label: "Inertia", color: SERIES[0] }] });
  };

  return (
    <div className="chart" ref={wrap}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${EB.w} ${EB.h}`}
        className="chart-svg"
        role="img"
        aria-label={`กราฟ Elbow ค่า inertia เมื่อ k เท่ากับ ${ks.join(", ")} เลือก k เท่ากับ ${chosen}`}
        onPointerMove={move}
        onPointerLeave={() => {
          setHover(null);
          hide();
        }}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line x1={EB.l} x2={EB.w - EB.r} y1={sy(v)} y2={sy(v)} className={v === 0 ? "axis-line" : "grid-line"} />
            <text x={EB.l - 8} y={sy(v) + 4} textAnchor="end" className="ax-label">
              {num(v)}
            </text>
          </g>
        ))}
        {data.map((d) => (
          <text key={d.k} x={sx(d.k)} y={EB.h - EB.b + 18} textAnchor="middle" className="ax-label">
            {d.k}
          </text>
        ))}
        <text x={(EB.l + EB.w - EB.r) / 2} y={EB.h - 4} textAnchor="middle" className="ax-title">
          จำนวนกลุ่ม (k)
        </text>
        {hover != null && <line x1={sx(hover)} x2={sx(hover)} y1={EB.t} y2={EB.h - EB.b} className="crosshair" />}
        <path d={line} className="series-line" stroke={SERIES[0]} />
        {data.map((d) => (
          <circle key={d.k} cx={sx(d.k)} cy={sy(d.inertia)} r={d.k === chosen ? 5.5 : 4} fill={SERIES[0]} className="mark" />
        ))}
        {data.some((d) => d.k === chosen) && (
          <text x={sx(chosen) + 10} y={sy(data.find((d) => d.k === chosen)!.inertia) - 10} className="dl-label">
            k = {chosen} จุดข้อศอก
          </text>
        )}
      </svg>
      {node}
    </div>
  );
}

// ---------- Fuzzy: กราฟความเป็นสมาชิก ----------
export interface FuzzySetDef {
  label: string;
  shape: "tri" | "trap";
  points: number[];
}

export interface FuzzyVarDef {
  name: string;
  label: string;
  low: number;
  high: number;
  sets: Record<string, FuzzySetDef>;
}

export function membership(set: FuzzySetDef, x: number) {
  const [a, b, c, d] = set.shape === "tri" ? [set.points[0], set.points[1], set.points[1], set.points[2]] : set.points;
  if (x < a || x > d) return 0;
  if (x >= b && x <= c) return 1;
  if (x < b) return b === a ? 1 : (x - a) / (b - a);
  return d === c ? 1 : (d - x) / (d - c);
}

function setOutline(set: FuzzySetDef, low: number, high: number): [number, number][] {
  const [a, b, c, d] = set.shape === "tri" ? [set.points[0], set.points[1], set.points[1], set.points[2]] : set.points;
  const pts: [number, number][] = [];
  if (!(a === b && a <= low)) pts.push([a, 0]);
  pts.push([b, 1]);
  if (c !== b) pts.push([c, 1]);
  if (!(c === d && d >= high)) pts.push([d, 0]);
  return pts.map(([x, y]) => [Math.max(low, Math.min(high, x)), y]);
}

const MF = { w: 420, h: 190, l: 40, r: 14, t: 26, b: 34 };

export function MembershipChart({ variable, value }: { variable: FuzzyVarDef; value?: number | null }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { wrap, show, hide, node } = useTip();
  const [hover, setHover] = useState<number | null>(null);
  const keys = Object.keys(variable.sets);
  const span = variable.high - variable.low || 1;
  const sx = (v: number) => MF.l + ((v - variable.low) / span) * (MF.w - MF.l - MF.r);
  const sy = (mu: number) => MF.t + (1 - mu) * (MF.h - MF.t - MF.b);
  const invert = (px: number) => variable.low + ((px - MF.l) / (MF.w - MF.l - MF.r)) * span;
  const ticks = [variable.low, variable.low + span / 2, variable.high];
  const fmt = (v: number) => (Math.abs(span) <= 3 ? num(v, 2) : num(v, 0));

  const move = (e: React.PointerEvent) => {
    const x = Math.max(variable.low, Math.min(variable.high, invert(svgX(svgRef.current, MF.w, e.clientX))));
    setHover(x);
    show(e, {
      title: `${variable.label} = ${fmt(x)}`,
      rows: keys.map((k, i) => ({ value: num(membership(variable.sets[k], x), 2), label: variable.sets[k].label, color: SERIES[i] })),
    });
  };

  return (
    <div className="chart" ref={wrap}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${MF.w} ${MF.h}`}
        className="chart-svg"
        role="img"
        aria-label={`ความเป็นสมาชิกของ ${variable.label}`}
        onPointerMove={move}
        onPointerLeave={() => {
          setHover(null);
          hide();
        }}
      >
        {[0, 0.5, 1].map((mu) => (
          <g key={mu}>
            <line x1={MF.l} x2={MF.w - MF.r} y1={sy(mu)} y2={sy(mu)} className={mu === 0 ? "axis-line" : "grid-line"} />
            <text x={MF.l - 8} y={sy(mu) + 4} textAnchor="end" className="ax-label">
              {mu}
            </text>
          </g>
        ))}
        {ticks.map((v) => (
          <text key={v} x={sx(v)} y={MF.h - MF.b + 17} textAnchor="middle" className="ax-label">
            {fmt(v)}
          </text>
        ))}
        {keys.map((k, i) => {
          const pts = setOutline(variable.sets[k], variable.low, variable.high);
          const peak = pts.filter(([, y]) => y === 1);
          const cx = peak.length ? (peak[0][0] + peak[peak.length - 1][0]) / 2 : variable.low;
          return (
            <g key={k}>
              <path d={pts.map(([x, y], j) => `${j ? "L" : "M"}${sx(x)},${sy(y)}`).join("")} className="series-line" stroke={SERIES[i]} />
              <text x={Math.max(MF.l + 16, Math.min(MF.w - MF.r - 16, sx(cx)))} y={MF.t - 9} textAnchor="middle" className="dl-label">
                {variable.sets[k].label}
              </text>
            </g>
          );
        })}
        {hover != null && <line x1={sx(hover)} x2={sx(hover)} y1={MF.t} y2={MF.h - MF.b} className="crosshair" />}
        {value != null && (
          <g>
            <line x1={sx(value)} x2={sx(value)} y1={MF.t - 2} y2={MF.h - MF.b} className="value-line" />
            {keys.map((k, i) => {
              const mu = membership(variable.sets[k], value);
              return mu > 0 ? <circle key={k} cx={sx(value)} cy={sy(mu)} r={4.5} fill={SERIES[i]} className="mark" /> : null;
            })}
          </g>
        )}
      </svg>
      <Legend
        items={keys.map((k, i) => ({
          label: variable.sets[k].label,
          color: SERIES[i],
          mark: "line" as const,
          value: value != null ? `μ ${num(membership(variable.sets[k], value), 2)}` : undefined,
        }))}
      />
      {node}
    </div>
  );
}

// ---------- Fuzzy: ผลลัพธ์หลังตัดยอดและจุดศูนย์ถ่วง ----------
export function OutputChart({
  variable,
  curve,
  crisp,
}: {
  variable: FuzzyVarDef;
  curve: [number, number][];
  crisp: number;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const { wrap, show, hide, node } = useTip();
  const [hover, setHover] = useState<number | null>(null);
  const keys = Object.keys(variable.sets);
  const span = variable.high - variable.low || 1;
  const sx = (v: number) => MF.l + ((v - variable.low) / span) * (MF.w - MF.l - MF.r);
  const sy = (mu: number) => MF.t + (1 - mu) * (MF.h - MF.t - MF.b);
  const area = curve.length
    ? `M${sx(curve[0][0])},${sy(0)}` + curve.map(([x, mu]) => `L${sx(x)},${sy(mu)}`).join("") + `L${sx(curve[curve.length - 1][0])},${sy(0)}z`
    : "";
  const top = curve.length ? curve.map(([x, mu], i) => `${i ? "L" : "M"}${sx(x)},${sy(mu)}`).join("") : "";

  const move = (e: React.PointerEvent) => {
    const px = svgX(svgRef.current, MF.w, e.clientX);
    const x = variable.low + ((px - MF.l) / (MF.w - MF.l - MF.r)) * span;
    const nearest = curve.reduce((best, p) => (Math.abs(p[0] - x) < Math.abs(best[0] - x) ? p : best), curve[0] ?? [0, 0]);
    setHover(nearest[0]);
    show(e, {
      title: `${variable.label} = ${num(nearest[0], 0)}`,
      rows: [
        { value: num(nearest[1], 2), label: "ผลรวมหลังตัดยอด", color: "var(--accent)" },
        ...keys.map((k, i) => ({ value: num(membership(variable.sets[k], nearest[0]), 2), label: variable.sets[k].label, color: SERIES[i] })),
      ],
    });
  };

  const cogX = sx(crisp);
  return (
    <div className="chart" ref={wrap}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${MF.w} ${MF.h}`}
        className="chart-svg"
        role="img"
        aria-label={`ผลลัพธ์ของ ${variable.label} หลัง Defuzzification ได้ ${num(crisp, 1)}`}
        onPointerMove={move}
        onPointerLeave={() => {
          setHover(null);
          hide();
        }}
      >
        {[0, 0.5, 1].map((mu) => (
          <g key={mu}>
            <line x1={MF.l} x2={MF.w - MF.r} y1={sy(mu)} y2={sy(mu)} className={mu === 0 ? "axis-line" : "grid-line"} />
            <text x={MF.l - 8} y={sy(mu) + 4} textAnchor="end" className="ax-label">
              {mu}
            </text>
          </g>
        ))}
        {[variable.low, (variable.low + variable.high) / 2, variable.high].map((v) => (
          <text key={v} x={sx(v)} y={MF.h - MF.b + 17} textAnchor="middle" className="ax-label">
            {num(v)}
          </text>
        ))}
        {keys.map((k, i) => {
          const pts = setOutline(variable.sets[k], variable.low, variable.high);
          return (
            <path
              key={k}
              d={pts.map(([x, y], j) => `${j ? "L" : "M"}${sx(x)},${sy(y)}`).join("")}
              className="series-line series-ghost"
              stroke={SERIES[i]}
            />
          );
        })}
        <path d={area} className="area-fill" />
        <path d={top} className="series-line" stroke="var(--accent)" />
        {hover != null && <line x1={sx(hover)} x2={sx(hover)} y1={MF.t} y2={MF.h - MF.b} className="crosshair" />}
        <line x1={cogX} x2={cogX} y1={MF.t - 6} y2={MF.h - MF.b} className="cog-line" />
        <text
          x={cogX + (cogX > MF.w - 110 ? -8 : 8)}
          y={MF.t + 2}
          textAnchor={cogX > MF.w - 110 ? "end" : "start"}
          className="dl-label dl-strong"
        >
          COG = {num(crisp, 1)}
        </text>
      </svg>
      <Legend
        items={[
          { label: "ผลรวมหลังตัดยอด", color: "var(--accent)", mark: "rect" },
          ...keys.map((k, i) => ({ label: variable.sets[k].label, color: SERIES[i], mark: "dash" as const })),
        ]}
      />
      {node}
    </div>
  );
}

// ---------- แท่งแนวนอน ----------
export interface BarRow {
  key: string;
  label: ReactNode;
  sub?: ReactNode;
  value: number;
  valueText?: ReactNode;
  color?: string;
}

export function BarList({ rows, max }: { rows: BarRow[]; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  const labelled = rows.some((r) => r.label);
  return (
    <ul className={labelled ? "barlist" : "barlist barlist-bare"}>
      {rows.map((row) => (
        <li key={row.key} title={typeof row.label === "string" ? `${row.label}: ${row.valueText ?? row.value}` : undefined}>
          {labelled && (
            <div className="barlist-label">
              <span>{row.label}</span>
              {row.sub && <span className="xsmall faint">{row.sub}</span>}
            </div>
          )}
          <div className="barlist-track">
            <span style={{ width: `${(row.value / top) * 100}%`, background: row.color ?? "var(--series-1)" }} />
          </div>
          <span className="barlist-value num">{row.valueText ?? row.value}</span>
        </li>
      ))}
    </ul>
  );
}

// ---------- เวลาคิดแต่ละครั้งในข้อเดียวกัน (ดูแนวโน้มก่อน Fuzzy Impasse) ----------
export function RtBars({ values, expected }: { values: number[]; expected?: number }) {
  if (!values.length) return <p className="small faint">ยังไม่มีการตอบในข้อนี้</p>;
  const w = 260;
  const h = 96;
  const top = Math.max(expected ?? 0, ...values) * 1.15 || 1;
  const bw = Math.min(34, (w - 20) / values.length - 8);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="chart-svg rt-bars" role="img" aria-label={`เวลาคิดแต่ละครั้ง ${values.map((v) => num(v, 0)).join(", ")} วินาที`}>
      <line x1={0} x2={w} y1={h - 16} y2={h - 16} className="axis-line" />
      {expected != null && (
        <g>
          <line x1={0} x2={w} y1={h - 16 - (expected / top) * (h - 30)} y2={h - 16 - (expected / top) * (h - 30)} className="value-line" />
          <text x={w - 2} y={h - 20 - (expected / top) * (h - 30)} textAnchor="end" className="ax-label">
            เวลาที่คาด {expected} วิ
          </text>
        </g>
      )}
      {values.map((v, i) => {
        const bh = Math.max(5, (v / top) * (h - 30));
        const x = 10 + i * (bw + 8);
        return (
          <g key={i}>
            <path
              d={`M${x},${h - 16}v${-(bh - 4)}q0,-4 4,-4h${bw - 8}q4,0 4,4v${bh - 4}z`}
              fill="var(--series-1)"
            />
            <text x={x + bw / 2} y={h - 20 - bh} textAnchor="middle" className="ax-label num">
              {num(v, 0)}
            </text>
            <text x={x + bw / 2} y={h - 3} textAnchor="middle" className="ax-label">
              ครั้งที่ {i + 1}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
