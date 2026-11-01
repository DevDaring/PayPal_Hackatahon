import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, FileClock, Fingerprint, History, Network, ScanSearch, ShieldAlert, ShieldCheck, ShieldQuestion, Sigma } from "lucide-react";
import { api } from "../lib/api";
import type { Comparison } from "../lib/types";
import { PageImage } from "./EvidenceViewer";
import { Badge, Card, cx, Skeleton } from "./ui";

type Finding = { id: string; kind: string; severity: "high" | "medium" | "low"; title: string; detail: string; quotes: string[]; evidence: any };
type Signal = { kind: string; strength: "high" | "medium" | "low"; detail: string };
type Report = {
  overall: "clear" | "review" | "block"; findings: Finding[]; links: { a: string; b: string; signals: Signal[]; level: string | null }[];
  clusters: { quotes: string[]; level: string }[]; screens: { n: number; cv: number; rd: number; cover_bid_pattern: boolean; note: string } | null;
  per_quote: Record<string, { status: string; detail: string }>; documents: Record<string, { supplier: string; filename: string; meta: any; revisions: number; doc_id: string | null; assessed: boolean }>;
  memo: { headline: string; explanation: string; next_steps: string[]; question_for_supplier: string; model: string } | null;
};

const VERDICT = {
  clear: { label: "No manipulation signals", icon: ShieldCheck, cls: "bg-teal-soft text-teal-strong border-teal/25" },
  review: { label: "Needs review", icon: ShieldQuestion, cls: "bg-amber-soft text-amber border-amber-line" },
  block: { label: "Manipulation detected", icon: ShieldAlert, cls: "bg-danger-soft text-danger border-danger-line" },
};
const SEV = { high: "bg-danger text-white", medium: "bg-amber text-white", low: "bg-sunken text-muted" };
const STROKE = { high: "#b42318", medium: "#a8550a", low: "#b9b2a6" };
const SHORT: Record<string, string> = { shared_document_id: "same file", shared_author: "same author", shared_phone: "same phone", shared_email: "same email", shared_bank: "same bank acct", created_together: "minutes apart" };
const KIND_ICON: Record<string, any> = { revision_edit: History, revision_text: History, overlay_patch: ScanSearch, font_outlier: ScanSearch, author_is_member: Fingerprint, not_independent: Network };

const CHECKS = [
  ["Hidden earlier revisions", "Incremental saves keep every earlier version of a PDF. We re-read it and diff what changed."],
  ["White-box patches", "Shapes drawn after the text they cover, in content-stream order, with new text typed on top."],
  ["Retyped amounts", "An amount set in a different font from its own label and from every other amount."],
  ["Shared origin", "Same original document ID, author, phone, email or bank details across 'different' suppliers."],
  ["Insider authorship", "A supplier's quote whose document author is a member of your own workspace."],
  ["Bid screens", "Coefficient of variation and relative distance from the bid-rigging literature (Huber & Imhof, 2019) — context only."],
];

export function IntegrityRadar({ requestId, cmp }: { requestId: string; cmp: Comparison }) {
  const sig = cmp.quotes.map((q) => `${q.quote_id}:${q.version.version}`).join(",");
  const q = useQuery<Report>({ queryKey: ["integrity", requestId, sig], queryFn: () => api(`/requests/${requestId}/integrity`), staleTime: 60_000 });
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <Skeleton className="h-24" />;
  if (!q.data) return null;
  const r = q.data;
  const v = VERDICT[r.overall];
  const material = r.findings.filter((f) => f.severity !== "low");
  const expanded = open || r.overall !== "clear";
  const nDocs = Object.keys(r.documents).length;
  return (
    <Card className={cx("overflow-hidden", r.overall === "block" && "border-danger-line! shadow-[0_0_0_4px_rgb(180_35_24/0.06)]")} data-integrity={r.overall}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 p-5 text-left" aria-expanded={expanded}>
        <span className={cx("grid size-11 shrink-0 place-items-center rounded-xl border", v.cls)}><v.icon className="size-5" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.14em] text-muted">Integrity Radar <Badge tone="neutral">document forensics · {nDocs} file{nDocs === 1 ? "" : "s"}</Badge></div>
          <div className="mt-0.5 font-display text-[24px] leading-tight text-ink">{r.memo?.headline ?? (r.overall === "clear" ? "No signs of editing or staged competition" : v.label)}</div>
          {r.overall === "clear" && <p className="text-[13px] text-muted">Checked for hidden earlier revisions, white-box patches, retyped amounts, shared authorship and shared contact details across suppliers.</p>}
        </div>
        <span className={cx("hidden rounded-full border px-3 py-1 text-[12.5px] font-semibold sm:inline", v.cls)}>{v.label}</span>
        <ChevronDown className={cx("size-4 text-muted transition-transform", expanded && "rotate-180")} aria-hidden />
      </button>

      {expanded && (
        <div className="grid gap-5 border-t border-line p-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className="grid content-start gap-3">
            {material.length === 0 && <p className="text-[13.5px] text-muted">No high- or medium-severity findings.</p>}
            {material.map((f) => <FindingCard key={f.id} f={f} r={r} cmp={cmp} />)}
            {r.memo && (
              <div className="rounded-2xl border border-[#c9d7ee] bg-[#f3f6fc] p-4">
                <div className="flex items-center gap-2 text-[12px] font-semibold uppercase tracking-wider text-[#1f4b8f]"><Bot className="size-4" aria-hidden />AI investigator memo</div>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">{r.memo.explanation}</p>
                {r.memo.next_steps.length > 0 && <ol className="mt-2 grid list-decimal gap-1 pl-5 text-[13px] text-ink-2">{r.memo.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>}
                {r.memo.question_for_supplier && <p className="mt-2 rounded-lg bg-white px-3 py-2 text-[13px] text-ink"><b>Ask the supplier:</b> {r.memo.question_for_supplier}</p>}
                <p className="mt-2 text-[11.5px] text-muted">Written by {r.memo.model} from the forensic findings only. Every number in it was checked against the findings; the verdict above is computed without the model.</p>
              </div>
            )}
          </div>
          <div className="grid content-start gap-4">
            <ProvenanceGraph r={r} cmp={cmp} />
            {r.screens && <Screens s={r.screens} />}
            <details className="rounded-xl border border-line bg-sunken/50 px-4 py-3 text-[12.5px] text-ink-2">
              <summary className="cursor-pointer font-medium text-ink">What the radar checks</summary>
              <ul className="mt-2 grid gap-1.5">{CHECKS.map(([t, d]) => <li key={t}><b className="text-ink">{t}.</b> {d}</li>)}</ul>
              <p className="mt-2 text-muted">Structural forensics cannot see a cleanly re-typed document with fresh metadata; approval still binds the payment to the configured PayPal merchant.</p>
            </details>
          </div>
        </div>
      )}
    </Card>
  );
}

function FindingCard({ f, r, cmp }: { f: Finding; r: Report; cmp: Comparison }) {
  const Icon = KIND_ICON[f.kind] ?? FileClock;
  const changes: { before: string; after: string }[] = f.evidence?.changes ?? [];
  const docId = f.quotes.length === 1 ? cmp.quotes.find((q) => q.quote_id === f.quotes[0])?.document.id : undefined;
  return (
    <div className="rounded-2xl border border-line bg-surface p-4" data-finding={f.kind}>
      <div className="flex items-start gap-2.5">
        <span className={cx("grid size-7 shrink-0 place-items-center rounded-lg", SEV[f.severity])}><Icon className="size-4" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-ink">{f.title}</span>
            <span className={cx("rounded-full px-1.5 py-px text-[10px] font-bold uppercase tracking-wider", SEV[f.severity])}>{f.severity}</span>
            <span className="text-[12px] text-muted">{f.quotes.map((k) => r.documents[k]?.supplier).join(" · ")}</span>
          </div>
          {f.kind !== "revision_edit" && <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{f.detail}</p>}
        </div>
      </div>
      {f.kind === "revision_edit" && changes.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-xl border border-line">
          <div className="grid grid-cols-2 bg-sunken text-[11px] font-semibold uppercase tracking-wider text-muted">
            <div className="px-3 py-1.5">Recovered original (revision {f.evidence.revision})</div><div className="border-l border-line px-3 py-1.5">Shown in the file now</div>
          </div>
          {changes.map((c, i) => (
            <div key={i} className="grid grid-cols-2 border-t border-line font-mono text-[12px]">
              <div className="bg-teal-soft/60 px-3 py-1.5 text-teal-strong">{c.before || "—"}</div>
              <div className="border-l border-line bg-danger-soft/70 px-3 py-1.5 text-danger">{c.after || "—"}</div>
            </div>
          ))}
        </div>
      )}
      {(f.kind === "overlay_patch" || f.kind === "font_outlier") && docId && f.evidence?.bbox && <ForensicPage documentId={docId} page={f.evidence.page} bbox={f.evidence.bbox} />}
    </div>
  );
}

function ForensicPage({ documentId, page, bbox }: { documentId: string; page: number; bbox: number[] }) {
  const doc = useQuery<any>({ queryKey: ["doc", documentId], queryFn: () => api(`/documents/${documentId}`) });
  const meta = doc.data?.page_meta?.find((p: any) => p.page === page);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el || !meta) return;
    const t = setTimeout(() => { el.scrollTop = Math.max(0, (bbox[1] / meta.height) * el.scrollHeight - el.clientHeight / 2); }, 400);
    return () => clearTimeout(t);
  }, [meta, bbox]);
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line bg-sunken">
      <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Page {page} · the box marks what was covered or retyped</div>
      <div ref={box} className="max-h-[230px] overflow-auto">
        {meta && <PageImage documentId={documentId} page={page} boxes={[bbox]} pageSize={{ width: meta.width, height: meta.height }} />}
      </div>
    </div>
  );
}

function ProvenanceGraph({ r, cmp }: { r: Report; cmp: Comparison }) {
  const keys = Object.keys(r.documents);
  if (keys.length < 2) return null;
  const W = 340, H = 250, cx0 = W / 2, cy0 = H / 2 + 8, rad = keys.length === 2 ? 95 : 72;
  const pos = Object.fromEntries(keys.map((k, i) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / keys.length;
    return [k, { x: cx0 + rad * 1.35 * Math.cos(a), y: cy0 + rad * Math.sin(a) }];
  }));
  const total = (k: string) => cmp.quotes.find((q) => q.quote_id === k)?.version.stated_total;
  const status = (k: string) => r.per_quote[k]?.status;
  const ring = (s?: string) => (s === "fail" ? "#b42318" : s === "unknown" ? "#a8550a" : "#0f766e");
  const decisive = r.links.filter((l) => l.level);
  return (
    <div className="rounded-2xl border border-line bg-[#0b1d36] p-3 text-white">
      <div className="flex items-center justify-between px-1 text-[11px] font-semibold uppercase tracking-wider text-white/60">
        <span className="inline-flex items-center gap-1.5"><Network className="size-3.5" aria-hidden />Provenance graph</span>
        <span>{decisive.length ? `${decisive.length} hidden link${decisive.length > 1 ? "s" : ""}` : "independent sources"}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full" role="img" aria-label="Links between supplier documents">
        {r.links.map((l, i) => {
          const s = l.signals.reduce((m, x) => (x.strength === "high" ? "high" : m === "high" ? m : x.strength === "medium" ? "medium" : m), "low" as Signal["strength"]);
          const a = pos[l.a], b = pos[l.b];
          const label = l.signals.filter((x) => x.strength !== "low").map((x) => SHORT[x.kind] ?? x.kind).join(" + ");
          const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, w = label.length * 5.4 + 12;
          return (
            <g key={i}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={STROKE[s]} strokeWidth={s === "high" ? 3 : s === "medium" ? 2 : 1.2} strokeDasharray={s === "low" ? "4 4" : undefined} opacity={0.95}>
                <title>{l.signals.map((x) => x.detail).join("\n")}</title>
              </line>
              {label && <g><rect x={mx - w / 2} y={my - 9} width={w} height={17} rx={8.5} fill="#2a0f14" stroke={STROKE[s]} strokeWidth={1} /><text x={mx} y={my + 3.5} textAnchor="middle" fontSize="9.5" fontWeight={600} fill="#fecaca">{label}</text></g>}
            </g>
          );
        })}
        {keys.map((k) => {
          const above = pos[k].y < cy0 - 10;
          const name = r.documents[k].supplier.replace(/\s*\(lab copy \d+\)/, "");
          return (
            <g key={k}>
              <circle cx={pos[k].x} cy={pos[k].y} r={21} fill="#0f2541" stroke={ring(status(k))} strokeWidth={3} />
              <text x={pos[k].x} y={pos[k].y + 4} textAnchor="middle" fontSize="11" fontWeight={600} fill="#fff">{name.split(/\s+/).filter((w) => /[A-Za-z]/.test(w)).map((w) => w[0]).slice(0, 2).join("")}</text>
              <text x={pos[k].x} y={above ? pos[k].y - 42 : pos[k].y + 36} textAnchor="middle" fontSize="10.5" fill="rgb(255 255 255 / .85)">{name.slice(0, 24)}</text>
              {total(k) && <text x={pos[k].x} y={above ? pos[k].y - 29 : pos[k].y + 49} textAnchor="middle" fontSize="10" fill="rgb(255 255 255 / .5)">${total(k)}</text>}
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-3 px-1 text-[10.5px] text-white/55">
        <span className="inline-flex items-center gap-1"><i className="h-0.5 w-4 bg-[#b42318]" />decisive link</span>
        <span className="inline-flex items-center gap-1"><i className="h-0.5 w-4 bg-[#a8550a]" />supporting</span>
        <span className="inline-flex items-center gap-1"><i className="h-0 w-4 border-t border-dashed border-[#b9b2a6]" />similar template (context)</span>
      </div>
    </div>
  );
}

function Screens({ s }: { s: NonNullable<Report["screens"]> }) {
  const cvPct = Math.min(100, (s.cv / 0.2) * 100);
  const rdPct = Math.min(100, (s.rd / 3) * 100);
  return (
    <div className="rounded-2xl border border-line p-4">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wider text-muted"><Sigma className="size-3.5" aria-hidden />Bid screens</span>
        <Badge tone={s.cover_bid_pattern ? "warn" : "neutral"}>{s.cover_bid_pattern ? "cover-bid shape" : "no cover-bid shape"}</Badge>
      </div>
      {[["Coefficient of variation", s.cv.toFixed(3), cvPct, 25, "low spread → suspicious (< 0.05)"], ["Relative distance", s.rd.toFixed(2), rdPct, 33.3, "isolated winner → suspicious (> 1)"]].map(([l, val, pct, mark, hint]) => (
        <div key={l as string} className="mt-3">
          <div className="flex justify-between text-[12.5px]"><span className="text-ink-2">{l}</span><span className="tnum font-mono font-medium text-ink">{val}</span></div>
          <div className="relative mt-1 h-1.5 rounded-full bg-sunken">
            <div className="absolute inset-y-0 left-0 rounded-full bg-ink/70" style={{ width: `${pct}%` }} />
            <div className="absolute -top-1 h-3.5 w-px bg-amber" style={{ left: `${mark}%` }} />
          </div>
          <div className="mt-0.5 text-[11px] text-muted">{hint}</div>
        </div>
      ))}
      <p className="mt-2 text-[11.5px] text-muted">Huber &amp; Imhof (2019), screens for detecting bid-rigging cartels. With {s.n} quotes these are context, never a verdict.</p>
    </div>
  );
}
