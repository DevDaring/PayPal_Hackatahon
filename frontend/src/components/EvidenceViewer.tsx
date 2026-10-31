import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Hash, MapPin, PencilLine, ScanText, ShieldAlert } from "lucide-react";
import { api, errorText } from "../lib/api";
import { FIELD_LABEL } from "../lib/format";
import type { Evidence } from "../lib/types";
import { Badge, Button, Callout, CopyText, Field, inputCls, Sheet, Spinner } from "./ui";

export type EvidenceTarget = {
  documentId: string;
  page: number;
  evidence?: Evidence | null;
  field?: string;
  supplier?: string;
  quoteId?: string;
  quoteVersion?: number;
  currentValue?: string | null;
  missing?: boolean;
};

export function PageImage({ documentId, page, boxes, pageSize }: { documentId: string; page: number; boxes?: number[][] | null; pageSize?: { width: number; height: number } }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const markRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const el = imgRef.current;
    if (!el || !pageSize) return;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / pageSize.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, [pageSize, loaded]);
  useEffect(() => {
    if (loaded && scale && markRef.current) markRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [loaded, scale]);
  return (
    <div className="relative overflow-hidden rounded-xl border border-line bg-white shadow-sm">
      {!loaded && <div className="skeleton aspect-[1/1.414] w-full" />}
      <img ref={imgRef} src={`/api/v1/documents/${documentId}/pages/${page}.png`} alt={`Page ${page} of the supplier document`} onLoad={() => setLoaded(true)} className={loaded ? "block w-full" : "hidden"} />
      {loaded && scale > 0 && boxes?.map((b, i) => (
        <div key={i} ref={i === 0 ? markRef : undefined} className="evidence-mark absolute" aria-hidden
          style={{ left: b[0] * scale - 4, top: b[1] * scale - 3, width: (b[2] - b[0]) * scale + 8, height: (b[3] - b[1]) * scale + 6 }} />
      ))}
    </div>
  );
}

export function EvidenceSheet({ target, onClose }: { target: EvidenceTarget | null; onClose: () => void }) {
  const doc = useQuery({ queryKey: ["doc", target?.documentId], queryFn: () => api(`/documents/${target!.documentId}`), enabled: !!target });
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  useEffect(() => { setEditing(false); setValue(target?.currentValue ?? ""); setNote(""); }, [target]);
  const correct = useMutation({
    mutationFn: () => api(`/quotes/${target!.quoteId}/correct`, { body: { field: target!.field, value: value || null, note, expected_version: target!.quoteVersion } }),
    onSuccess: (v: any) => {
      toast.success(`Saved as quote version ${v.version}. Affected approvals were invalidated and checks re-run.`);
      qc.invalidateQueries();
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const ev = target?.evidence;
  const pageMeta = doc.data?.page_meta?.find((p: any) => p.page === (target?.page ?? 1));
  const label = target?.field ? FIELD_LABEL[target.field] ?? target.field : "Document";
  const editable = target?.quoteId && target?.field && !["product_description", "shipping_terms", "pricing_terms"].includes(target.field);

  return (
    <Sheet open={!!target} onClose={onClose} title={<span className="flex items-center gap-2"><FileText className="size-4 text-teal" aria-hidden />{target?.supplier ? `${target.supplier} · ` : ""}{label}</span>}>
      {target && (
        <div className="grid gap-5">
          {doc.data?.suspicious?.length ? (
            <Callout tone="warn" icon={<ShieldAlert className="size-4" aria-hidden />} title="Embedded instructions detected — treated as data">
              {doc.data.suspicious.map((s: any, i: number) => <div key={i} className="mt-1 text-[12.5px]">p{s.page} · {s.label}: “{s.excerpt.slice(0, 110)}…”</div>)}
            </Callout>
          ) : null}
          {target.missing ? (
            <Callout tone="warn" title={`${label} is not stated in this quote`}>
              QuoteGuard does not guess missing terms. This value stays <b>unknown</b> and blocks eligibility until the supplier clarifies it or someone records a correction with a note.
            </Callout>
          ) : ev ? (
            <div className="rounded-xl border border-line bg-surface p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone={ev.location === "bbox" ? "good" : ev.location === "correction" ? "info" : "warn"} icon={<MapPin className="size-3" aria-hidden />}>
                  {ev.location === "bbox" ? "Exact location on page" : ev.location === "correction" ? "Human correction" : "Text match only — no precise coordinates"}
                </Badge>
                <Badge tone="neutral" icon={<ScanText className="size-3" aria-hidden />}>{ev.method}</Badge>
                <Badge tone="neutral">Page {ev.page ?? "—"} · quote v{ev.quote_version}</Badge>
              </div>
              <blockquote className="border-l-4 border-amber-line bg-amber-soft/50 px-3 py-2 font-mono text-[13px] text-ink">{ev.source_text}</blockquote>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted"><Hash className="size-3.5" aria-hidden /> Document SHA-256 <CopyText value={ev.document_sha256} /></div>
            </div>
          ) : null}

          {editable && (
            <div className="rounded-xl border border-line bg-surface p-4">
              {!editing ? (
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm text-ink-2">Extraction wrong or missing? Corrections keep the original value, source, actor and time, and create a new quote version.</div>
                  <Button size="sm" variant="secondary" icon={<PencilLine className="size-3.5" aria-hidden />} onClick={() => setEditing(true)}>Correct</Button>
                </div>
              ) : (
                <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); correct.mutate(); }}>
                  <Field label={`Corrected ${label.toLowerCase()}`} hint={target.currentValue ? `Current value: ${target.currentValue}` : "Currently not stated"}>
                    <input className={inputCls} value={value} onChange={(e) => setValue(e.target.value)} placeholder={target.field?.includes("date") || target.field === "valid_until" ? "YYYY-MM-DD" : ""} />
                  </Field>
                  <Field label="Note (required)" hint="Who confirmed it and how, e.g. “Supplier confirmed by email on 1 Nov”.">
                    <textarea className={inputCls} rows={2} value={note} onChange={(e) => setNote(e.target.value)} required minLength={4} />
                  </Field>
                  <Callout tone="warn">Saving creates quote version {(target.quoteVersion ?? 1) + 1} and invalidates any approval that used this quote.</Callout>
                  <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button type="submit" loading={correct.isPending} disabled={note.trim().length < 4}>Save correction</Button></div>
                </form>
              )}
            </div>
          )}

          {doc.isLoading ? <Spinner label="Loading page…" /> : doc.data && (
            <div>
              <div className="mb-2 flex items-center justify-between text-[13px] text-muted">
                <span className="truncate">{doc.data.filename} · page {target.page} of {doc.data.pages}</span>
                {doc.data.is_sample && <Badge tone="info">Synthetic demo sample</Badge>}
              </div>
              {pageMeta?.method === "ocr" && <div className="mb-2"><Callout tone="warn">OCR text from an image-only page — positions are not available and values need human review.</Callout></div>}
              <PageImage documentId={target.documentId} page={target.page} boxes={ev?.bbox} pageSize={pageMeta ? { width: pageMeta.width, height: pageMeta.height } : undefined} />
              <a href={`/api/v1/documents/${target.documentId}/file`} className="mt-2 inline-block text-[13px] font-medium text-teal hover:underline">Download original PDF</a>
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}
