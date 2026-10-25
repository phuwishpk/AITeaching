import { EyeOff } from "lucide-react";
import type { FlowEdge, FlowNode } from "../../components/FlowMap";

// ผังของ Gem แต่ละตัว (backend/app/gems/design.py): ไม่ใช่ผังตายตัว กล่องของเครื่องมือที่ครูปิดไม่อยู่ในผัง
// และเส้นต่อไปยังขั้นที่ engine ใช้จริง

export interface GemFlow {
  gem_id?: string;
  name?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  disabled: Record<string, string>;
  alerts: Record<string, { key: string; label: string; level: string; mode: "notify" | "pause" }[]>;
}

// บอกว่ากล่องไหนไม่อยู่ในผังของ Gem นี้เพราะครูปิดเครื่องมือ (รวมกล่องตามเหตุผลเดียวกัน)
// allNodes คือผังเต็มของระบบ ใช้หาชื่อของกล่องที่ไม่อยู่ในผังนี้
export function HiddenNote({ disabled, allNodes }: { disabled: Record<string, string>; allNodes: FlowNode[] }) {
  const name = new Map(allNodes.map((n) => [n.id, n.label.replace("\n", " ")]));
  const groups = new Map<string, string[]>();
  for (const [node, reason] of Object.entries(disabled)) groups.set(reason, [...(groups.get(reason) ?? []), name.get(node) ?? node]);
  if (!groups.size) return <p className="xsmall muted">Gem นี้เปิดเครื่องมือการสอนครบ ผังจึงมีทุกขั้น</p>;
  return (
    <ul className="hidden-note">
      {[...groups].map(([reason, nodes]) => (
        <li key={reason} className="xsmall">
          <EyeOff size={13} />
          <span>
            <span className="strong">{reason}</span> · ไม่อยู่ในผัง: {nodes.join(", ")}
          </span>
        </li>
      ))}
    </ul>
  );
}
