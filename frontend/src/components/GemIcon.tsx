import { BookOpen, Calculator, Code2, FlaskConical, Globe, Music, Palette, Sparkles } from "lucide-react";

// ไอคอนและสีของ Gem ที่ครูเลือก ใช้ทั้งหน้าครู (รายการ ตัวแก้) และการ์ดฝั่งนักเรียน

export const GEM_ICONS: Record<string, typeof Sparkles> = {
  sparkles: Sparkles,
  calculator: Calculator,
  book: BookOpen,
  flask: FlaskConical,
  globe: Globe,
  code: Code2,
  palette: Palette,
  music: Music,
};

export const GEM_COLORS: Record<string, string> = {
  teal: "var(--accent)",
  blue: "var(--info)",
  violet: "var(--lane-care)",
  amber: "var(--lane-wrong)",
  rose: "var(--lane-human)",
  green: "var(--lane-correct)",
};

export default function GemIcon({ icon, color, size = 40 }: { icon?: string | null; color?: string | null; size?: number }) {
  const Icon = GEM_ICONS[icon ?? ""] ?? Sparkles;
  const tone = GEM_COLORS[color ?? ""] ?? GEM_COLORS.teal;
  return (
    <span className="gem-icon" style={{ width: size, height: size, color: tone, ["--gem-tone" as string]: tone }} aria-hidden>
      <Icon size={Math.round(size * 0.5)} />
    </span>
  );
}
