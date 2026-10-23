import { useCallback, useEffect, useRef, useState } from "react";
import { getAuth, type Role } from "./api";

// รับเหตุการณ์สดจาก backend ผ่าน WebSocket และต่อใหม่เองเมื่อหลุด
export function useLive(role: Role, onMessage: (message: any) => void, enabled = true) {
  const handler = useRef(onMessage);
  handler.current = onMessage;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let stopped = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const auth = getAuth(role);
      if (!auth || stopped) return;
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${location.host}/ws?token=${encodeURIComponent(auth.token)}`);
      socket.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        try {
          handler.current(JSON.parse(event.data));
        } catch {
          /* ข้อความที่อ่านไม่ได้ ข้ามไป */
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) timer = setTimeout(connect, Math.min(8000, 800 * 2 ** retry++));
      };
    };

    connect();
    const ping = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
    }, 25000);
    return () => {
      stopped = true;
      clearTimeout(timer);
      clearInterval(ping);
      socket?.close();
    };
  }, [role, enabled]);

  return connected;
}

// โหลดข้อมูลแบบ async พร้อมสถานะกำลังโหลดและข้อผิดพลาด
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    try {
      const result = await loaderRef.current();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, setData, error, loading, reload };
}

// นับถอยหลังจากจำนวนวินาทีที่ได้จาก backend
export function useCountdown(seconds: number | null | undefined, onDone?: () => void) {
  const [left, setLeft] = useState<number | null>(seconds ?? null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (seconds == null) {
      setLeft(null);
      return;
    }
    const end = Date.now() + seconds * 1000;
    setLeft(seconds);
    let fired = false;
    const id = setInterval(() => {
      const value = Math.max(0, (end - Date.now()) / 1000);
      setLeft(value);
      if (value <= 0 && !fired) {
        fired = true;
        clearInterval(id);
        done.current?.();
      }
    }, 200);
    return () => clearInterval(id);
  }, [seconds]);

  return left;
}

// ธีม: ตามระบบ / สว่าง / มืด (จำไว้เฉพาะเครื่องนี้)
export type ThemeMode = "system" | "light" | "dark";

export function useTheme(): [ThemeMode, (mode: ThemeMode) => void] {
  const [mode, setMode] = useState<ThemeMode>(() => {
    try {
      return (localStorage.getItem("adaptive-tutor:theme") as ThemeMode) || "system";
    } catch {
      return "system";
    }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (mode === "system") delete root.dataset.theme;
    else root.dataset.theme = mode;
    try {
      localStorage.setItem("adaptive-tutor:theme", mode);
    } catch {
      /* ไม่บันทึกก็ได้ */
    }
  }, [mode]);
  return [mode, setMode];
}

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now() / 1000), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
