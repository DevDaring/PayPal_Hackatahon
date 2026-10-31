import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { api } from "../lib/api";
import { CheckoutPanel, Receipt } from "../components/PaymentPanel";
import { Callout, ErrorBox, PageHeader, Spinner } from "../components/ui";

export default function PaymentPage() {
  const { id = "" } = useParams();
  const q = useQuery<any>({ queryKey: ["payment", id], queryFn: () => api(`/payments/${id}`) });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Spinner />;
  const p = q.data;
  return (
    <div>
      <Link to="/payments" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink"><ArrowLeft className="size-3.5" aria-hidden />Payments</Link>
      <PageHeader eyebrow="Payment" title={p.request_title} subtitle={<Link className="text-teal hover:underline" to={`/requests/${p.request_id}`}>Open the purchase request</Link>} />
      {p.state === "completed" ? <Receipt requestId={p.request_id} opId={p.id} />
        : ["canceled", "failed"].includes(p.state) ? <Callout tone="bad" title={`Payment ${p.state}`}>{p.last_error_message ?? p.last_error_code}. A fresh approval is required for a new attempt.</Callout>
          : <CheckoutPanel requestId={p.request_id} approval={{ ...p.approval, snapshot: p.snapshot }} op={p} />}
    </div>
  );
}
