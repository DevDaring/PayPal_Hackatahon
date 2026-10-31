import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Activity, ArrowLeft, Check, ChevronRight, CreditCard, FileSearch, ListChecks, Receipt as ReceiptIcon, Scale, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { money, REQUEST_STATUS, PAYMENT_STATUS } from "../lib/format";
import type { Comparison, RequestDetail, WfEvent } from "../lib/types";
import { ApproveStep } from "../components/ApproveStep";
import { ChatPanel } from "../components/ChatPanel";
import { CompareStep } from "../components/CompareStep";
import { EvidenceStep } from "../components/EvidenceStep";
import { EvidenceSheet, type EvidenceTarget } from "../components/EvidenceViewer";
import { CheckoutPanel, Receipt } from "../components/PaymentPanel";
import { RequirementsStep } from "../components/RequirementsStep";
import { Timeline } from "../components/Timeline";
import { Badge, Callout, Card, cx, ErrorBox, Skeleton } from "../components/ui";

const STEPS = [
  { key: "requirements", label: "Requirements", icon: ListChecks },
  { key: "evidence", label: "Quotes & evidence", icon: FileSearch },
  { key: "compare", label: "Compare", icon: Scale },
  { key: "approve", label: "Approve", icon: ShieldCheck },
  { key: "pay", label: "Pay", icon: CreditCard },
  { key: "receipt", label: "Receipt", icon: ReceiptIcon },
] as const;

function defaultStep(r: RequestDetail): string {
  const done = r.payments.find((p) => p.state === "completed");
  if (done) return "receipt";
  if (r.payments.some((p) => !["canceled", "failed"].includes(p.state))) return "pay";
  if (r.approvals.some((a) => a.status === "active")) return "approve";
  if (!r.versions.length) return "requirements";
  if (!r.documents.length || r.status === "analyzing") return "evidence";
  return "compare";
}

function useLiveEvents(requestId: string, onEvent: () => void) {
  const [events, setEvents] = useState<WfEvent[]>([]);
  useEffect(() => {
    setEvents([]);
    let es: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let last = 0;
    const add = (e: WfEvent) => { if (e.id > last) { last = e.id; setEvents((xs) => [...xs, e]); onEvent(); } };
    if ("EventSource" in window) {
      es = new EventSource(`/api/v1/requests/${requestId}/events/stream`, { withCredentials: true });
      es.addEventListener("workflow", (m) => add(JSON.parse((m as MessageEvent).data)));
      es.onerror = () => {
        // Fall back to polling persisted events; refresh keeps the state recoverable.
        es?.close();
        if (!poll) poll = setInterval(async () => { try { const r = await api(`/requests/${requestId}/events?after=${last}`); r.items.forEach(add); } catch { /* retry next tick */ } }, 2500);
      };
    }
    return () => { es?.close(); if (poll) clearInterval(poll); };
  }, [requestId]); // eslint-disable-line react-hooks/exhaustive-deps
  return events;
}

export default function RequestWorkspace() {
  const { id = "", step } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [target, setTarget] = useState<EvidenceTarget | null>(null);
  const [activity, setActivity] = useState<boolean | null>(null);
  const req = useQuery<RequestDetail>({
    queryKey: ["request", id], queryFn: () => api(`/requests/${id}`),
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "analyzing" || q.state.data.documents.some((d) => ["uploaded", "extracting"].includes(d.status))) ? 2500 : 15000),
  });
  const cmp = useQuery<Comparison>({ queryKey: ["comparison", id, req.data?.updated_at, req.data?.documents.map((d) => d.status).join()], queryFn: () => api(`/requests/${id}/comparison`), enabled: !!req.data?.versions.length,
    refetchInterval: (q) => (q.state.data && q.state.data.quotes.length > 0 && !q.state.data.explanation ? 2500 : false) });
  const events = useLiveEvents(id, () => { qc.invalidateQueries({ queryKey: ["request", id] }); });
  const r = req.data;
  const current = step ?? (r ? defaultStep(r) : "requirements");
  const live = r?.approvals.find((a) => a.status === "active" || a.status === "consumed_for_execution");
  const op = live ? r?.payments.find((p) => p.approval_id === live.id) : r?.payments[0];
  const completed = r?.payments.find((p) => p.state === "completed");

  const reached = useMemo(() => {
    if (!r) return new Set<string>();
    const s = new Set(["requirements"]);
    if (r.versions.length) s.add("evidence");
    if (r.versions.length && r.documents.length) s.add("compare");
    if (cmp.data?.summary?.payment_eligible_quote_ids?.length || live) s.add("approve");
    if (live) s.add("pay");
    if (completed) { s.add("pay"); s.add("receipt"); }
    return s;
  }, [r, cmp.data, live, completed]);

  if (req.error) return <ErrorBox error={req.error} onRetry={() => req.refetch()} />;
  if (!r) return <div className="grid gap-4"><Skeleton className="h-16" /><Skeleton className="h-12" /><Skeleton className="h-96" /></div>;
  const idx = STEPS.findIndex((s) => s.key === current);
  const showActivity = activity ?? (current === "requirements" || current === "evidence");

  return (
    <div className="pb-16">
      <Link to="/requests" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" aria-hidden />Purchase requests</Link>
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={REQUEST_STATUS[r.status]?.tone}>{REQUEST_STATUS[r.status]?.label}</Badge>
            {op && <Badge tone={PAYMENT_STATUS[op.state]?.tone}>{PAYMENT_STATUS[op.state]?.label}</Badge>}
            {r.lab_scenario && <Badge tone="info">Demo Lab · controlled test</Badge>}
            {r.version && <span className="text-[12px] text-muted">requirements v{r.version}</span>}
          </div>
          <h1 className="mt-1.5 font-display text-[32px] leading-tight text-ink md:text-[38px]">{r.title}</h1>
          {r.budget && <p className="text-sm text-muted">{r.quantity} units · budget {money(r.budget, r.currency)} · deliver by {r.deadline}</p>}
        </div>
        <button onClick={() => setActivity(!showActivity)} aria-pressed={showActivity} className="hidden items-center gap-2 self-start rounded-xl border border-line-strong bg-surface px-3 py-2 text-[13px] font-medium text-ink-2 hover:bg-sunken md:inline-flex">
          <Activity className="size-4 text-teal" aria-hidden />{showActivity ? "Hide" : "Show"} live activity{r.workflow?.status === "running" && <span className="size-2 rounded-full bg-teal-bright pulse-ring" aria-label="running" />}
        </button>
      </div>

      <nav aria-label="Purchase journey" className="mb-6 overflow-x-auto">
        <ol className="flex min-w-max items-center gap-1 rounded-2xl border border-line bg-surface p-1.5 shadow-[var(--shadow-card)]">
          {STEPS.map((s, i) => {
            const enabled = reached.has(s.key) || s.key === current;
            const done = i < idx && reached.has(s.key);
            return (
              <li key={s.key} className="flex items-center">
                <button disabled={!enabled} onClick={() => nav(`/requests/${id}/${s.key}`)} aria-current={s.key === current ? "step" : undefined}
                  className={cx("flex items-center gap-2 rounded-xl px-3 py-2 text-[13.5px] transition", s.key === current ? "bg-ink text-white" : enabled ? "text-ink hover:bg-sunken" : "text-muted/60 cursor-not-allowed")}>
                  <span className={cx("grid size-6 place-items-center rounded-full text-[11px]", s.key === current ? "bg-teal-bright text-navy-900" : done ? "bg-teal text-white" : "bg-sunken text-muted")}>
                    {done ? <Check className="size-3.5" aria-hidden /> : <s.icon className="size-3.5" aria-hidden />}
                  </span>
                  {s.label}
                </button>
                {i < STEPS.length - 1 && <ChevronRight className="mx-0.5 size-4 text-line-strong" aria-hidden />}
              </li>
            );
          })}
        </ol>
      </nav>

      <div className={cx("grid gap-6", showActivity && "xl:grid-cols-[1fr_300px]")}>
        <div className="min-w-0 animate-in" key={current}>
          {current === "requirements" && <RequirementsStep req={r} onConfirmed={() => nav(`/requests/${id}/evidence`)} />}
          {current === "evidence" && <EvidenceStep req={r} cmp={cmp.data} onOpen={setTarget} />}
          {current === "compare" && (cmp.data ? <CompareStep req={r} cmp={cmp.data} onOpen={setTarget} /> : <Skeleton className="h-96" />)}
          {current === "approve" && <ApproveStep req={r} cmp={cmp.data} onOpen={setTarget} />}
          {current === "pay" && (live ? <CheckoutPanel requestId={id} approval={live} op={op?.approval_id === live.id ? op : null} /> : completed ? <Callout tone="good" title="Paid">This request's payment is complete — see the receipt.</Callout> : <Callout tone="warn" title="An active organisation approval is required">Approve the exact purchase first. If an earlier approval was invalidated, a fresh one is required.</Callout>)}
          {current === "receipt" && (completed ? <Receipt requestId={id} opId={completed.id} /> : <Callout tone="info">No confirmed payment yet.</Callout>)}
        </div>
        <aside className={showActivity ? "hidden xl:block" : "hidden"}>
          <Card className="sticky top-6 max-h-[calc(100vh-48px)] overflow-y-auto p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-ink"><Activity className="size-4 text-teal" aria-hidden />Live activity {r.workflow?.status === "running" && <span className="size-2 rounded-full bg-teal-bright pulse-ring" aria-label="running" />}</div>
            <Timeline events={[...events].reverse().slice(0, 30)} compact />
          </Card>
        </aside>
      </div>
      {r.versions.length > 0 && <ChatPanel requestId={id} cmp={cmp.data} onOpen={setTarget} />}
      <EvidenceSheet target={target} onClose={() => setTarget(null)} />
    </div>
  );
}
