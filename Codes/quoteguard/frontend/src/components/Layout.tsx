import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  BarChart3, ChevronDown, ClipboardList, CreditCard, FileSearch, FlaskConical, LayoutDashboard, LogOut, Menu, Plus, Settings, ShieldCheck, UserRoundCog, X,
} from "lucide-react";
import { api, errorText, post } from "../lib/api";
import { useSession } from "../lib/session";
import type { Me } from "../lib/types";
import { Badge, cx } from "./ui";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/requests", label: "Purchase Requests", icon: ClipboardList },
  { to: "/evidence", label: "Evidence", icon: FileSearch },
  { to: "/payments", label: "Payments", icon: CreditCard },
  { to: "/demo-lab", label: "Demo Lab", icon: FlaskConical },
  { to: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Logo({ light }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 64 64" className="size-8" aria-hidden>
        <rect width="64" height="64" rx="14" fill={light ? "#ffffff" : "#0F2541"} />
        <path d="M32 12 48 18v12c0 11-7 19-16 22-9-3-16-11-16-22V18z" fill="#14B8A6" />
        <path d="m24 32 6 6 11-12" fill="none" stroke={light ? "#ffffff" : "#0F2541"} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className={cx("text-[17px] font-semibold tracking-tight", light ? "text-white" : "text-ink")}>QuoteGuard</span>
    </div>
  );
}

function PersonaSwitch({ me }: { me: Me }) {
  const { setMe } = useSession();
  const [busy, setBusy] = useState(false);
  if (!me.workspace?.is_demo || me.personas.length < 2) return null;
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/60">
        <UserRoundCog className="size-3.5" aria-hidden /> Demo role switch
      </div>
      <div className="grid grid-cols-2 gap-1" role="radiogroup" aria-label="Act as">
        {me.personas.map((p) => (
          <button key={p.user_id} role="radio" aria-checked={p.active} disabled={busy || p.active}
            onClick={async () => {
              setBusy(true);
              try {
                const m = await api<Me>("/auth/switch-persona", { body: { user_id: p.user_id } });
                setMe(m);
                toast.success(`Now acting as ${p.name.split(" · ")[0]} (${p.roles.join(", ")})`);
              } catch (e) { toast.error(errorText(e)); } finally { setBusy(false); }
            }}
            className={cx("rounded-lg px-2 py-1.5 text-left text-[12px] leading-tight transition", p.active ? "bg-teal-bright text-navy-900 font-semibold" : "text-white/80 hover:bg-white/10")}>
            <div className="truncate">{p.name.split(" · ")[0]}</div>
            <div className={cx("text-[10.5px]", p.active ? "text-navy-900/70" : "text-white/50")}>{p.roles.includes("approver") ? "Approver" : "Requester · Admin"}</div>
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-[10.5px] leading-snug text-white/45">Labelled demo personas. Self-approval stays disabled.</p>
    </div>
  );
}

function Sidebar({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const { setMe } = useSession();
  const nav = useNavigate();
  const [wsOpen, setWsOpen] = useState(false);
  return (
    <div className="flex h-full flex-col gap-4 bg-ink px-3 py-4 text-white">
      <div className="px-2"><Logo light /></div>
      <div className="relative px-1">
        <button onClick={() => setWsOpen((v) => !v)} aria-expanded={wsOpen} className="flex w-full items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-left hover:bg-white/10">
          <div className="min-w-0">
            <div className="text-[10.5px] uppercase tracking-wider text-white/50">Workspace</div>
            <div className="truncate text-[13px] font-medium">{me.workspace?.name}</div>
          </div>
          <ChevronDown className="size-4 shrink-0 text-white/60" aria-hidden />
        </button>
        {wsOpen && (
          <div className="absolute inset-x-1 top-full z-30 mt-1 rounded-xl border border-white/10 bg-navy-900 p-1 shadow-xl">
            {me.workspaces.map((w) => (
              <button key={w.id} className={cx("block w-full truncate rounded-lg px-3 py-2 text-left text-[13px] hover:bg-white/10", w.id === me.workspace?.id && "text-teal-bright")}
                onClick={async () => { setWsOpen(false); try { setMe(await api<Me>("/auth/workspace", { body: { workspace_id: w.id } })); nav("/"); } catch (e) { toast.error(errorText(e)); } }}>
                {w.name}
              </button>
            ))}
            {me.principal.is_demo_account && (
              <button className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] text-teal-bright hover:bg-white/10"
                onClick={async () => { setWsOpen(false); try { setMe(await post<Me>("/auth/new-demo-workspace")); nav("/"); toast.success("Fresh isolated demo workspace ready"); } catch (e) { toast.error(errorText(e)); } }}>
                <Plus className="size-3.5" aria-hidden /> New isolated demo workspace
              </button>
            )}
          </div>
        )}
      </div>
      <nav aria-label="Primary" className="flex flex-col gap-0.5">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} onClick={onNavigate}
            className={({ isActive }) => cx("flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition", isActive ? "bg-white text-ink font-medium shadow" : "text-white/75 hover:bg-white/10 hover:text-white")}>
            <n.icon className="size-[18px]" aria-hidden />
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3">
        <PersonaSwitch me={me} />
        <div className="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
          <div className="grid size-8 shrink-0 place-items-center rounded-full bg-teal-bright/20 text-[13px] font-semibold text-teal-bright">{me.acting.name.slice(0, 1)}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium">{me.acting.name.split(" · ")[0]}</div>
            <div className="truncate text-[11px] text-white/55">{me.roles.join(" · ")}</div>
          </div>
          <button aria-label="Sign out" className="rounded-lg p-1.5 text-white/60 hover:bg-white/10 hover:text-white"
            onClick={async () => { await post("/auth/logout").catch(() => {}); setMe(null); nav("/login"); }}>
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export function Layout() {
  const { me } = useSession();
  const [open, setOpen] = useState(false);
  if (!me) return null;
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2">Skip to content</a>
      <aside className="sticky top-0 hidden h-screen lg:block"><Sidebar me={me} /></aside>
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-canvas/90 px-4 py-3 backdrop-blur lg:hidden">
        <Logo />
        <button onClick={() => setOpen(true)} aria-label="Open navigation" className="rounded-lg p-2 hover:bg-sunken"><Menu className="size-5" /></button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[272px] slide-in">
            <button onClick={() => setOpen(false)} aria-label="Close navigation" className="absolute right-2 top-3 z-10 rounded-lg p-2 text-white/70"><X className="size-5" /></button>
            <Sidebar me={me} onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
      <main id="main" className="min-w-0">
        {me.workspace?.is_demo && <DemoStrip />}
        <div className="mx-auto max-w-[1280px] px-4 py-6 md:px-8 md:py-8"><Outlet /></div>
      </main>
    </div>
  );
}

function DemoStrip() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-sunken px-4 py-2 text-[12.5px] text-ink-2 md:px-8">
      <Badge tone="info" icon={<ShieldCheck className="size-3" aria-hidden />}>Isolated demo workspace</Badge>
      <span>Synthetic supplier documents · PayPal <b>Sandbox</b> only — no real money moves.</span>
    </div>
  );
}

export function Protected({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
