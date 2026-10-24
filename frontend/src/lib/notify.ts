// แจ้งเตือนครูในเว็บ (Q12): เสียงสั้น ๆ และ Browser Notification ที่เด้งแม้แท็บไม่ได้เปิดอยู่
// ทุกอย่างเกิดในเบราว์เซอร์ของครู ไม่ส่งข้อมูลนักเรียนออกนอกเครื่อง

const KEY = "adaptive-tutor:notify";

export function notifyEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export async function setNotify(on: boolean): Promise<boolean> {
  if (on && "Notification" in window && Notification.permission === "default") {
    await Notification.requestPermission().catch(() => "denied");
  }
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* โหมดส่วนตัวบางเบราว์เซอร์เขียนไม่ได้ ใช้ได้จนปิดหน้า */
  }
  if (on) chime("normal");
  return on;
}

let audio: AudioContext | null = null;

// เสียงสองแบบ: ด่วนดังสองครั้งเสียงสูง ปกติดังครั้งเดียว
export function chime(level: string) {
  try {
    audio ??= new AudioContext();
    const notes = level === "urgent" ? [880, 1175] : [660];
    notes.forEach((frequency, i) => {
      const start = audio!.currentTime + i * 0.22;
      const osc = audio!.createOscillator();
      const gain = audio!.createGain();
      osc.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.2);
      osc.connect(gain).connect(audio!.destination);
      osc.start(start);
      osc.stop(start + 0.21);
    });
  } catch {
    /* เบราว์เซอร์ไม่รองรับเสียง ข้ามไป */
  }
}

export function notifyAlert(alert: { level: string; message: string; code: string }, who: string) {
  if (!notifyEnabled() || alert.level === "silent") return;
  chime(alert.level);
  if ("Notification" in window && Notification.permission === "granted" && document.visibilityState !== "visible") {
    const notice = new Notification(`${alert.level === "urgent" ? "ด่วน · " : ""}${who}`, { body: alert.message, tag: `${alert.code}-${alert.message}` });
    notice.onclick = () => window.focus();
  }
}
