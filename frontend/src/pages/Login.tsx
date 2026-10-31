import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, BadgeCheck, FileSearch, KeyRound, Lock, ShieldCheck, Sparkles, Wallet } from "lucide-react";
import { api, errorText } from "../lib/api";
import { usePublicConfig, useSession } from "../lib/session";
import type { Me } from "../lib/types";
import { Logo } from "../components/Layout";
import { Button, inputCls } from "../components/ui";

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

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden overflow-hidden bg-ink lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="pointer-events-none absolute -right-40 -top-40 size-[520px] rounded-full bg-teal-bright/10 blur-3xl" />
        <Logo light />
        <div className="relative z-10 max-w-[440px] xl:max-w-[520px]">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[12px] text-white/80">
            <Sparkles className="size-3.5 text-teal-bright" aria-hidden /> Built for the PayPal AI Hackathon
          </div>
          <h1 className="font-display text-[56px] leading-[1.02] text-white">
            From supplier PDF to <em className="text-teal-bright">approved</em> PayPal purchase.
          </h1>
          <p className="mt-4 max-w-lg text-[16px] leading-relaxed text-white/70">
            Evidence for every decision. Approval bound to the exact purchase. Checks before money moves.
          </p>
          <ul className="mt-8 grid max-w-[420px] gap-3 text-[14px] text-white/80">
            {[
              [FileSearch, "Every number links to the line on the supplier's PDF it came from"],
              [ShieldCheck, "Approval is hashed to the exact supplier, amount and payee"],
              [Wallet, "Genuine PayPal Sandbox checkout with durable reconciliation"],
            ].map(([Icon, t], i) => (
              <li key={i} className="flex items-center gap-3">
                <span className="grid size-8 place-items-center rounded-lg bg-white/10"><Icon className="size-4 text-teal-bright" aria-hidden /></span>
                {t as string}
              </li>
            ))}
          </ul>
        </div>
        <img src="/illustrations/login-hero.webp" alt="" className="pointer-events-none absolute bottom-10 right-[-36px] hidden w-[300px] rotate-[-4deg] rounded-[28px] shadow-2xl xl:block 2xl:w-[360px]" />
        <p className="relative z-10 text-[12px] text-white/40">Synthetic demo data · PayPal Sandbox · no real money moves</p>
      </section>

      <section className="flex items-center justify-center px-5 py-10">
        <div className="w-full max-w-[420px] animate-in">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h2 className="font-display text-[40px] leading-tight text-ink">Sign in</h2>
          <p className="mt-1 text-[15px] text-muted">Each demo sign-in opens a fresh, isolated workspace.</p>

          {jury && (
            <div className="mt-6 rounded-2xl border border-teal/25 bg-teal-soft/70 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-1.5 text-[13px] font-semibold text-teal-strong"><BadgeCheck className="size-4" aria-hidden /> Jury access</div>
                  <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px]">
                    <dt className="text-muted">User</dt><dd className="font-mono font-medium text-ink">{jury.username}</dd>
                    <dt className="text-muted">Password</dt><dd className="font-mono font-medium text-ink">{jury.password}</dd>
                  </dl>
                </div>
                <KeyRound className="size-5 text-teal" aria-hidden />
              </div>
              <Button className="mt-3 w-full" size="lg" loading={busy} icon={<ArrowRight className="size-4" aria-hidden />}
                onClick={() => { setUsername(jury.username); setPassword(jury.password); signIn(jury.username, jury.password); }}>
                Fill to Sign in
              </Button>
            </div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            <label className="block">
              <span className="mb-1 block text-[13px] font-medium text-ink-2">Username or email</span>
              <input className={inputCls + " h-11"} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
            </label>
            <label className="block">
              <span className="mb-1 block text-[13px] font-medium text-ink-2">Password</span>
              <input className={inputCls + " h-11"} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            {error && <p role="alert" className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{error}</p>}
            <Button type="submit" variant="dark" size="lg" className="w-full" loading={busy} disabled={!username || !password} icon={<Lock className="size-4" aria-hidden />}>
              Sign in
            </Button>
          </form>
          <p className="mt-6 text-center text-[12px] text-muted">Passwords are hashed with scrypt · sessions use HttpOnly cookies with CSRF protection.</p>
        </div>
      </section>
    </div>
  );
}
