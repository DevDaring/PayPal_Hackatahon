import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, ArrowRight, Bot, CheckCircle2, ClipboardList, FileSearch, Fingerprint, Hourglass, Play, Plus, RefreshCcw, ShieldCheck, Wallet } from "lucide-react";
import { api, errorText, post } from "../lib/api";
import { money, PAYMENT_STATUS, relative, REQUEST_STATUS } from "../lib/format";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, SectionTitle, Skeleton, Stat } from "../components/ui";

const JOURNEY = [
  ["Describe", "Plain-language request becomes typed, confirmed requirements"],
  ["Extract", "Supplier PDFs parsed; every term linked to its source line"],
  ["Compare", "Deterministic checks: totals, connector, delivery, validity"],
  ["Approve", "Approver signs the exact, hashed purchase snapshot"],
  ["Pay", "PayPal Sandbox order built only from the approved snapshot"],
  ["Prove", "Capture reconciled; evidence package and decision replay"],
];

export default function Overview() {
  const { me } = useSession();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["overview"], queryFn: () => api("/overview"), refetchInterval: 8000 });
  const sample = useMutation({
    mutationFn: () => post("/demo/sample-request"),
    onSuccess: (r: any) => { toast.success("Sample request drafted — review the parsed requirements"); nav(`/requests/${r.id}/requirements`); },
    onError: (e) => toast.error(errorText(e)),
  });
  const m = q.data?.metrics;
  const first = (me?.acting.name ?? "").split(" ")[0];

  return (
    <div>
      <PageHeader eyebrow="Overview" title={<>Good to see you, {first}.</>} subtitle="Buy with evidence: every supplier term traced, every approval bound to the exact purchase, every payment confirmed by PayPal."
        actions={<><Link to="/requests/new"><Button variant="secondary" icon={<Plus className="size-4" aria-hidden />}>New request</Button></Link></>} />

      <Card className="relative mb-6 overflow-hidden border-0 bg-ink p-0 text-white animate-in">
        <div className="pointer-events-none absolute -right-24 -top-24 size-80 rounded-full bg-teal-bright/15 blur-3xl" />
        <div className="grid gap-6 p-6 md:grid-cols-[1.2fr_1fr] md:p-8">
          <div className="relative z-10">
            <Badge tone="info" className="border-white/20! bg-white/10! text-white!">Guided demo · about 2 minutes</Badge>
            <h2 className="mt-3 font-display text-[34px] leading-tight md:text-[40px]">Try the sample purchase</h2>
            <p className="mt-2 max-w-md text-[15px] text-white/70">
              30 USB-C headsets, $600 budget, delivery in 7 days. Three synthetic supplier quotes — the cheapest one hides a wrong connector, another hides $160 of shipping.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link to="/agent"><Button size="lg" className="bg-teal-bright! text-navy-900! hover:bg-white!" icon={<Bot className="size-4" aria-hidden />}>Watch the agent work</Button></Link>
              <Button size="lg" variant="ghost" className="border border-white/20 text-white! hover:bg-white/10!" loading={sample.isPending} icon={<Play className="size-4" aria-hidden />} onClick={() => sample.mutate()}>
                Try sample purchase
              </Button>
              <Link to="/demo-lab"><Button size="lg" variant="ghost" className="text-white! hover:bg-white/10!">Open Demo Lab <ArrowRight className="size-4" aria-hidden /></Button></Link>
            </div>
          </div>
          <ol className="relative z-10 grid grid-cols-2 gap-2 self-center sm:grid-cols-3">
            {JOURNEY.map(([t, d], i) => (
              <li key={t} className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                <div className="flex items-center gap-2 text-[13px] font-semibold"><span className="grid size-5 place-items-center rounded-full bg-teal-bright/20 text-[11px] text-teal-bright">{i + 1}</span>{t}</div>
                <p className="mt-1 text-[11.5px] leading-snug text-white/55">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </Card>

      {q.error ? <ErrorBox error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {m ? <>
            <Stat label="Outstanding requests" value={m.outstanding_requests} icon={<ClipboardList className="size-4" aria-hidden />} hint="Draft, analysing or ready" />
            <Stat label="Awaiting approval" value={m.awaiting_approval} icon={<Hourglass className="size-4" aria-hidden />} tone="teal" hint="Compliant quote found" />
            <Stat label="Confirmed payments" value={m.confirmed_payments} icon={<Wallet className="size-4" aria-hidden />} tone="teal" hint={`${money(m.confirmed_payment_total)} captured · ${m.payments_reconciling} reconciling`} />
            <Stat label="Unresolved issues" value={m.unresolved_issues} icon={<AlertTriangle className="size-4" aria-hidden />} tone={m.unresolved_issues ? "amber" : "navy"} hint="Failed docs, reviews, clarifications" />
          </> : [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[118px]" />)}
        </div>
      )}
      {q.data && <p className="mt-2 text-[11.5px] text-muted">{q.data.derived_from}</p>}

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div>
          <SectionTitle hint="Most recently updated in this workspace" right={<Link to="/requests" className="text-sm font-medium text-teal hover:underline">All requests</Link>}>Recent requests</SectionTitle>
          <Card>
            {!q.data ? <div className="space-y-3 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
              : q.data.recent.length === 0 ? <Empty image title="No purchase requests yet" body="Start with the sample purchase to see the full journey from quote to confirmed sandbox payment." />
                : (
                  <ul className="divide-y divide-line">
                    {q.data.recent.map((r: any) => (
                      <li key={r.id}>
                        <Link to={`/requests/${r.id}`} className="flex items-center gap-4 px-4 py-3.5 hover:bg-sunken/60">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="truncate font-medium text-ink">{r.title}</span>
                              {r.lab_scenario && <Badge tone="info">Demo Lab</Badge>}
                            </div>
                            <div className="mt-0.5 text-[12.5px] text-muted">{r.quantity ? `${r.quantity} units · ` : ""}{r.budget ? `budget ${money(r.budget, r.currency)} · ` : ""}{r.documents} quote{r.documents === 1 ? "" : "s"} · {relative(r.updated_at)}</div>
                          </div>
                          {r.payment_state && <Badge tone={PAYMENT_STATUS[r.payment_state]?.tone}>{PAYMENT_STATUS[r.payment_state]?.label}</Badge>}
                          <Badge tone={REQUEST_STATUS[r.status]?.tone}>{REQUEST_STATUS[r.status]?.label ?? r.status}</Badge>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
          </Card>
        </div>
        <div>
          <SectionTitle hint="What QuoteGuard checks before money moves">Safeguards</SectionTitle>
          <div className="space-y-2.5">
            {[
              [FileSearch, "Evidence or it's unknown", "Missing shipping, tax or delivery evidence is shown as unknown — never assumed to pass."],
              [Fingerprint, "Approval = exact snapshot hash", "Supplier, quote version, amount, merchant and expiry are canonicalised and hashed."],
              [ShieldCheck, "Re-checked before order and capture", "Any change blocks execution and requires a fresh approval."],
              [RefreshCcw, "Lost responses reconcile", "Timeouts become 'reconciling' and are resolved by PayPal lookup — never a second charge."],
              [CheckCircle2, "PDF text is data, not instructions", "Embedded instructions cannot change budgets, permissions or payees."],
            ].map(([Icon, t, d], i) => (
              <Card key={i} className="flex gap-3 p-3.5">
                <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-teal-soft text-teal">{/* @ts-ignore */}<Icon className="size-[18px]" aria-hidden /></span>
                <div><div className="text-[14px] font-semibold text-ink">{t as string}</div><p className="text-[12.5px] leading-snug text-muted">{d as string}</p></div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
