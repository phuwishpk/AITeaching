// รูปข้อมูลของ Gem จาก /api/gems (backend/app/gems/manage.py)

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
  locked_constraints: string;
  options: { icons: string[]; colors: string[] };
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
