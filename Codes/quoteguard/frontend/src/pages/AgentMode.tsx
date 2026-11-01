import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight, Bot, Check, FileSearch, Hand, Loader2, Lock, PackageOpen, Play, Scale, ShieldAlert, ShieldCheck, Sparkles, UserCheck, Wallet, X,
} from "lucide-react";
import { api, errorText, post } from "../lib/api";
import { dateOnly, money } from "../lib/format";
import type { Comparison, RequestDetail, WfEvent } from "../lib/types";
import { Badge, Button, Card, cx } from "../components/ui";

type NodeState = "idle" | "active" | "done" | "gate" | "error";
const NODES = [
  { key: "understand", title: "Understand the request", sub: "Gemini drafts typed requirements from plain English", icon: Bot },
  { key: "confirm", title: "Human checkpoint · confirm requirements", sub: "Nothing counts until a person confirms", icon: UserCheck, gate: true },
  { key: "gather", title: "Gather supplier quotes", sub: "Three synthetic supplier PDFs", icon: PackageOpen },
  { key: "read", title: "Read & cite every term", sub: "Each value must point to a verbatim line on the page", icon: FileSearch },
  { key: "verify", title: "Verify evidence & surface unknowns", sub: "Numbers re-checked, missing costs flagged, injected text quarantined", icon: ShieldAlert },
  { key: "decide", title: "Decide with deterministic policy", sub: "Decimal arithmetic · pass / fail / unknown · the AI only explains", icon: Scale },
  { key: "approve", title: "Human checkpoint · approve the exact purchase", sub: "Approval is a hash of supplier, amount, payee and expiry", icon: ShieldCheck, gate: true },
  { key: "pay", title: "Pay through PayPal", sub: "Order built only from the approved snapshot", icon: Wallet },
] as const;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function AgentMode() {
  const nav = useNavigate();
  const [state, setState] = useState<Record<string, NodeState>>({});
  const [req, setReq] = useState<RequestDetail | null>(null);
  const [cmp, setCmp] = useState<Comparison | null>(null);
  const [events, setEvents] = useState<WfEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [waitConfirm, setWaitConfirm] = useState(false);
  const lastEvent = useRef(0);
  const reqId = useRef<string | null>(null);
  const set = (k: string, v: NodeState) => setState((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      if (!reqId.current) return;
      try {
        const r = await api(`/requests/${reqId.current}/events?after=${lastEvent.current}`);
        if (r.items.length) { lastEvent.current = r.items[r.items.length - 1].id; setEvents((e) => [...e, ...r.items]); }
      } catch { /* next tick */ }
    }, 1200);
    return () => clearInterval(t);
  }, [running]);

  async function start() {
    setRunning(true); setEvents([]); setCmp(null); setReq(null); lastEvent.current = 0; setState({});
    try {
      set("understand", "active");
      const r = await post<RequestDetail>("/demo/sample-request");
      reqId.current = r.id;
      setReq(r);
      await sleep(600);
      set("understand", "done");
      set("confirm", "gate");
      setWaitConfirm(true);
    } catch (e) { set("understand", "error"); toast.error(errorText(e)); setRunning(false); }
  }

  async function confirmAndContinue() {
    if (!req) return;
    setWaitConfirm(false);
    try {
      await post(`/requests/${req.id}/confirm`, { requirements: req.draft.spec, expected_version: 0 });
      set("confirm", "done");
      set("gather", "active");
      await post(`/requests/${req.id}/sample-quotes`);
      await sleep(500);
      set("gather", "done");
      set("read", "active");
      let detail: RequestDetail;
      for (;;) {
        detail = await api<RequestDetail>(`/requests/${req.id}`);
        setReq(detail);
        if (detail.documents.length && detail.documents.every((d) => !["uploaded", "extracting"].includes(d.status))) break;
        await sleep(1200);
      }
      set("read", "done");
      set("verify", "active");
      let c: Comparison;
      for (;;) {
        c = await api<Comparison>(`/requests/${req.id}/comparison`);
        if (c.quotes.length === detail.documents.length && c.summary) break;
        await sleep(1000);
      }
      setCmp(c);
      await sleep(700);
      set("verify", "done");
      set("decide", "active");
      for (let i = 0; i < 25 && !c.explanation; i++) { await sleep(1000); c = await api<Comparison>(`/requests/${req.id}/comparison`); }
      setCmp(c);
      set("decide", "done");
      set("approve", "gate");
    } catch (e) { toast.error(errorText(e)); }
  }

  const s = cmp?.summary;
  const evidenceCount = cmp?.quotes.reduce((n, q) => n + q.evidence.length, 0) ?? 0;
  const bboxCount = cmp?.quotes.reduce((n, q) => n + q.evidence.filter((e) => e.location === "bbox").length, 0) ?? 0;
  const unknowns = s?.unknowns?.length ?? 0;
  const spec = req?.draft?.spec;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between animate-in">
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-teal">Agent mode · agentic commerce with guardrails</div>
          <h1 className="font-display text-[38px] leading-[1.05] text-ink md:text-[46px]">Watch the procurement agent work.</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-muted">The agent reads, cites, compares and recommends on its own — and stops at the two moments that need a human: confirming what to buy, and approving the exact purchase before PayPal moves money.</p>
        </div>
        {!running ? <Button size="lg" onClick={start} icon={<Play className="size-4" aria-hidden />}>Run the agent</Button> : <Badge tone="info" icon={<Sparkles className="size-3" aria-hidden />}>Live run on real services</Badge>}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Card className="relative overflow-hidden border-0 bg-ink p-6 text-white md:p-8">
          <div className="pointer-events-none absolute -right-28 -top-28 size-96 rounded-full bg-teal-bright/10 blur-3xl" />
          <ol className="relative grid gap-0">
            {NODES.map((n, i) => {
              const st = state[n.key] ?? "idle";
              const Icon = n.icon;
              return (
                <li key={n.key} className="relative flex gap-4 pb-6 last:pb-0">
                  {i < NODES.length - 1 && <span className={cx("absolute left-[19px] top-11 h-[calc(100%-36px)] w-0.5 transition-colors duration-700", st === "done" ? "bg-teal-bright" : "bg-white/10")} aria-hidden />}
                  <span className={cx("relative z-10 grid size-10 shrink-0 place-items-center rounded-xl transition-all duration-500",
                    st === "done" ? "bg-teal-bright text-navy-900" : st === "active" ? "bg-white text-ink pulse-ring" : st === "gate" ? "bg-amber-400 text-navy-900 pulse-ring" : st === "error" ? "bg-danger text-white" : "bg-white/8 text-white/40")}>
                    {st === "done" ? <Check className="size-5" aria-hidden /> : st === "active" ? <Loader2 className="size-5 animate-spin" aria-hidden /> : st === "gate" ? <Hand className="size-5" aria-hidden /> : st === "error" ? <X className="size-5" aria-hidden /> : <Icon className="size-5" aria-hidden />}
                  </span>
                  <div className={cx("min-w-0 flex-1 pt-1 transition-opacity duration-500", st === "idle" && "opacity-45")}>
                    <div className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">{n.title}{"gate" in n && n.gate && <Badge className="border-amber-300/40! bg-amber-300/15! text-amber-200!">human</Badge>}</div>
                    <p className="text-[13px] text-white/55">{n.sub}</p>

                    {n.key === "understand" && spec && (
                      <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
                        {[`${spec.quantity} units`, spec.item, `${money(spec.budget_amount, spec.currency)} incl. shipping & tax`, `by ${dateOnly(spec.deadline_date)}`, ...spec.mandatory.map((m: any) => m.label)].map((t, k) => (
                          <span key={k} className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5">{t}</span>
                        ))}
                      </div>
                    )}
                    {n.key === "confirm" && waitConfirm && (
                      <Button className="mt-3 bg-amber-400! text-navy-900! hover:bg-amber-300!" onClick={confirmAndContinue} icon={<UserCheck className="size-4" aria-hidden />}>Confirm requirements & continue</Button>
                    )}
                    {n.key === "read" && req && req.documents.length > 0 && (
                      <div className="mt-2 grid gap-1">
                        {req.documents.map((d) => (
                          <div key={d.id} className="flex items-center gap-2 text-[12.5px] text-white/75">
                            {d.status === "extracted" ? <Check className="size-3.5 text-teal-bright" aria-hidden /> : <Loader2 className="size-3.5 animate-spin" aria-hidden />}
                            {d.filename.replace("_quote_DEMO.pdf", "").replaceAll("_", " ")}
                          </div>
                        ))}
                      </div>
                    )}
                    {n.key === "verify" && cmp && (
                      <p className="mt-2 text-[12.5px] text-white/75"><b className="text-white">{evidenceCount}</b> terms cited · <b className="text-white">{bboxCount}</b> pinned to page coordinates · <b className="text-amber-200">{unknowns}</b> unknowns surfaced</p>
                    )}
                    {n.key === "decide" && s && (
                      <div className="mt-2 rounded-xl border border-white/10 bg-white/5 p-3 text-[13px]">
                        {s.best_compliant_supplier ? <>Recommend <b className="text-teal-bright">{s.best_compliant_supplier}</b> at <b>{money(s.best_compliant_total)}</b>.</> : <>No compliant quote — nothing recommended.</>}
                        {s.why_cheapest_loses && <div className="mt-1 text-white/65">Cheapest ({s.why_cheapest_loses.supplier}) rejected: {s.why_cheapest_loses.blocking_checks.map((c: any) => c.label).join(", ")}.</div>}
                      </div>
                    )}
                    {n.key === "approve" && st === "gate" && s?.best_compliant_quote_id && (
                      <Button className="mt-3 bg-amber-400! text-navy-900! hover:bg-amber-300!" onClick={() => nav(`/requests/${req!.id}/approve?quote=${s.best_compliant_quote_id}`)} icon={<ArrowRight className="size-4" aria-hidden />}>Review & approve the exact purchase</Button>
                    )}
                    {n.key === "pay" && <p className="mt-1 flex items-center gap-1.5 text-[12px] text-white/45"><Lock className="size-3" aria-hidden />Unreachable for the agent — only an approved snapshot can create a PayPal order.</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>

        <div className="grid content-start gap-4">
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between"><h2 className="text-[15px] font-semibold">Live agent log</h2><span className="text-[11.5px] text-muted">recorded events, not model reasoning</span></div>
            <ol className="grid max-h-[420px] gap-2 overflow-y-auto pr-1" aria-live="polite">
              {events.length === 0 && <li className="text-sm text-muted">Press “Run the agent” to start a fresh request in this workspace.</li>}
              {[...events].reverse().map((e) => (
                <li key={e.id} className="animate-in rounded-lg border border-line px-3 py-2">
                  <div className="flex items-center justify-between gap-2 text-[13px] font-medium text-ink"><span className="truncate">{e.title}</span><span className="shrink-0 text-[11px] text-muted">{e.tool ?? e.actor}</span></div>
                  {e.detail && <p className="mt-0.5 line-clamp-2 text-[12px] text-ink-2">{e.detail}</p>}
                </li>
              ))}
            </ol>
          </Card>
          <Card className="p-5">
            <h2 className="mb-2 text-[15px] font-semibold">Guardrails</h2>
            <div className="grid grid-cols-2 gap-3 text-[13px]">
              <div><div className="mb-1 font-semibold text-teal-strong">The agent can</div><ul className="grid gap-1 text-ink-2">{["Draft requirements", "Read & cite PDFs", "Flag unknowns", "Compare & explain", "Query PayPal (read-only Agent Toolkit)"].map((t) => <li key={t} className="flex gap-1.5"><Check className="mt-0.5 size-3.5 shrink-0 text-teal" aria-hidden />{t}</li>)}</ul></div>
              <div><div className="mb-1 font-semibold text-danger">It cannot</div><ul className="grid gap-1 text-ink-2">{["Change the budget", "Approve anything", "Choose a payee", "Create or capture payments", "Follow instructions in PDFs"].map((t) => <li key={t} className="flex gap-1.5"><X className="mt-0.5 size-3.5 shrink-0 text-danger" aria-hidden />{t}</li>)}</ul></div>
            </div>
          </Card>
          {req && <Link to={`/requests/${req.id}`} className="text-sm font-medium text-teal hover:underline">Open this request step by step →</Link>}
        </div>
      </div>
    </div>
  );
}
