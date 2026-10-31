import { AlertTriangle, Ban, CheckCircle2, CircleDot, FileText, Info, Loader2, ShieldCheck, Wallet, XCircle } from "lucide-react";
import { dateTime } from "../lib/format";
import type { WfEvent } from "../lib/types";
import { cx } from "./ui";

const STAGE_ICON: Record<string, any> = { request: FileText, document: FileText, extract: FileText, validate: AlertTriangle, recommend: CheckCircle2, approve: ShieldCheck, execute: Ban, payment: Wallet, correct: Info, workflow: CircleDot };
const STATUS_CLS: Record<string, string> = {
  done: "bg-teal text-white", started: "bg-[#e8eef8] text-[#1f4b8f]", info: "bg-sunken text-ink-2", warning: "bg-amber-soft text-amber", blocked: "bg-danger-soft text-danger", failed: "bg-danger text-white",
};

export function Timeline({ events, compact }: { events: WfEvent[]; compact?: boolean }) {
  if (!events.length) return <p className="text-sm text-muted">No events recorded yet.</p>;
  return (
    <ol className="relative grid gap-0">
      {events.map((e, i) => {
        const Icon = e.status === "blocked" ? XCircle : e.status === "started" ? Loader2 : STAGE_ICON[e.stage] ?? CircleDot;
        return (
          <li key={e.id} className="relative flex gap-3 pb-4 animate-in">
            {i < events.length - 1 && <span className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-line-strong" aria-hidden />}
            <span className={cx("relative z-10 grid size-7 shrink-0 place-items-center rounded-full", STATUS_CLS[e.status] ?? STATUS_CLS.info)}>
              <Icon className={cx("size-3.5", e.status === "started" && "animate-spin")} aria-hidden />
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className={cx("text-[13.5px] font-medium", e.status === "blocked" || e.status === "failed" ? "text-danger" : "text-ink")}>{e.title}</span>
                <time className="text-[11px] text-muted tnum">{dateTime(e.at)}</time>
              </div>
              {!compact && e.detail && <p className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{e.detail}</p>}
              <div className="mt-0.5 text-[11px] text-muted">{e.actor}{e.tool ? ` · ${e.tool}` : ""}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
