export const TZ = "Asia/Kolkata";

export function money(v: string | null | undefined, currency: string | null | undefined = "USD") {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  const sym = currency === "USD" ? "$" : currency === "EUR" ? "€" : currency === "INR" ? "₹" : currency === "GBP" ? "£" : "";
  const s = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return sym ? `${sym}${s}` : `${s} ${currency ?? ""}`.trim();
}

export function dateTime(iso: string | null | undefined, tz = TZ) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { timeZone: tz, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) + " IST";
}

export function dateOnly(iso: string | null | undefined) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function relative(iso: string) {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export const FIELD_LABEL: Record<string, string> = {
  supplier_name: "Supplier", currency: "Currency", quantity: "Quantity", unit_price: "Unit price", subtotal: "Item subtotal", shipping: "Shipping", tax: "Tax",
  discount: "Discount", total: "Stated total", delivery_days: "Delivery promise", valid_until: "Valid until", issue_date: "Issue date", product_description: "Product",
  shipping_terms: "Shipping terms", pricing_terms: "Pricing terms", "attr:connector": "Connector", "attr:microphone": "Microphone",
};

export const REQUEST_STATUS: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "neutral" }, analyzing: { label: "Analyzing", tone: "info" }, needs_clarification: { label: "Needs clarification", tone: "warn" },
  ready_for_review: { label: "Ready for approval", tone: "info" }, approved: { label: "Approved", tone: "good" }, superseded: { label: "Superseded", tone: "neutral" }, canceled: { label: "Canceled", tone: "neutral" },
};
export const PAYMENT_STATUS: Record<string, { label: string; tone: Tone }> = {
  not_started: { label: "Not started", tone: "neutral" }, order_creating: { label: "Creating order", tone: "info" }, awaiting_payer: { label: "Awaiting PayPal buyer", tone: "info" },
  capture_pending: { label: "Capturing", tone: "info" }, reconciling: { label: "Reconciling", tone: "warn" }, completed: { label: "Paid · confirmed", tone: "good" },
  canceled: { label: "Canceled", tone: "bad" }, failed: { label: "Failed", tone: "bad" },
};
export type Tone = "good" | "bad" | "warn" | "info" | "neutral";
