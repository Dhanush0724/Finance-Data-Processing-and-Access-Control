"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { isAuthenticated, getUser, clearSession } from "@/lib/auth";
import { User } from "@/types";
import { LayoutDashboard, ArrowLeftRight, Users, LogOut } from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/dashboard",              label: "Overview",     icon: LayoutDashboard, roles: ["viewer","analyst","admin"] },
  { href: "/dashboard/transactions", label: "Transactions", icon: ArrowLeftRight,  roles: ["viewer","analyst","admin"] },
  { href: "/dashboard/users",        label: "Users",        icon: Users,           roles: ["admin"] },
];

const ROLE_BADGE: Record<string, string> = {
  admin:   "bg-purple-100 text-purple-700",
  analyst: "bg-blue-100 text-blue-700",
  viewer:  "bg-slate-100 text-slate-600",
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router   = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.replace("/login"); return; }
    setUser(getUser());
  }, [router]);

  function logout() {
    clearSession();
    router.push("/login");
  }

  if (!user) return null;

  const visibleNav = NAV.filter((n) => n.roles.includes(user.role));

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-100">
          <span className="font-bold text-slate-900 text-lg">FinanceOS</span>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {visibleNav.map(({ href, label, icon: Icon }) => (
            <Link
              key={href} href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                pathname === href
                  ? "bg-green-50 text-green-700"
                  : "text-slate-600 hover:bg-slate-50"
              )}
            >
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>

        <div className="px-4 py-4 border-t border-slate-100">
          <div className="mb-3">
            <p className="text-sm font-medium text-slate-900 truncate">{user.name}</p>
            <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium", ROLE_BADGE[user.role])}>
              {user.role}
            </span>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 text-xs text-slate-500 hover:text-red-600 transition-colors"
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
