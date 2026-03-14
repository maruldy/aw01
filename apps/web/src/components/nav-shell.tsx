import { Link, NavLink } from "react-router-dom";
import { Activity, BookOpen, Radio, Settings2, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

const navItems = [
  { to: "/", label: "Inbox", icon: Sparkles },
  { to: "/runs", label: "Runs", icon: Radio },
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/settings", label: "Settings", icon: Settings2 }
];

export function NavShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_top_left,rgba(196,91,50,0.14),transparent_32%),radial-gradient(circle_at_top_right,rgba(15,92,99,0.12),transparent_34%)]" />
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-4 py-5 lg:px-6">
        <aside className="sticky top-5 hidden h-[calc(100vh-2.5rem)] w-72 shrink-0 flex-col rounded-[28px] border border-black/5 bg-white/70 p-5 shadow-panel backdrop-blur xl:flex">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ink text-canvas">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="font-display text-lg font-semibold">Work Harness</p>
              <p className="text-sm text-ink/60">AI-driven enterprise inbox</p>
            </div>
          </Link>

          <nav className="mt-8 space-y-2">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-2xl px-4 py-3 transition ${
                    isActive ? "bg-ink text-canvas" : "bg-transparent text-ink/70 hover:bg-sand/50 hover:text-ink"
                  }`
                }
              >
                <Icon className="h-4 w-4" />
                <span className="font-medium">{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto rounded-[24px] bg-ink p-5 text-canvas">
            <p className="font-display text-lg">Push-first operations</p>
            <p className="mt-2 text-sm text-canvas/70">
              Let agents frame the next move. Keep human intervention for approval, rejection, and advice.
            </p>
          </div>
        </aside>

        <main className="flex-1 animate-fade-up">{children}</main>
      </div>
    </div>
  );
}
