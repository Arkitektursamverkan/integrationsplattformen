import { useState, type ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { clearTokens } from "@/api/auth";
import {
  AppBar,
  Box,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import {
  Menu as MenuIcon,
  Logout as LogoutIcon,
  Dashboard as DashboardIcon,
  Cable as CableIcon,
  AccountTree as AccountTreeIcon,
  History as HistoryIcon,
  Storage as StorageIcon,
  Settings as SettingsIcon,
  Schedule as ScheduleIcon,
  UploadFile as UploadFileIcon,
} from "@mui/icons-material";

const DRAWER_WIDTH = 240;

const NAV_ITEMS = [
  { label: "Dashboard", path: "/", icon: <DashboardIcon /> },
  { label: "Connections", path: "/connections", icon: <CableIcon /> },
  { label: "Flows", path: "/flows", icon: <AccountTreeIcon /> },
  { label: "Schedules", path: "/schedules", icon: <ScheduleIcon /> },
  { label: "Executions", path: "/executions", icon: <HistoryIcon /> },
  { label: "Data Explorer", path: "/data", icon: <StorageIcon /> },
  { label: "Settings", path: "/settings", icon: <SettingsIcon /> },
];

export default function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const drawer = (
    <Box>
      <Toolbar>
        <Typography variant="h6" noWrap sx={{ fontWeight: 700 }}>
          IntegrationHub
        </Typography>
      </Toolbar>
      <List>
        {NAV_ITEMS.map((item) => (
          <ListItemButton
            key={item.path}
            selected={location.pathname === item.path}
            onClick={() => {
              navigate(item.path);
              setMobileOpen(false);
            }}
          >
            <ListItemIcon>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={() => setMobileOpen(!mobileOpen)}
            sx={{ mr: 2, display: { md: "none" } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" noWrap sx={{ flexGrow: 1 }}>
            Integration Platform
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography variant="body2" sx={{ opacity: 0.8 }}>
              {localStorage.getItem("username") || ""}
            </Typography>
            <IconButton color="inherit" size="small" title="Sign out" onClick={() => {
              clearTokens();
              navigate("/login");
            }}>
              <LogoutIcon fontSize="small" />
            </IconButton>
          </Box>
        </Toolbar>
      </AppBar>

      {/* Mobile drawer */}
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        sx={{ display: { xs: "block", md: "none" }, "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
      >
        {drawer}
      </Drawer>

      {/* Desktop drawer */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: "none", md: "block" },
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
        open
      >
        {drawer}
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3, mt: 8, ml: { md: `${DRAWER_WIDTH}px` }, height: "calc(100vh - 64px)", overflow: "auto", display: "flex", flexDirection: "column" }}>
        {children}
      </Box>
    </Box>
  );
}
