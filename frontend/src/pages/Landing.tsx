import { Link } from "react-router";
import { ArrowRight, GraduationCap, Network, UsersRound } from "lucide-react";
import { BrandMark, ThemeToggle } from "../components/Shell";

const ROLES = [
  {
    to: "/student",
    icon: <GraduationCap size={22} />,
    title: "นักเรียน",
    text: "ทำชุดคำถามที่ปรับตามจังหวะของตัวเอง มีคำใบ้ทีละขั้นและครูผู้ช่วยคอยถามนำ",
    action: "เข้าด้วยรหัสนักเรียน",
  },
  {
    to: "/teacher",
    icon: <UsersRound size={22} />,
    title: "ครู",
    text: "ดูแลนักเรียนรายคน รับการแจ้งเตือน สั่งแทรกแซงได้ทุกเมื่อ และจัดการชุดคำถาม",
    action: "เข้าหน้าครู",
  },
  {
    to: "/admin",
    icon: <Network size={22} />,
    title: "ผู้ดูแลระบบ",
    text: "ดูตรรกะของระบบแบบสด นักเรียนแต่ละคนอยู่ตรงไหนในผัง และหลักการเบื้องหลังทุกขั้น",
    action: "เข้าหน้าผู้ดูแลระบบ",
  },
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-top">
        <div className="brand">
          <BrandMark />
          <span>Adaptive Tutor</span>
        </div>
        <ThemeToggle />
      </header>
      <main className="landing-main">
        <section className="landing-hero fade-in">
          <p className="eyebrow">Intelligent Tutoring System</p>
          <h1 className="landing-title">ติวเตอร์ที่รอให้คิดก่อน แล้วค่อยช่วยทีละขั้น</h1>
          <p className="lead">
            ระบบอ่านร่องรอยการเรียนของนักเรียนแต่ละคน ปรับลำดับโจทย์ ความยาก และคำใบ้ให้พอดีกับเขตพัฒนาการ
            โดยไม่เฉลยคำตอบ และให้ครูเป็นผู้ตัดสินใจขั้นสุดท้ายเสมอ
          </p>
        </section>
        <section className="role-grid">
          {ROLES.map((role, index) => (
            <Link key={role.to} to={role.to} className="card card-hover role-card fade-in" style={{ animationDelay: `${index * 60}ms` }}>
              <span className="role-icon">{role.icon}</span>
              <h2 className="title">{role.title}</h2>
              <p className="muted small">{role.text}</p>
              <span className="role-action">
                {role.action}
                <ArrowRight size={16} />
              </span>
            </Link>
          ))}
        </section>
        <p className="faint small landing-note">
          เปิดหลายแท็บพร้อมกันได้ ตอนสาธิตให้วางหน้านักเรียนคู่กับหน้าผู้ดูแลระบบ แล้วผังตรรกะจะขยับตามทุกครั้งที่ตอบ
        </p>
      </main>
    </div>
  );
}
