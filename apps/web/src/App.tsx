// V0.8.0 主 App — react-router-dom 路由分组 + 路由级 code splitting
// 5 个 layout 按功能分组 (training / ai / plan / data / settings)
// 每个 page 走 lazy(), 配合 Suspense + LoadingSkeleton
import { lazy, Suspense } from "react";
import { BrowserRouter, HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { useLegacyRedirect } from "./hooks/useLegacyRedirect";
import { LoadingSkeleton, ErrorBoundary } from "./components/common";

// 5 个 layout — 共用 AppShell
import { TrainingLayout } from "./components/layout/TrainingLayout";
import { AILayout } from "./components/layout/AILayout";
import { PlanLayout } from "./components/layout/PlanLayout";
import { DataLayout } from "./components/layout/DataLayout";
import { SettingsLayout } from "./components/layout/SettingsLayout";

// 路由级 lazy — 每个 page 一个 chunk
const Dashboard = lazy(() => import("./pages/Dashboard").then(m => ({ default: m.Dashboard })));
const ActivityList = lazy(() => import("./pages/ActivityList").then(m => ({ default: m.ActivityList })));
const ActivityDetail = lazy(() => import("./pages/ActivityDetail").then(m => ({ default: m.ActivityDetail })));
const TrendsPage = lazy(() => import("./pages/TrendsPage").then(m => ({ default: m.TrendsPage })));
const DiaryPage = lazy(() => import("./pages/DiaryPage").then(m => ({ default: m.DiaryPage })));
const ChatPage = lazy(() => import("./pages/ChatPage").then(m => ({ default: m.ChatPage })));
const RaceTacticsPage = lazy(() => import("./pages/RaceTacticsPage").then(m => ({ default: m.RaceTacticsPage })));
const InsightsPage = lazy(() => import("./pages/InsightsPage").then(m => ({ default: m.InsightsPage })));
const CalendarPage = lazy(() => import("./pages/CalendarPage").then(m => ({ default: m.CalendarPage })));
const LibraryPage = lazy(() => import("./pages/LibraryPage").then(m => ({ default: m.LibraryPage })));
const BuilderPage = lazy(() => import("./pages/BuilderPage").then(m => ({ default: m.BuilderPage })));
const PhasesPage = lazy(() => import("./pages/PhasesPage").then(m => ({ default: m.PhasesPage })));
const ImportPage = lazy(() => import("./pages/ImportPage").then(m => ({ default: m.ImportPage })));
const KnowledgeBasePage = lazy(() => import("./pages/KnowledgeBasePage").then(m => ({ default: m.KnowledgeBasePage })));
const FTPTestPage = lazy(() => import("./pages/FTPTestPage").then(m => ({ default: m.FTPTestPage })));
const Profile = lazy(() => import("./pages/Profile").then(m => ({ default: m.Profile })));
const ComparePage = lazy(() => import("./pages/ComparePage").then(m => ({ default: m.ComparePage })));

// 桌面模式 (file://) 用 HashRouter, web 模式 (http://) 用 BrowserRouter
function useRouterType() {
  if (typeof window === "undefined") return BrowserRouter;
  if (window.location.protocol === "file:") return HashRouter;
  return BrowserRouter;
}

function LegacyRedirectGuard() {
  useLegacyRedirect();
  return null;
}

function AppRoutes() {
  return (
    <>
      <LegacyRedirectGuard />
      <Suspense fallback={<LoadingSkeleton variant="detail" />}>
        <Routes>
          {/* / 默认跳到 training dashboard */}
          <Route path="/" element={<Navigate to="/training" replace />} />

          {/* === Training 组 === */}
          <Route path="/training" element={<TrainingLayout />}>
            <Route
              index
              element={
                <ErrorBoundary>
                  <Dashboard />
                </ErrorBoundary>
              }
            />
            <Route
              path="activities"
              element={
                <ErrorBoundary>
                  <ActivityList />
                </ErrorBoundary>
              }
            />
            <Route
              path="activities/:id"
              element={
                <ErrorBoundary>
                  <ActivityDetail />
                </ErrorBoundary>
              }
            />
            <Route
              path="trends"
              element={
                <ErrorBoundary>
                  <TrendsPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="diary"
              element={
                <ErrorBoundary>
                  <DiaryPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="compare"
              element={
                <ErrorBoundary>
                  <ComparePage />
                </ErrorBoundary>
              }
            />
          </Route>

          {/* === AI 组 === */}
          <Route path="/ai" element={<AILayout />}>
            <Route
              index
              element={<Navigate to="/ai/chat" replace />}
            />
            <Route
              path="chat"
              element={
                <ErrorBoundary>
                  <ChatPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="race-tactics"
              element={
                <ErrorBoundary>
                  <RaceTacticsPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="hrv"
              element={
                <ErrorBoundary>
                  <InsightsPage />
                </ErrorBoundary>
              }
            />
          </Route>

          {/* === Plan 组 === */}
          <Route path="/plan" element={<PlanLayout />}>
            <Route
              index
              element={
                <ErrorBoundary>
                  <BuilderPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="calendar"
              element={
                <ErrorBoundary>
                  <CalendarPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="workouts"
              element={
                <ErrorBoundary>
                  <LibraryPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="phases"
              element={
                <ErrorBoundary>
                  <PhasesPage />
                </ErrorBoundary>
              }
            />
          </Route>

          {/* === Data 组 === */}
          <Route path="/data" element={<DataLayout />}>
            <Route
              index
              element={<Navigate to="/data/import" replace />}
            />
            <Route
              path="import"
              element={
                <ErrorBoundary>
                  <ImportPage />
                </ErrorBoundary>
              }
            />
            <Route
              path="knowledge"
              element={
                <ErrorBoundary>
                  <KnowledgeBasePage />
                </ErrorBoundary>
              }
            />
            <Route
              path="ftp-test"
              element={
                <ErrorBoundary>
                  <FTPTestPage />
                </ErrorBoundary>
              }
            />
          </Route>

          {/* === Settings 组 === */}
          <Route path="/settings" element={<SettingsLayout />}>
            <Route
              index
              element={
                <ErrorBoundary>
                  <Profile />
                </ErrorBoundary>
              }
            />
          </Route>

          {/* 兜底: 未知路径跳回 /training */}
          <Route path="*" element={<Navigate to="/training" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}

export default function App() {
  const Router = useRouterType();
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}
