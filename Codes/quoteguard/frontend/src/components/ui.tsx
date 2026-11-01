import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { AlertTriangle, Check, CircleHelp, Copy, Loader2, X, XCircle } from "lucide-react";
import type { Tone } from "../lib/format";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" | "dark"; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode };
export function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }: BtnProps) {
  const v = {
    primary: "bg-teal text-white hover:bg-teal-strong shadow-sm shadow-teal/20",
    secondary: "bg-surface text-ink border border-line-strong hover:bg-sunken",
    ghost: "text-ink-2 hover:bg-sunken",
    danger: "bg-danger text-white hover:bg-[#8f1c13]",
    dark: "bg-ink text-white hover:bg-navy-900",
  }[variant];
  const s = { sm: "h-8 px-3 text-[13px] gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-5 text-[15px] gap-2" }[size];
  return (
    <button {...rest} disabled={disabled || loading} className={cx("inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed select-none whitespace-nowrap", v, s, className)}>
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

const toneCls: Record<Tone, string> = {
  good: "bg-teal-soft text-teal-strong border-teal/20",
  bad: "bg-danger-soft text-danger border-danger-line",
  warn: "bg-amber-soft text-amber border-amber-line",
  info: "bg-[#e8eef8] text-[#1f4b8f] border-[#c9d7ee]",
  neutral: "bg-sunken text-ink-2 border-line",
};
export function Badge({ tone = "neutral", children, icon, className }: { tone?: Tone; children: ReactNode; icon?: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", toneCls[tone], className)}>{icon}{children}</span>;
}

export function CheckBadge({ status, label }: { status: "pass" | "fail" | "unknown"; label?: string }) {
  if (status === "pass") return <Badge tone="good" icon={<Check className="size-3" aria-hidden />}>{label ?? "Pass"}</Badge>;
  if (status === "fail") return <Badge tone="bad" icon={<XCircle className="size-3" aria-hidden />}>{label ?? "Fail"}</Badge>;
  return <Badge tone="warn" icon={<CircleHelp className="size-3" aria-hidden />}>{label ?? "Unknown"}</Badge>;
}

export function Card({ children, className, ...rest }: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  // Callers may override the surface: skip the defaults they replace (no class-merging library needed).
  const c = className ?? "";
  return <div {...rest} className={cx("rounded-2xl shadow-[var(--shadow-card)]", !/\bborder-0\b/.test(c) && "border border-line", !/(^|\s)bg-/.test(c) && "bg-surface", className)}>{children}</div>;
}

export function PageHeader({ eyebrow, title, subtitle, actions }: { eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between animate-in">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-teal">{eyebrow}</div>}
        <h1 className="font-display text-[34px] leading-[1.05] text-ink md:text-[40px]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-[15px] text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children, hint, right }: { children: ReactNode; hint?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">{children}</h2>
        {hint && <p className="text-[13px] text-muted">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label ?? "Loading…"}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}

export function Empty({ title, body, action, image }: { title: string; body?: ReactNode; action?: ReactNode; image?: boolean }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      {image && <img src="/illustrations/empty-requests.webp" alt="" className="mb-4 h-28 w-28 rounded-2xl object-cover" />}
      <h3 className="font-semibold text-ink">{title}</h3>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error as any;
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-danger-line bg-danger-soft p-4 text-sm text-danger">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <div className="font-medium">{e?.message ?? "Something went wrong"}</div>
        {e?.code && <div className="mt-0.5 text-xs opacity-80">{e.code}{e.correlationId ? ` · ref ${e.correlationId}` : ""}</div>}
      </div>
      {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Callout({ tone = "info", title, children, icon }: { tone?: Tone; title?: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className={cx("rounded-xl border p-3.5 text-sm", toneCls[tone])}>
      <div className="flex gap-2.5">
        {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
        <div className="min-w-0">
          {title && <div className="font-semibold">{title}</div>}
          {children && <div className={cx(!!title && "mt-0.5", "opacity-90")}>{children}</div>}
        </div>
      </div>
    </div>
  );
}

export function CopyText({ value, short = true, className }: { value: string; short?: boolean; className?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" onClick={() => { navigator.clipboard?.writeText(value); setOk(true); setTimeout(() => setOk(false), 1200); }}
      className={cx("inline-flex items-center gap-1 rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[12px] text-ink-2 hover:bg-line", className)} title={`Copy ${value}`} aria-label={`Copy ${value}`}>
      {short && value.length > 18 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value}
      {ok ? <Check className="size-3 text-teal" aria-hidden /> : <Copy className="size-3 opacity-60" aria-hidden />}
    </button>
  );
}

/** Modal built on <dialog>: native focus trap, Escape to close, focus returns to the opener. */
export function Dialog({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose} aria-labelledby="dlg-title"
      className={cx("m-auto w-[calc(100%-32px)] rounded-2xl border border-line bg-surface p-0 text-ink shadow-[var(--shadow-pop)] backdrop:bg-ink/40 backdrop:backdrop-blur-[2px]", wide ? "max-w-3xl" : "max-w-lg")}>
      {open && (
        <div className="flex max-h-[85vh] flex-col">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 id="dlg-title" className="font-semibold">{title}</h2>
            <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-sunken" aria-label="Close dialog"><X className="size-4" /></button>
          </div>
          <div className="overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </div>
      )}
    </dialog>
  );
}

/** Side sheet (also a <dialog>, so focus handling and Escape match the modal). */
export function Sheet({ open, onClose, title, children, width = "max-w-[720px]" }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; width?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose} aria-labelledby="sheet-title"
      className={cx("fixed inset-y-0 right-0 left-auto m-0 h-full max-h-none w-full bg-canvas p-0 text-ink shadow-[var(--shadow-pop)] backdrop:bg-ink/30", width)}>
      {open && (
        <div className="slide-in flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-line bg-surface px-5 py-4">
            <h2 id="sheet-title" className="min-w-0 truncate font-semibold">{title}</h2>
            <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-sunken" aria-label="Close panel"><X className="size-4" /></button>
          </div>
          <div className="flex-1 overflow-y-auto p-5">{children}</div>
        </div>
      )}
    </dialog>
  );
}

export function Field({ label, hint, children, error }: { label: string; hint?: ReactNode; children: ReactNode; error?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/20";

export function Stat({ label, value, hint, icon, tone }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "teal" | "amber" | "navy" | "red" }) {
  const t = { teal: "bg-teal-soft text-teal", amber: "bg-amber-soft text-amber", navy: "bg-[#e8eef8] text-ink", red: "bg-danger-soft text-danger" }[tone ?? "navy"];
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-muted">{label}</span>
        {icon && <span className={cx("grid size-8 place-items-center rounded-lg", t)}>{icon}</span>}
      </div>
      <div className="mt-2 font-display text-[34px] leading-none tnum text-ink">{value}</div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}
