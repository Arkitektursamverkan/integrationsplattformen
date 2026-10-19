import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import AppShell from "@/components/layout/AppShell";
import Dashboard from "@/pages/Dashboard";
import Connections from "@/pages/Connections";
import Flows from "@/pages/Flows";
import FlowDetail from "@/pages/FlowDetail";
import ExecutionLog from "@/pages/ExecutionLog";
import DataExplorer from "@/pages/DataExplorer";
import Schedules from "@/pages/Schedules";
import Settings from "@/pages/Settings";
import Login from "@/pages/Login";
import Setup from "@/pages/Setup";
import { isLoggedIn } from "@/api/auth";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isLoggedIn()) {
    return <Navigate to="/login" replace />;
  }
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/setup" element={<Setup />} />
      <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/connections" element={<ProtectedRoute><Connections /></ProtectedRoute>} />
      <Route path="/flows" element={<ProtectedRoute><Flows /></ProtectedRoute>} />
      <Route path="/flows/:id" element={<ProtectedRoute><FlowDetail /></ProtectedRoute>} />
      <Route path="/schedules" element={<ProtectedRoute><Schedules /></ProtectedRoute>} />
      <Route path="/executions" element={<ProtectedRoute><ExecutionLog /></ProtectedRoute>} />
      <Route path="/data" element={<ProtectedRoute><DataExplorer /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
