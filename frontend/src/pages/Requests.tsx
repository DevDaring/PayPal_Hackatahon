import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "../lib/api";
import { dateOnly, money, PAYMENT_STATUS, relative, REQUEST_STATUS } from "../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, Skeleton } from "../components/ui";

export default function Requests() {
  const [includeLab, setIncludeLab] = useState(false);
  const [page, setPage] = useState(1);
  const q = useQuery({ queryKey: ["requests", includeLab, page], queryFn: () => api(`/requests?page=${page}&limit=20&include_lab=${includeLab}`), refetchInterval: 10000 });
  const pages = q.data ? Math.max(1, Math.ceil(q.data.total / q.data.limit)) : 1;
  return (
    <div>
      <PageHeader eyebrow="Purchasing" title="Purchase requests" subtitle="Every request keeps its original wording, each confirmed requirements version, its quotes, approvals and payments."
        actions={<Link to="/requests/new"><Button icon={<Plus className="size-4" aria-hidden />}>New request</Button></Link>} />
      <label className="mb-3 inline-flex items-center gap-2 text-sm text-ink-2">
        <input type="checkbox" checked={includeLab} onChange={(e) => { setIncludeLab(e.target.checked); setPage(1); }} className="size-4 accent-teal" /> Show Demo Lab requests
      </label>
      {q.error && <ErrorBox error={q.error} onRetry={() => q.refetch()} />}
      <Card className="overflow-hidden">
        {!q.data ? <div className="space-y-2 p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11" />)}</div> : q.data.items.length === 0 ? (
          <Empty image title="No requests yet" body="Create one from plain language, or try the sample purchase from the Overview." action={<Link to="/requests/new"><Button>New request</Button></Link>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-sunken text-left text-[12px] uppercase tracking-wider text-muted">
                <tr><th className="px-4 py-2.5 font-medium">Request</th><th className="px-4 py-2.5 font-medium">Budget</th><th className="px-4 py-2.5 font-medium">Deliver by</th><th className="px-4 py-2.5 font-medium">Quotes</th><th className="px-4 py-2.5 font-medium">Status</th><th className="px-4 py-2.5 font-medium">Payment</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {q.data.items.map((r: any) => (
                  <tr key={r.id} className="hover:bg-sunken/50">
                    <td className="px-4 py-3"><Link to={`/requests/${r.id}`} className="font-medium text-ink hover:text-teal">{r.title}</Link><div className="text-[12px] text-muted">v{r.version ?? "—"} · updated {relative(r.updated_at)}</div></td>
                    <td className="px-4 py-3 tnum">{money(r.budget, r.currency) ?? "—"}</td>
                    <td className="px-4 py-3">{dateOnly(r.deadline)}</td>
                    <td className="px-4 py-3 tnum">{r.documents}</td>
                    <td className="px-4 py-3"><Badge tone={REQUEST_STATUS[r.status]?.tone}>{REQUEST_STATUS[r.status]?.label ?? r.status}</Badge></td>
                    <td className="px-4 py-3">{r.payment_state ? <Badge tone={PAYMENT_STATUS[r.payment_state]?.tone}>{PAYMENT_STATUS[r.payment_state]?.label}</Badge> : <span className="text-muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {pages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-sm">
          <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span className="text-muted">Page {page} of {pages}</span>
          <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}
