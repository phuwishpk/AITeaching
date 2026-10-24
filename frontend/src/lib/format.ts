export const pct = (value?: number | null, digits = 0) =>
  value == null || Number.isNaN(value) ? "–" : `${(value * 100).toFixed(digits)}%`;

export const num = (value?: number | null, digits = 0) =>
  value == null || Number.isNaN(value) ? "–" : value.toLocaleString("th-TH", { maximumFractionDigits: digits });

export function ago(ts?: number | null, now = Date.now() / 1000, short = false) {
  if (!ts) return "–";
  const diff = Math.max(0, now - ts);
  const suffix = short ? "" : "ที่แล้ว";
  if (diff < 45) return "เมื่อสักครู่";
  if (diff < 3600) return `${Math.round(diff / 60)} นาที${suffix}`;
  if (diff < 86400) return `${Math.round(diff / 3600)} ชม. ${suffix}`.trim();
  return `${Math.round(diff / 86400)} วัน${suffix}`;
}

export function clock(ts?: number | null) {
  if (!ts) return "–";
  return new Date(ts * 1000).toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function mmss(seconds?: number | null) {
  if (seconds == null) return "";
  const s = Math.ceil(seconds);
  return s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : `${s}`;
}

export const POSITION_LABELS: Record<string, string> = {
  ANSWERING: "กำลังคิด",
  DELIBERATE_DELAY: "Deliberate Delay",
  RAPID_GUESS_LOCK: "ล็อก Rapid Guess",
  HINT_L1: "คำใบ้ L1",
  HINT_L2: "คำใบ้ L2",
  HINT_L3: "คำใบ้ L3",
  ISOMORPHIC_TEST: "Isomorphic Test",
  IMPASSE: "Impasse",
  REMEDIAL: "Remedial Loop",
  CIRCUIT_BREAKER: "Circuit Breaker",
  WALKTHROUGH: "Walkthrough",
  IDLE_PAUSE: "Idle Pause",
  CHOOSING_PATH: "รอเลือกทางต่อ",
  SAFETY_STOP: "หยุดเพื่อความปลอดภัย",
  STAGNATION_DEADLOCK: "Stagnation Deadlock",
  COMPLETED: "จบชุด",
  SESSION_ENDED: "จบ Session",
  LIVE_GEN: "สร้างโจทย์สด",
  AI_OUTAGE: "AI ขัดข้อง",
};

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info" | "calm";

export const POSITION_TONE: Record<string, Tone> = {
  ANSWERING: "neutral",
  DELIBERATE_DELAY: "warning",
  RAPID_GUESS_LOCK: "warning",
  HINT_L1: "info",
  HINT_L2: "info",
  HINT_L3: "info",
  ISOMORPHIC_TEST: "accent",
  IMPASSE: "calm",
  REMEDIAL: "calm",
  CIRCUIT_BREAKER: "calm",
  WALKTHROUGH: "calm",
  IDLE_PAUSE: "neutral",
  CHOOSING_PATH: "warning",
  SAFETY_STOP: "danger",
  STAGNATION_DEADLOCK: "danger",
  COMPLETED: "success",
  SESSION_ENDED: "neutral",
  LIVE_GEN: "info",
  AI_OUTAGE: "warning",
};

export const PATH_LABELS: Record<string, string> = {
  FAST_TRACK: "Fast-Track",
  STANDARD: "Standard",
  SUPPORTED: "Supported",
};

export const CLUSTER_COLORS: Record<string, string> = {
  fast: "var(--cluster-fast)",
  guesser: "var(--cluster-guesser)",
  struggling: "var(--cluster-struggling)",
  bite: "var(--cluster-bite)",
};

export const CLUSTER_SHORT: Record<string, string> = {
  fast: "Fast",
  struggling: "Struggling",
  guesser: "Guessers",
  bite: "Bite-sized",
};

export const CLUSTER_NAMES: Record<string, string> = {
  fast: "Fast Learners",
  struggling: "Struggling Learners",
  guesser: "Trial-and-Error Guessers",
  bite: "Bite-sized Users",
};

export const ALERT_TONE: Record<string, Tone> = { urgent: "danger", normal: "warning", silent: "calm" };
export const ALERT_LABEL: Record<string, string> = { urgent: "ด่วน", normal: "ปกติ", silent: "เงียบ" };
