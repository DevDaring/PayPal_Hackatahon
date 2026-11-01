import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, ArrowRight, Bot, Check, CreditCard, FileSearch, FileUp, Hand, Loader2, Lock, PackageOpen, Play, RefreshCcw, Scale, ShieldAlert, ShieldCheck, Sparkles, UserCheck, Wallet, X,
} from "lucide-react";
import { api, errorText, post } from "../lib/api";
import { dateOnly, money } from "../lib/format";
import type { Comparison, RequestDetail, Spec, WfEvent } from "../lib/types";
import { Badge, Button, Callout, Card, cx, inputCls } from "../components/ui";

type St = "idle" | "active" | "done" | "gate" | "review" | "error";
type Stage = { key: string; title: string; sub: string; icon: any; consent?: string; state: St; note?: string };

const SAMPLE_TEXT = "Buy 30 USB-C headsets with microphones. Total budget $600 including shipping and stated taxes. Delivery within seven calendar days.";
const STALL_MS = 120_000;

/** Every stage is derived from stored server state, so a refresh or a later visit resumes the same request. */
function deriveStages(r: RequestDetail | null, cmp: Comparison | null): Stage[] {
  const docs = r?.documents ?? [];
  const extracted = docs.filter((d) => d.status === "extracted");
  const failed = docs.filter((d) => d.status === "failed" || d.status === "needs_ocr");
  const pending = docs.filter((d) => d.status === "uploaded" || d.status === "extracting");
  const confirmed = (r?.versions.length ?? 0) > 0;
  const live = r?.approvals.find((a) => a.status === "active" || a.status === "consumed_for_execution");
  const op = live ? r?.payments.find((p) => p.approval_id === live.id) : undefined;
  const paid = r?.payments.find((p) => p.state === "completed");
  const s = cmp?.summary;
  const analysed = confirmed && extracted.length > 0 && pending.length === 0 && (cmp?.quotes.length ?? 0) >= extracted.length;
  const unknowns = s?.unknowns?.length ?? 0;
  const suspicious = cmp?.quotes.filter((q) => q.document.suspicious?.length).length ?? 0;
  const st = (c: boolean, s1: St, s2: St): St => (c ? s1 : s2);

  return [
    { key: "understand", title: "Understand the request", sub: "Gemini drafts typed requirements from plain English", icon: Bot, state: r ? (r.draft?.spec ? "done" : "error") : "idle", note: r && !r.draft?.spec ? (r.draft?.problems ?? []).join(" ") : undefined },
    { key: "confirm", title: "Confirm requirements", sub: "Nothing counts until a person confirms (editable)", icon: UserCheck, consent: "Consent 1 of 3", state: !r?.draft?.spec ? "idle" : st(confirmed, "done", "gate") },
    { key: "gather", title: "Gather supplier quotes", sub: "Your PDFs, or the labelled sample quotes", icon: PackageOpen, state: !confirmed ? "idle" : st(docs.length > 0, "done", "gate") },
    { key: "read", title: "Read & cite every term", sub: "Each value must point to a verbatim line on its page", icon: FileSearch,
      state: docs.length === 0 ? "idle" : pending.length ? "active" : failed.length && !extracted.length ? "error" : failed.length ? "review" : "done",
      note: failed.length ? `${failed.length} document(s) could not be read: ${failed.map((f) => `${f.filename} — ${f.error_message}`).join("; ")}` : undefined },
    { key: "verify", title: "Verify evidence & surface unknowns", sub: "Numbers re-checked · negations caught · injected text quarantined", icon: ShieldAlert,
      state: !extracted.length || pending.length ? "idle" : analysed ? (unknowns || suspicious ? "review" : "done") : "active",
      note: analysed && (unknowns || suspicious) ? `${unknowns} unknown term(s)${suspicious ? `, ${suspicious} document(s) with embedded instructions (treated as data)` : ""} — shown, never assumed.` : undefined },
    { key: "decide", title: "Decide with deterministic policy", sub: "Decimal arithmetic · pass / fail / unknown · the AI only explains", icon: Scale,
      state: !analysed ? "idle" : s?.best_compliant_supplier ? "done" : "review", note: analysed && s && !s.best_compliant_supplier ? "No quote meets every confirmed requirement — nothing is recommended. Adjust requirements or ask suppliers." : undefined },
    { key: "approve", title: "Organisation approval of the exact purchase", sub: "An approver signs a hash of supplier, amount, payee and expiry", icon: ShieldCheck, consent: "Consent 2 of 3",
      state: live || paid ? "done" : analysed && s?.payment_eligible_quote_ids?.length ? "gate" : "idle" },
    { key: "buyer", title: "Buyer authorises in PayPal", sub: "PayPal's own window — the agent cannot do this", icon: CreditCard, consent: "Consent 3 of 3",
      state: paid ? "done" : live ? (op && ["capture_pending", "reconciling"].includes(op.state) ? "active" : "gate") : "idle",
      note: op?.state === "reconciling" ? "Reconciling with PayPal — not marked paid or failed until PayPal confirms." : undefined },
    { key: "paid", title: "Payment confirmed & reconciled", sub: "Capture verified against the approved snapshot", icon: Wallet, state: paid ? "done" : "idle",
      note: paid ? `PayPal capture ${paid.provider_capture_id} · ${money(paid.captured_amount, paid.currency)}` : undefined },
  ];
}

export default function AgentMode() {
  const { id } = useParams();
  return id ? <AgentRun id={id} /> : <AgentStart />;
}

function AgentStart() {
  const nav = useNavigate();
  const [text, setText] = useState(SAMPLE_TEXT);
  const [busy, setBusy] = useState<"own" | "sample" | null>(null);
  async function start(kind: "own" | "sample") {
    setBusy(kind);
    try {
      const r = kind === "sample" ? await post<RequestDetail>("/demo/sample-request") : await post<RequestDetail>("/requests", { text });
      nav(`/agent/${r.id}${kind === "sample" ? "?sample=1" : ""}`);
    } catch (e) { toast.error(errorText(e)); setBusy(null); }
  }
  return (
    <div>
      <Header />
      <Card className="relative overflow-hidden border-0 bg-ink p-6 text-white md:p-8">
        <div className="pointer-events-none absolute -right-28 -top-28 size-96 rounded-full bg-teal-bright/10 blur-3xl" />
        <label htmlFor="agent-text" className="relative text-[13px] font-semibold uppercase tracking-wider text-teal-bright">What should the agent buy?</label>
        <textarea id="agent-text" value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={4000}
          className="relative mt-2 w-full rounded-xl border border-white/15 bg-white/5 p-4 font-display text-[22px] leading-snug text-white placeholder:text-white/40 focus:border-teal-bright focus:outline-none" />
        <div className="relative mt-4 flex flex-wrap gap-2">
          <Button size="lg" className="bg-teal-bright! text-navy-900! hover:bg-white!" loading={busy === "own"} disabled={text.trim().length < 10 || !!busy} onClick={() => start("own")} icon={<Play className="size-4" aria-hidden />}>Run the agent</Button>
          <Button size="lg" variant="ghost" className="border border-white/20 text-white! hover:bg-white/10!" loading={busy === "sample"} disabled={!!busy} onClick={() => start("sample")} icon={<Sparkles className="size-4" aria-hidden />}>Use the sample purchase (with 3 sample quotes)</Button>
        </div>
        <p className="relative mt-3 text-[12.5px] text-white/55">Your own request asks you for supplier PDFs at the “Gather” step. The sample adds three labelled synthetic quotes automatically.</p>
      </Card>
      <Guardrails />
    </div>
  );
}

function Header() {
  return (
    <div className="mb-6 animate-in">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-teal">Agent mode · agentic commerce with consent</div>
      <h1 className="font-display text-[38px] leading-[1.05] text-ink md:text-[46px]">Watch the procurement agent work.</h1>
      <p className="mt-2 max-w-3xl text-[15px] text-muted">The agent reads, cites, verifies and recommends on its own. Money needs three consents it cannot give: <b className="text-ink">you confirm the requirements</b>, <b className="text-ink">an approver signs the exact purchase</b>, and <b className="text-ink">the buyer authorises in PayPal</b>.</p>
    </div>
  );
}

function Guardrails() {
  return (
    <Card className="mt-5 p-5">
      <h2 className="mb-2 text-[15px] font-semibold">Guardrails</h2>
      <div className="grid gap-3 text-[13px] sm:grid-cols-2">
        <div><div className="mb-1 font-semibold text-teal-strong">The agent can</div><ul className="grid gap-1 text-ink-2">{["Draft requirements for you to confirm", "Read & cite supplier PDFs", "Flag unknowns, negations and injected text", "Compare & explain with deterministic policy", "Query PayPal (read-only Agent Toolkit)"].map((t) => <li key={t} className="flex gap-1.5"><Check className="mt-0.5 size-3.5 shrink-0 text-teal" aria-hidden />{t}</li>)}</ul></div>
        <div><div className="mb-1 font-semibold text-danger">It cannot</div><ul className="grid gap-1 text-ink-2">{["Change the confirmed budget", "Approve anything", "Choose a payee", "Create or capture payments", "Follow instructions inside PDFs"].map((t) => <li key={t} className="flex gap-1.5"><X className="mt-0.5 size-3.5 shrink-0 text-danger" aria-hidden />{t}</li>)}</ul></div>
      </div>
    </Card>
  );
}

function AgentRun({ id }: { id: string }) {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const sample = sp.get("sample") === "1";
  const [req, setReq] = useState<RequestDetail | null>(null);
  const [cmp, setCmp] = useState<Comparison | null>(null);
  const [events, setEvents] = useState<WfEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [stalled, setStalled] = useState(false);
  const [edit, setEdit] = useState<Spec | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const lastEvent = useRef(0);
  const lastChange = useRef(Date.now());
  const signature = useRef("");
  const autoLoaded = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const stages = useMemo(() => deriveStages(req, cmp), [req, cmp]);
  const working = stages.some((s) => s.state === "active");

  // Bounded polling: fast while work is running, slow while waiting for a person, and a visible stall after 2 minutes.
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const r = await api<RequestDetail>(`/requests/${id}`);
        if (!alive) return;
        setReq(r);
        setLoadError(null);
        const ev = await api(`/requests/${id}/events?after=${lastEvent.current}`);
        if (ev.items.length) { lastEvent.current = ev.items[ev.items.length - 1].id; setEvents((e) => [...e, ...ev.items]); }
        if (r.versions.length && r.documents.some((d) => d.status === "extracted")) setCmp(await api<Comparison>(`/requests/${id}/comparison`));
        const sig = JSON.stringify([r.status, r.documents.map((d) => d.status), r.approvals.map((a) => a.status), r.payments.map((p) => p.state), ev.items.length]);
        if (sig !== signature.current) { signature.current = sig; lastChange.current = Date.now(); setStalled(false); }
      } catch (e) {
        if (alive) setLoadError(errorText(e));
      }
      if (!alive) return;
      const busyNow = document.visibilityState === "visible";
      timer = setTimeout(tick, busyNow ? 1500 : 6000);
    }
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);

  useEffect(() => {
    const t = setInterval(() => setStalled(working && Date.now() - lastChange.current > STALL_MS), 5000);
    return () => clearInterval(t);
  }, [working]);

  useEffect(() => { if (req?.draft?.spec && !req.versions.length && !edit) setEdit(req.draft.spec); }, [req, edit]);

  // Sample shortcut: after confirmation, add the labelled sample quotes once (the server de-duplicates by file hash).
  useEffect(() => {
    if (sample && req && req.versions.length && !req.documents.length && !autoLoaded.current) {
      autoLoaded.current = true;
      post(`/requests/${id}/sample-quotes`).catch((e) => toast.error(errorText(e)));
    }
  }, [sample, req, id]);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    try { await fn(); lastChange.current = Date.now(); } catch (e) { toast.error(errorText(e)); } finally { setBusy(null); }
  }
  const confirm = () => act("confirm", () => post(`/requests/${id}/confirm`, { requirements: { ...edit, deadline_date: null }, expected_version: 0 }));
  const retry = () => act("retry", async () => { await post(`/requests/${id}/analyze`); setStalled(false); lastChange.current = Date.now(); toast.message("Analysis re-queued — existing documents are reused, nothing is duplicated."); });
  const upload = (files: File[]) => act("upload", async () => { for (const f of files) { const fd = new FormData(); fd.append("file", f); await api(`/requests/${id}/documents`, { form: fd }); } });

  if (loadError && !req) return <div><Header /><Callout tone="bad" title="This request could not be loaded">{loadError} <Link to="/agent" className="underline">Start a new run</Link></Callout></div>;
  if (!req) return <div><Header /><Card className="p-8"><Loader2 className="size-5 animate-spin text-teal" aria-label="Loading" /></Card></div>;
  const s = cmp?.summary;
  const evidenceCount = cmp?.quotes.reduce((n, q) => n + q.evidence.length, 0) ?? 0;
  const bboxCount = cmp?.quotes.reduce((n, q) => n + q.evidence.filter((e) => e.location === "bbox").length, 0) ?? 0;

  return (
    <div>
      <Header />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-[13px]">
        <Badge tone="info" icon={<Sparkles className="size-3" aria-hidden />}>Live run on real services</Badge>
        <span className="text-muted">Request “{req.title}” · resumable at this URL</span>
        <Link to={`/requests/${id}`} className="ml-auto font-medium text-teal hover:underline">Open step by step →</Link>
      </div>
      {stalled && (
        <div className="mb-4"><Callout tone="warn" icon={<AlertTriangle className="size-4" aria-hidden />} title="This is taking longer than expected">
          <div className="flex flex-wrap items-center justify-between gap-3"><span>No progress for 2 minutes — the model or worker may be slow. Retrying re-queues analysis for the same documents.</span><Button size="sm" loading={busy === "retry"} onClick={retry} icon={<RefreshCcw className="size-3.5" aria-hidden />}>Retry analysis</Button></div>
        </Callout></div>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <Card className="relative overflow-hidden border-0 bg-ink p-6 text-white md:p-8">
          <div className="pointer-events-none absolute -right-28 -top-28 size-96 rounded-full bg-teal-bright/10 blur-3xl" />
          <ol className="relative grid gap-0">
            {stages.map((n, i) => {
              const Icon = n.icon;
              const st = n.state;
              return (
                <li key={n.key} className="relative flex gap-4 pb-6 last:pb-0" data-stage={n.key} data-state={st}>
                  {i < stages.length - 1 && <span className={cx("absolute left-[19px] top-11 h-[calc(100%-36px)] w-0.5 transition-colors duration-700", st === "done" ? "bg-teal-bright" : "bg-white/10")} aria-hidden />}
                  <span className={cx("relative z-10 grid size-10 shrink-0 place-items-center rounded-xl transition-all duration-500",
                    st === "done" ? "bg-teal-bright text-navy-900" : st === "active" ? "bg-white text-ink pulse-ring" : st === "gate" ? "bg-amber-400 text-navy-900 pulse-ring" : st === "review" ? "bg-amber-200 text-navy-900" : st === "error" ? "bg-danger text-white" : "bg-white/8 text-white/40")}>
                    {st === "done" ? <Check className="size-5" aria-hidden /> : st === "active" ? <Loader2 className="size-5 animate-spin" aria-hidden /> : st === "gate" ? <Hand className="size-5" aria-hidden /> : st === "error" ? <X className="size-5" aria-hidden /> : st === "review" ? <AlertTriangle className="size-5" aria-hidden /> : <Icon className="size-5" aria-hidden />}
                  </span>
                  <div className={cx("min-w-0 flex-1 pt-1 transition-opacity duration-500", st === "idle" && "opacity-45")}>
                    <div className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">{n.title}{n.consent && <Badge className="border-amber-300/40! bg-amber-300/15! text-amber-200!">{n.consent}</Badge>}
                      <span className="sr-only">status: {st}</span></div>
                    <p className="text-[13px] text-white/55">{n.sub}</p>
                    {n.note && <p className={cx("mt-1.5 text-[12.5px]", st === "error" ? "text-red-300" : st === "review" ? "text-amber-200" : "text-white/75")}>{n.note}</p>}

                    {n.key === "understand" && req.draft?.spec && (
                      <div className="mt-2 flex flex-wrap gap-1.5 text-[12px]">
                        {[`${req.draft.spec.quantity} units`, req.draft.spec.item, `${money(req.draft.spec.budget_amount, req.draft.spec.currency)} incl. shipping & tax`, req.draft.spec.deadline_date ? `by ${dateOnly(req.draft.spec.deadline_date)}` : null, ...req.draft.spec.mandatory.map((m: any) => m.label)].filter(Boolean).map((t, k) => (
                          <span key={k} className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5">{t}</span>
                        ))}
                      </div>
                    )}
                    {n.key === "confirm" && st === "gate" && edit && (
                      <div className="mt-3 rounded-xl border border-amber-300/30 bg-white/5 p-3">
                        <div className="grid gap-2 sm:grid-cols-3">
                          <label className="text-[12px] text-white/70">Quantity<input type="number" min={1} className={inputCls + " mt-1 bg-white/90 text-ink"} value={edit.quantity} onChange={(e) => setEdit({ ...edit, quantity: Number(e.target.value) })} /></label>
                          <label className="text-[12px] text-white/70">Budget ({edit.currency})<input inputMode="decimal" className={inputCls + " mt-1 bg-white/90 text-ink"} value={edit.budget_amount} onChange={(e) => setEdit({ ...edit, budget_amount: e.target.value })} /></label>
                          <label className="text-[12px] text-white/70">Deliver within (days)<input type="number" min={0} className={inputCls + " mt-1 bg-white/90 text-ink"} value={edit.deadline_days ?? ""} onChange={(e) => setEdit({ ...edit, deadline_days: e.target.value === "" ? null : Number(e.target.value) })} /></label>
                        </div>
                        <Button className="mt-3 bg-amber-400! text-navy-900! hover:bg-amber-300!" loading={busy === "confirm"} onClick={confirm} icon={<UserCheck className="size-4" aria-hidden />}>Confirm requirements & continue</Button>
                      </div>
                    )}
                    {n.key === "gather" && st === "gate" && !sample && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <input ref={fileRef} type="file" accept="application/pdf" multiple className="hidden" onChange={(e) => { const f = [...(e.target.files ?? [])]; if (f.length) upload(f); e.target.value = ""; }} />
                        <Button className="bg-amber-400! text-navy-900! hover:bg-amber-300!" loading={busy === "upload"} onClick={() => fileRef.current?.click()} icon={<FileUp className="size-4" aria-hidden />}>Upload supplier PDFs</Button>
                        <Button variant="ghost" className="border border-white/20 text-white! hover:bg-white/10!" loading={busy === "samples"} onClick={() => act("samples", () => post(`/requests/${id}/sample-quotes`))}>Use 3 sample quotes</Button>
                      </div>
                    )}
                    {n.key === "read" && req.documents.length > 0 && (
                      <div className="mt-2 grid gap-1">
                        {req.documents.map((d) => (
                          <div key={d.id} className="flex items-center gap-2 text-[12.5px] text-white/75">
                            {d.status === "extracted" ? <Check className="size-3.5 text-teal-bright" aria-hidden /> : d.status === "failed" || d.status === "needs_ocr" ? <X className="size-3.5 text-red-300" aria-hidden /> : <Loader2 className="size-3.5 animate-spin" aria-hidden />}
                            {d.filename.replace("_quote_DEMO.pdf", "").replaceAll("_", " ")}
                          </div>
                        ))}
                        {(st === "error" || st === "review") && <Button size="sm" variant="ghost" className="mt-1 w-fit border border-white/20 text-white! hover:bg-white/10!" loading={busy === "retry"} onClick={retry} icon={<RefreshCcw className="size-3.5" aria-hidden />}>Retry analysis</Button>}
                      </div>
                    )}
                    {n.key === "verify" && cmp && (st === "done" || st === "review") && (
                      <p className="mt-2 text-[12.5px] text-white/75"><b className="text-white">{evidenceCount}</b> terms cited · <b className="text-white">{bboxCount}</b> pinned to page coordinates</p>
                    )}
                    {n.key === "decide" && s?.best_compliant_supplier && (
                      <div className="mt-2 rounded-xl border border-white/10 bg-white/5 p-3 text-[13px]">
                        Recommend <b className="text-teal-bright">{s.best_compliant_supplier}</b> at <b>{money(s.best_compliant_total)}</b>.
                        {s.why_cheapest_loses && <div className="mt-1 text-white/65">Cheapest ({s.why_cheapest_loses.supplier}) rejected: {s.why_cheapest_loses.blocking_checks.map((c: any) => c.label).join(", ")}.</div>}
                      </div>
                    )}
                    {n.key === "approve" && st === "gate" && s?.best_compliant_quote_id && (
                      <Button className="mt-3 bg-amber-400! text-navy-900! hover:bg-amber-300!" onClick={() => nav(`/requests/${id}/approve?quote=${s.best_compliant_quote_id}`)} icon={<ArrowRight className="size-4" aria-hidden />}>Review & approve the exact purchase</Button>
                    )}
                    {n.key === "buyer" && st === "gate" && (
                      <Button className="mt-3 bg-amber-400! text-navy-900! hover:bg-amber-300!" onClick={() => nav(`/requests/${id}/pay`)} icon={<CreditCard className="size-4" aria-hidden />}>Open PayPal checkout</Button>
                    )}
                    {n.key === "paid" && st === "done" && <Link to={`/requests/${id}/receipt`} className="mt-2 inline-block text-[13px] font-medium text-teal-bright hover:underline">Open receipt & evidence package →</Link>}
                    {n.key === "buyer" && st === "idle" && <p className="mt-1 flex items-center gap-1.5 text-[12px] text-white/45"><Lock className="size-3" aria-hidden />Unreachable for the agent — only an approved snapshot can create a PayPal order.</p>}
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>

        <div className="grid content-start gap-4">
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between"><h2 className="text-[15px] font-semibold">Live agent log</h2><span className="text-[11.5px] text-muted">recorded events, not model reasoning</span></div>
            <ol className="grid max-h-[460px] gap-2 overflow-y-auto pr-1" aria-live="polite">
              {events.length === 0 && <li className="text-sm text-muted">Waiting for the first event…</li>}
              {[...events].reverse().map((e) => (
                <li key={e.id} className={cx("animate-in rounded-lg border px-3 py-2", e.status === "blocked" || e.status === "failed" ? "border-danger-line bg-danger-soft/50" : e.status === "warning" ? "border-amber-line bg-amber-soft/40" : "border-line")}>
                  <div className="flex items-center justify-between gap-2 text-[13px] font-medium text-ink"><span className="truncate">{e.title}</span><span className="shrink-0 text-[11px] text-muted">{e.tool ?? e.actor}</span></div>
                  {e.detail && <p className="mt-0.5 line-clamp-2 text-[12px] text-ink-2">{e.detail}</p>}
                </li>
              ))}
            </ol>
          </Card>
          <Guardrails />
        </div>
      </div>
    </div>
  );
}
