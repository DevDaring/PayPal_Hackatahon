import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from "ag-grid-community";
import { ArrowRight, Award, Bot, CircleHelp, CreditCard, Info, Scale, SlidersHorizontal, TrendingDown, XCircle } from "lucide-react";
import { api, errorText } from "../lib/api";
import { dateOnly, money } from "../lib/format";
import { useRoles } from "../lib/session";
import type { CompareQuote, Comparison, RequestDetail } from "../lib/types";
import { openFieldTarget } from "./EvidenceStep";
import type { EvidenceTarget } from "./EvidenceViewer";
import { Badge, Button, Callout, Card, CheckBadge, cx, Empty, SectionTitle } from "./ui";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeQuartz.withParams({
  fontFamily: "Inter Variable, ui-sans-serif, system-ui",
  fontSize: 13.5,
  headerFontSize: 12,
  headerFontWeight: 600,
  headerTextColor: "#66708a",
  headerBackgroundColor: "#f5f1ea",
  foregroundColor: "#0f2541",
  backgroundColor: "#ffffff",
  borderColor: "#e8e1d5",
  rowBorder: { color: "#efe9df" },
  accentColor: "#0f766e",
  rowHoverColor: "#faf7f1",
  selectedRowBackgroundColor: "#e2f2ee",
  wrapperBorderRadius: 16,
  rowHeight: 58,
  headerHeight: 42,
  cellHorizontalPadding: 14,
});

type Row = CompareQuote & { rec: boolean };
const checkFor = (q: CompareQuote, key: string) => q.outcome.checks.find((c) => c.key === key);
const tone = (s?: string) => (s === "pass" ? "text-teal-strong" : s === "fail" ? "text-danger" : s === "unknown" ? "text-amber" : "text-ink");

function ValueCell({ q, field, value, status, sub }: { q: CompareQuote; field: string; value: string | null; status?: string; sub?: string | null }) {
  const ev = q.evidence.find((e) => e.field === field);
  return (
    <div className="flex h-full flex-col justify-center leading-tight">
      <span className={cx("tnum font-medium", value == null ? "text-amber" : tone(status))}>
        {value ?? "Not stated"}
        {status === "fail" && <XCircle className="ml-1 inline size-3.5" aria-label="fails requirement" />}
        {value == null && <CircleHelp className="ml-1 inline size-3.5" aria-label="unknown" />}
      </span>
      <span className="text-[11px] text-muted">{sub ?? (ev ? (ev.location === "bbox" ? `p${ev.page} · source linked` : ev.location === "correction" ? "corrected" : `p${ev.page} · text match`) : value == null ? "no evidence" : "")}</span>
    </div>
  );
}

export function CompareStep({ req, cmp, onOpen }: { req: RequestDetail; cmp: Comparison; onOpen: (t: EvidenceTarget) => void }) {
  const nav = useNavigate();
  const s = cmp.summary;
  const spec = cmp.request_version?.requirements;
  const rows: Row[] = useMemo(() => [...cmp.quotes].sort((a, b) => (a.outcome.compliant_rank ?? 99) - (b.outcome.compliant_rank ?? 99) || Number(a.outcome.verified_total ?? 1e9) - Number(b.outcome.verified_total ?? 1e9))
    .map((q) => ({ ...q, rec: q.quote_id === s?.best_compliant_quote_id })), [cmp, s]);

  const cols: ColDef<Row>[] = useMemo(() => [
    {
      headerName: "Supplier", field: "supplier", pinned: "left", minWidth: 190, flex: 1.3,
      cellRenderer: (p: ICellRendererParams<Row>) => (
        <div className="flex h-full items-center gap-2">
          {p.data!.rec ? <Award className="size-4 shrink-0 text-teal" aria-label="Recommended" /> : <span className="size-4" />}
          <div className="min-w-0 leading-tight"><div className="truncate font-semibold">{p.data!.supplier}</div><div className="text-[11px] text-muted">quote v{p.data!.version.version}{p.data!.outcome.compliant_rank ? ` · rank ${p.data!.outcome.compliant_rank}` : ""}</div></div>
        </div>
      ),
    },
    { headerName: "Checks", minWidth: 112, cellRenderer: (p: ICellRendererParams<Row>) => <div className="flex h-full items-center"><CheckBadge status={p.data!.outcome.mandatory_status} label={{ pass: "All pass", fail: "Fails", unknown: "Unknown" }[p.data!.outcome.mandatory_status]} /></div> },
    {
      headerName: "Verified total", minWidth: 128, comparator: (a, b) => Number(a ?? 1e9) - Number(b ?? 1e9), valueGetter: (p) => p.data!.outcome.verified_total,
      cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field="total" value={money(p.data!.outcome.verified_total, p.data!.version.currency)} status={checkFor(p.data!, "budget")?.status} sub={p.data!.outcome.verified_total ? (checkFor(p.data!, "budget")?.status === "fail" ? "over budget" : "within budget") : p.data!.version.stated_total ? `stated ${money(p.data!.version.stated_total, p.data!.version.currency)} · unverified` : "cannot verify"} />,
    },
    { headerName: "Items", minWidth: 96, cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field="subtotal" value={money(p.data!.version.subtotal, p.data!.version.currency)} /> },
    {
      headerName: "Shipping", minWidth: 118,
      cellRenderer: (p: ICellRendererParams<Row>) => {
        const v = p.data!.version;
        const pushesOver = checkFor(p.data!, "budget")?.status === "fail" && v.shipping != null && v.computed_total != null && spec && Number(v.computed_total) - Number(v.shipping) <= Number(spec.budget_amount);
        return <ValueCell q={p.data!} field="shipping" value={money(v.shipping, v.currency)} status={pushesOver ? "fail" : undefined} sub={pushesOver ? "pushes total over budget" : null} />;
      },
    },
    { headerName: "Tax", minWidth: 80, cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field="tax" value={money(p.data!.version.tax, p.data!.version.currency)} /> },
    { headerName: "Delivery (claim)", minWidth: 124, cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field="delivery_days" value={p.data!.version.delivery_days != null ? `${p.data!.version.delivery_days} days` : null} status={checkFor(p.data!, "delivery")?.status} sub={p.data!.outcome.estimated_delivery ? `≈ ${dateOnly(p.data!.outcome.estimated_delivery)}` : null} /> },
    ...((spec?.mandatory ?? []).map((c) => ({
      headerName: c.key === "connector" ? "Connector" : c.key === "microphone" ? "Mic" : c.label, minWidth: 100,
      cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field={`attr:${c.key}`} value={p.data!.version.attributes[c.key] ?? null} status={checkFor(p.data!, `attr:${c.key}`)?.status} />,
    })) as ColDef<Row>[]),
    { headerName: "Valid until", minWidth: 108, cellRenderer: (p: ICellRendererParams<Row>) => <ValueCell q={p.data!} field="valid_until" value={p.data!.version.valid_until ? dateOnly(p.data!.version.valid_until) : null} status={checkFor(p.data!, "validity")?.status} /> },
    {
      headerName: "Checkout", minWidth: 132,
      cellRenderer: (p: ICellRendererParams<Row>) => (
        <div className="flex h-full items-center" title={p.data!.checkout_reason}>
          {p.data!.outcome.checkout_available ? <Badge tone="good" icon={<CreditCard className="size-3" aria-hidden />}>{p.data!.merchant?.adapter === "sandbox" ? "PayPal Sandbox" : "Simulated (lab)"}</Badge> : <Badge tone="neutral">Not configured</Badge>}
        </div>
      ),
    },
  ], [spec]);

  const fieldForCol: Record<string, string> = { "Verified total": "total", Items: "subtotal", Shipping: "shipping", Tax: "tax", "Delivery (claim)": "delivery_days", Connector: "attr:connector", Mic: "attr:microphone", "Valid until": "valid_until", Supplier: "supplier_name" };

  if (cmp.quotes.length === 0) return <Card><Empty title="No extracted quotes yet" body="Upload or load sample quotes on the previous step." /></Card>;

  const best = rows.find((r) => r.rec);
  return (
    <div className="grid gap-6">
      <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
        <RecommendationCard cmp={cmp} best={best} onOpen={onOpen} onApprove={(qid) => nav(`/requests/${req.id}/approve?quote=${qid}`)} />
        <div className="grid content-start gap-4">
          {s?.why_cheapest_loses && (
            <Card className="p-5">
              <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-danger"><TrendingDown className="size-4" aria-hidden />Why the cheapest quote loses</div>
              <p className="mt-2 font-display text-[22px] leading-snug text-ink">{s.why_cheapest_loses.supplier} looks cheapest, but:</p>
              <ul className="mt-2 grid gap-1.5">
                {s.why_cheapest_loses.blocking_checks.map((c: any) => (
                  <li key={c.key} className="flex gap-2 text-[13.5px]"><CheckBadge status={c.status} label={c.label} /><span className="text-ink-2">{c.detail}</span></li>
                ))}
              </ul>
            </Card>
          )}
          {s?.unknowns?.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-amber"><CircleHelp className="size-4" aria-hidden />Unknowns — ask the supplier</div>
              <ul className="mt-2 grid gap-1.5 text-[13px] text-ink-2">{s.unknowns.slice(0, 6).map((u: any, i: number) => <li key={i}><b className="text-ink">{u.supplier}:</b> {u.check.detail}</li>)}</ul>
            </Card>
          )}
        </div>
      </div>

      <div>
        <SectionTitle hint="Deterministic policy · lowest verified total, then fastest delivery · click a cell for its source" right={<Badge tone="neutral" icon={<Scale className="size-3" aria-hidden />}>policy v{cmp.policy.version}</Badge>}>Comparison grid</SectionTitle>
        <div className="overflow-hidden rounded-2xl border border-line shadow-[var(--shadow-card)]">
          <AgGridReact<Row> theme={gridTheme} rowData={rows} columnDefs={cols} domLayout="autoHeight" suppressCellFocus={false} ensureDomOrder
            defaultColDef={{ sortable: false, resizable: true, suppressMovable: true, flex: 1 }}
            getRowStyle={(p) => (p.data?.rec ? { background: "#f2faf8" } : undefined)}
            onCellClicked={(e) => { const f = fieldForCol[e.colDef.headerName ?? ""]; if (f && e.data) onOpen(openFieldTarget(e.data, f)); }}
            onCellKeyDown={(e: any) => { if (e.event?.key === "Enter") { const f = fieldForCol[e.colDef.headerName ?? ""]; if (f && e.data) onOpen(openFieldTarget(e.data, f)); } }} />
        </div>
        <p className="mt-2 text-[12px] text-muted">Delivery times are supplier claims, not verified fulfilment. Tax values in sample quotes are synthetic fixture terms. “Checkout” is shown separately so integration availability never changes the compliance ranking.</p>
      </div>

      <WhatIf req={req} cmp={cmp} />
    </div>
  );
}

function RecommendationCard({ cmp, best, onOpen, onApprove }: { cmp: Comparison; best?: Row; onOpen: (t: EvidenceTarget) => void; onApprove: (qid: string) => void }) {
  const ex = cmp.explanation;
  const s = cmp.summary;
  const openKey = (k: string) => {
    const e = ex?.evidence?.[k];
    const q = cmp.quotes.find((x) => x.quote_id === e?.quote_id);
    if (e && q) onOpen(openFieldTarget(q, e.field));
  };
  const withCites = (text: string) => text.split(/(\[E\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(E\d+)\]$/);
    return m && ex?.evidence?.[m[1]] ? (
      <button key={i} onClick={() => openKey(m[1])} className="mx-0.5 rounded bg-teal-soft px-1 py-px align-baseline text-[11px] font-semibold text-teal-strong hover:bg-teal hover:text-white" aria-label={`Open evidence ${m[1]}`}>{m[1]}</button>
    ) : <span key={i}>{part}</span>;
  });
  return (
    <Card className="relative overflow-hidden p-6">
      <div className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-teal-soft blur-2xl" />
      <div className="relative">
        {best ? (
          <>
            <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-teal"><Award className="size-4" aria-hidden />Best compliant quote</div>
            <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-1">
              <h3 className="font-display text-[40px] leading-none text-ink">{best.supplier}</h3>
              <span className="font-display text-[40px] leading-none tnum text-teal-strong">{money(best.outcome.verified_total, best.version.currency)}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {best.outcome.checks.map((c) => <CheckBadge key={c.key} status={c.status} label={c.label} />)}
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-amber"><CircleHelp className="size-4" aria-hidden />No recommendation</div>
            <h3 className="mt-2 font-display text-[34px] leading-tight text-ink">No quote passes every mandatory requirement.</h3>
            <p className="mt-1 text-sm text-muted">QuoteGuard never forces a recommendation. Resolve unknowns with suppliers or adjust requirements.</p>
          </>
        )}
        {ex ? (
          <div className="mt-5 rounded-xl border border-line bg-sunken/60 p-4">
            <div className="mb-1.5 flex items-center gap-2 text-[12px] text-muted"><Bot className="size-3.5" aria-hidden />{ex.method === "llm" ? <>Plain-English summary by <b>{ex.model}</b></> : "Template summary"}</div>
            <div className="grid gap-2 text-[14px] leading-relaxed text-ink-2">{(ex.paragraphs ?? []).map((p: string, i: number) => <p key={i}>{withCites(p)}</p>)}</div>
            <p className="mt-2 flex items-start gap-1.5 text-[11.5px] text-muted"><Info className="mt-0.5 size-3 shrink-0" aria-hidden />{ex.disclaimer}</p>
          </div>
        ) : <div className="mt-5 skeleton h-24" />}
        {best && (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button size="lg" disabled={!best.outcome.payment_eligible} onClick={() => onApprove(best.quote_id)} icon={<ArrowRight className="size-4" aria-hidden />}>Review exact purchase for approval</Button>
            {!s?.best_has_checkout && <span className="text-[13px] text-amber">Checkout is not configured for this supplier.</span>}
          </div>
        )}
      </div>
    </Card>
  );
}

function WhatIf({ req, cmp }: { req: RequestDetail; cmp: Comparison }) {
  const spec = cmp.request_version!.requirements;
  const qc = useQueryClient();
  const { isRequester } = useRoles();
  const [budget, setBudget] = useState(Number(spec.budget_amount));
  const [days, setDays] = useState(spec.deadline_days ?? 7);
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const changed = budget !== Number(spec.budget_amount) || days !== (spec.deadline_days ?? 7);
  useEffect(() => { setBudget(Number(spec.budget_amount)); setDays(spec.deadline_days ?? 7); setRes(null); }, [cmp.request_version?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!changed) { setRes(null); return; }
    const ac = new AbortController();
    const t = setTimeout(async () => {
      setLoading(true);
      try { setRes(await api(`/requests/${req.id}/whatif`, { body: { budget: budget.toFixed(2), deadline_days: days }, signal: ac.signal })); } catch (e) { if ((e as Error).name !== "AbortError") toast.error(errorText(e)); } finally { setLoading(false); }
    }, 250);
    return () => { clearTimeout(t); ac.abort(); };
  }, [budget, days]); // eslint-disable-line react-hooks/exhaustive-deps
  const apply = useMutation({
    mutationFn: () => api(`/requests/${req.id}/whatif/apply`, { body: { budget: budget.toFixed(2), deadline_days: days } }),
    onSuccess: () => { toast.success("Applied as a new requirements version — checks re-run, prior approvals invalidated"); qc.invalidateQueries(); },
    onError: (e) => toast.error(errorText(e)),
  });
  const before = new Map(cmp.quotes.map((q) => [q.quote_id, q.outcome.mandatory_status]));
  return (
    <Card className="p-5 md:p-6">
      <SectionTitle hint="Previews recompute from existing evidence. Nothing here reaches payment unless applied as a new version." right={<Badge tone="info" icon={<SlidersHorizontal className="size-3" aria-hidden />}>Preview only</Badge>}>What-if explorer</SectionTitle>
      <div className="grid gap-6 md:grid-cols-[1fr_1.3fr]">
        <div className="grid gap-5">
          <label className="block">
            <div className="flex justify-between text-[13px]"><span className="font-medium text-ink-2">Budget</span><span className="tnum font-semibold text-ink">{money(budget.toFixed(2), spec.currency)}</span></div>
            <input type="range" min={400} max={900} step={10} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="mt-2 w-full accent-teal" aria-label="Budget" />
            <div className="flex justify-between text-[11px] text-muted"><span>$400</span><span>confirmed {money(spec.budget_amount, spec.currency)}</span><span>$900</span></div>
          </label>
          <label className="block">
            <div className="flex justify-between text-[13px]"><span className="font-medium text-ink-2">Delivery window</span><span className="tnum font-semibold text-ink">{days} days</span></div>
            <input type="range" min={1} max={21} value={days} onChange={(e) => setDays(Number(e.target.value))} className="mt-2 w-full accent-teal" aria-label="Delivery window in days" />
            <div className="flex justify-between text-[11px] text-muted"><span>1</span><span>confirmed {spec.deadline_days} days</span><span>21</span></div>
          </label>
          <div className="flex flex-wrap gap-2">
            {[560, 600, 650].map((b) => <button key={b} onClick={() => setBudget(b)} className={cx("rounded-full border px-3 py-1 text-[12.5px]", budget === b ? "border-teal bg-teal-soft text-teal-strong" : "border-line-strong hover:bg-sunken")}>${b}</button>)}
            <button onClick={() => { setBudget(Number(spec.budget_amount)); setDays(spec.deadline_days ?? 7); }} className="rounded-full px-3 py-1 text-[12.5px] text-muted hover:bg-sunken">Reset</button>
          </div>
          <p className="text-[12px] text-muted">Quantity changes need a revised quote unless the supplier's pricing terms explicitly say the unit price applies.</p>
        </div>
        <div aria-live="polite">
          {!changed ? <div className="grid h-full place-items-center rounded-xl border border-dashed border-line-strong p-6 text-center text-sm text-muted">Move a slider to preview how eligibility would change.</div> : !res ? <div className="skeleton h-40" /> : (
            <div className={cx("grid gap-3 transition-opacity", loading && "opacity-60")}>
              {res.changes.length ? res.changes.map((c: any) => (
                <div key={c.quote_id} className="rounded-xl border border-teal/25 bg-teal-soft/60 px-4 py-3 text-[14px] text-ink"><b>Δ</b> {c.sentence}</div>
              )) : <div className="rounded-xl bg-sunken px-4 py-3 text-[14px] text-ink-2">No supplier changes compliance status.</div>}
              {res.notes.map((n: string, i: number) => <Callout key={i} tone={n.startsWith("No quote") ? "warn" : "info"}>{n}</Callout>)}
              <ul className="grid gap-1.5">
                {res.outcomes.map((o: any) => (
                  <li key={o.quote_id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-[13px]">
                    <span className="font-medium">{o.supplier}{o.compliant_rank === 1 && <Award className="ml-1 inline size-3.5 text-teal" aria-label="best" />}</span>
                    <span className="flex items-center gap-1.5"><CheckBadge status={before.get(o.quote_id) as any} /> <ArrowRight className="size-3 text-muted" aria-hidden /> <CheckBadge status={o.mandatory_status} /></span>
                  </li>
                ))}
              </ul>
              <div className="flex justify-end"><Button variant="secondary" loading={apply.isPending} disabled={!isRequester} onClick={() => apply.mutate()}>Apply as requirements v{(cmp.request_version?.version ?? 0) + 1}</Button></div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
