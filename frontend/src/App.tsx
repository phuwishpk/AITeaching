import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import Landing from "./pages/Landing";
import StudentHome from "./pages/student/StudentHome";
import Workspace from "./pages/student/Workspace";
import { Spinner } from "./components/ui";

// หน้าครูและ Admin โหลดแยก หน้านักเรียนจึงเปิดได้เร็ว
const TeacherApp = lazy(() => import("./pages/teacher/TeacherApp"));
const AdminApp = lazy(() => import("./pages/admin/AdminApp"));

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/student" element={<StudentHome />} />
        <Route path="/student/:setId" element={<Workspace />} />
        <Route path="/teacher/*" element={<TeacherApp />} />
        <Route path="/admin/*" element={<AdminApp />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
