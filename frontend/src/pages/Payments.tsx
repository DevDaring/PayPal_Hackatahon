import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { dateTime, money, PAYMENT_STATUS } from "../lib/format";
import { Badge, Card, CopyText, Empty, ErrorBox, PageHeader, Skeleton } from "../components/ui";

export default function Payments() {
  const q = useQuery({ queryKey: ["payments"], queryFn: () => api("/payments"), refetchInterval: 6000 });
  const wh = useQuery({ queryKey: ["webhooks"], queryFn: () => api("/webhooks/events"), refetchInterval: 15000 });
  return (
    <div>
      <PageHeader eyebrow="Payments" title="Payment operations" subtitle="One durable operation per approval, with stable PayPal-Request-Ids, every provider call recorded, and reconciliation for anything ambiguous." />
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      <Card className="overflow-hidden">
        {!q.data ? <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div> : q.data.items.length === 0 ? <Empty title="No payments yet" body="Approve a compliant quote, then pay through PayPal Sandbox." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-sunken text-left text-[12px] uppercase tracking-wider text-muted"><tr><th className="px-4 py-2.5">Request</th><th className="px-4 py-2.5">Amount</th><th className="px-4 py-2.5">Provider</th><th className="px-4 py-2.5">PayPal order / capture</th><th className="px-4 py-2.5">State</th><th className="px-4 py-2.5">Updated</th></tr></thead>
              <tbody className="divide-y divide-line">
                {q.data.items.map((p: any) => (
                  <tr key={p.id} className="hover:bg-sunken/50">
                    <td className="px-4 py-3"><Link to={`/payments/${p.id}`} className="font-medium text-ink hover:text-teal">{p.request_title}</Link>{p.lab && <Badge tone="info" className="ml-2">Demo Lab</Badge>}</td>
                    <td className="px-4 py-3 tnum font-medium">{money(p.amount, p.currency)}</td>
                    <td className="px-4 py-3"><Badge tone={p.adapter === "sandbox" ? "info" : "warn"}>{p.adapter === "sandbox" ? "PayPal Sandbox" : "Simulated"}</Badge></td>
                    <td className="px-4 py-3"><div className="flex flex-col gap-1">{p.provider_order_id ? <CopyText value={p.provider_order_id} short={false} /> : "—"}{p.provider_capture_id && <CopyText value={p.provider_capture_id} short={false} />}</div></td>
                    <td className="px-4 py-3"><Badge tone={PAYMENT_STATUS[p.state]?.tone}>{PAYMENT_STATUS[p.state]?.label}</Badge>{p.last_error_code && p.state !== "completed" && <div className="mt-1 text-[11px] text-muted">{p.last_error_code}</div>}</td>
                    <td className="px-4 py-3 text-[12.5px] text-muted">{dateTime(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <h2 className="mb-2 mt-8 text-[15px] font-semibold">Verified webhook deliveries</h2>
      <Card className="p-4 text-sm">
        {!wh.data?.items?.length ? <p className="text-muted">No webhook deliveries linked to this workspace yet. Deliveries are stored first, verified with PayPal, deduplicated, and applied only via an authoritative order lookup.</p> : (
          <ul className="grid gap-2">{wh.data.items.map((w: any) => <li key={w.id} className="flex flex-wrap items-center gap-2"><Badge tone={w.verification === "verified" ? "good" : "bad"}>{w.verification}</Badge><span className="font-medium">{w.event_type}</span><span className="text-muted">{w.outcome}</span><span className="ml-auto text-[12px] text-muted">{dateTime(w.received_at)}</span></li>)}</ul>
        )}
      </Card>
    </div>
  );
}
