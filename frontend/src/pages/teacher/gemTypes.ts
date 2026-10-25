// รูปข้อมูลของ Gem จาก /api/gems (backend/app/gems/manage.py)

export type AlertLevel = "urgent" | "normal" | "silent";

export interface AlertRule {
  enabled: boolean;
  level: AlertLevel;
  mode: "notify" | "pause";
}

export interface AlertSituation {
  key: string;
  label: string;
  locked: boolean;
  chat: boolean; // เกิดจากแชตเท่านั้น ครูปิดแชตก็ไม่แสดง
}

export interface GemMeta {
  alert_situations: AlertSituation[];
  alert_defaults: Record<string, AlertRule>;
  flow: FlowCatalog;
  // คู่มือคำที่ใช้เขียนคำสั่ง: ตัวอย่างที่ครูพิมพ์ และระบบทำอะไร (ไม่บังคับ AI ตีความตามบริบท)
  guide: { title: string; items: { say: string; does: string }[] }[];
  guide_note: string;
  // ตัวอย่างคำสั่งทั้งชุด เช่น ครบผังมาตรฐาน
  examples: { title: string; text: string }[];
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
  knowledge: GemKnowledge | null;
  // เจ้าของ Gem (มีผู้ใช้หลายคน): AI ของ Gem นี้คิดกับ API key ของคนนี้
  owner: string | null;
  owner_name: string | null;
  // สถานการณ์แจ้งเตือนที่ Flow ของ Gem นี้เกิดได้จริง
  options: { icons: string[]; colors: string[]; alert_situations: AlertSituation[] };
  features: FlowFeatures;
}

// ฟีเจอร์ที่ Flow ของ Gem ใช้จริง (engine/gemflow.features) ทุกหน้าแสดงเฉพาะส่วนที่มีใน Flow
// all = ยังไม่มี Flow ที่ออกแบบจากคำสั่ง
export interface FlowFeatures {
  all: boolean;
  hint_button?: boolean;
  hints?: boolean;
  lesson?: boolean;
  walkthrough?: boolean;
  reflect?: boolean;
  activity?: boolean;
  widget?: boolean;
  widgets?: string[];
  chat_flow?: boolean;
  break?: boolean;
  notify?: boolean;
  teacher?: boolean;
  isomorphic?: boolean;
  remedial?: boolean;
}

export const FEATURE_LABELS: [Exclude<keyof FlowFeatures, "all" | "widgets">, string][] = [
  ["hint_button", "ปุ่มขอคำใบ้"],
  ["hints", "คำใบ้หลังตอบผิด"],
  ["isomorphic", "Isomorphic Test (ข้อคู่ขนานไม่มีคำใบ้)"],
  ["remedial", "ทบทวนพื้นฐาน (Prerequisite)"],
  ["lesson", "บทเรียนย่อ / ทบทวนเนื้อหา"],
  ["walkthrough", "ตัวอย่างทีละขั้น (Walkthrough)"],
  ["reflect", "อธิบายความคิด"],
  ["activity", "กิจกรรมที่ AI สร้าง"],
  ["widget", "Widget ให้ลงมือทำ"],
  ["chat_flow", "แนวทางตอบแชตจากครู"],
  ["break", "พักสายตา"],
  ["notify", "แจ้งครู"],
  ["teacher", "หยุดรอครู"],
];

// สิ่งที่ AI อ่านและจดจากไฟล์ความรู้ก่อนสร้างโจทย์ (backend/app/gems/builder.py › read_knowledge)
export interface GemKnowledge {
  mode: "full" | "digest";
  files: number;
  chars: number;
  read: number;
  segments?: number;
  memory: {
    summary: string;
    concepts: { name: string; detail?: string; source?: string }[];
    teacher_items: { problem: string; answer?: string; source?: string }[];
    misconceptions: { name: string; example?: string; source?: string }[];
    teaching: string[];
  } | null;
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
  owner_name: string | null;
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
  goal?: string;
  response?: string;
  // ขั้น widget: ชนิดในคลัง (หรือ custom ที่ AI เขียนเอง) คำสั่งถึงนักเรียน และข้อมูลของ Widget
  widget?: string;
  prompt?: string;
  config?: Record<string, unknown>;
  // ข้อความในคำสั่งของครูหรือเอกสารที่เป็นที่มาของขั้นนี้
  reason?: string;
}

export interface FlowEdgeSpec {
  id?: string;
  from: string;
  to: string;
  when: string;
  label: string;
  text?: string;
}

// แนวทางการตอบแชตของ AI ที่ดึงจากคำสั่งของครู (ไม่มี = แชตแบบอัตโนมัติ) ข้อห้ามที่ล็อกไว้ใช้เสมอ
export interface ChatIntent {
  id: string;
  label: string;
  keywords: string[];
  reply: string;
  goto: string | null;
  notify: boolean;
}

export interface ChatSpec {
  style: string;
  sentences: number;
  examples: boolean;
  // ถามเรื่องโจทย์ในแชตนับเป็นการขอคำใบ้ระดับ 1 (ค่าเริ่มต้น)
  count_as_hint: boolean;
  guards: string[];
  intents: ChatIntent[];
  reason?: string;
}

export interface FlowSpec {
  summary: string;
  chat?: ChatSpec;
  // ขั้นที่ไปหลังพักเพราะเครียด (Circuit Breaker) ไม่มี = กลับขั้นเดิม
  after_stress?: string;
  // แนวทางของครูแต่ละข้อ และขั้นที่ทำแนวทางนั้น (AI เขียนก่อนออกแบบ)
  guidelines?: { text: string; steps: string[] }[];
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
  reference_map: FlowMapData;
  outdated: boolean;
  // คำที่ครูเขียนไว้ใน prompt ให้จับในแชต
  teacher_keywords: string[];
  table: FlowTable[];
  audit: { guideline: string; ok: boolean; evidence: string; fix: string }[];
}

// ระบบจำลองว่านักเรียนแต่ละแบบจะไปขั้นไหน (gems/simulate.py)
export interface FlowTable {
  step: string;
  label: string;
  rows: { case: string; to: string }[];
}

export interface FlowCheck {
  spec: FlowSpec | null;
  errors: string[];
  warnings: string[];
  map: FlowMapData | null;
  table: FlowTable[];
}

export interface FlowCatalog {
  kinds: { key: string; label: string; lane: string; wait: boolean; about: string }[];
  picks: { key: string; label: string }[];
  widgets: { key: string; label: string; about: string; config: string; graded: boolean }[];
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
