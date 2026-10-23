import { BookOpen, Code2, Quote } from "lucide-react";

// การ์ดหลักการ: ผูกขั้นตอนในผังกับแนวคิดที่มาจากบทเรียน และไฟล์โค้ดที่ทำหน้าที่นั้น
export interface Principle {
  title: string;
  theory: string;
  principle: string;
  source: string;
  code: string;
}

export default function PrincipleCard({ card, compact }: { card: Principle; compact?: boolean }) {
  return (
    <article className={`principle ${compact ? "principle-compact" : ""}`}>
      <div className="principle-theory">
        <BookOpen size={15} aria-hidden />
        {card.theory}
      </div>
      <h3 className="principle-title">{card.title}</h3>
      <p className="principle-text">{card.principle}</p>
      <dl className="principle-meta">
        <div>
          <dt>
            <Quote size={13} aria-hidden />
            ที่มา
          </dt>
          <dd>{card.source}</dd>
        </div>
        <div>
          <dt>
            <Code2 size={13} aria-hidden />
            โค้ด
          </dt>
          <dd className="mono">{card.code}</dd>
        </div>
      </dl>
    </article>
  );
}
