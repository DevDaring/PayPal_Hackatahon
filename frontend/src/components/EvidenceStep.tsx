import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, FileUp, FlaskConical, Loader2, MapPin, PackageOpen, ShieldAlert, XCircle } from "lucide-react";
import { api, errorText, post } from "../lib/api";
import { FIELD_LABEL, money } from "../lib/format";
import { useRoles } from "../lib/session";
import type { CompareQuote, Comparison, RequestDetail } from "../lib/types";
import type { EvidenceTarget } from "./EvidenceViewer";
import { Badge, Button, Callout, Card, cx, SectionTitle } from "./ui";

const FIELDS: [string, (q: CompareQuote) => string | null][] = [
  ["supplier_name", (q) => q.version.supplier_name],
  ["currency", (q) => q.version.currency ? `${q.version.currency}${q.version.currency_status !== "explicit" ? " (inferred)" : ""}` : null],
  ["quantity", (q) => q.version.quantity?.toString() ?? null],
  ["unit_price", (q) => money(q.version.unit_price, q.version.currency)],
  ["subtotal", (q) => money(q.version.subtotal, q.version.currency)],
  ["shipping", (q) => money(q.version.shipping, q.version.currency)],
  ["tax", (q) => money(q.version.tax, q.version.currency)],
  ["total", (q) => money(q.version.stated_total, q.version.currency)],
  ["delivery_days", (q) => (q.version.delivery_days != null ? `${q.version.delivery_days} days (claim)` : null)],
  ["valid_until", (q) => q.version.valid_until],
  ["attr:connector", (q) => q.version.attributes.connector ?? null],
  ["attr:microphone", (q) => q.version.attributes.microphone ?? null],
];

export function rawValue(q: CompareQuote, field: string): string | null {
  const v = q.version as any;
  if (field === "total") return v.stated_total;
  if (field.startsWith("attr:")) return v.attributes[field.slice(5)] ?? null;
  return v[field] == null ? null : String(v[field]);
}

export function openFieldTarget(q: CompareQuote, field: string): EvidenceTarget {
  const ev = q.evidence.find((e) => e.field === field) ?? null;
  return { documentId: q.document.id, page: ev?.page ?? 1, evidence: ev, field, supplier: q.supplier, quoteId: q.quote_id, quoteVersion: q.version.version, currentValue: rawValue(q, field), missing: !ev && rawValue(q, field) == null };
}

export function EvidenceStep({ req, cmp, onOpen }: { req: RequestDetail; cmp?: Comparison; onOpen: (t: EvidenceTarget) => void }) {
  const qc = useQueryClient();
  const { isRequester } = useRoles();
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const fixtures = useQuery({ queryKey: ["fixtures"], queryFn: () => api("/demo/fixtures"), staleTime: Infinity });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["request", req.id] }); qc.invalidateQueries({ queryKey: ["comparison", req.id] }); };
  const samples = useMutation({ mutationFn: () => post(`/requests/${req.id}/sample-quotes`), onSuccess: () => { toast.success("Three labelled sample quotes uploaded — extracting now"); refresh(); }, onError: (e) => toast.error(errorText(e)) });
  const fixture = useMutation({ mutationFn: (k: string) => post(`/requests/${req.id}/fixtures/${k}`), onSuccess: () => { toast.success("Edge-case fixture added"); refresh(); }, onError: (e) => toast.error(errorText(e)) });
  const upload = useMutation({
    mutationFn: async (files: File[]) => { for (const f of files) { const fd = new FormData(); fd.append("file", f); await api(`/requests/${req.id}/documents`, { form: fd }); } },
    onSuccess: () => { toast.success("Uploaded — extraction started"); refresh(); },
    onError: (e) => toast.error(errorText(e)),
  });
  const quotesByDoc = new Map((cmp?.quotes ?? []).map((q) => [q.document.id, q]));
  const confirmed = req.versions.length > 0;

  return (
    <div className="grid gap-6">
      {!confirmed && <Callout tone="warn" title="Confirm the requirements first">Quotes can be uploaded any time, but nothing affects eligibility until requirements are confirmed.</Callout>}
      <div className="grid gap-4 md:grid-cols-[1.3fr_1fr]">
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = [...e.dataTransfer.files].filter((x) => x.type === "application/pdf" || x.name.toLowerCase().endsWith(".pdf")); if (f.length) upload.mutate(f); }}
          className={cx("flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition", drag ? "border-teal bg-teal-soft" : "border-line-strong bg-surface")}>
          <FileUp className="size-8 text-teal" aria-hidden />
          <p className="mt-2 font-medium text-ink">Drop supplier quotation PDFs here</p>
          <p className="text-[13px] text-muted">Text-readable PDF · max 10 MB · 20 pages. Password-protected files are rejected.</p>
          <input ref={fileRef} type="file" accept="application/pdf" multiple className="hidden" onChange={(e) => { const f = [...(e.target.files ?? [])]; if (f.length) upload.mutate(f); e.target.value = ""; }} />
          <Button className="mt-3" variant="secondary" loading={upload.isPending} disabled={!isRequester} onClick={() => fileRef.current?.click()}>Choose files</Button>
        </div>
        <Card className="flex flex-col justify-between gap-3 p-5">
          <div>
            <div className="flex items-center gap-2 font-semibold text-ink"><PackageOpen className="size-4 text-teal" aria-hidden /> Sample supplier quotes</div>
            <p className="mt-1 text-[13px] text-muted">Northstar Office, ClearWave Supplies and Harbor Devices — fictitious businesses, clearly labelled synthetic PDFs dated today.</p>
          </div>
          <Button loading={samples.isPending} disabled={!isRequester || req.documents.some((d) => d.is_sample && d.filename.includes("ClearWave"))} onClick={() => samples.mutate()}>Load 3 sample quotes</Button>
          <details className="text-[13px]">
            <summary className="cursor-pointer select-none text-ink-2"><FlaskConical className="mr-1 inline size-3.5" aria-hidden />Add an edge-case fixture</summary>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(fixtures.data?.fixtures ?? []).map((f: any) => (
                <button key={f.key} disabled={fixture.isPending || !isRequester} onClick={() => fixture.mutate(f.key)} className="rounded-full border border-line-strong bg-surface px-2.5 py-1 text-[12px] hover:bg-sunken disabled:opacity-50">{f.label}</button>
              ))}
            </div>
          </details>
        </Card>
      </div>

      <div>
        <SectionTitle hint="Click any value to open the page it came from">Quotes and extracted terms</SectionTitle>
        {req.documents.length === 0 ? <Card className="p-8 text-center text-sm text-muted">No quotes yet.</Card> : (
          <div className="grid gap-4 xl:grid-cols-3 md:grid-cols-2">
            {req.documents.map((d) => {
              const q = quotesByDoc.get(d.id);
              return (
                <Card key={d.id} className="flex flex-col overflow-hidden animate-in">
                  <div className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-ink">{q?.supplier ?? d.filename}</div>
                      <div className="truncate text-[12px] text-muted">{d.filename} · {d.pages ?? "?"} page{d.pages === 1 ? "" : "s"}</div>
                    </div>
                    <DocStatus status={d.status} />
                  </div>
                  {d.suspicious?.length ? (
                    <div className="flex items-start gap-2 border-b border-danger-line bg-danger-soft px-4 py-2 text-[12.5px] text-danger">
                      <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> <span><b>Embedded instructions detected.</b> Treated as data — they cannot change budget, permissions or payee.</span>
                    </div>
                  ) : null}
                  {d.status === "failed" || d.status === "needs_ocr" ? (
                    <div className="p-4 text-[13px] text-danger">{d.error_message} <span className="text-muted">({d.error_code})</span></div>
                  ) : !q ? (
                    <div className="grid gap-2 p-4">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-6" />)}</div>
                  ) : (
                    <div className="flex-1 p-2">
                      <dl className="grid">
                        {FIELDS.map(([f, get]) => {
                          const v = get(q);
                          const ev = q.evidence.find((e) => e.field === f);
                          return (
                            <button key={f} onClick={() => onOpen(openFieldTarget(q, f))} className="group flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-sunken">
                              <dt className="text-[12.5px] text-muted">{FIELD_LABEL[f]}</dt>
                              <dd className={cx("flex items-center gap-1.5 text-[13px] tnum", v ? "text-ink" : "text-amber font-medium")}>
                                {v ?? "Not stated"}
                                {ev?.location === "bbox" ? <MapPin className="size-3 text-teal opacity-60 group-hover:opacity-100" aria-label="Linked to page location" /> : ev?.location === "correction" ? <Badge tone="info">corrected</Badge> : null}
                              </dd>
                            </button>
                          );
                        })}
                      </dl>
                      {q.version.issues.length > 0 && (
                        <ul className="mx-2 mb-2 mt-2 grid gap-1 rounded-lg bg-amber-soft px-3 py-2 text-[12px] text-amber">
                          {q.version.issues.slice(0, 4).map((i, k) => <li key={k} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />{i}</li>)}
                        </ul>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5 px-2 pb-2 text-[11.5px] text-muted">
                        <Badge tone="neutral">v{q.version.version}</Badge>
                        <Badge tone="neutral">{q.version.extraction_method}{q.version.model ? ` · ${q.version.model}` : ""}</Badge>
                        {d.is_sample && <Badge tone="info">Synthetic sample</Badge>}
                        {q.supplier_link === "suggested" && <Badge tone="warn">Supplier identity unconfirmed</Badge>}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function DocStatus({ status }: { status: string }) {
  if (status === "extracted") return <Badge tone="good" icon={<CheckCircle2 className="size-3" aria-hidden />}>Extracted</Badge>;
  if (status === "failed") return <Badge tone="bad" icon={<XCircle className="size-3" aria-hidden />}>Failed</Badge>;
  if (status === "needs_ocr") return <Badge tone="warn">Needs text PDF</Badge>;
  return <Badge tone="info" icon={<Loader2 className="size-3 animate-spin" aria-hidden />}>{status === "uploaded" ? "Queued" : "Reading"}</Badge>;
}
