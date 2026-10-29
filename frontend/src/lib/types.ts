// รูปแบบข้อมูลที่ backend ส่งให้หน้าครูและ Admin (ดู backend/app/engine/core.py › staff_view)

export interface Decision {
  ts: number;
  from: string;
  to: string;
  edges: string[];
  rule: string;
  detail?: Record<string, unknown>;
  item?: string | null;
}

export interface StoredDecision {
  id?: number;
  ts: number;
  set_id: string;
  from_pos: string;
  to_pos: string;
  rule: string;
  from_text?: string;
  to_text?: string;
  edges?: string[];
  detail?: Record<string, unknown>;
}

export interface Alert {
  id: number;
  ts: number;
  code: string;
  level: "urgent" | "normal" | "silent";
  kind: string;
  message: string;
  acknowledged: number;
}

export interface StaffItem {
  id: string;
  mode: string;
  concept: string;
  error_count: number;
  hint_level: number;
  hint_floor: number;
  last_tag: string | null;
  last_class: string | null;
  rts: number[];
}

export interface Remedial {
  concept: string;
  round: number;
  streak: number;
  suspended: string;
  root: boolean;
}

export interface Risk {
  score: number;
  inputs: Record<string, number>;
}

export interface StaffView {
  code: string;
  kind: string;
  name?: string | null;
  persona?: string | null;
  cluster?: { key: string; name: string } | null;
  position: string | null;
  teacher_text: string;
  set_id?: string;
  subject_id?: string;
  set_name?: string;
  target?: string;
  position_label?: string;
  position_since?: number;
  path?: string;
  item?: StaffItem | null;
  item_concept_name?: string | null;
  mastery?: Record<string, number | null>;
  cross_format?: Record<string, boolean>;
  remedial?: Remedial | null;
  remedial_concept_name?: string;
  remedial_rounds?: Record<string, number>;
  timers?: Record<string, number | null>;
  items_count?: number;
  attempts?: number;
  accuracy?: number | null;
  avg_rt?: number | null;
  first_attempt_success?: number;
  hint_abuse_index?: number;
  rapid_total?: number;
  idle_count?: number;
  content_revisits?: number;
  ended?: boolean;
  end_reason?: string | null;
  last_decision?: Decision | null;
  last_activity?: number;
  // Flow ของ Gem: กล่องในผังที่นักเรียนอยู่ และ AI กำลังคิดคำตอบแชตอยู่หรือไม่
  map_node?: string | null;
  chat_thinking?: boolean;
  risk?: Risk;
  concept_names?: Record<string, string>;
}

export interface Telemetry {
  drop_off: Record<string, { sessions: number; dropped: number; completed: number; drop_off_rate: number }>;
  remediation_success: number | null;
  remediation_counts: { started: number; passed: number };
  hint_utility: number | null;
  hint_counts: { shown: number; useful: number };
}

export interface FuzzyResult {
  system: string;
  inputs: Record<string, number>;
  memberships: Record<string, Record<string, number>>;
  rules: { text: string; result: string; strength: number }[];
  clip?: Record<string, number>;
  curve?: [number, number][];
  output: number;
}

export interface AiLog {
  id: number;
  ts: number;
  code: string | null;
  purpose: string;
  provider: string;
  model: string | null;
  frames?: { role?: string; context?: string; task?: string; constraints?: string } | null;
  retrieved?: { query_terms?: string[]; documents?: { filename?: string; text?: string; score?: number }[]; tag?: string | null } | null;
  output?: string | null;
  final_text: string | null;
  guard?: { blocked?: boolean; reason?: string | null; matched?: string | null; trigger?: boolean } | null;
  tokens_in?: number;
  tokens_out?: number;
  latency_ms?: number;
  error?: string | null;
}

// ---------- เนื้อหาวิชา ----------
export interface Concept {
  id: string;
  name: string;
  grade?: string;
  description?: string;
  prerequisites?: string[];
}

export interface BugTag {
  id: string;
  type: "misconception" | "slip";
  name: string;
  prerequisite?: string | null;
  description?: string;
  response?: string;
  socratic?: string;
}

export interface ItemOption {
  id: string;
  text: string;
}

export interface Item {
  id: string;
  concept: string;
  kind: "main" | "isomorphic" | "challenge" | "remedial";
  iso_of?: string | null;
  isomorphs?: string[];
  format: "numeric" | "mcq" | "short";
  prompt: string;
  math?: string | null;
  difficulty?: number;
  min_read_time?: number;
  expected_time?: number;
  hints?: Record<string, string>;
  socratic?: string[];
  options?: ItemOption[];
  answer: { value?: number | string; option?: string; accepted?: string[] };
  bugs?: { answer: number | string; tag: string }[];
}

export interface Walkthrough {
  concept: string;
  title: string;
  problem: string;
  steps: string[];
}

export interface QuestionSet {
  id: string;
  name: string;
  description?: string;
  target_concept: string;
  main_items: string[];
  challenge_items: string[];
  max_items?: number;
  published?: boolean;
}

export interface Subject {
  id: string;
  name: string;
  grade?: string;
  description?: string;
  concepts: Concept[];
  bug_tags: BugTag[];
  items: Item[];
  walkthroughs: Walkthrough[];
  question_sets: QuestionSet[];
}

export interface Readiness {
  ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface SubjectSummary {
  id: string;
  name: string;
  grade: string;
  description: string;
  concepts: number;
  items: number;
  bug_tags: number;
  sets: (QuestionSet & { readiness: Readiness })[];
}
