import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Archive, Ban, Check, CircleAlert, CopyCheck, FileWarning, FlaskConical, Info, Loader2, Play, Shuffle, TimerOff, X } from "lucide-react";
import { api, errorText } from "../lib/api";
import { dateTime } from "../lib/format";
import { Badge, Button, Callout, Card, cx, PageHeader, Skeleton } from "../components/ui";

const META: Record<string, { icon: any; blurb: string; expect: string }> = {
  amount_changed: { icon: Shuffle, blurb: "Approve ClearWave at $570, then the supplier revises shipping. A second pass edits the amount directly in the database after re-approval.", expect: "Both attempts blocked; fresh approval required" },
  merchant_changed: { icon: Ban, blurb: "Approve, then change the payee mapping — once via the admin service and once by a direct database edit that bypasses it.", expect: "Execution blocked by the snapshot hash check" },
  malicious_pdf: { icon: FileWarning, blurb: "A quote PDF tells the AI to ignore the budget, approve immediately and pay a different email.", expect: "Text stays data; budget, permissions and payee unchanged" },
  double_click: { icon: CopyCheck, blurb: "Five simultaneous ‘Pay’ clicks, then five simultaneous capture requests.", expect: "One payment operation, one provider capture" },
  lost_response: { icon: TimerOff, blurb: "The provider performs the capture but its response is discarded, as if the network dropped it.", expect: "Payment becomes ‘reconciling’, then recovers by lookup" },
};
const VERDICT: Record<string, { label: string; tone: "good" | "bad" | "warn" }> = {
  blocked_as_expected: { label: "Blocked as expected", tone: "good" }, one_operation: { label: "One logical operation", tone: "good" }, recovered: { label: "Recovered safely", tone: "good" },
  not_blocked: { label: "NOT blocked", tone: "bad" }, duplicate_detected: { label: "Duplicate observed", tone: "bad" }, not_recovered: { label: "Not recovered", tone: "bad" }, error: { label: "Error", tone: "bad" },
};

export default function DemoLab() {
  const qc = useQueryClient();
  const q = useQuery<any>({ queryKey: ["demo-lab"], queryFn: () => api("/demo/scenarios"), refetchInterval: (x) => (x.state.data?.runs?.some((r: any) => r.status === "running") ? 1500 : 10000) });
  const run = useMutation({ mutationFn: (k: string) => api(`/demo/scenarios/${k}`), onSuccess: () => { toast.message("Controlled test started"); qc.invalidateQueries({ queryKey: ["demo-lab"] }); }, onError: (e) => toast.error(errorText(e)) });
  const archive = useMutation({ mutationFn: () => api("/demo/archive"), onSuccess: (r: any) => { toast.success(`Archived ${r.archived_requests} request(s). Payment history preserved.`); qc.invalidateQueries(); }, onError: (e) => toast.error(errorText(e)) });
  const latest = (k: string) => q.data?.runs?.find((r: any) => r.scenario === k);
  return (
    <div>
      <PageHeader eyebrow="Demo Lab · controlled tests" title="Try to break the payment path"
        subtitle="Each scenario runs the same policy, approval and payment services as normal operation, in a fresh lab request. Verdicts are computed from what those services actually returned."
        actions={<Button variant="secondary" loading={archive.isPending} disabled={!q.data?.available} icon={<Archive className="size-4" aria-hidden />} onClick={() => archive.mutate()}>Archive demo session</Button>} />
      {q.data && !q.data.available && <div className="mb-4"><Callout tone="warn" title="Demo Lab is available to demo-workspace admins only">Switch back to the requester/admin persona in this isolated demo workspace.</Callout></div>}
      <div className="mb-5"><Callout tone="info" icon={<Info className="size-4" aria-hidden />}>These are labelled fixtures, not proof of comprehensive security. Payment-concurrency scenarios use the explicitly labelled simulated provider because a real capture needs a human PayPal buyer login; use “discard PayPal's capture response” on the checkout screen to run the lost-response test against real PayPal Sandbox.</Callout></div>
      {!q.data ? <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}</div> : (
        <div className="grid gap-5 lg:grid-cols-2">
          {q.data.scenarios.map((s: any) => {
            const r = latest(s.key);
            const M = META[s.key];
            return (
              <Card key={s.key} className="flex flex-col overflow-hidden">
                <div className="flex items-start gap-3 border-b border-line p-5">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-teal-bright"><M.icon className="size-5" aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold text-ink">{s.title}</h3><Badge tone="info" icon={<FlaskConical className="size-3" aria-hidden />}>controlled test</Badge></div>
                    <p className="mt-1 text-[13px] text-muted">{M.blurb}</p>
                    <p className="mt-1 text-[12px] text-ink-2"><b>Expected:</b> {M.expect}</p>
                  </div>
                  <Button size="sm" loading={run.isPending && run.variables === s.key} disabled={!q.data.available || r?.status === "running"} onClick={() => run.mutate(s.key)} icon={<Play className="size-3.5" aria-hidden />}>Run</Button>
                </div>
                <div className="flex-1 p-5">
                  {!r ? <p className="text-sm text-muted">Not run yet in this workspace.</p> : (
                    <>
                      <div className="mb-3 flex flex-wrap items-center gap-2">
                        {r.status === "running" ? <Badge tone="info" icon={<Loader2 className="size-3 animate-spin" aria-hidden />}>Running</Badge> : <Badge tone={VERDICT[r.verdict]?.tone ?? "warn"}>{VERDICT[r.verdict]?.label ?? r.verdict}</Badge>}
                        <span className="text-[12px] text-muted">{dateTime(r.started_at)}</span>
                        {r.request_id && <Link to={`/requests/${r.request_id}`} className="ml-auto text-[12.5px] font-medium text-teal hover:underline">Open lab request</Link>}
                      </div>
                      {r.summary && <p className="mb-3 text-[13.5px] font-medium text-ink">{r.summary}</p>}
                      <ol className="grid gap-2">
                        {r.steps.map((st: any, i: number) => (
                          <li key={i} className="flex gap-2.5 text-[13px]">
                            <span className={cx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full", st.status === "ok" ? "bg-teal text-white" : st.status === "blocked" ? "bg-ink text-teal-bright" : st.status === "failed" ? "bg-danger text-white" : "bg-sunken text-muted")}>
                              {st.status === "ok" ? <Check className="size-3" aria-hidden /> : st.status === "blocked" ? <Ban className="size-3" aria-hidden /> : st.status === "failed" ? <X className="size-3" aria-hidden /> : <CircleAlert className="size-3" aria-hidden />}
                            </span>
                            <div className="min-w-0">
                              <div className="font-medium text-ink">{st.title}{st.status === "blocked" && <span className="ml-1.5 text-[11px] font-semibold uppercase text-teal">blocked</span>}</div>
                              {st.detail && <div className="text-[12.5px] text-ink-2">{st.detail}</div>}
                              {st.data?.changes?.length > 0 && (
                                <ul className="mt-1 grid gap-0.5 rounded-lg bg-sunken px-2 py-1.5 font-mono text-[11px] text-ink-2">{st.data.changes.slice(0, 4).map((c: any, k: number) => <li key={k}>{c.field}: {String(c.approved)} → <b className="text-danger">{String(c.current)}</b></li>)}</ul>
                              )}
                            </div>
                          </li>
                        ))}
                      </ol>
                    </>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
