import { useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef } from "ag-grid-community";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BarChart3, Download, Play, Search } from "lucide-react";
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
  const [sel, setSel] = useState<string | null>(null);
  const runId = sel ?? runs.data?.items?.find((r: any) => r.status === "finished")?.id;
  const detail = useQuery<any>({ queryKey: ["eval-run", runId], queryFn: () => api(`/evaluation/runs/${runId}`), enabled: !!runId });
  const start = useMutation({ mutationFn: (mode: string) => api("/evaluation/runs", { body: { mode } }), onSuccess: () => { toast.message("Evaluation started"); qc.invalidateQueries({ queryKey: ["eval-runs"] }); }, onError: (e) => toast.error(errorText(e)) });
  const d = detail.data;
  const s = d?.summary;
  return (
    <div>
      <PageHeader eyebrow="Evaluation" title="Measured, not claimed" subtitle="A labelled set of synthetic quotations — clean, ambiguous, malformed and adversarial. Expected labels live in a separate manifest the model never sees."
        actions={isAdmin ? <><Button variant="secondary" loading={start.isPending && start.variables === "rules"} onClick={() => start.mutate("rules")}>Run deterministic baseline</Button><Button loading={start.isPending && start.variables === "llm"} onClick={() => start.mutate("llm")} icon={<Play className="size-4" aria-hidden />}>Run with AI model</Button></> : undefined} />
      {runs.data?.items?.length ? (
        <div className="mb-5 flex flex-wrap gap-2">
          {runs.data.items.map((r: any) => (
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
          <Callout tone="info" title="Honest limitations">Synthetic documents from one template family; the deterministic baseline was written alongside these templates, so its scores overstate real-world accuracy. Model confidence is not reported (no calibrated percentages). Checkout is assumed configured in evaluation so extraction and policy are measured in isolation.</Callout>
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
    { field: "payment_blocked", headerName: "Payment", minWidth: 105, valueFormatter: (p) => (p.value ? "blocked" : "eligible") },
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
