"""PayPal REST adapter (Orders v2, Payments v2, Webhook verification) — sandbox only.

The base URL comes from a strict mode enum; there is no live URL in this codebase path.
Credentials stay in this process; access tokens are cached in memory and never logged.
"""

from __future__ import annotations

import threading
import time

import httpx

from ..config import get_settings
from .base import PaymentProvider, ProviderAmbiguous, ProviderError, ProviderResult


class PayPalSandbox(PaymentProvider):
    name = "sandbox"

    def __init__(self):
        s = get_settings()
        self.base = s.paypal_api_base
        assert "sandbox" in self.base, "live PayPal endpoints are disabled"
        self._cid, self._secret = s.PAYPAL_CLIENT_ID, s.PAYPAL_CLIENT_SECRET
        self._timeout = s.PAYPAL_TIMEOUT_SECONDS
        self._token: str | None = None
        self._token_exp = 0.0
        self._lock = threading.Lock()

    # -- auth -----------------------------------------------------------------------
    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_exp - 120:
                return self._token
            try:
                r = httpx.post(f"{self.base}/v1/oauth2/token", auth=(self._cid, self._secret), data={"grant_type": "client_credentials"}, timeout=self._timeout)
            except httpx.HTTPError as e:
                raise ProviderAmbiguous(f"oauth: {type(e).__name__}") from None
            if r.status_code != 200:
                raise ProviderError("PROVIDER_AUTH_FAILED", "PayPal rejected the configured sandbox credentials.", r.status_code)
            d = r.json()
            self._token, self._token_exp = d["access_token"], time.time() + int(d.get("expires_in", 3000))
            return self._token

    def _call(self, method: str, path: str, *, json: dict | None = None, request_id: str | None = None, retry_auth: bool = True) -> ProviderResult:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Content-Type": "application/json", "Prefer": "return=representation"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        t0 = time.monotonic()
        try:
            r = httpx.request(method, f"{self.base}{path}", json=json, headers=headers, timeout=self._timeout)
        except httpx.TimeoutException:
            raise ProviderAmbiguous("timeout") from None
        except httpx.HTTPError as e:
            raise ProviderAmbiguous(type(e).__name__) from None
        latency = int((time.monotonic() - t0) * 1000)
        debug_id = r.headers.get("paypal-debug-id")
        if r.status_code == 401 and retry_auth:
            with self._lock:
                self._token = None
            return self._call(method, path, json=json, request_id=request_id, retry_auth=False)
        if r.status_code >= 500:
            raise ProviderAmbiguous(f"provider {r.status_code}", r.status_code)
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {}
        if r.status_code >= 400:
            issue = ((body.get("details") or [{}])[0]).get("issue") or body.get("name") or "PROVIDER_ERROR"
            raise ProviderError(issue, body.get("message") or "PayPal rejected the request.", r.status_code, debug_id, {"name": body.get("name"), "details": body.get("details")})
        return ProviderResult(body=body, http_status=r.status_code, latency_ms=latency, debug_id=debug_id)

    # -- operations -----------------------------------------------------------------
    def create_order(self, body: dict, request_id: str) -> ProviderResult:
        return self._call("POST", "/v2/checkout/orders", json=body, request_id=request_id)

    def get_order(self, order_id: str) -> ProviderResult:
        return self._call("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str, request_id: str) -> ProviderResult:
        return self._call("POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id)

    def get_capture(self, capture_id: str) -> ProviderResult:
        return self._call("GET", f"/v2/payments/captures/{capture_id}")

    def refund_capture(self, capture_id: str, amount: str, currency: str, request_id: str, note: str) -> ProviderResult:
        return self._call("POST", f"/v2/payments/captures/{capture_id}/refund", json={"amount": {"value": amount, "currency_code": currency}, "note_to_payer": note[:255]}, request_id=request_id)

    def verify_webhook(self, headers: dict, event: dict, webhook_id: str) -> str:
        h = {k.lower(): v for k, v in headers.items()}
        payload = {
            "auth_algo": h.get("paypal-auth-algo"),
            "cert_url": h.get("paypal-cert-url"),
            "transmission_id": h.get("paypal-transmission-id"),
            "transmission_sig": h.get("paypal-transmission-sig"),
            "transmission_time": h.get("paypal-transmission-time"),
            "webhook_id": webhook_id,
            "webhook_event": event,
        }
        if not all(payload.values()):
            return "FAILURE"
        res = self._call("POST", "/v1/notifications/verify-webhook-signature", json=payload)
        return res.body.get("verification_status", "FAILURE")

    def list_webhooks(self) -> list[dict]:
        return self._call("GET", "/v1/notifications/webhooks").body.get("webhooks", [])

    def create_webhook(self, url: str, events: list[str]) -> dict:
        return self._call("POST", "/v1/notifications/webhooks", json={"url": url, "event_types": [{"name": e} for e in events]}).body
