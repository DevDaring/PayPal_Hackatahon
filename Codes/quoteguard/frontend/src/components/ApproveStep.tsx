import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, BadgeCheck, Ban, Clock, Fingerprint, Lock, ShieldCheck, UserRoundCog } from "lucide-react";
import { api, errorText } from "../lib/api";
import { dateTime, FIELD_LABEL, money } from "../lib/format";
import { useSession } from "../lib/session";
import type { Comparison, Me, RequestDetail } from "../lib/types";
import { openFieldTarget } from "./EvidenceStep";
import type { EvidenceTarget } from "./EvidenceViewer";
import { Badge, Button, Callout, Card, CheckBadge, CopyText, Dialog, Empty, ErrorBox, Field, inputCls, SectionTitle, Skeleton } from "./ui";

export function Countdown({ to }: { to: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const ms = new Date(to).getTime() - now;
  if (ms <= 0) return <span className="text-danger">expired</span>;
  const m = Math.floor(ms / 60000), s = Math.floor((ms % 60000) / 1000);
  return <span className="tnum">{m}:{s.toString().padStart(2, "0")}</span>;
}

export function ApproveStep({ req, cmp, onOpen }: { req: RequestDetail; cmp?: Comparison; onOpen: (t: EvidenceTarget) => void }) {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { me, setMe } = useSession();
  const live = req.approvals.find((a) => a.status === "active" || a.status === "consumed_for_execution");
  const quoteId = sp.get("quote") ?? live?.snapshot?.quote?.id ?? cmp?.summary?.best_compliant_quote_id;
  const review = useQuery({ queryKey: ["review", req.id, quoteId, me?.acting.id, req.version], queryFn: () => api(`/requests/${req.id}/approval-review?quote_id=${quoteId}`), enabled: !!quoteId && !live });
  const [note, setNote] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const approve = useMutation({
    mutationFn: () => api(`/requests/${req.id}/approvals`, { body: { quote_id: quoteId, terms_hash: review.data.terms_hash, note: note || null } }),
    onSuccess: () => { toast.success("Approved — bound to the exact purchase snapshot"); qc.invalidateQueries({ queryKey: ["request", req.id] }); },
    onError: (e) => { toast.error(errorText(e)); review.refetch(); },
  });
  const reject = useMutation({
    mutationFn: () => api(`/requests/${req.id}/reject`, { body: { quote_id: quoteId, note: rejectNote } }),
    onSuccess: () => { toast.success("Rejection recorded"); setRejectOpen(false); qc.invalidateQueries({ queryKey: ["request", req.id] }); },
    onError: (e) => toast.error(errorText(e)),
  });
  const revoke = useMutation({
    mutationFn: () => api(`/approvals/${live!.id}/revoke`, { body: { reason: "Revoked by approver before payment" } }),
    onSuccess: () => { toast.success("Approval revoked"); qc.invalidateQueries({ queryKey: ["request", req.id] }); },
    onError: (e) => toast.error(errorText(e)),
  });
  const switchTo = async (role: "approver" | "requester") => {
    const p = me?.personas.find((x) => (role === "approver" ? x.roles.includes("approver") : !x.is_persona));
    if (!p) return;
    try { setMe(await api<Me>("/auth/switch-persona", { body: { user_id: p.user_id } })); toast.success(`Now acting as ${p.name.split(" · ")[0]}`); } catch (e) { toast.error(errorText(e)); }
  };

  if (live) {
    const snap = live.snapshot;
    return (
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card className="p-6">
          <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-teal"><BadgeCheck className="size-4" aria-hidden />Organisation approval {live.status === "active" ? "active" : "in use for payment"}</div>
          <h3 className="mt-2 font-display text-[34px] leading-tight text-ink">{snap.supplier.name} · {money(snap.amounts.total, snap.currency)}</h3>
          <p className="mt-1 text-sm text-muted">Pay to merchant <b className="text-ink">{snap.merchant.merchant_id}</b> ({snap.merchant.environment} · {snap.merchant.adapter})</p>
          <div className="mt-4 grid gap-2 text-[13px] sm:grid-cols-2">
            <div className="rounded-xl bg-sunken p-3"><div className="text-muted">Snapshot hash</div><CopyText value={live.snapshot_hash} /></div>
            <div className="rounded-xl bg-sunken p-3"><div className="text-muted">Expires in</div><div className="flex items-center gap-1.5 font-semibold text-ink"><Clock className="size-3.5" aria-hidden /><Countdown to={live.expires_at} /> <span className="font-normal text-muted">({dateTime(live.expires_at)})</span></div></div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button size="lg" onClick={() => nav(`/requests/${req.id}/pay`)} icon={<ArrowRight className="size-4" aria-hidden />}>Continue to PayPal checkout</Button>
            {live.status === "active" && <Button variant="secondary" loading={revoke.isPending} onClick={() => revoke.mutate()}>Revoke</Button>}
          </div>
        </Card>
        <Card className="p-5">
          <SectionTitle>Two approvals, both required</SectionTitle>
          <ol className="grid gap-3 text-[13.5px]">
            <li className="flex gap-3"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-teal text-white"><BadgeCheck className="size-4" aria-hidden /></span><div><b>Organisation approval</b><div className="text-muted">Done — bound to snapshot {live.snapshot_hash.slice(0, 10)}…</div></div></li>
            <li className="flex gap-3"><span className="grid size-7 shrink-0 place-items-center rounded-full bg-sunken text-ink-2"><Lock className="size-4" aria-hidden /></span><div><b>PayPal buyer approval</b><div className="text-muted">Next — in PayPal's own window. Neither approval alone can move money.</div></div></li>
          </ol>
        </Card>
      </div>
    );
  }

  if (!quoteId) return <Card><Empty title="Nothing to approve yet" body="Compare quotes first; approval opens for a payment-eligible quote." /></Card>;
  if (review.error) return <ErrorBox error={review.error} onRetry={() => review.refetch()} />;
  if (!review.data) return <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-96" /><Skeleton className="h-96" /></div>;
  const t = review.data.terms;
  const quote = cmp?.quotes.find((q) => q.quote_id === quoteId);
  const isApprover = me?.roles.includes("approver");

  return (
    <div className="grid gap-6">
      {!isApprover && (
        <Callout tone="info" icon={<UserRoundCog className="size-4" aria-hidden />} title="You are acting as the requester">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Self-approval is disabled. In this demo workspace you can switch to the labelled approver persona.</span>
            {me?.workspace?.is_demo && <Button size="sm" onClick={() => switchTo("approver")}>Switch to Avery Chen (approver)</Button>}
          </div>
        </Callout>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <SectionTitle hint="Rebuilt from the database right now — this exact content is hashed">Exact purchase terms</SectionTitle>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5 text-[14px]">
            <dt className="text-muted">Supplier</dt><dd className="font-semibold">{t.supplier.name} <Badge tone={t.supplier.link === "confirmed" ? "good" : "warn"}>{t.supplier.link}</Badge></dd>
            <dt className="text-muted">Recipient</dt><dd><span className="font-mono">{t.merchant?.merchant_id ?? "—"}</span> <Badge tone="info">PayPal {t.merchant?.environment}</Badge></dd>
            <dt className="text-muted">Items</dt><dd>{t.line_items.map((l: any, i: number) => <div key={i}>{l.quantity} × {l.description} @ {money(l.unit_price, t.currency)}</div>)}</dd>
            <dt className="text-muted">Subtotal</dt><dd className="tnum">{money(t.amounts.subtotal, t.currency)}</dd>
            <dt className="text-muted">Shipping</dt><dd className="tnum">{money(t.amounts.shipping, t.currency)}</dd>
            <dt className="text-muted">Tax</dt><dd className="tnum">{money(t.amounts.tax, t.currency)}</dd>
            <dt className="text-muted">Currency</dt><dd>{t.currency}</dd>
            <dt className="text-muted">Shipping terms</dt><dd>{t.shipping_terms ?? "—"}</dd>
            <dt className="text-muted">Delivery claim</dt><dd>{t.delivery_promise_days} days (supplier claim)</dd>
            <dt className="text-muted">Versions</dt><dd>Requirements v{t.request.version} · quote v{t.quote.version} · policy v{t.policy.version}</dd>
          </dl>
          <div className="mt-5 rounded-2xl bg-ink p-5 text-white">
            <div className="text-[12px] uppercase tracking-wider text-white/60">Total to approve</div>
            <div className="font-display text-[48px] leading-none tnum">{money(t.amounts.total, t.currency)}</div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-white/70"><Fingerprint className="size-3.5" aria-hidden />Terms hash <span className="font-mono">{review.data.terms_hash.slice(0, 16)}…</span> · approval expires {review.data.approval_ttl_minutes} min after signing</div>
          </div>
        </Card>
        <Card className="p-6">
          <SectionTitle hint="Each amount next to the line on the supplier's PDF it came from">Source evidence</SectionTitle>
          <ul className="grid gap-2">
            {quote && ["subtotal", "shipping", "tax", "total", "delivery_days", "attr:connector", "valid_until"].map((f) => {
              const ev = quote.evidence.find((e) => e.field === f);
              return (
                <li key={f}>
                  <button onClick={() => onOpen(openFieldTarget(quote, f))} className="w-full rounded-xl border border-line px-3 py-2.5 text-left hover:border-teal/40 hover:bg-teal-soft/40">
                    <div className="flex items-center justify-between text-[12px] text-muted"><span>{FIELD_LABEL[f]}</span><span>{ev ? `page ${ev.page}` : "no evidence"}</span></div>
                    <div className="mt-0.5 truncate font-mono text-[12.5px] text-ink">{ev?.source_text ?? "—"}</div>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="mt-4 flex flex-wrap gap-1.5">{review.data.outcome.checks.map((c: any) => <CheckBadge key={c.key} status={c.status} label={c.label} />)}</div>
        </Card>
      </div>

      <Card className="p-5">
        {review.data.eligible ? (
          <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
            <Field label="Approval note (optional)"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Within Q4 support budget" /></Field>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={!isApprover} onClick={() => setRejectOpen(true)} icon={<Ban className="size-4" aria-hidden />}>Reject</Button>
              <Button size="lg" disabled={!review.data.can_approve} loading={approve.isPending} onClick={() => approve.mutate()} icon={<ShieldCheck className="size-4" aria-hidden />}>Approve exact purchase</Button>
            </div>
            {review.data.self_approval_blocked && <p className="text-[12.5px] text-amber md:col-span-2">You created this request; self-approval is disabled by organisation policy.</p>}
          </div>
        ) : <Callout tone="bad" title="This quote is not payment-eligible">{review.data.blocked_reason}</Callout>}
      </Card>

      <Dialog open={rejectOpen} onClose={() => setRejectOpen(false)} title="Reject this purchase"
        footer={<><Button variant="ghost" onClick={() => setRejectOpen(false)}>Cancel</Button><Button variant="danger" loading={reject.isPending} disabled={rejectNote.trim().length < 4} onClick={() => reject.mutate()}>Record rejection</Button></>}>
        <Field label="Reason (required)"><textarea className={inputCls} rows={3} value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} autoFocus /></Field>
      </Dialog>
    </div>
  );
}
