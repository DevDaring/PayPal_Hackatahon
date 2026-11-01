import { useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BarChart3, Download, Play, Search, ShieldAlert } from "lucide-react";
import { api, errorText } from "../lib/api";
import { csvSafe } from "../components/CompareStep";
import { dateTime, FIELD_LABEL } from "../lib/format";
import { useRoles } from "../lib/session";
import { Badge, Button, Callout, Card, cx, Empty, PageHeader, SectionTitle, Skeleton, Stat } from "../components/ui";

const pct = (r: number | null | undefined) => (r == null ? "—" : `${Math.round(r * 1000) / 10}%`);

export default function Evaluation() {
  const qc = useQueryClient();
  const { isAdmin } = useRoles();
  const runs = useQuery<any>({ queryKey: ["eval-runs"], queryFn: () => api("/evaluation/runs"), refetchInterval: (q) => (q.state.data?.items?.some((r: any) => r.status === "running") ? 3000 : false) });
  const [dataset, setDataset] = useState("quoteguard-holdout-v1");
  const [sel, setSel] = useState<string | null>(null);
  const dsRuns = (runs.data?.items ?? []).filter((r: any) => r.dataset_version === dataset);
  const runId = sel && dsRuns.some((r: any) => r.id === sel) ? sel : dsRuns.find((r: any) => r.status === "finished" && r.extraction_mode === "llm")?.id ?? dsRuns.find((r: any) => r.status === "finished")?.id;
  const detail = useQuery<any>({ queryKey: ["eval-run", runId], queryFn: () => api(`/evaluation/runs/${runId}`), enabled: !!runId });
  const start = useMutation({ mutationFn: (mode: string) => api("/evaluation/runs", { body: { mode, dataset } }), onSuccess: () => { toast.message("Evaluation started"); qc.invalidateQueries({ queryKey: ["eval-runs"] }); }, onError: (e) => toast.error(errorText(e)) });
  const d = detail.data;
  const s = d?.summary;
  return (
    <div>
      <PageHeader eyebrow="Evaluation" title="Measured, not claimed" subtitle="Labelled synthetic quotations. Expected labels live in a separate manifest the model never sees; every run is kept, including the bad ones."
        actions={isAdmin ? <><Button variant="secondary" loading={start.isPending && start.variables === "rules"} onClick={() => start.mutate("rules")}>Run deterministic baseline</Button><Button loading={start.isPending && start.variables === "llm"} onClick={() => start.mutate("llm")} icon={<Play className="size-4" aria-hidden />}>Run with AI model</Button></> : undefined} />
      <IntegrityBench />
      <ResearchCard />
      <h2 className="mb-3 mt-8 font-display text-[28px] text-ink">Quote extraction: rules vs. AI</h2>
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Dataset">
        {[["quoteguard-holdout-v1", "Holdout · unfamiliar layouts (26)", "Built independently; labels frozen before any run"], ["quoteguard-eval-v1", "Development set (24)", "Template family the parser was written against"]].map(([k, l, h]) => (
          <button key={k} role="tab" aria-selected={dataset === k} onClick={() => { setDataset(k); setSel(null); }} className={cx("rounded-xl border px-4 py-2 text-left", dataset === k ? "border-ink bg-ink text-white" : "border-line-strong bg-surface hover:bg-sunken")}>
            <div className="text-[13.5px] font-semibold">{l}</div><div className={cx("text-[11.5px]", dataset === k ? "text-white/65" : "text-muted")}>{h}</div>
          </button>
        ))}
      </div>
      <RulesVsAi runs={dsRuns} />
      {dsRuns.length ? (
        <div className="mb-5 flex flex-wrap gap-2">
          {dsRuns.map((r: any) => (
            <button key={r.id} onClick={() => setSel(r.id)} className={cx("rounded-xl border px-3 py-2 text-left text-[12.5px]", r.id === runId ? "border-ink bg-ink text-white" : "border-line-strong bg-surface hover:bg-sunken")}>
              <div className="font-semibold">{r.extraction_mode === "llm" ? r.model : "deterministic rules"}</div>
              <div className="opacity-70">{r.status === "running" ? "running…" : dateTime(r.finished_at)}</div>
            </button>
          ))}
        </div>
      ) : null}
      {!runs.data ? <Skeleton className="h-64" /> : !runId ? <Card><Empty title="No finished evaluation runs yet" body="Run the evaluation to store real measurements. Nothing is pre-filled." /></Card> : !d ? <Skeleton className="h-64" /> : (
        <div className="grid gap-6">
          <Card className="p-5">
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-[13px]">
              <div><span className="text-muted">Dataset</span> <b>{d.dataset_version}</b></div>
              <div><span className="text-muted">Mode</span> <b>{d.extraction_mode}</b></div>
              <div><span className="text-muted">Provider / model</span> <b>{d.provider} · {d.model}</b></div>
              <div><span className="text-muted">Run</span> <b>{dateTime(d.finished_at)}</b></div>
              <div><span className="text-muted">Code revision</span> <b>{d.code_revision ?? "not recorded"}</b></div>
              <div><span className="text-muted">Scenario clock</span> <b>{d.config.scenario_date}</b></div>
            </div>
          </Card>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Decision agreement" value={pct(s.decision_agreement.rate)} hint={`${s.decision_agreement.agree}/${s.decision_agreement.total} cases match the labelled pass/fail/unknown`} tone="teal" icon={<BarChart3 className="size-4" aria-hidden />} />
            <Stat label="Non-payable cases rejected by policy" value={`${s.unsafe_payment_attempts.blocked}/${s.unsafe_payment_attempts.total}`} hint="Policy-level result (no PayPal call per case). Payment-boundary behaviour is covered by the backend test suite." tone="teal" />
            <Stat label="False blocking" value={`${s.false_blocking.blocked}/${s.false_blocking.total}`} hint="Payable cases that were wrongly blocked" tone={s.false_blocking.blocked ? "amber" : "navy"} />
            <Stat label="Evidence references valid" value={pct(s.evidence.rate)} hint={`${s.evidence.correct}/${s.evidence.checked} cited lines found on the cited page`} />
          </div>
          <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
            <Card className="p-5">
              <SectionTitle hint="Exact match after normalisation; missing values count as correct only when the label is also missing">Field accuracy</SectionTitle>
              <ul className="grid gap-2.5">
                {Object.entries(s.field_accuracy).map(([f, v]: any) => (
                  <li key={f}>
                    <div className="flex justify-between text-[13px]"><span>{FIELD_LABEL[f] ?? f}</span><span className="tnum font-semibold">{v.correct}/{v.total} · {pct(v.accuracy)}</span></div>
                    <div className="mt-1 h-2 rounded-full bg-sunken"><div className={cx("h-2 rounded-full", v.accuracy >= 0.95 ? "bg-teal" : v.accuracy >= 0.8 ? "bg-teal-bright" : "bg-amber")} style={{ width: `${(v.accuracy ?? 0) * 100}%` }} /></div>
                  </li>
                ))}
              </ul>
            </Card>
            <Card className="p-5">
              <SectionTitle hint={`${s.latency_ms.count} samples · median ${s.latency_ms.median} ms (individual timings; too few samples for percentiles)`}>Extraction + decision time</SectionTitle>
              <div className="flex h-36 items-end gap-1" role="img" aria-label="Per-case latency bars">
                {s.latency_ms.samples.map((ms: number, i: number) => { const max = Math.max(...s.latency_ms.samples); return <div key={i} title={`${ms} ms`} className="flex-1 rounded-t bg-ink/80" style={{ height: `${Math.max(4, (ms / max) * 100)}%` }} />; })}
              </div>
              <SectionTitle>By category</SectionTitle>
              <div className="flex flex-wrap gap-2">{Object.entries(s.by_category).map(([k, v]: any) => <Badge key={k} tone={v.agree === v.total ? "good" : "warn"}>{k}: {v.agree}/{v.total}</Badge>)}</div>
            </Card>
          </div>
          <CaseGrid cases={d.cases} runId={d.id} />
          <Callout tone="info" title="Honest limitations">{d.dataset_version.includes("holdout") ? "Synthetic quotes from a separate generator with unfamiliar layouts; labels were committed before the first run. Runs marked “seen” came after fixing defects this set exposed, so only the unseen runs measure generalisation." : "Synthetic documents from one template family; the deterministic baseline was written alongside these templates, so its scores overstate real-world accuracy."} Model confidence is not reported (no calibrated percentages). Checkout is assumed configured in evaluation so extraction and policy are measured in isolation.</Callout>
        </div>
      )}
    </div>
  );
}

ModuleRegistry.registerModules([AllCommunityModule]);
const theme = themeQuartz.withParams({ fontFamily: "Inter Variable, ui-sans-serif", fontSize: 13, headerBackgroundColor: "#f5f1ea", headerTextColor: "#66708a", borderColor: "#e8e1d5", accentColor: "#0f766e", wrapperBorderRadius: 16, rowHoverColor: "#faf7f1" });

function CaseGrid({ cases, runId }: { cases: any[]; runId: string }) {
  const ref = useRef<AgGridReact>(null);
  const [q, setQ] = useState("");
  const rows = useMemo(() => cases.map((c) => {
    const fr = Object.values(c.field_results) as any[];
    return { ...c, fields_ok: fr.filter((x) => x.correct).length, fields_total: fr.length, agree: c.decision_expected === c.decision_actual, wrong_fields: fr.filter((x) => !x.correct).length };
  }), [cases]);
  const cols: ColDef[] = useMemo(() => [
    { field: "case_id", headerName: "Case", minWidth: 200, cellClass: "font-mono text-[12px]", filter: "agTextColumnFilter", pinned: "left" },
    { field: "category", headerName: "Category", filter: "agTextColumnFilter", minWidth: 120 },
    { field: "decision_expected", headerName: "Expected", minWidth: 105 },
    { field: "decision_actual", headerName: "Actual", minWidth: 100, cellClass: (p) => (p.data.agree ? "font-semibold" : "font-semibold text-[#b42318]") },
    { field: "agree", headerName: "Agrees", minWidth: 95, cellRenderer: (p: any) => (p.value ? "✓" : "✗"), headerTooltip: "Decision matches the hidden label" },
    { headerName: "Fields", valueGetter: (p) => `${p.data.fields_ok}/${p.data.fields_total}`, minWidth: 90, comparator: (_a, _b, x, y) => x.data.wrong_fields - y.data.wrong_fields },
    { headerName: "Evidence", valueGetter: (p) => (p.data.evidence_checked ? `${p.data.evidence_correct}/${p.data.evidence_checked}` : "—"), minWidth: 100 },
    { field: "payment_blocked", headerName: "Payment", minWidth: 105, cellDataType: false, valueFormatter: (p) => (p.value ? "blocked" : "eligible") },
    { field: "latency_ms", headerName: "ms", minWidth: 85, filter: "agNumberColumnFilter", type: "numericColumn" },
  ], []);
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter cases…" aria-label="Filter evaluation cases" className="h-9 w-64 rounded-lg border border-line-strong bg-surface pl-8 pr-3 text-sm focus:border-teal focus:outline-none" />
        </label>
        <Button size="sm" variant="secondary" icon={<Download className="size-3.5" aria-hidden />} onClick={() => ref.current?.api.exportDataAsCsv({ fileName: `quoteguard-eval-${runId.slice(0, 8)}.csv`, processCellCallback: (p) => csvSafe(p.value) })}>Export CSV</Button>
      </div>
      <AgGridReact ref={ref} theme={theme} rowData={rows} columnDefs={cols} quickFilterText={q} domLayout="autoHeight" tooltipShowDelay={300}
        defaultColDef={{ sortable: true, resizable: true, flex: 1, floatingFilter: true, filter: true }}
        getRowStyle={(p) => (p.data && !p.data.agree ? { background: "#fdf1d8" } : undefined)} />
    </div>
  );
}

/** Same inputs, same labels: every run in time order, rules and AI side by side (none hidden). */
function RulesVsAi({ runs }: { runs: any[] }) {
  const cols = runs.filter((r) => r.status === "finished" && r.summary).sort((a, b) => a.started_at.localeCompare(b.started_at));
  if (!cols.some((r) => r.extraction_mode === "rules") || !cols.some((r) => r.extraction_mode === "llm")) return null;
  const holdout = cols[0].dataset_version.includes("holdout");
  const frac = (o: any) => `${o.agree ?? o.correct ?? o.blocked ?? o.count ?? o.needs_review}/${o.total ?? o.checked}`;
  const fieldTotals = (s: any) => { const v = Object.values(s.field_accuracy) as any[]; return `${v.reduce((a, x) => a + x.correct, 0)}/${v.reduce((a, x) => a + x.total, 0)}`; };
  const rows: [string, (s: any) => string][] = [
    ["Decisions matching labels", (s) => frac(s.decision_agreement)],
    ["False eligibility (non-payable marked payable)", (s) => `${s.false_eligibility?.count ?? s.unsafe_payment_attempts.total - s.unsafe_payment_attempts.blocked}/${s.unsafe_payment_attempts.total}`],
    ["False blocks (payable marked not payable)", (s) => frac(s.false_blocking)],
    ["Cases needing human review", (s) => (s.review_burden ? frac(s.review_burden) : "—")],
    ["Field accuracy (all fields)", fieldTotals],
    ["Cited lines found on cited page", (s) => frac(s.evidence)],
    ["Median time per document", (s) => `${s.latency_ms.median} ms`],
    ["Model tokens (prompt + completion)", (s) => (s.tokens ? (s.tokens.prompt_tokens + s.tokens.completion_tokens).toLocaleString() : "—")],
  ];
  return (
    <Card className="mb-5 overflow-x-auto p-5">
      <SectionTitle hint={`Same PDFs and frozen labels in every column, oldest run first.${holdout ? " “Unseen” runs happened before any code change prompted by this dataset; “seen” runs came after we fixed what it exposed." : ""}`}>Rules vs AI on these documents</SectionTitle>
      <table className="w-full min-w-[640px]">
        <thead>
          <tr className="text-left align-bottom text-[11.5px] uppercase tracking-wider text-muted">
            <th className="pb-2 font-medium">Measure</th>
            {cols.map((r) => (
              <th key={r.id} className={cx("pb-2 pr-3 font-medium", r.extraction_mode === "llm" && "text-teal-strong")}>
                {r.extraction_mode === "llm" ? "AI + checks" : "Rules"}
                <div className="normal-case tracking-normal">{holdout ? (r.config?.holdout_status ? <Badge tone="warn">seen</Badge> : <Badge tone="good">unseen</Badge>) : <span className="text-[11px]">{dateTime(r.started_at)}</span>}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, f]) => (
            <tr key={label} className="border-t border-line">
              <td className="py-2 pr-3 text-[13px] text-ink-2">{label}</td>
              {cols.map((r) => <td key={r.id} className={cx("py-2 pr-3 text-[13px] tnum", r.extraction_mode === "llm" && "font-semibold text-ink")}>{f(r.summary)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function IntegrityBench() {
  const q = useQuery<any>({ queryKey: ["eval-integrity"], queryFn: () => api("/evaluation/integrity") });
  const r = q.data?.run;
  if (q.isLoading) return <Skeleton className="h-48" />;
  if (!r) return null;
  const s = r.summary;
  const cats = Object.entries(s.by_category as Record<string, any>);
  return (
    <Card className="overflow-hidden" data-testid="integrity-bench">
      <div className="flex flex-wrap items-start gap-4 bg-ink p-5 text-white">
        <span className="grid size-11 place-items-center rounded-xl bg-white/10 text-teal-bright"><ShieldAlert className="size-5" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[12px] font-semibold uppercase tracking-[0.14em] text-teal-bright">Document integrity benchmark · {r.dataset}</div>
          <div className="mt-0.5 font-display text-[26px] leading-tight">Edited bills and staged competition, scored on {s.cases} labelled purchase cases</div>
          <p className="mt-1 max-w-3xl text-[13px] text-white/65">Deterministic forensics ({r.analyzer}); no model involved in the verdict. Attacks are applied to the demo templates and to the 26 independently built holdout layouts. Cases we expected to miss are included and reported.</p>
        </div>
      </div>
      <div className="grid gap-px bg-line sm:grid-cols-4">
        {[[`${s.false_alarms} / ${s.controls}`, "honest cases flagged", `${s.control_documents} honest documents`],
          [`${s.caught} / ${s.attacks}`, "attacks caught", `${s.blocked} blocked, ${s.caught - s.blocked} sent to review`],
          [`${s.originals_recovered} / ${s.recoverable}`, "original amounts recovered", "from hidden PDF revisions"],
          [`${s.decision_matches_label} / ${s.cases}`, "decisions match the label", "clear · review · block"]].map(([v, l, h]) => (
          <div key={l} className="bg-surface p-4"><div className="font-display text-[34px] leading-none text-ink tnum">{v}</div><div className="mt-1 text-[13px] font-medium text-ink-2">{l}</div><div className="text-[11.5px] text-muted">{h}</div></div>
        ))}
      </div>
      <div className="overflow-x-auto p-5">
        <table className="w-full min-w-[560px] text-[13px]">
          <thead><tr className="text-left text-[11.5px] uppercase tracking-wider text-muted"><th className="pb-2 font-semibold">Attack</th><th className="pb-2 font-semibold">Expected</th><th className="pb-2 text-right font-semibold">Caught</th><th className="pb-2 text-right font-semibold">Blocked</th></tr></thead>
          <tbody>
            {cats.map(([k, v]) => (
              <tr key={k} className="border-t border-line">
                <td className="py-1.5 text-ink">{k}</td><td className="py-1.5 text-muted">{v.expected}</td>
                <td className={cx("tnum py-1.5 text-right font-medium", v.caught === v.cases ? "text-teal-strong" : v.caught === 0 ? "text-danger" : "text-amber")}>{v.caught}/{v.cases}</td>
                <td className="tnum py-1.5 text-right text-ink-2">{v.blocked}/{v.cases}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {s.missed.length > 0 && <p className="mt-3 text-[12.5px] text-ink-2"><b>Missed ({s.missed.length}):</b> {s.missed.join(", ")} — a cleanly re-saved edit leaves no structural trace, and an invented competitor with fresh, unrelated metadata shares nothing to link. These limits are why approval also binds the payment to the configured PayPal merchant.</p>}
        <p className="mt-2 text-[11.5px] text-muted">Synthetic documents; the detectors and the attack generator were written by the same team, so treat this as a regression benchmark, not a field accuracy estimate. Run {dateTime(r.finished_at)}{r.code_revision ? ` · code ${String(r.code_revision).slice(0, 7)}` : ""}.</p>
      </div>
    </Card>
  );
}

function ResearchCard() {
  const q = useQuery<any>({ queryKey: ["eval-research"], queryFn: () => api("/evaluation/research") });
  if (!q.data) return null;
  const r = q.data;
  const best = (m: string) => Math.max(...r.rows.map((x: any) => x.auc[m]));
  return (
    <Card className="mt-6 overflow-hidden" data-testid="research-card">
      <div className="border-b border-line p-5">
        <div className="text-[12px] font-semibold uppercase tracking-[0.14em] text-teal">Our research · {r.version}</div>
        <div className="mt-0.5 font-display text-[26px] leading-tight text-ink">Detecting bid-rigging in a market the model has never seen</div>
        <p className="mt-1 max-w-3xl text-[13px] text-muted">Real cartel data: {Object.entries(r.data.groups).map(([k, v]) => `${k} ${Number(v).toLocaleString()}`).join(" · ")} bidder groups with proven cartel periods ({r.data.license}). {r.protocol}</p>
      </div>
      <div className="overflow-x-auto p-5">
        <table className="w-full min-w-[620px] text-[13px]">
          <thead><tr className="text-left text-[11.5px] uppercase tracking-wider text-muted"><th className="pb-2 font-semibold">Method (held-out market AUC)</th>{["JP", "CH", "IT"].map((m) => <th key={m} className="pb-2 text-right font-semibold">{{ JP: "Japan", CH: "Switzerland", IT: "Italy" }[m]}</th>)}<th className="pb-2 text-right font-semibold">Mean</th></tr></thead>
          <tbody>
            {r.rows.map((x: any) => (
              <tr key={x.method} className={cx("border-t border-line", x.ours && "bg-teal-soft/50 font-semibold")}>
                <td className="py-2 pr-3 text-ink">{x.method}</td>
                {["JP", "CH", "IT"].map((m) => <td key={m} className={cx("tnum py-2 text-right", x.auc[m] === best(m) ? "text-teal-strong" : "text-ink-2")}>{x.auc[m].toFixed(3)}{!x.ours && x.vs_ours[m].ci95[0] > 0 && <span className="ml-1 text-[10px] text-teal" title={`ours better: +${x.vs_ours[m].diff} (95% CI ${x.vs_ours[m].ci95.join(" to ")})`}>▲</span>}</td>)}
                <td className="tnum py-2 text-right text-ink">{x.mean_auc.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[12px] text-ink-2">▲ = ours significantly better (paired bootstrap, 95% CI excludes 0): 9 of 12 comparisons; the other 3 are statistical ties, none worse. Baselines are re-implemented on the same features in the style of each paper, not exact replications. The model runs inside Integrity Radar for supplier groups seen in 3+ purchases.</p>
      </div>
    </Card>
  );
}
