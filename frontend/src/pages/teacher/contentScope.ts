import { createContext, useContext } from "react";

// หน้าจัดการวิชาใช้ได้ทั้งครูและ Admin: บอกว่าเรียก API ด้วย token ของบทบาทไหน และลิงก์กลับไปที่ไหน
export interface ContentScope {
  role: "teacher" | "admin";
  base: string;
}

export const ContentScopeContext = createContext<ContentScope>({ role: "teacher", base: "/teacher/content" });

export const useContentScope = () => useContext(ContentScopeContext);
