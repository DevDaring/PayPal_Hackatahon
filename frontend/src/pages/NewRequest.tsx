import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, Wand2 } from "lucide-react";
import { api, errorText } from "../lib/api";
import { useRoles } from "../lib/session";
import { Button, Callout, Card, inputCls, PageHeader } from "../components/ui";

const EXAMPLES = [
  "Buy 30 USB-C headsets with microphones. Total budget $600 including shipping and stated taxes. Delivery within seven calendar days.",
  "We need 12 USB-C headsets with mics for the new hires, max $300 all-in, delivered within 10 days.",
  "Order 50 Bluetooth headsets with microphone, budget USD 1500 including shipping, within fourteen days.",
];

export default function NewRequest() {
  const nav = useNavigate();
  const { isRequester } = useRoles();
  const [text, setText] = useState("");
  const create = useMutation({
    mutationFn: () => api("/requests", { body: { text } }),
    onSuccess: (r: any) => { toast.success("Draft ready — confirm the structured requirements"); nav(`/requests/${r.id}/requirements`); },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader eyebrow="New purchase request" title="What do you need to buy?" subtitle="Write it the way you'd say it. QuoteGuard drafts typed requirements — quantity, budget, deadline, must-haves — for you to confirm before anything counts." />
      <Card className="p-5 md:p-6">
        <label htmlFor="req-text" className="mb-2 block text-[13px] font-medium text-ink-2">Request</label>
        <textarea id="req-text" className={inputCls + " min-h-36 text-[15px] leading-relaxed"} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000}
          placeholder="e.g. Buy 30 USB-C headsets with microphones. Total budget $600 including shipping and stated taxes. Delivery within seven calendar days." />
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((e, i) => <button key={i} onClick={() => setText(e)} className="rounded-full border border-line-strong bg-surface px-3 py-1 text-left text-[12.5px] text-ink-2 hover:bg-sunken"><Sparkles className="mr-1 inline size-3 text-teal" aria-hidden />Example {i + 1}</button>)}
        </div>
        <div className="mt-5 flex items-center justify-between gap-3">
          <p className="text-[12px] text-muted">Your text is treated as data. Relative dates are resolved in Asia/Kolkata and stored in UTC.</p>
          <Button size="lg" loading={create.isPending} disabled={text.trim().length < 10 || !isRequester} onClick={() => create.mutate()} icon={<Wand2 className="size-4" aria-hidden />}>Draft requirements</Button>
        </div>
      </Card>
      {!isRequester && <div className="mt-4"><Callout tone="warn">Switch to the requester persona to create requests.</Callout></div>}
    </div>
  );
}
