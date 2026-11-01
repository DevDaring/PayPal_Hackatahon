import { useRef, useState } from "react";
import { Bot, MessageSquareText, Send, Wrench } from "lucide-react";
import { api, errorText } from "../lib/api";
import type { Comparison } from "../lib/types";
import { openFieldTarget } from "./EvidenceStep";
import type { EvidenceTarget } from "./EvidenceViewer";
import { Button, inputCls, Sheet } from "./ui";

type Msg = { role: "user" | "assistant"; text: string; citations?: any[]; model?: string | null; tools?: any[] };
const SUGGESTED = ["Why isn't Harbor Devices recommended?", "What would make Northstar compliant?", "Which costs are unknown?", "Has PayPal actually received the money?"];

export function ChatPanel({ requestId, cmp, onOpen }: { requestId: string; cmp?: Comparison; onOpen: (t: EvidenceTarget) => void }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  async function ask(question: string) {
    if (!question.trim()) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api(`/requests/${requestId}/chat`, { body: { question } });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, citations: r.citations, model: r.model, tools: r.tool_calls }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", text: errorText(e) }]);
    } finally {
      setBusy(false);
      setTimeout(() => end.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  }
  const openCite = (c: any) => {
    const quote = cmp?.quotes.find((x) => x.quote_id === c.quote_id);
    if (quote) { setOpen(false); onOpen(openFieldTarget(quote, c.field)); }
  };
  return (
    <>
      <button onClick={() => setOpen(true)} className="fixed bottom-5 right-5 z-30 inline-flex items-center gap-2 rounded-full bg-ink px-4 py-3 text-sm font-medium text-white shadow-[var(--shadow-pop)] hover:bg-navy-900">
        <MessageSquareText className="size-4 text-teal-bright" aria-hidden /> Ask about this request
      </button>
      <Sheet open={open} onClose={() => setOpen(false)} title="Ask about this request" width="max-w-[460px]">
        <div className="flex h-full flex-col">
          <p className="mb-3 rounded-xl bg-sunken p-3 text-[12.5px] text-muted">Answers use only this request's authorised evidence. For live payment status it can call read-only PayPal Agent Toolkit tools, scoped by the server to this request's order. It cannot approve, pay or change anything.</p>
          <div className="flex-1 space-y-3">
            {msgs.length === 0 && (
              <div className="grid gap-2">
                {SUGGESTED.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-xl border border-line bg-surface px-3 py-2 text-left text-[13px] hover:bg-sunken">{s}</button>)}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "ml-8 rounded-2xl rounded-br-sm bg-ink px-3.5 py-2.5 text-[13.5px] text-white" : "mr-4 rounded-2xl rounded-bl-sm border border-line bg-surface px-3.5 py-2.5 text-[13.5px] text-ink"}>
                {m.role === "assistant" && <div className="mb-1 flex items-center gap-1 text-[11px] text-muted"><Bot className="size-3" aria-hidden />{m.model ?? "assistant"}</div>}
                {m.tools && m.tools.length > 0 && (
                  <div className="mb-2 grid gap-1">
                    {m.tools.map((t: any, k: number) => (
                      <div key={k} className="flex items-center gap-1.5 rounded-lg border border-[#c9d7ee] bg-[#eef3fb] px-2 py-1 text-[11.5px] text-[#1f4b8f]">
                        <Wrench className="size-3 shrink-0" aria-hidden />
                        <span><b>{t.source}</b> · {t.tool.replace("paypal_", "")}{t.result?.order?.status ? ` → ${t.result.order.status}` : t.result?.found === false ? " → not found yet" : ""}</span>
                        <span className="ml-auto opacity-70">{t.result?.latency_ms} ms · read-only</span>
                      </div>
                    ))}
                  </div>
                )}
                <p className="whitespace-pre-wrap">{m.text}</p>
                {m.citations && m.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">{m.citations.map((c: any) => <button key={c.key} onClick={() => openCite(c)} className="rounded bg-teal-soft px-1.5 py-0.5 text-[11px] font-semibold text-teal-strong hover:bg-teal hover:text-white">{c.key} · p{c.page}</button>)}</div>
                )}
              </div>
            ))}
            {busy && <div className="mr-4 skeleton h-14" />}
            <div ref={end} />
          </div>
          <form className="sticky bottom-0 mt-4 flex gap-2 bg-canvas pt-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
            <input className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question…" maxLength={600} aria-label="Question" />
            <Button type="submit" loading={busy} disabled={!q.trim()} aria-label="Send"><Send className="size-4" /></Button>
          </form>
        </div>
      </Sheet>
    </>
  );
}
