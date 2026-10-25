// รูปข้อมูลของ Gem จาก /api/gems (backend/app/gems/manage.py)

export type AlertLevel = "urgent" | "normal" | "silent";

export interface AlertRule {
  enabled: boolean;
  level: AlertLevel;
  mode: "notify" | "pause";
}

export interface GemMeta {
  alert_situations: { key: string; label: string; locked: boolean }[];
  alert_defaults: Record<string, AlertRule>;
  flow: FlowCatalog;
}

export interface GemTools {
  chat: boolean;
  hints: boolean;
  isomorphic: boolean;
  walkthrough: boolean;
  remedial: boolean;
}

export interface BuildStep {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
}

export interface GemBuild {
  status: "idle" | "building" | "ready" | "error";
  step?: string;
  steps?: BuildStep[];
  error?: string;
  warnings?: string[];
  errors?: string[];
  started_at?: number;
  finished_at?: number;
  stats?: BankStats;
}

export interface BankStats {
  concepts: number;
  bugs: number;
  main: number;
  isomorphic: number;
  remedial: number;
  challenge: number;
  flagged: number;
  pending: number;
  check: number;
  formats: string[];
}

export interface BankItem {
  id: string;
  kind: string;
  format: string;
  prompt: string;
  math: string | null;
  answer: string;
  concept: string | null;
  options: { id: string; text: string }[] | null;
  flag: { reasons: string[] } | null;
}

export interface GemFile {
  id: number;
  filename: string;
  kind: string;
  chars: number;
  chunks: number;
  warning: string | null;
  // ใครอ่านไฟล์นี้: gemini (Gemini อ่านเอง รวมภาพสแกน) · gemini+local (บางหน้าใช้ตัวอ่านในเครื่อง) · local
  reader: string | null;
}

export interface GemDetail {
  id: string;
  name: string;
  description: string;
  instructions: string;
  icon: string;
  color: string;
  tools: GemTools;
  starter_prompts: string[];
  alert_rules: Record<string, AlertRule>;
  bank_version: number;
  build: GemBuild;
  files: GemFile[];
  bank: {
    subject_id: string;
    set_id: string;
    grade: string;
    target: string | null;
    concepts: { id: string; name: string; prerequisites: string[] }[];
    bugs: { id: string; type: string; name: string }[];
    stats: BankStats;
    readiness: { ok: boolean; errors: string[]; warnings: string[] };
    flagged: BankItem[];
    samples: BankItem[];
  } | null;
  versions: GemVersion[];
  locked_constraints: string;
  options: { icons: string[]; colors: string[] };
}

export interface GemVersion {
  n: number;
  ts: number;
  actor: string;
  note: string;
  bank_version: number | null;
}

export interface GemSummary {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  bank_version: number;
  status: GemBuild["status"];
  stats: BankStats | null;
  files: number;
  updated_at: number;
}

export const TOOL_LABELS: Record<keyof GemTools, { label: string; text: string }> = {
  chat: { label: "แชตครูผู้ช่วย", text: "นักเรียนพิมพ์ถาม AI ได้ ตอบแบบ Socratic ไม่เฉลย" },
  hints: { label: "บันไดคำใบ้", text: "คำใบ้ 3 ระดับหลังตอบผิด" },
  isomorphic: { label: "Isomorphic Test", text: "ข้อคู่ขนานไม่มีคำใบ้ หลังผ่านด้วยคำใบ้" },
  walkthrough: { label: "Walkthrough", text: "ตัวอย่างทีละขั้นเมื่อติดหล่ม" },
  remedial: { label: "ทบทวนพื้นฐาน", text: "พาไปทำโจทย์ Prerequisite เมื่อ Impasse" },
};

export const STATUS_TEXT: Record<GemBuild["status"], { label: string; tone: "neutral" | "info" | "success" | "warning" }> = {
  idle: { label: "ยังไม่สร้างคลังโจทย์", tone: "neutral" },
  building: { label: "กำลังสร้างคลังโจทย์", tone: "info" },
  ready: { label: "พร้อมใช้", tone: "success" },
  error: { label: "สร้างไม่สำเร็จ", tone: "warning" },
};

// ---------------------------------------------------------------- Flow ที่ AI ออกแบบจากคำสั่ง (backend/app/gems/flowspec.py)

export interface FlowStepSpec {
  id: string;
  kind: string;
  label: string;
  pick?: string;
  hint_button?: boolean;
  level?: number | "auto" | string;
  delay?: number;
  title?: string;
  text?: string;
  walkthrough?: boolean;
  question?: string;
  judge?: boolean;
  rubric?: string;
  seconds?: number;
  result?: string;
}

export interface FlowEdgeSpec {
  id?: string;
  from: string;
  to: string;
  when: string;
  label: string;
  text?: string;
}

export interface FlowSpec {
  summary: string;
  start: string;
  params: Record<string, number>;
  steps: FlowStepSpec[];
  edges: FlowEdgeSpec[];
}

export interface FlowMapData {
  nodes: { id: string; label: string; kind: string; lane: string; about: string; start: boolean }[];
  edges: { id: string; source: string; target: string; label: string; when: string; text: string }[];
  guards: { id: string; label: string; text: string }[];
}

export interface GemFlowDetail {
  mode: "custom" | "standard";
  source: "ai" | "teacher" | "template" | null;
  reviewed: boolean;
  updated_at: number | null;
  warnings: string[];
  summary: string;
  spec: FlowSpec | null;
  map: FlowMapData | null;
  template: FlowSpec;
  outdated: boolean;
}

export interface FlowCheck {
  spec: FlowSpec | null;
  errors: string[];
  warnings: string[];
  map: FlowMapData | null;
}

export interface FlowCatalog {
  kinds: { key: string; label: string; lane: string; wait: boolean; about: string }[];
  picks: { key: string; label: string }[];
  vars: { key: string; label: string; type: string }[];
  params: { key: string; label: string; min: number; max: number; default: number }[];
  step_numbers: Record<string, { min: number; max: number }>;
  locked: { title: string; text: string }[];
  guards: { id: string; label: string; text: string }[];
}

export const FLOW_SOURCE: Record<string, string> = {
  ai: "AI ออกแบบจากคำสั่ง",
  teacher: "ครูแก้เอง",
  template: "แม่แบบมาตรฐาน",
};
