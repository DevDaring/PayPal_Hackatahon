import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, FileText, Loader2, ShieldAlert, XCircle } from "lucide-react";
import { api } from "../lib/api";
import { money, relative } from "../lib/format";
import { EvidenceSheet, type EvidenceTarget } from "../components/EvidenceViewer";
import { Badge, Card, Empty, ErrorBox, PageHeader, Skeleton } from "../components/ui";

const FILTERS = [["all", "All"], ["issues", "Needs attention"], ["suspicious", "Suspicious text"], ["failed", "Failed"]] as const;

export default function EvidenceDesk() {
  const [filter, setFilter] = useState<string>("all");
  const [target, setTarget] = useState<EvidenceTarget | null>(null);
  const q = useQuery({ queryKey: ["evidence-desk"], queryFn: () => api("/evidence"), refetchInterval: 6000 });
  const items = (q.data?.items ?? []).filter((d: any) =>
    filter === "all" ? true : filter === "issues" ? (d.quote?.issues?.length || d.quote?.needs_review || d.supplier_link === "suggested") : filter === "suspicious" ? d.suspicious?.length : ["failed", "needs_ocr"].includes(d.status));
  return (
    <div>
      <PageHeader eyebrow="Evidence desk" title="Every document, every extracted term" subtitle="Upload status, extraction method, missing information and suspicious content across all requests in this workspace. Uploading happens inside each request." />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Filter documents">
        {FILTERS.map(([k, l]) => <button key={k} role="tab" aria-selected={filter === k} onClick={() => setFilter(k)} className={"rounded-full border px-3 py-1.5 text-[13px] " + (filter === k ? "border-ink bg-ink text-white" : "border-line-strong bg-surface hover:bg-sunken")}>{l}</button>)}
      </div>
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      {!q.data ? <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div> : items.length === 0 ? <Card><Empty image title="Nothing here" body="Load the sample quotes inside a purchase request to see extraction and evidence." /></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((d: any) => (
            <Card key={d.id} className="flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2.5">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink-2"><FileText className="size-4" aria-hidden /></span>
                  <div className="min-w-0"><div className="truncate font-semibold text-ink">{d.quote?.supplier_name ?? d.filename}</div><div className="truncate text-[12px] text-muted">{d.filename}</div></div>
                </div>
                {d.status === "extracted" ? <CheckCircle2 className="size-5 text-teal" aria-label="Extracted" /> : ["failed", "needs_ocr"].includes(d.status) ? <XCircle className="size-5 text-danger" aria-label="Failed" /> : <Loader2 className="size-5 animate-spin text-muted" aria-label="Processing" />}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {d.is_sample && <Badge tone="info">Synthetic sample</Badge>}
                {d.lab && <Badge tone="info">Demo Lab</Badge>}
                {d.quote && <Badge>{d.quote.extraction_method} · v{d.quote.version}</Badge>}
                {d.quote?.needs_review && <Badge tone="warn">Needs review</Badge>}
                {d.supplier_link === "suggested" && <Badge tone="warn">Identity unconfirmed</Badge>}
                {d.suspicious?.length > 0 && <Badge tone="bad" icon={<ShieldAlert className="size-3" aria-hidden />}>Embedded instructions</Badge>}
              </div>
              {d.quote && <div className="mt-3 text-[13px] text-ink-2">Stated total <b className="tnum text-ink">{money(d.quote.stated_total, d.quote.currency) ?? "—"}</b> · shipping {money(d.quote.shipping, d.quote.currency) ?? <span className="text-amber">not stated</span>}</div>}
              {d.error_message && <p className="mt-2 text-[12.5px] text-danger">{d.error_message}</p>}
              {d.quote?.issues?.length > 0 && <ul className="mt-2 grid gap-1 text-[12px] text-amber">{d.quote.issues.slice(0, 3).map((i: string, k: number) => <li key={k} className="flex gap-1"><AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />{i}</li>)}</ul>}
              <div className="mt-auto flex items-center justify-between pt-3 text-[12px] text-muted">
                <Link to={`/requests/${d.request_id}/evidence`} className="truncate font-medium text-teal hover:underline">{d.request_title}</Link>
                <span className="flex items-center gap-2">{relative(d.created_at)}{d.pages ? <button className="font-medium text-ink hover:underline" onClick={() => setTarget({ documentId: d.id, page: 1, supplier: d.quote?.supplier_name ?? d.filename })}>View</button> : null}</span>
              </div>
            </Card>
          ))}
        </div>
      )}
      <EvidenceSheet target={target} onClose={() => setTarget(null)} />
    </div>
  );
}
