import { useEffect, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Bot, CalendarClock, Check, History, Plus, Trash2 } from "lucide-react";
import { api, errorText } from "../lib/api";
import { dateOnly, dateTime, money } from "../lib/format";
import { useRoles } from "../lib/session";
import type { Criterion, RequestDetail, Spec } from "../lib/types";
import { Badge, Button, Callout, Card, Field, inputCls, SectionTitle } from "./ui";

const KNOWN: Record<string, { label: (e: string) => string; synonyms: Record<string, string[]> }> = {
  connector: { label: (e) => `${e} connector`, synonyms: { "USB-C": ["usb-c", "usb type-c", "type-c", "usb c"], "USB-A": ["usb-a", "usb type-a"], "3.5mm": ["3.5mm", "3.5 mm"], Bluetooth: ["bluetooth", "wireless"] } },
  microphone: { label: () => "Built-in microphone", synonyms: { yes: ["microphone", "mic", "boom mic", "noise-cancelling mic"] } },
};

function addDays(base: string, days: number) {
  const d = new Date(base + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function RequirementsStep({ req, onConfirmed }: { req: RequestDetail; onConfirmed: () => void }) {
  const qc = useQueryClient();
  const { isRequester } = useRoles();
  const current = req.versions[req.versions.length - 1];
  const initial: Spec | null = current?.requirements ?? req.draft?.spec ?? null;
  const [spec, setSpec] = useState<Spec | null>(initial);
  const [editing, setEditing] = useState(!current);
  const [note, setNote] = useState("");
  useEffect(() => { setSpec(current?.requirements ?? req.draft?.spec ?? null); }, [current?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const created = req.created_at.slice(0, 10);
  const createdLocal = useMemo(() => new Date(req.created_at).toLocaleDateString("en-CA", { timeZone: req.timezone }), [req.created_at, req.timezone]);
  const deadline = spec?.deadline_days != null ? addDays(createdLocal, spec.deadline_days) : spec?.deadline_date ?? null;

  const confirm = useMutation({
    mutationFn: () => api(`/requests/${req.id}/confirm`, { body: { requirements: { ...spec, deadline_date: null }, expected_version: current?.version ?? 0, note: note || null } }),
    onSuccess: () => {
      toast.success(current ? "New requirements version confirmed — approvals invalidated and quotes re-checked" : "Requirements confirmed");
      qc.invalidateQueries({ queryKey: ["request", req.id] });
      setEditing(false);
      onConfirmed();
    },
    onError: (e) => toast.error(errorText(e)),
  });

  if (!spec) {
    return (
      <Callout tone="warn" title="The request could not be parsed into requirements">
        {(req.draft?.problems ?? []).join(" ")} Please create a new request stating quantity, budget and currency.
      </Callout>
    );
  }
  const set = (patch: Partial<Spec>) => setSpec({ ...spec, ...patch });
  const setCrit = (i: number, c: Partial<Criterion>) => set({ mandatory: spec.mandatory.map((x, j) => (j === i ? { ...x, ...c } : x)) });
  const valid = spec.quantity > 0 && Number(spec.budget_amount) > 0 && spec.currency?.length === 3 && spec.item.length > 1;

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card className="p-5 md:p-6">
        <SectionTitle hint={current ? `Confirmed version ${current.version} · ${dateTime(current.confirmed_at)}` : "Check every value before analysis can affect payment eligibility"}
          right={current && !editing && isRequester && req.status !== "canceled" ? <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>Edit → new version</Button> : null}>
          {current ? "Confirmed requirements" : "Confirm the structured requirements"}
        </SectionTitle>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Item"><input className={inputCls} value={spec.item} disabled={!editing} onChange={(e) => set({ item: e.target.value })} /></Field>
          <Field label="Quantity"><input className={inputCls + " tnum"} type="number" min={1} value={spec.quantity} disabled={!editing} onChange={(e) => set({ quantity: Number(e.target.value) })} /></Field>
          <Field label="Budget (total, inclusive)" hint={`Includes: ${spec.budget_includes.join(" and ") || "items only"}`}>
            <div className="flex gap-2">
              <select className={inputCls + " w-24"} value={spec.currency} disabled={!editing} onChange={(e) => set({ currency: e.target.value })} aria-label="Currency">
                {["USD", "EUR", "INR", "GBP"].map((c) => <option key={c}>{c}</option>)}
              </select>
              <input className={inputCls + " tnum"} inputMode="decimal" value={spec.budget_amount} disabled={!editing} onChange={(e) => set({ budget_amount: e.target.value })} aria-label="Budget amount" />
            </div>
          </Field>
          <Field label="Delivery window (calendar days)" hint={<span className="inline-flex items-center gap-1"><CalendarClock className="size-3.5" aria-hidden /> Deliver by <b className="text-ink">{dateOnly(deadline)}</b> ({req.timezone})</span>}>
            <input className={inputCls + " tnum"} type="number" min={0} max={365} value={spec.deadline_days ?? ""} disabled={!editing} onChange={(e) => set({ deadline_days: e.target.value === "" ? null : Number(e.target.value) })} />
          </Field>
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[13px] font-medium text-ink-2">Mandatory requirements</span>
            {editing && <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" aria-hidden />} onClick={() => set({ mandatory: [...spec.mandatory, { key: "connector", label: "USB-C connector", expected: "USB-C", synonyms: KNOWN.connector.synonyms["USB-C"] }] })}>Add</Button>}
          </div>
          <ul className="grid gap-2">
            {spec.mandatory.map((c, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-sunken/60 px-3 py-2">
                <Check className="size-4 text-teal" aria-hidden />
                {editing ? (
                  <>
                    <select className={inputCls + " w-40"} value={c.key} aria-label="Attribute" onChange={(e) => {
                      const key = e.target.value; const expected = key === "microphone" ? "yes" : "USB-C";
                      setCrit(i, { key, expected, label: KNOWN[key].label(expected), synonyms: KNOWN[key].synonyms[expected] ?? [expected.toLowerCase()] });
                    }}>
                      <option value="connector">Connector</option><option value="microphone">Microphone</option>
                    </select>
                    {c.key === "connector" && (
                      <select className={inputCls + " w-32"} value={c.expected} aria-label="Required value" onChange={(e) => setCrit(i, { expected: e.target.value, label: KNOWN.connector.label(e.target.value), synonyms: KNOWN.connector.synonyms[e.target.value] })}>
                        {Object.keys(KNOWN.connector.synonyms).map((v) => <option key={v}>{v}</option>)}
                      </select>
                    )}
                    <button className="ml-auto rounded-lg p-1.5 text-muted hover:bg-line" aria-label={`Remove ${c.label}`} onClick={() => set({ mandatory: spec.mandatory.filter((_, j) => j !== i) })}><Trash2 className="size-4" /></button>
                  </>
                ) : <span className="text-sm font-medium text-ink">{c.label}</span>}
              </li>
            ))}
            {spec.mandatory.length === 0 && <li className="text-sm text-muted">None — only budget, quantity, delivery and validity will be checked.</li>}
          </ul>
        </div>

        {editing && (
          <div className="mt-5 grid gap-3">
            {current && <Field label="Why are you changing the requirements?"><input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Finance approved a higher budget" /></Field>}
            {current && <Callout tone="warn">Confirming creates version {current.version + 1}. Any approval for this request is invalidated and quotes are re-checked.</Callout>}
            <div className="flex justify-end gap-2">
              {current && <Button variant="ghost" onClick={() => { setSpec(current.requirements); setEditing(false); }}>Cancel</Button>}
              <Button size="lg" loading={confirm.isPending} disabled={!valid || !isRequester} onClick={() => confirm.mutate()} icon={<Check className="size-4" aria-hidden />}>
                {current ? "Confirm new version" : "Confirm requirements"}
              </Button>
            </div>
            {!isRequester && <p className="text-right text-xs text-muted">Switch to the requester persona to confirm requirements.</p>}
          </div>
        )}
      </Card>

      <div className="grid content-start gap-4">
        <Card className="p-5">
          <SectionTitle>Original request</SectionTitle>
          <p className="font-display text-[22px] leading-snug text-ink">“{req.original_text}”</p>
          {req.draft && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
              <Bot className="size-3.5" aria-hidden /> Draft parsed by {req.draft.method === "llm" ? <Badge tone="info">{req.draft.model}</Badge> : <Badge>deterministic rules</Badge>}
              <span>· created {dateOnly(created)}</span>
            </div>
          )}
        </Card>
        {(spec.ambiguities?.length ?? 0) > 0 && (
          <Callout tone="warn" icon={<AlertTriangle className="size-4" aria-hidden />} title="Please double-check">
            <ul className="mt-1 list-disc pl-4">{spec.ambiguities.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </Callout>
        )}
        <Card className="p-5">
          <SectionTitle>What will be checked</SectionTitle>
          <ul className="grid gap-1.5 text-[13.5px] text-ink-2">
            <li>• Verified total ≤ <b>{money(spec.budget_amount, spec.currency)}</b> including {spec.budget_includes.join(" & ")}</li>
            <li>• Exactly <b>{spec.quantity}</b> units quoted, in <b>{spec.currency}</b></li>
            <li>• Supplier-claimed delivery on or before <b>{dateOnly(deadline)}</b></li>
            <li>• Quote validity not expired</li>
            {spec.mandatory.map((c) => <li key={c.key}>• {c.label}</li>)}
          </ul>
          <p className="mt-3 text-[12px] text-muted">Missing evidence for any of these is “unknown”, never “pass”.</p>
        </Card>
        {req.versions.length > 1 && (
          <Card className="p-5">
            <SectionTitle><span className="inline-flex items-center gap-1.5"><History className="size-4" aria-hidden />Version history</span></SectionTitle>
            <ol className="grid gap-2 text-[13px]">
              {[...req.versions].reverse().map((v) => (
                <li key={v.id} className="rounded-lg bg-sunken px-3 py-2"><b>v{v.version}</b> · {v.source} · {money(v.requirements.budget_amount, v.requirements.currency)} · {v.requirements.deadline_days} days<div className="text-muted">{v.note ?? "—"} · {dateTime(v.confirmed_at)}</div></li>
              ))}
            </ol>
          </Card>
        )}
      </div>
    </div>
  );
}
