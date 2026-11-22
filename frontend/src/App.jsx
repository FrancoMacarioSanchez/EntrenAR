import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useLocation, useOutletContext } from "react-router-dom";
import Layout from "./components/Layout";
import { Loader } from "./components/ui";
import { useAuth } from "./state/auth";
import Login from "./pages/Login";

const ChangePassword = lazy(() => import("./pages/ChangePassword"));
const Profile = lazy(() => import("./pages/Profile"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Home = lazy(() => import("./pages/student/Home"));
const Workout = lazy(() => import("./pages/student/Workout"));
const RoutineView = lazy(() => import("./pages/student/RoutineView"));
const Progress = lazy(() => import("./pages/student/Progress"));
const ExerciseHistory = lazy(() => import("./pages/student/ExerciseHistory"));
const Body = lazy(() => import("./pages/student/Body"));
const Membership = lazy(() => import("./pages/student/Membership"));
const Classes = lazy(() => import("./pages/student/Classes"));
const SessionDetail = lazy(() => import("./pages/student/SessionDetail"));
const SelfCheckin = lazy(() => import("./pages/student/SelfCheckin"));
const Scan = lazy(() => import("./pages/student/Scan"));
const Nutrition = lazy(() => import("./pages/student/Nutrition"));
const NutritionBoard = lazy(() => import("./pages/trainer/Nutrition").then((m) => ({ default: m.NutritionBoard })));
const StudentNutrition = lazy(() => import("./pages/trainer/Nutrition").then((m) => ({ default: m.StudentNutrition })));
const TrainerHome = lazy(() => import("./pages/trainer/TrainerHome"));
const Students = lazy(() => import("./pages/trainer/Students"));
const StudentDetail = lazy(() => import("./pages/trainer/StudentDetail"));
const Routines = lazy(() => import("./pages/trainer/Routines"));
const RoutineBuilder = lazy(() => import("./pages/trainer/RoutineBuilder"));
const Exercises = lazy(() => import("./pages/trainer/Exercises"));
const MyClasses = lazy(() => import("./pages/trainer/MyClasses"));
const ClassDetail = lazy(() => import("./pages/trainer/ClassDetail"));

function Private({ children }) {
  const { ready, me } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="splash"><span className="spinner" /></div>;
  if (!me) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  if (me.user.must_change_password) return <Suspense fallback={<Loader />}><ChangePassword forced /></Suspense>;
  return children;
}

function Index() {
  const { trainerMode } = useOutletContext();
  const { isStudent, isTrainer } = useAuth();
  if (!isStudent && !isTrainer) {
    return (
      <div className="page-pad"><div className="card stack center">
        <h2>Esta app es para alumnos y entrenadores</h2>
        <p className="muted">Tu usuario es del staff del gimnasio. Ingresá al panel para gestionar socios, cobros y el CRM.</p>
        <a className="btn primary block" href="/">Ir al panel</a>
      </div></div>
    );
  }
  return trainerMode ? <TrainerHome /> : <Home />;
}

function StudentOnly({ children }) {
  const { isStudent } = useAuth();
  return isStudent ? children : <Navigate to="/" replace />;
}

function TrainerOnly({ children }) {
  const { isTrainer } = useAuth();
  return isTrainer ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Private><Layout /></Private>}>
        <Route index element={<Suspense fallback={<Loader />}><Index /></Suspense>} />
        <Route path="*" element={<Suspense fallback={<Loader />}><Inner /></Suspense>} />
      </Route>
    </Routes>
  );
}

function Inner() {
  return (
    <Routes>
      <Route path="password" element={<ChangePassword />} />
      <Route path="perfil" element={<Profile />} />
      <Route path="notificaciones" element={<Notifications />} />
      <Route path="entrenar" element={<StudentOnly><Workout /></StudentOnly>} />
      <Route path="entrenar/:dayId" element={<StudentOnly><Workout /></StudentOnly>} />
      <Route path="rutina" element={<StudentOnly><RoutineView /></StudentOnly>} />
      <Route path="progreso" element={<StudentOnly><Progress /></StudentOnly>} />
      <Route path="progreso/ejercicio/:id" element={<StudentOnly><ExerciseHistory /></StudentOnly>} />
      <Route path="progreso/sesion/:id" element={<StudentOnly><SessionDetail /></StudentOnly>} />
      <Route path="ingreso" element={<StudentOnly><SelfCheckin /></StudentOnly>} />
      <Route path="escanear" element={<StudentOnly><Scan /></StudentOnly>} />
      <Route path="cuerpo" element={<StudentOnly><Body /></StudentOnly>} />
      <Route path="membresia" element={<StudentOnly><Membership /></StudentOnly>} />
      <Route path="clases" element={<StudentOnly><Classes /></StudentOnly>} />
      <Route path="nutricion" element={<StudentOnly><Nutrition /></StudentOnly>} />
      <Route path="entrenador/nutricion" element={<TrainerOnly><NutritionBoard /></TrainerOnly>} />
      <Route path="entrenador/nutricion/:id" element={<TrainerOnly><StudentNutrition /></TrainerOnly>} />
      <Route path="entrenador/alumnos" element={<TrainerOnly><Students /></TrainerOnly>} />
      <Route path="entrenador/alumnos/:id" element={<TrainerOnly><StudentDetail /></TrainerOnly>} />
      <Route path="entrenador/rutinas" element={<TrainerOnly><Routines /></TrainerOnly>} />
      <Route path="entrenador/rutinas/nueva" element={<TrainerOnly><RoutineBuilder /></TrainerOnly>} />
      <Route path="entrenador/rutinas/:id" element={<TrainerOnly><RoutineBuilder /></TrainerOnly>} />
      <Route path="entrenador/ejercicios" element={<TrainerOnly><Exercises /></TrainerOnly>} />
      <Route path="entrenador/clases" element={<TrainerOnly><MyClasses /></TrainerOnly>} />
      <Route path="entrenador/clases/:id/:date" element={<TrainerOnly><ClassDetail /></TrainerOnly>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
