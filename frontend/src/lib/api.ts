// เรียก API ของ backend โดยแยก token ตามบทบาท
// เปิดหน้านักเรียนกับหน้า Admin พร้อมกันบนเครื่องเดียวได้ เพราะแต่ละบทบาทใช้ token ของตัวเอง

export type Role = "student" | "teacher" | "admin";

export interface Auth {
  token: string;
  code?: string;
}

const key = (role: Role) => `adaptive-tutor:auth:${role}`;

export function getAuth(role: Role): Auth | null {
  try {
    const raw = localStorage.getItem(key(role));
    return raw ? (JSON.parse(raw) as Auth) : null;
  } catch {
    return null;
  }
}

export function setAuth(role: Role, auth: Auth) {
  try {
    localStorage.setItem(key(role), JSON.stringify(auth));
  } catch {
    /* โหมดส่วนตัวบางเบราว์เซอร์เขียนไม่ได้ ใช้ต่อได้จนปิดหน้า */
  }
}

export function clearAuth(role: Role) {
  try {
    localStorage.removeItem(key(role));
  } catch {
    /* ไม่มีอะไรต้องทำ */
  }
}

export const STAFF_ROLES = ["teacher", "admin"] as const;

export interface Account {
  username: string;
  name: string;
}

// หน้าแรก: บัญชีเดียวได้ token ทั้งหน้าครูและหน้าผู้ดูแลระบบ ชื่อที่แสดงเก็บไว้แสดงบนแถบด้านบน
export async function staffLogin(username: string, password: string): Promise<Account> {
  const result = await api<Account & { tokens: Record<(typeof STAFF_ROLES)[number], string> }>(null, "/api/auth/login", {
    body: { username, password },
  });
  for (const role of STAFF_ROLES) setAuth(role, { token: result.tokens[role], code: result.name });
  return { username: result.username, name: result.name };
}

// ออกจากระบบทั้งหน้าครูและหน้าผู้ดูแลระบบ (ใช้สลับบัญชีด้วย)
export function staffLogout() {
  for (const role of STAFF_ROLES) {
    // api อ่าน token ทันทีที่เรียก จึงล้างที่เก็บต่อได้เลยโดยไม่ต้องรอ
    if (getAuth(role)) api(role, "/api/auth/logout", { method: "POST" }).catch(() => {});
    clearAuth(role);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface Options {
  method?: string;
  body?: unknown;
  form?: FormData;
}

export async function api<T = any>(role: Role | null, path: string, options: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const auth = role ? getAuth(role) : null;
  if (auth) headers.Authorization = `Bearer ${auth.token}`;
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(path, { method: options.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError(0, "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ ระบบจะลองใหม่เมื่อกลับมาออนไลน์");
  }
  if (response.status === 401 && role) {
    clearAuth(role);
    window.dispatchEvent(new CustomEvent("auth-expired", { detail: role }));
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = typeof data.detail === "string" ? data.detail : "เกิดข้อผิดพลาด ลองใหม่อีกครั้ง";
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}
