export type Me = {
  principal: { id: string; name: string; username: string | null; is_demo_account: boolean };
  acting: { id: string; name: string; is_persona: boolean };
  workspace: { id: string; name: string; is_demo: boolean; self_approval_allowed: boolean } | null;
  roles: string[];
  personas: { user_id: string; name: string; roles: string[]; is_persona: boolean; active: boolean }[];
  workspaces: { id: string; name: string; is_demo: boolean }[];
  csrf_token: string;
};

export type Criterion = { key: string; label: string; expected: string; synonyms: string[] };
export type Spec = {
  item: string; quantity: number; budget_amount: string; currency: string; budget_includes: string[];
  deadline_days: number | null; deadline_date: string | null; timezone: string; mandatory: Criterion[]; preferred: string[]; ambiguities: string[];
};

export type Check = { key: string; label: string; status: "pass" | "fail" | "unknown"; detail: string; fields: string[] };
export type Outcome = {
  quote_id: string; supplier: string; checks: Check[]; mandatory_status: "pass" | "fail" | "unknown"; verified_total: string | null; computed_total: string | null;
  arithmetic_status: string; estimated_delivery: string | null; checkout_available: boolean; payment_eligible: boolean; compliant_rank: number | null;
};
export type Evidence = { id: string; field: string; document_id: string; document_sha256: string; quote_version: number; page: number | null; source_text: string | null; method: string; location: string; bbox: number[][] | null };
export type QuoteVersion = {
  id: string; version: number; supplier_name: string | null; currency: string | null; currency_status: string; quantity: number | null; unit_price: string | null;
  subtotal: string | null; shipping: string | null; tax: string | null; discount: string | null; stated_total: string | null; computed_total: string | null; arithmetic_status: string;
  delivery_days: number | null; delivery_text: string | null; issue_date: string | null; valid_until: string | null; product_description: string | null; attributes: Record<string, string | null>;
  scalable_pricing: boolean; shipping_terms: string | null; pricing_terms: string | null; issues: string[]; needs_review: boolean; extraction_method: string; model: string | null; reason: string;
  correction: any; created_at: string;
};
export type CompareQuote = {
  quote_id: string; supplier: string; supplier_link: string; supplier_confirmed_by: string | null;
  document: { id: string; filename: string; sha256: string; pages: number; is_sample: boolean; suspicious: { page: number; label: string; excerpt: string }[] | null };
  version: QuoteVersion; outcome: Outcome; checkout_reason: string; merchant: { merchant_id: string; adapter: string; label: string } | null; evidence: Evidence[];
};
export type Comparison = {
  request_version: { id: string; version: number; requirements: Spec } | null; order_date: string; quotes: CompareQuote[];
  summary: any; policy: any; explanation: any;
};
export type Doc = { id: string; filename: string; sha256: string; pages: number | null; status: string; error_code: string | null; error_message: string | null; is_sample: boolean; suspicious: any[] | null; created_at: string; request_id: string };
export type Payment = {
  id: string; state: string; adapter: string; amount: string; currency: string; merchant_id: string; approval_id: string; request_id: string; provider_order_id: string | null;
  provider_order_status: string | null; provider_capture_id: string | null; provider_capture_status: string | null; captured_amount: string | null; last_error_code: string | null;
  last_error_message: string | null; reconcile_attempts: number; fault_injection_armed: boolean; order_request_id: string; capture_request_id: string; created_at: string; updated_at: string;
  completed_at: string | null; provider_calls?: any[]; refunds?: any[]; duplicate?: boolean; in_progress?: boolean;
};
export type Approval = { id: string; status: string; snapshot_hash: string; expires_at: string; created_at: string; approver_id: string; requested_by: string; note: string | null; ended_at: string | null; end_reason: string | null; end_details: any; snapshot: any; total: string | null; currency: string | null };
export type RequestDetail = {
  id: string; title: string; status: string; lab_scenario: string | null; created_at: string; updated_at: string; version: number | null; budget: string | null; currency: string | null; quantity: number | null;
  deadline: string | null; documents: Doc[]; original_text: string; timezone: string; draft: any; created_by: string; versions: { id: string; version: number; requirements: Spec; source: string; note: string | null; confirmed_at: string; deadline_at: string | null }[];
  approvals: Approval[]; payments: Payment[]; workflow: { status: string; current_node: string | null; completed_nodes: string[] } | null; is_requester: boolean; payment_state: string | null;
};
export type WfEvent = { id: number; stage: string; status: string; title: string; detail: string | null; refs: any; actor: string; tool: string | null; at: string };
