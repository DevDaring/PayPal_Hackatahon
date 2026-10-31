import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BarChart3, Play } from "lucide-react";
import { api, errorText } from "../lib/api";
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
            <Stat label="Unsafe payments blocked" value={`${s.unsafe_payment_attempts.blocked}/${s.unsafe_payment_attempts.total}`} hint="Cases labelled not-payable that were not payment-eligible" tone="teal" />
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
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead className="bg-sunken text-left text-[11.5px] uppercase tracking-wider text-muted"><tr><th className="px-4 py-2">Case</th><th className="px-4 py-2">Category</th><th className="px-4 py-2">Expected</th><th className="px-4 py-2">Actual</th><th className="px-4 py-2">Fields</th><th className="px-4 py-2">Evidence</th><th className="px-4 py-2">Payment</th><th className="px-4 py-2">ms</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {d.cases.map((c: any) => {
                    const fr = Object.values(c.field_results) as any[];
                    return (
                      <tr key={c.case_id} className={c.decision_expected !== c.decision_actual ? "bg-amber-soft/40" : ""}>
                        <td className="px-4 py-2 font-mono text-[12px]">{c.case_id}</td><td className="px-4 py-2">{c.category}</td>
                        <td className="px-4 py-2">{c.decision_expected}</td><td className="px-4 py-2 font-semibold">{c.decision_actual}</td>
                        <td className="px-4 py-2 tnum">{fr.length ? `${fr.filter((x) => x.correct).length}/${fr.length}` : "—"}</td>
                        <td className="px-4 py-2 tnum">{c.evidence_checked ? `${c.evidence_correct}/${c.evidence_checked}` : "—"}</td>
                        <td className="px-4 py-2">{c.payment_blocked ? <Badge>blocked</Badge> : <Badge tone="good">eligible</Badge>}</td>
                        <td className="px-4 py-2 tnum text-muted">{c.latency_ms}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
          <Callout tone="info" title="Honest limitations">Synthetic documents from one template family; the deterministic baseline was written alongside these templates, so its scores overstate real-world accuracy. Model confidence is not reported (no calibrated percentages). Checkout is assumed configured in evaluation so extraction and policy are measured in isolation.</Callout>
        </div>
      )}
    </div>
  );
}
