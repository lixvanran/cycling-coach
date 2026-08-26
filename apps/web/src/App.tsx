// 主 App — 路由 + 布局
import { Sidebar } from "./components/Sidebar";
import { TopBar } from "./components/TopBar";
import { Dashboard } from "./pages/Dashboard";
import { CalendarPage } from "./pages/CalendarPage";
import { ActivityList } from "./pages/ActivityList";
import { ComparePage } from "./pages/ComparePage";
import { TrendsPage } from "./pages/TrendsPage";
import { PhasesPage } from "./pages/PhasesPage";
import { FTPTestPage } from "./pages/FTPTestPage";
import { ActivityDetail } from "./pages/ActivityDetail";
import { ImportPage } from "./pages/ImportPage";
import { Profile } from "./pages/Profile";
import { ChatPage } from "./pages/ChatPage";
import { LibraryPage } from "./pages/LibraryPage";
import { BuilderPage } from "./pages/BuilderPage";
import { KnowledgeBasePage } from "./pages/KnowledgeBasePage";
import { useAppStore } from "./store/useAppStore";

export default function App() {
  const view = useAppStore((s) => s.view);

  return (
    <div className="h-full flex bg-bg-base text-text-primary">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-hidden">
          {view === "dashboard" && <Dashboard />}
          {view === "calendar" && <CalendarPage />}
          {view === "library" && <LibraryPage />}
          {view === "builder" && <BuilderPage />}
          {view === "kb" && <KnowledgeBasePage />}
          {view === "kb-search" && <KnowledgeBasePage />}
          {view === "activities" && <ActivityList />}
          {view === "activity-detail" && <ActivityDetail />}
          {view === "compare" && <ComparePage />}
          {view === "trends" && <TrendsPage />}
          {view === "chat" && <ChatPage />}
          {view === "import" && <ImportPage />}
          {view === "profile" && <Profile />}
        </main>
      </div>
    </div>
  );
}
