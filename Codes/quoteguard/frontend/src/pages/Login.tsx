import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BadgeCheck, Bot, Check, CircleCheck, FileSearch, FlaskConical, Lock, ShieldCheck, Sparkles, Wallet, X } from "lucide-react";
import { api, errorText } from "../lib/api";
import { usePublicConfig, useSession } from "../lib/session";
import type { Me } from "../lib/types";
import { Logo } from "../components/Layout";
import { Button, CopyText, cx, inputCls } from "../components/ui";

// The preview replays the bundled sample request (30 USB-C headsets, budget $600 incl. shipping) with its real outcomes.
const QUOTES = [
  { supplier: "Harbor Devices", total: "$470.00", ok: false, note: "USB-A connector — USB-C required", tag: "Cheapest" },
  { supplier: "Northstar Office", total: "$640.00", ok: false, note: "$40.00 over the $600 budget", cite: "Shipping (expedited freight, required for 5-day delivery): $160.00" },
  { supplier: "ClearWave Supplies", total: "$570.00", ok: true, note: "Meets every confirmed requirement", tag: "Recommended" },
];
const STEPS = [
  { icon: FileSearch, label: "Evidence cited", sub: "every value → its PDF line" },
  { icon: ShieldCheck, label: "Policy + forensics", sub: "no edited bills, no staged rivals" },
  { icon: BadgeCheck, label: "Approval signed", sub: "SHA-256 of the exact purchase" },
  { icon: Wallet, label: "PayPal captured", sub: "$570.00 · Sandbox" },
];

function useTicker(steps: number) {
  const [tick, setTick] = useState(steps);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    setTick(0);
    const t = setInterval(() => setTick((n) => (n + 1) % (steps + 3)), 1300);
    return () => clearInterval(t);
  }, [steps]);
  return Math.min(tick, steps);
}

function ProductPreview() {
  const stage = useTicker(STEPS.length);
  return (
    <div className="qg-float relative rounded-2xl border border-white/12 bg-white/[0.06] p-1.5 shadow-[0_30px_80px_-30px_rgb(0_0_0/0.7)] backdrop-blur-md">
      <div className="rounded-[13px] bg-[#0b1d36]/80">
        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
          <span className="flex gap-1.5" aria-hidden><i className="size-2.5 rounded-full bg-white/20" /><i className="size-2.5 rounded-full bg-white/20" /><i className="size-2.5 rounded-full bg-white/20" /></span>
          <span className="ml-1 truncate text-[12px] text-white/60">Sample request · <span className="text-white/85">30 USB-C headsets</span> · budget $600 incl. shipping</span>
        </div>

        <ul className="relative space-y-1.5 overflow-hidden p-3">
          <span className="qg-scan pointer-events-none absolute inset-x-0 h-14 bg-gradient-to-b from-transparent via-teal-bright/10 to-transparent" aria-hidden />
          {QUOTES.map((q, i) => (
            <li key={q.supplier} style={{ animationDelay: `${150 + i * 160}ms` }}
              className={cx("animate-in rounded-xl border px-3 py-2.5", q.ok ? "border-teal-bright/50 bg-teal-bright/[0.12]" : "border-white/8 bg-white/[0.03]")}>
              <div className="flex items-center gap-3">
                <span className={cx("grid size-6 shrink-0 place-items-center rounded-full", q.ok ? "bg-teal-bright text-ink" : "bg-[#f87171]/20 text-[#fca5a5]")}>
                  {q.ok ? <Check className="size-3.5" strokeWidth={3} aria-hidden /> : <X className="size-3.5" strokeWidth={3} aria-hidden />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-[14px] font-medium text-white">{q.supplier}</span>
                    {q.tag && <span className={cx("rounded-full px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider", q.ok ? "bg-teal-bright text-ink" : "bg-white/10 text-white/70")}>{q.tag}</span>}
                  </div>
                  <div className={cx("truncate text-[12px]", q.ok ? "text-teal-bright" : "text-[#fca5a5]/90")}>{q.note}</div>
                </div>
                <span className={cx("tnum font-mono text-[14px]", q.ok ? "text-white" : "text-white/55 line-through decoration-white/30")}>{q.total}</span>
              </div>
              {q.cite && (
                <div className="mt-2 ml-9 flex items-center gap-2 rounded-md bg-[#fbf8f3] px-2 py-1 text-[11px] text-ink-2">
                  <FileSearch className="size-3 shrink-0 text-amber" aria-hidden />
                  <span className="truncate"><mark className="rounded-sm bg-[#f59e0b]/30 px-0.5 text-ink outline outline-1 outline-[#d97706]/70">{q.cite}</mark></span>
                  <span className="ml-auto shrink-0 text-[10px] text-muted">cited line</span>
                </div>
              )}
            </li>
          ))}
        </ul>

        <ol className="grid grid-cols-4 gap-1 border-t border-white/10 p-3" aria-label="What happens to the recommended quote">
          {STEPS.map((s, i) => {
            const on = i < stage, now = i === stage - 1;
            return (
              <li key={s.label} className="relative">
                {i > 0 && <span className={cx("absolute right-1/2 top-4 h-px w-full -translate-y-1/2 transition-colors duration-500", on ? "bg-teal-bright" : "bg-white/12")} aria-hidden />}
                <div className="relative flex flex-col items-center text-center">
                  <span className={cx("grid size-8 place-items-center rounded-full border transition-all duration-500",
                    on ? "border-teal-bright bg-teal-bright text-ink" : "border-white/15 bg-[#0b1d36] text-white/45", now && "pulse-ring")}>
                    <s.icon className="size-4" aria-hidden />
                  </span>
                  <span className={cx("mt-1.5 text-[11.5px] font-medium leading-tight transition-colors duration-500", on ? "text-white" : "text-white/45")}>{s.label}</span>
                  <span className="mt-0.5 hidden text-[10.5px] leading-tight text-white/45 xl:block">{s.sub}</span>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

const PROOF = [
  { value: "40/44", label: "document-fraud attacks caught, 0 false alarms on 38 honest cases" },
  { value: "3", label: "human consents the agent can never give itself" },
  { value: "$0", label: "real money — PayPal Sandbox, synthetic quotes" },
];

const TRY = [
  { icon: Bot, text: "Agent Mode — watch it read, cite and decide" },
  { icon: FlaskConical, text: "Demo Lab — try to trick the payment path" },
  { icon: Wallet, text: "Pay the approved quote in PayPal Sandbox" },
];

export function LoginPage() {
  const { me, setMe } = useSession();
  const cfg = usePublicConfig();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to={loc.state?.from ?? "/"} replace />;

  async function signIn(u: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const m = await api<Me>("/auth/login", { body: { username: u, password: p } });
      setMe(m);
      nav(loc.state?.from ?? "/", { replace: true });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  const submit = (e: FormEvent) => { e.preventDefault(); signIn(username, password); };
  const jury = cfg.data?.jury_login;
  const ready = Boolean(username && password);

  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-[1.12fr_1fr]">
      <section className="login-hero relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:gap-6 lg:px-12 lg:py-8 xl:px-16">
        <div className="relative z-10 flex items-center justify-between">
          <Logo light />
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[12px] text-white/80">
            <Sparkles className="size-3.5 text-teal-bright" aria-hidden /> Built for the PayPal AI Hackathon
          </span>
        </div>

        <div className="relative z-10 my-auto grid max-w-[620px] gap-6 2xl:max-w-[720px]">
          <div className="animate-in">
            <h1 className="font-display text-[46px] leading-[1.02] xl:text-[56px] 2xl:text-[64px]">
              From supplier PDF to an <em className="bg-gradient-to-r from-teal-bright to-[#5eead4] bg-clip-text pr-1 text-transparent">approved</em> PayPal purchase.
            </h1>
            <p className="mt-3 max-w-[540px] text-[16px] leading-relaxed text-white/70">
              An AI agent that reads supplier quotes, cites the line behind every number, catches edited bills and staged competition, and only pays what a person approved.
            </p>
          </div>
          <ProductPreview />
        </div>

        <div className="relative z-10 grid grid-cols-3 gap-6 border-t border-white/10 pt-5">
          {PROOF.map((p) => (
            <div key={p.value}>
              <div className="font-display text-[30px] leading-none text-white">{p.value}</div>
              <div className="mt-1.5 text-[12px] leading-snug text-white/55">{p.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="login-side relative flex items-center justify-center px-5 py-10 sm:px-8">
        <div className="relative w-full max-w-[440px] animate-in">
          <div className="mb-6 lg:hidden">
            <Logo />
            <p className="mt-3 text-[14px] text-muted">From supplier PDF to an <em className="font-medium not-italic text-teal">approved</em> PayPal purchase — evidence for every decision.</p>
          </div>
          <h2 className="font-display text-[42px] leading-tight text-ink">Welcome, judges</h2>
          <p className="mt-1 text-[15px] text-muted">One click opens your own fresh, isolated workspace with sample quotes ready.</p>

          {jury && (
            <div className="jury-card mt-6 rounded-2xl p-[1.5px] shadow-[var(--shadow-pop)]">
              <div className="rounded-[15px] bg-gradient-to-br from-ink via-[#0f2f4d] to-teal-strong p-5 text-white">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-teal-bright"><BadgeCheck className="size-4" aria-hidden /> Jury access</span>
                  <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/70">no setup needed</span>
                </div>
                <dl className="mt-3 grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-[14px]">
                  <dt className="text-white/60">User</dt>
                  <dd><CopyText value={jury.username} className="bg-white/10! text-[13px]! text-white! hover:bg-white/20!" /></dd>
                  <dt className="text-white/60">Password</dt>
                  <dd><CopyText value={jury.password} className="bg-white/10! text-[13px]! text-white! hover:bg-white/20!" /></dd>
                </dl>
                <Button className="mt-4 h-13! w-full bg-teal-bright! text-[16px]! font-semibold text-ink! shadow-lg shadow-teal-bright/30 hover:bg-[#2dd4bf]!" size="lg" loading={busy}
                  icon={<ArrowRight className="size-[18px]" aria-hidden />}
                  onClick={() => { setUsername(jury.username); setPassword(jury.password); signIn(jury.username, jury.password); }}>
                  Fill to Sign in
                </Button>
              </div>
            </div>
          )}

          <div className="mt-5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Try in three minutes</div>
          <ol className="mt-2 grid gap-2">
            {TRY.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-[14px] text-ink-2">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-teal-soft text-teal-strong"><Icon className="size-3.5" aria-hidden /></span>
                {text}
              </li>
            ))}
          </ol>

          <div className="my-6 flex items-center gap-3 text-[12px] text-muted"><span className="h-px flex-1 bg-line" />or sign in with an account<span className="h-px flex-1 bg-line" /></div>

          <form onSubmit={submit} className="space-y-3" noValidate>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-[13px] font-medium text-ink-2">Username or email</span>
                <input className={inputCls + " h-11"} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </label>
              <label className="block">
                <span className="mb-1 block text-[13px] font-medium text-ink-2">Password</span>
                <input className={inputCls + " h-11"} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </label>
            </div>
            {error && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
            <Button type="submit" variant={ready ? "dark" : "secondary"} size="lg" className="w-full" loading={busy} disabled={!ready} icon={<Lock className="size-4" aria-hidden />}>
              Sign in
            </Button>
          </form>
          <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-[12px] text-muted">
            <CircleCheck className="size-3.5 text-teal" aria-hidden /> scrypt-hashed passwords · HttpOnly sessions · CSRF protection
          </p>
        </div>
      </section>
    </div>
  );
}
