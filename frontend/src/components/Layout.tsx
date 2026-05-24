import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Calendar, Library, Search, MessageSquare,
  BarChart2, PenSquare, Bell, Settings, Users, LogOut,
} from "lucide-react";
import { getUnreadCount } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Logo } from "./Logo";
import { VerificationBanner } from "./VerificationBanner";
import clsx from "clsx";

const NAV = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/calendar", icon: Calendar, label: "Calendar" },
  { to: "/library", icon: Library, label: "Library" },
  { to: "/research", icon: Search, label: "Research" },
  { to: "/engagement", icon: MessageSquare, label: "Engagement" },
  { to: "/analytics", icon: BarChart2, label: "Analytics" },
  { to: "/compose", icon: PenSquare, label: "Compose" },
] as const;

export default function Layout() {
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useAuth();

  const { data: countData } = useQuery({
    queryKey: ["unread-count"],
    queryFn: getUnreadCount,
    refetchInterval: 30_000,
  });
  const unread = countData?.count ?? 0;

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex h-screen bg-gray-950 font-sans">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 flex flex-col border-r border-gray-800 bg-gray-900">
        <div className="flex items-center gap-2.5 px-5 py-4 border-b border-gray-800">
          <Logo size={28} className="flex-shrink-0 text-gray-400" />
          <span className="text-sm font-semibold text-gray-100">Content Engine</span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                  isActive
                    ? "bg-gray-800 text-gray-100 font-medium"
                    : "text-gray-400 hover:text-gray-100 hover:bg-gray-800/60"
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-3 border-t border-gray-800 space-y-0.5">
          <NavLink
            to="/notifications"
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive ? "bg-gray-800 text-gray-100" : "text-gray-400 hover:text-gray-100 hover:bg-gray-800/60"
              )
            }
          >
            <div className="relative">
              <Bell className="w-4 h-4" />
              {unread > 0 && (
                <span className="absolute -top-1.5 -right-1.5 w-3.5 h-3.5 rounded-full bg-[color:var(--danger)] text-white text-[9px] flex items-center justify-center font-bold">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </div>
            Notifications
          </NavLink>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive ? "bg-gray-800 text-gray-100" : "text-gray-400 hover:text-gray-100 hover:bg-gray-800/60"
              )
            }
          >
            <Settings className="w-4 h-4" />
            Settings
          </NavLink>
          {isAdmin && (
            <NavLink
              to="/admin"
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                  isActive ? "bg-gray-800 text-gray-100" : "text-gray-400 hover:text-gray-100 hover:bg-gray-800/60"
                )
              }
            >
              <Users className="w-4 h-4" />
              Users
            </NavLink>
          )}
        </div>

        <div className="px-3 py-3 border-t border-gray-800">
          <div className="px-3 py-2 text-xs text-gray-500 truncate">
            <div className="truncate text-gray-300">{user?.name}</div>
            <div className="truncate">{user?.email}</div>
            {isAdmin && <span className="mt-1 inline-block text-[color:var(--accent)]">admin</span>}
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-gray-100 hover:bg-gray-800/60 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <VerificationBanner />
        <div className="max-w-6xl mx-auto px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
