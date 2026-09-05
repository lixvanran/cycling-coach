// 共用 AppShell — Sidebar + TopBar + Outlet
// 5 个 layout (TrainingLayout / AILayout / PlanLayout / DataLayout / SettingsLayout)
// 都用这个壳, 保持视觉一致
import { Outlet } from "react-router-dom";
import { Sidebar } from "../Sidebar";
import { TopBar } from "../TopBar";
import { ToastContainer } from "../Toast";

export function AppShell() {
  return (
    <div className="h-full flex bg-bg-base text-text-primary">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <ToastContainer />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
