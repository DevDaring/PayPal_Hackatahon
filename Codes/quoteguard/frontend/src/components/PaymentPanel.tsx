import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PayPalButtons, PayPalScriptProvider } from "@paypal/react-paypal-js";
import { AlertTriangle, BadgeCheck, Check, CircleDashed, Download, FileJson, FlaskConical, Loader2, Lock, RefreshCcw, ShieldCheck, Undo2, Wallet } from "lucide-react";
import { api, ApiError, errorText, post } from "../lib/api";
import { dateTime, money, PAYMENT_STATUS } from "../lib/format";
import { usePublicConfig, useRoles, useSession } from "../lib/session";
import type { Approval, Payment, WfEvent } from "../lib/types";
import { Countdown } from "./ApproveStep";
import { Timeline } from "./Timeline";
import { Badge, Button, Callout, Card, CopyText, cx, Dialog, Field, inputCls, SectionTitle, Spinner } from "./ui";

function Steps({ op, approval }: { op?: Payment | null; approval?: Approval | null }) {
  const s = op?.state;
  const steps = [
    { label: "Organisation approval", done: !!approval, sub: approval ? `snapshot ${approval.snapshot_hash.slice(0, 8)}…` : "required" },
    { label: "PayPal order created", done: !!op?.provider_order_id, sub: op?.provider_order_id ?? "from approved snapshot only" },
    { label: "Buyer approves in PayPal", done: !!op && ["capture_pending", "completed"].includes(s!) || op?.provider_order_status === "APPROVED" || op?.provider_order_status === "COMPLETED", sub: "PayPal's own window" },
    { label: "Capture confirmed", done: s === "completed", active: s === "capture_pending" || s === "reconciling", sub: op?.provider_capture_id ?? (s === "reconciling" ? "reconciling with PayPal" : "verified response") },
  ];
  return (
    <ol className="grid gap-2 sm:grid-cols-4">
      {steps.map((st, i) => (
        <li key={i} className={cx("rounded-xl border p-3", st.done ? "border-teal/30 bg-teal-soft/60" : st.active ? "border-amber-line bg-amber-soft/60" : "border-line bg-surface")}>
          <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
            <span className={cx("grid size-5 place-items-center rounded-full", st.done ? "bg-teal text-white" : st.active ? "bg-amber text-white pulse-ring" : "bg-sunken text-muted")}>
              {st.done ? <Check className="size-3" aria-hidden /> : st.active ? <Loader2 className="size-3 animate-spin" aria-hidden /> : <CircleDashed className="size-3" aria-hidden />}
            </span>
            {st.label}
          </div>
          <div className="mt-1 truncate font-mono text-[11px] text-muted">{st.sub}</div>
        </li>
      ))}
    </ol>
  );
}

export function CheckoutPanel({ requestId, approval, op: initialOp }: { requestId: string; approval: Approval; op?: Payment | null }) {
  const cfg = usePublicConfig();
  const qc = useQueryClient();
  const nav = useNavigate();
  const { me } = useSession();
  const { isAdmin } = useRoles();
  const [opId, setOpId] = useState<string | null>(initialOp?.id ?? null);
  const opQ = useQuery<Payment>({
    queryKey: ["payment", opId], queryFn: () => api(`/payments/${opId}`), enabled: !!opId,
    refetchInterval: (q) => (q.state.data && ["reconciling", "capture_pending", "order_creating"].includes(q.state.data.state) ? 2000 : false),
  });
  const op = opQ.data ?? initialOp ?? null;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["payment", opId] }); qc.invalidateQueries({ queryKey: ["request", requestId] }); };
  const reconcile = useMutation({ mutationFn: () => post(`/payments/${opId}/reconcile`), onSuccess: (r: any) => { toast.success(`PayPal says: ${PAYMENT_STATUS[r.state]?.label ?? r.state}`); refresh(); }, onError: (e) => toast.error(errorText(e)) });
  const arm = useMutation({ mutationFn: () => post(`/payments/${opId}/arm-lost-response`), onSuccess: () => { toast.message("Controlled test armed: the next capture response will be discarded"); refresh(); }, onError: (e) => toast.error(errorText(e)) });
  const simApprove = useMutation({ mutationFn: () => post(`/payments/${opId}/simulated-approve`), onSuccess: () => doCapture(), onError: (e) => toast.error(errorText(e)) });
  const startSim = useMutation({ mutationFn: () => post<Payment>(`/approvals/${approval.id}/checkout`), onSuccess: (o) => { setOpId(o.id); refresh(); }, onError: (e) => toast.error(errorText(e)) });

  async function doCapture(id = opId) {
    try {
      const r = await post<Payment>(`/payments/${id}/capture`);
      qc.setQueryData(["payment", id], r);
      refresh();
      if (r.state === "completed") { toast.success(`Payment captured: ${money(r.captured_amount, r.currency)}`); nav(`/requests/${requestId}/receipt`); }
      else if (r.state === "reconciling") toast.warning("Capture result unknown — reconciling with PayPal. You will not be charged twice.");
      else if (r.last_error_code) toast.error(r.last_error_message ?? r.last_error_code);
    } catch (e) { toast.error(errorText(e)); refresh(); }
  }

  const adapter = op?.adapter ?? approval.snapshot?.merchant?.adapter;
  const blocked = op && ["canceled", "failed"].includes(op.state);
  const snap = approval.snapshot;

  return (
    <div className="grid gap-6">
      <Steps op={op} approval={approval} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <SectionTitle hint="Server-built from the approved snapshot. The browser cannot change amount or payee.">Pay {snap.supplier.name}</SectionTitle>
            <Badge tone="warn" icon={<FlaskConical className="size-3" aria-hidden />}>{adapter === "simulated" ? "SIMULATED (Demo Lab)" : "PayPal SANDBOX"}</Badge>
          </div>
          <div className="rounded-2xl bg-ink p-5 text-white">
            <div className="text-[12px] uppercase tracking-wider text-white/60">Approved total</div>
            <div className="font-display text-[48px] leading-none tnum">{money(snap.amounts.total, snap.currency)}</div>
            <div className="mt-3 grid gap-1 text-[12.5px] text-white/70">
              <div>Merchant <span className="font-mono text-white">{snap.merchant.merchant_id}</span></div>
              <div>{snap.line_items?.[0] ? `${snap.line_items[0].quantity} × ${snap.line_items[0].description}` : ""}</div>
              <div className="flex items-center gap-1.5"><Lock className="size-3" aria-hidden />Approval expires in <Countdown to={approval.expires_at} /></div>
            </div>
          </div>
          {op && (
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              <dt className="text-muted">Status</dt><dd><Badge tone={PAYMENT_STATUS[op.state]?.tone}>{PAYMENT_STATUS[op.state]?.label}</Badge>{op.provider_capture_status === "PENDING" && <Badge tone="warn" className="ml-1">PayPal: PENDING</Badge>}</dd>
              {op.provider_order_id && <><dt className="text-muted">PayPal order</dt><dd><CopyText value={op.provider_order_id} short={false} /></dd></>}
              <dt className="text-muted">Request IDs</dt><dd className="truncate font-mono text-[11.5px] text-ink-2">{op.order_request_id} · {op.capture_request_id}</dd>
            </dl>
          )}
          {op?.last_error_code && op.state !== "completed" && (
            <div className="mt-3"><Callout tone={op.last_error_code === "BUYER_CANCELED" ? "info" : ["canceled", "failed"].includes(op.state) ? "bad" : "warn"} title={op.last_error_code.replaceAll("_", " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())}>{op.last_error_message}</Callout></div>
          )}
        </Card>

        <Card className="p-6">
          {blocked ? (
            <Callout tone="bad" title="This payment cannot continue">A new organisation approval is required for the current terms. {op?.last_error_message}</Callout>
          ) : op?.state === "completed" ? (
            <div className="grid place-items-center gap-3 py-8 text-center">
              <span className="grid size-14 place-items-center rounded-full bg-teal text-white"><BadgeCheck className="size-7" aria-hidden /></span>
              <div className="font-display text-[30px] text-ink">Payment confirmed by PayPal</div>
              <Button onClick={() => nav(`/requests/${requestId}/receipt`)}>Open receipt</Button>
            </div>
          ) : op?.state === "reconciling" || op?.state === "capture_pending" ? (
            <div className="grid gap-3">
              <div className="flex items-center gap-2 font-semibold text-amber"><RefreshCcw className="size-4 animate-spin" aria-hidden />Reconciling with PayPal</div>
              <p className="text-[14px] text-ink-2">The capture response was not received. The payment is neither marked failed nor paid until PayPal confirms its state. The worker checks automatically; you can also check now.</p>
              <Button variant="secondary" loading={reconcile.isPending} onClick={() => reconcile.mutate()} icon={<RefreshCcw className="size-4" aria-hidden />}>Check status with PayPal</Button>
            </div>
          ) : adapter === "simulated" ? (
            <div className="grid gap-3">
              <Callout tone="warn" title="Simulated provider — controlled Demo Lab test">This is not a PayPal transaction. It exercises the same payment service with a deterministic in-database provider.</Callout>
              {!op ? <Button loading={startSim.isPending} onClick={() => startSim.mutate()}>Create simulated order</Button>
                : <Button loading={simApprove.isPending} onClick={() => simApprove.mutate()}>Simulate buyer approval & capture</Button>}
            </div>
          ) : cfg.data?.paypal_client_id ? (
            <div>
              <div className="mb-3 flex items-center gap-2 text-[14px] font-semibold text-ink"><Wallet className="size-4 text-teal" aria-hidden />Buyer approval in PayPal</div>
              {cfg.data.sandbox_buyer ? (
                <div className="mb-3 rounded-xl border border-line bg-sunken p-3 text-[12.5px]">
                  <div className="font-semibold text-ink">Sandbox test buyer (no real money)</div>
                  <div className="mt-1 grid grid-cols-[auto_1fr] gap-x-3"><span className="text-muted">Email</span><CopyText value={cfg.data.sandbox_buyer.email} short={false} /><span className="text-muted">Password</span><CopyText value={cfg.data.sandbox_buyer.password} short={false} /></div>
                </div>
              ) : (
                <p className="mb-3 text-[12.5px] text-muted">Sign in with a PayPal <b>sandbox</b> personal account, or choose “Debit or Credit Card” and use a PayPal sandbox test card.</p>
              )}
              <PayPalScriptProvider options={{ clientId: cfg.data.paypal_client_id, currency: snap.currency, intent: "capture", components: "buttons", "disable-funding": "paylater,venmo" } as any}>
                <PayPalButtons style={{ layout: "vertical", shape: "rect", label: "pay", height: 46 }} forceReRender={[opId]}
                  createOrder={async () => {
                    try {
                      const o = await post<Payment>(`/approvals/${approval.id}/checkout`);
                      setOpId(o.id);
                      qc.setQueryData(["payment", o.id], o);
                      if (!o.provider_order_id || o.state !== "awaiting_payer") throw new ApiError(409, o.last_error_code ?? "NOT_READY", o.last_error_message ?? `Payment is ${o.state}`);
                      return o.provider_order_id;
                    } catch (e) { toast.error(errorText(e)); refresh(); throw e; }
                  }}
                  onApprove={async () => { const o = await post<Payment>(`/approvals/${approval.id}/checkout`); await doCapture(o.id); }}
                  onCancel={async () => { if (opId) { await post(`/payments/${opId}/buyer-canceled`).catch(() => {}); refresh(); } toast.message("PayPal window closed — nothing was charged. You can try again."); }}
                  onError={(err) => { console.error(err); toast.error("PayPal could not complete this step. Nothing was charged."); refresh(); }} />
              </PayPalScriptProvider>
              {isAdmin && me?.workspace?.is_demo && op?.state === "awaiting_payer" && !op.fault_injection_armed && (
                <button onClick={() => arm.mutate()} className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] text-muted hover:text-ink"><FlaskConical className="size-3.5" aria-hidden />Demo Lab: discard PayPal's capture response to show recovery</button>
              )}
              {op?.fault_injection_armed && <div className="mt-3"><Callout tone="warn" title="Controlled test armed">The real capture will happen at PayPal, but QuoteGuard will discard the response and must reconcile.</Callout></div>}
            </div>
          ) : (
            <Callout tone="bad" title="PayPal sandbox is not configured">Checkout is disabled until sandbox credentials are present on the server. QuoteGuard never substitutes a fake success.</Callout>
          )}
        </Card>
      </div>
    </div>
  );
}

export function Receipt({ requestId, opId }: { requestId: string; opId: string }) {
  const op = useQuery<any>({ queryKey: ["payment", opId], queryFn: () => api(`/payments/${opId}`) });
  const ev = useQuery<{ items: WfEvent[] }>({ queryKey: ["events-all", requestId], queryFn: () => api(`/requests/${requestId}/events`) });
  const chain = useQuery<any>({ queryKey: ["audit-verify"], queryFn: () => api("/audit/verify") });
  const { isAdmin } = useRoles();
  const [refundOpen, setRefundOpen] = useState(false);
  if (!op.data) return <Spinner />;
  const o = op.data;
  return (
    <div className="grid gap-6">
      <Card className="relative overflow-hidden p-6 md:p-8">
        <div className="pointer-events-none absolute -right-20 -top-20 size-72 rounded-full bg-teal-soft blur-2xl" />
        <div className="relative grid gap-6 md:grid-cols-[1.2fr_1fr]">
          <div>
            <Badge tone={o.state === "completed" ? "good" : "warn"} icon={o.state === "completed" ? <ShieldCheck className="size-3" aria-hidden /> : <AlertTriangle className="size-3" aria-hidden />}>
              {o.state === "completed" ? `Verified by ${o.adapter === "sandbox" ? "PayPal Sandbox" : "simulated provider (Demo Lab)"}` : PAYMENT_STATUS[o.state]?.label}
            </Badge>
            <div className="mt-3 text-[13px] uppercase tracking-wider text-muted">Captured amount</div>
            <div className="font-display text-[56px] leading-none tnum text-ink">{money(o.captured_amount ?? o.amount, o.currency)}</div>
            <p className="mt-2 text-sm text-muted">{o.request_title} · paid to <span className="font-mono">{o.merchant_id}</span> · {dateTime(o.completed_at ?? o.updated_at)}</p>
          </div>
          <dl className="grid content-start grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[13px]">
            <dt className="text-muted">PayPal order</dt><dd>{o.provider_order_id ? <CopyText value={o.provider_order_id} short={false} /> : "—"}</dd>
            <dt className="text-muted">Capture ID</dt><dd>{o.provider_capture_id ? <CopyText value={o.provider_capture_id} short={false} /> : "—"}</dd>
            <dt className="text-muted">Capture status</dt><dd>{o.provider_capture_status ?? "—"}</dd>
            <dt className="text-muted">Snapshot hash</dt><dd><CopyText value={o.snapshot_hash} /></dd>
            <dt className="text-muted">Approval</dt><dd>{o.approval.status.replaceAll("_", " ")}</dd>
            <dt className="text-muted">Audit chain</dt><dd>{chain.data ? (chain.data.valid ? <Badge tone="good">intact · {chain.data.checked} entries</Badge> : <Badge tone="bad">broken at {chain.data.broken_at}</Badge>) : "…"}</dd>
          </dl>
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2">
          <a href={`/api/v1/requests/${requestId}/export.pdf`}><Button icon={<Download className="size-4" aria-hidden />}>Evidence package (PDF)</Button></a>
          <a href={`/api/v1/requests/${requestId}/export.json`}><Button variant="secondary" icon={<FileJson className="size-4" aria-hidden />}>Evidence package (JSON)</Button></a>
          {isAdmin && o.state === "completed" && <Button variant="ghost" icon={<Undo2 className="size-4" aria-hidden />} onClick={() => setRefundOpen(true)}>Partial refund (sandbox)</Button>}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card className="p-6">
          <SectionTitle hint="Actual recorded application events — not model reasoning">Decision replay</SectionTitle>
          {ev.data ? <Timeline events={ev.data.items} /> : <Spinner />}
        </Card>
        <div className="grid content-start gap-6">
          <Card className="p-6">
            <SectionTitle hint="Every call QuoteGuard made to the provider for this payment">Provider calls</SectionTitle>
            <ul className="grid gap-2 text-[12.5px]">
              {o.provider_calls.map((c: any, i: number) => (
                <li key={i} className="rounded-lg border border-line px-3 py-2">
                  <div className="flex items-center justify-between"><span className="font-semibold">{c.call}</span><Badge tone={c.outcome === "ok" ? "good" : c.outcome.includes("discarded") ? "warn" : "bad"}>{c.outcome}</Badge></div>
                  <div className="mt-0.5 font-mono text-[11px] text-muted">{c.provider_ref ?? "—"} {c.provider_status ? `· ${c.provider_status}` : ""} {c.http_status ? `· HTTP ${c.http_status}` : ""} {c.debug_id ? `· debug ${c.debug_id}` : ""}</div>
                </li>
              ))}
            </ul>
          </Card>
          {o.refunds?.length > 0 && (
            <Card className="p-6"><SectionTitle>Refunds</SectionTitle>
              <ul className="grid gap-1.5 text-[13px]">{o.refunds.map((r: any) => <li key={r.id} className="flex justify-between"><span>{money(r.amount, o.currency)} · {r.note}</span><Badge tone={r.state === "completed" ? "good" : "warn"}>{r.state}</Badge></li>)}</ul>
            </Card>
          )}
          <Callout tone="info" title="Limits">Sandbox transactions move no real money. Supplier PDFs are synthetic. The audit hash chain detects ordinary edits but is not tamper-proof against a database administrator.</Callout>
        </div>
      </div>
      <RefundDialog open={refundOpen} onClose={() => setRefundOpen(false)} op={o} onDone={() => op.refetch()} />
    </div>
  );
}

function RefundDialog({ open, onClose, op, onDone }: { open: boolean; onClose: () => void; op: any; onDone: () => void }) {
  const [amount, setAmount] = useState("10.00");
  const [note, setNote] = useState("");
  const m = useMutation({ mutationFn: () => api(`/payments/${op.id}/refund`, { body: { amount, note } }), onSuccess: () => { toast.success("Refund sent to PayPal Sandbox"); onClose(); onDone(); }, onError: (e) => toast.error(errorText(e)) });
  return (
    <Dialog open={open} onClose={onClose} title="Partial refund (merchant admin)" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={m.isPending} disabled={note.trim().length < 4} onClick={() => m.mutate()}>Refund {money(amount, op.currency)}</Button></>}>
      <div className="grid gap-3">
        <Callout tone="warn">Issues a real sandbox refund through the Payments API against capture {op.provider_capture_id}. It cannot exceed the remaining captured balance.</Callout>
        <Field label="Amount"><input className={inputCls} value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" /></Field>
        <Field label="Reason (required)"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. 2 headsets arrived damaged" /></Field>
      </div>
    </Dialog>
  );
}
