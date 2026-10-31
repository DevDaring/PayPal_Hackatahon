import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, CircleSlash, KeyRound, PencilLine } from "lucide-react";
import { api, errorText } from "../lib/api";
import { dateTime } from "../lib/format";
import { useRoles } from "../lib/session";
import { Badge, Button, Callout, Card, Dialog, Field, inputCls, PageHeader, SectionTitle, Skeleton } from "../components/ui";

function Ready({ ok, label, detail }: { ok: boolean; label: string; detail?: string | null }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5">
      {ok ? <CheckCircle2 className="mt-0.5 size-5 text-teal" aria-label="ready" /> : <CircleSlash className="mt-0.5 size-5 text-amber" aria-label="not configured" />}
      <div><div className="text-[14px] font-medium text-ink">{label}</div>{detail && <div className="text-[12.5px] text-muted">{detail}</div>}</div>
    </div>
  );
}

export default function SettingsPage() {
  const q = useQuery<any>({ queryKey: ["settings"], queryFn: () => api("/settings") });
  const { isAdmin } = useRoles();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<any>(null);
  const [mid, setMid] = useState("");
  const [note, setNote] = useState("");
  const change = useMutation({ mutationFn: () => api(`/merchant-bindings/${edit.id}`, { body: { merchant_id: mid, note } }), onSuccess: () => { toast.success("Merchant changed — approvals that used it were invalidated"); setEdit(null); qc.invalidateQueries(); }, onError: (e) => toast.error(errorText(e)) });
  if (!q.data) return <Skeleton className="h-96" />;
  const r = q.data.readiness;
  return (
    <div>
      <PageHeader eyebrow="Settings" title="Integration readiness" subtitle="Non-secret configuration status. Secrets are read from the server environment and are never shown in this interface." />
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        <Ready ok={r.database === "connected"} label="PostgreSQL" detail={r.database} />
        <Ready ok={r.ai.configured} label="AI provider" detail={r.ai.configured ? `${r.ai.provider} · ${r.ai.model} · ${r.ai.keys_loaded} key(s) loaded` : "Not configured — deterministic extractor in use"} />
        <Ready ok={r.ocr.configured} label="OCR / vision" detail={r.ocr.configured ? r.ocr.provider : "Image-only PDFs will ask for a text-readable copy"} />
        <Ready ok={r.paypal.credentials_present} label="PayPal Sandbox credentials" detail={`adapter: ${r.paypal.adapter} · live mode ${r.paypal.live_mode_available ? "available" : "disabled"}`} />
        <Ready ok={r.paypal.merchant_id_configured} label="Sandbox merchant ID" detail="Validated against each order's payee before capture" />
        <Ready ok={r.paypal.webhook_configured} label="Webhook subscription" detail={r.paypal.webhook_configured ? "Signed deliveries verified with PayPal" : "Not registered — reconciliation still works by provider lookup"} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="p-5">
          <SectionTitle hint="Set by an admin, never derived from document content. Changing a payee invalidates approvals that used it.">Merchant bindings</SectionTitle>
          <ul className="grid gap-2">
            {q.data.merchant_bindings.map((b: any) => (
              <li key={b.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line px-3 py-2.5">
                <div className="min-w-0 flex-1"><div className="font-medium text-ink">{b.supplier}</div><div className="font-mono text-[12px] text-muted">{b.merchant_id} · v{b.version} · {b.environment}</div></div>
                <Badge tone={b.adapter === "sandbox" ? "info" : "warn"}>{b.adapter}</Badge>
                <Badge tone={b.verified_at ? "good" : "warn"}>{b.verified_at ? "verified" : "unverified"}</Badge>
                {isAdmin && <Button size="sm" variant="ghost" icon={<PencilLine className="size-3.5" aria-hidden />} onClick={() => { setEdit(b); setMid(b.merchant_id); setNote(""); }}>Change</Button>}
              </li>
            ))}
          </ul>
        </Card>
        <div className="grid content-start gap-4">
          <Card className="p-5">
            <SectionTitle>Workspace policy</SectionTitle>
            <dl className="grid grid-cols-[1fr_auto] gap-y-2 text-[13.5px]">
              <dt className="text-muted">Self-approval</dt><dd><Badge>{q.data.workspace_policy.self_approval_allowed ? "allowed" : "disabled"}</Badge></dd>
              <dt className="text-muted">Approval expiry</dt><dd>{q.data.workspace_policy.approval_ttl_minutes} min</dd>
              <dt className="text-muted">Checkout currency</dt><dd>{r.paypal.currency}</dd>
              <dt className="text-muted">Timezone</dt><dd>{r.timezone}</dd>
              <dt className="text-muted">Upload limits</dt><dd>{r.limits.max_upload_mb} MB · {r.limits.max_pdf_pages} pages</dd>
              <dt className="text-muted">Your roles</dt><dd>{q.data.roles.join(", ")}</dd>
            </dl>
          </Card>
          <Card className="p-5">
            <SectionTitle>AI usage in this workspace</SectionTitle>
            {q.data.ai_usage.length === 0 ? <p className="text-sm text-muted">No model calls yet.</p> : <ul className="grid gap-1 text-[13px]">{q.data.ai_usage.map((u: any) => <li key={u.purpose} className="flex justify-between"><span>{u.purpose}</span><span className="tnum text-muted">{u.calls} calls · avg {u.avg_latency_ms} ms</span></li>)}</ul>}
          </Card>
          <Callout tone="info" icon={<KeyRound className="size-4" aria-hidden />}>{q.data.secrets_note}</Callout>
        </div>
      </div>
      <Dialog open={!!edit} onClose={() => setEdit(null)} title={`Change payee for ${edit?.supplier ?? ""}`}
        footer={<><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button><Button variant="danger" loading={change.isPending} disabled={note.trim().length < 4} onClick={() => change.mutate()}>Change merchant</Button></>}>
        <div className="grid gap-3">
          <Callout tone="warn">Any active approval that pays this supplier will be invalidated. A mismatched sandbox merchant disables checkout.</Callout>
          <Field label="PayPal merchant ID"><input className={inputCls + " font-mono"} value={mid} onChange={(e) => setMid(e.target.value)} /></Field>
          <Field label="Reason (required)"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <p className="text-[12px] text-muted">Last updated {edit ? dateTime(edit.updated_at) : ""}</p>
        </div>
      </Dialog>
    </div>
  );
}
