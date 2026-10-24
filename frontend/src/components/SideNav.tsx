import type { ReactNode } from "react";
import { NavLink } from "react-router";

// เมนูด้านข้างของหน้าครูและ Admin: แบ่งเป็นกลุ่มตามงาน หัวกลุ่มบอกว่าเมนูในกลุ่มใช้ทำอะไร
export interface NavEntry {
  to: string;
  label: ReactNode;
  icon: ReactNode;
  end?: boolean;
  count?: number;
  tone?: "calm";
}

export interface NavSection {
  title: string;
  items: NavEntry[];
}

export default function SideNav({ sections, label, footer }: { sections: NavSection[]; label: string; footer?: ReactNode }) {
  return (
    <nav className="sidebar" aria-label={label}>
      {sections.map((section) => (
        <div key={section.title} className="nav-section">
          <span className="nav-section-title">{section.title}</span>
          {section.items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              {item.icon}
              <span>{item.label}</span>
              {!!item.count && <span className={`nav-count ${item.tone === "calm" ? "nav-count-calm" : ""}`}>{item.count}</span>}
            </NavLink>
          ))}
        </div>
      ))}
      {footer && <div className="sidebar-foot xsmall faint">{footer}</div>}
    </nav>
  );
}
